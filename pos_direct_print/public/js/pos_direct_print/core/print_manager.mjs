/**
 * PrintManager — top-level orchestration (A.12.3).
 *
 * Depends only on domain contracts: JobCoordinator, capability registry,
 * driver contract, error normalizer. Never on a printer SDK (A-DOD-09/12) and
 * never called from the POS adapter except through requestPrint.
 */

import { makeError } from "./errors.mjs";
import { classifyRetry, normalize, toUserError } from "./error_normalizer.mjs";
import {
  canTransition,
  deriveContentRisk,
  isRetryAllowed,
} from "./print_job.mjs";

// Valid transition walks from PREFLIGHT to each settled state (plan.md table).
const SETTLE_PATHS = Object.freeze({
  SUCCEEDED: ["PRINTING", "VERIFYING", "SUCCEEDED"],
  UNCERTAIN: ["PRINTING", "UNCERTAIN"],
  FAILED_SAFE: ["FAILED_SAFE"],
  FALLBACK_BROWSER: ["FALLBACK_BROWSER"],
});

export class PrintManager {
  /**
   * @param {object} deps
   * @param {import("./job_coordinator.mjs").JobCoordinator} deps.coordinator
   * @param {import("./capability_registry.mjs").CapabilityRegistry} deps.registry
   * @param {Function} deps.resolveDriver returns a driver instance for a key
   * @param {Function} deps.buildReceipt invoice snapshot -> ReceiptDocument
   */
  constructor({
    coordinator,
    registry,
    resolveDriver,
    buildReceipt,
    default_driver_key = null,
    fetchReceipt = null,
  }) {
    this.coordinator = coordinator;
    this.registry = registry;
    this.resolveDriver = resolveDriver;
    this.buildReceipt = buildReceipt;
    // Receipt lookup for same-job retries: a retry prints the same receipt
    // snapshot the original Job carried, never a rebuilt one.
    this.fetchReceipt = fetchReceipt;
    this.default_driver_key = default_driver_key;
    this.requests_received = [];
  }

  /**
   * Orchestrate one print request end to end.
   * @param {object} request PrintRequest (A.10.1)
   * @param {object} context { invoice_snapshot, idempotency_key,
   *   reservation_owner, receipt } — `receipt` short-circuits receipt building
   *   for same-job retries.
   * @returns {Promise<object>} PrintOutcome (A.10.7)
   */
  async requestPrint(request, context = {}) {
    this.requests_received.push(request);

    const state = {
      phase: "RESERVATION",
      content_started: false,
      from_state: context.from_state || "CREATED",
    };

    try {
      const reservation = await this.coordinator.reserve(request, {
        reservation_owner: context.reservation_owner,
        idempotency_key: context.idempotency_key,
      });
      state.job_id = reservation.job_id;
      state.reservation_token = reservation.reservation_token;

      const receipt =
        context.receipt || (await this._buildReceipt(request, context));

      const driver = await this._selectDriver(request);

      const started = await this.coordinator.beginAttempt({
        job_id: reservation.job_id,
        reservation_token: reservation.reservation_token,
        terminal_id: request.terminal_id,
      });
      state.attempt_id = started.attempt.attempt_id;
      state.phase = "PRINT";

      const result = await this._executePrint(driver, receipt, request, state);
      return await this._settle(state, result, driver);
    } catch (raw) {
      return this._failureOutcome(state, raw);
    }
  }

  /**
   * Same-job safe retry (plan.md section 7 / A-AT-11): the SAME Job gets a new
   * Attempt through the FAILED_SAFE -> RESERVED -> PREFLIGHT cycle. It never
   * creates a new Job — a new Job is REPRINT territory and belongs to the
   * reprint authorization path.
   */
  async retryJob(job_id, initiator, reason) {
    const snapshot = await this.coordinator.api.retrieveJob(job_id);
    const attempt = await this._latestAttempt(snapshot);

    const decision = isRetryAllowed(snapshot, attempt, null);
    if (!decision.allowed) {
      throw makeError("PDP_JOB_INVALID_TRANSITION", {
        phase: "RESERVATION",
        retry_class: decision.retry_class,
        content_may_have_printed: deriveContentRisk(attempt),
        metadata: { job_id, initiator, reason },
      });
    }

    const state = {
      phase: "RESERVATION",
      content_started: false,
      job_id,
      from_state: "FAILED_SAFE",
    };

    try {
      // Re-reserve the SAME Job (FAILED_SAFE -> RESERVED), then run the
      // standard attempt cycle with the original receipt snapshot.
      const re_reserved = await this.coordinator.transition({
        job_id,
        expected_from_state: "FAILED_SAFE",
        target_state: "RESERVED",
        reservation_token: initiator,
      });
      state.reservation_token = re_reserved.reservation_owner || initiator;

      const receipt = this.fetchReceipt
        ? await this.fetchReceipt(job_id)
        : await this._buildReceipt(
            {
              reference_doctype: snapshot.reference_doctype,
              reference_name: snapshot.reference_name,
            },
            { invoice_snapshot: snapshot }
          );

      const driver = await this._selectDriver({
        driver_key: snapshot.driver_key,
        terminal_id: snapshot.terminal,
      });

      const started = await this.coordinator.beginAttempt({
        job_id,
        reservation_token: state.reservation_token,
        terminal_id: snapshot.terminal,
      });
      state.attempt_id = started.attempt.attempt_id;
      state.phase = "PRINT";

      const result = await this._executePrint(driver, receipt, {}, state);
      return await this._settle(state, result, driver);
    } catch (raw) {
      return this._failureOutcome(state, raw);
    }
  }

  async cancelJob(job_id, reason) {
    const snapshot = await this.coordinator.api.retrieveJob(job_id);
    if (!canTransition(snapshot.status, "CANCELLED")) {
      throw makeError("PDP_JOB_INVALID_TRANSITION", {
        phase: "RESERVATION",
        metadata: { job_id, status: snapshot.status, reason },
      });
    }
    return this.coordinator.transition({
      job_id,
      expected_from_state: snapshot.status,
      target_state: "CANCELLED",
      reservation_token: snapshot.reservation_owner,
    });
  }

  async fallbackToBrowser(job_id, approved) {
    if (!approved) {
      throw makeError("PDP_PERMISSION_DENIED", {
        phase: "FALLBACK",
        metadata: { job_id, reason: "explicit approval required" },
      });
    }

    const snapshot = await this.coordinator.api.retrieveJob(job_id);
    if (snapshot.content_may_have_printed) {
      throw makeError("PDP_JOB_CONFLICT", {
        phase: "FALLBACK",
        content_may_have_printed: true,
        retry_class: "REPRINT_ONLY",
        metadata: { job_id, reason: "content may have printed" },
      });
    }

    return this.coordinator.transition({
      job_id,
      expected_from_state: snapshot.status,
      target_state: "FALLBACK_BROWSER",
      reservation_token: snapshot.reservation_owner,
    });
  }

  getJobStatus(job_id) {
    return this.coordinator.api.retrieveJob(job_id);
  }

  async _buildReceipt(request, context) {
    if (typeof this.buildReceipt !== "function") {
      throw makeError("PDP_RECEIPT_BUILD_FAILED", { phase: "RECEIPT" });
    }
    return this.buildReceipt(context.invoice_snapshot, request);
  }

  async _selectDriver(request) {
    const driver_key = request.driver_key || this.default_driver_key;
    if (!driver_key || !this.registry.hasDriver(driver_key)) {
      throw makeError("PDP_DRIVER_NOT_FOUND", {
        phase: "PREFLIGHT",
        metadata: { driver_key },
      });
    }
    const record = this.registry.getDriver(driver_key);
    const driver = this.resolveDriver(record);
    return driver;
  }

  async _executePrint(driver, receipt, request, state) {
    try {
      const result = await driver.print(receipt, {
        job_id: state.job_id,
        driver_key: driver.driver_key,
      });
      if (result.content_started) {
        state.content_started = true;
      }
      return result;
    } catch (raw) {
      // Driver threw: normalize, then wrap in a rejected result so the
      // settlement path stays single.
      state.driver_error = normalize(raw, state.phase, {
        content_started: state.content_started,
      });
      return {
        accepted: false,
        content_started: state.content_started,
        content_completed: false,
        verification_supported: false,
        final_status: null,
        metadata: {},
      };
    }
  }

  async _settle(state, result, driver) {
    const settled_status = this._settleStatus(result);

    await this.coordinator.completeAttempt({
      attempt_id: state.attempt_id,
      outcome: settled_status,
      content_started: result.content_started,
      content_completed: result.content_completed,
      error: state.driver_error || null,
    });

    // Walk the valid transition path from the post-attempt state (PREFLIGHT)
    // to the settled state — SUCCEEDED and UNCERTAIN are only reachable
    // through PRINTING/VERIFYING.
    let current = "PREFLIGHT";
    for (const next of SETTLE_PATHS[settled_status]) {
      await this.coordinator.transition({
        job_id: state.job_id,
        expected_from_state: current,
        target_state: next,
        reservation_token: state.reservation_token,
      });
      current = next;
    }

    return {
      job_id: state.job_id,
      status: current,
      attempt_id: state.attempt_id,
      success: current === "SUCCEEDED",
      fallback_used: current === "FALLBACK_BROWSER",
      requires_user_action: current === "BLOCKED",
      error: state.driver_error ? toUserError(state.driver_error) : null,
    };
  }

  _settleStatus(result) {
    // Browser handoff (BrowserDriver) is its own settled state — never a
    // physical success, never a plain failure.
    if (result.metadata && result.metadata.handoff) {
      return "FALLBACK_BROWSER";
    }
    if (result.accepted && result.content_completed) {
      return "SUCCEEDED";
    }
    if (result.content_started && !result.content_completed) {
      return "UNCERTAIN";
    }
    return "FAILED_SAFE";
  }

  async _failureOutcome(state, raw) {
    const domainError = normalize(raw, state.phase, {
      content_started: state.content_started,
    });
    domainError.retry_class = classifyRetry(domainError, {
      content_started: state.content_started,
    });

    if (state.attempt_id) {
      try {
        await this.coordinator.completeAttempt({
          attempt_id: state.attempt_id,
          outcome: state.content_started ? "UNCERTAIN" : "FAILED_SAFE",
          content_started: state.content_started,
          error: domainError,
        });
      } catch {
        // Best effort: the attempt completion must not mask the primary error.
      }
    }

    return {
      job_id: state.job_id || null,
      status: state.content_started ? "UNCERTAIN" : "FAILED_SAFE",
      attempt_id: state.attempt_id || null,
      success: false,
      fallback_used: false,
      requires_user_action: true,
      error: toUserError(domainError),
    };
  }

  async _latestAttempt(snapshot) {
    // Milestone A has no dedicated attempt-listing endpoint. Content risk comes
    // from the Job's own content_may_have_printed flag; the retry class comes
    // from the transport when it reports the last attempt (fail-closed null
    // otherwise, which keeps isRetryAllowed denying).
    const attempt = this.coordinator.api.lastAttemptFor
      ? await this.coordinator.api.lastAttemptFor(snapshot.job_id)
      : null;
    return {
      content_started: snapshot.content_may_have_printed,
      content_completed: Boolean(attempt && attempt.content_completed),
      retry_class: attempt ? attempt.retry_class : null,
    };
  }
}
