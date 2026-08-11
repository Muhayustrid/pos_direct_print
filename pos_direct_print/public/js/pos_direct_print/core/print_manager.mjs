/**
 * PrintManager — top-level orchestration (A.12.3).
 *
 * Depends only on domain contracts: JobCoordinator, capability registry,
 * driver contract, error normalizer. Never on a printer SDK (A-DOD-09/12) and
 * never called from the POS adapter except through requestPrint.
 *
 * Frozen driver lifecycle (milestone-b §1.6 / R-GAP-05): preflight
 * (detect -> initialize -> getStatus) happens while the Job is PREFLIGHT;
 * PREFLIGHT -> PRINTING happens only after the driver is READY; dispatch runs
 * while the Job is PRINTING; settlement walks the tail of SETTLE_PATHS from
 * the live state. B-COMP Option A gates SUCCEEDED on a bounded post-dispatch
 * READY query (post_status_checked + final_status.ready).
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
      current: "CREATED",
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
      state.current = "RESERVED";

      const receipt =
        context.receipt || (await this._buildReceipt(request, context));

      await this.coordinator.bindReceiptSnapshot({
        job_id: reservation.job_id,
        reservation_token: reservation.reservation_token,
        receipt,
      });

      const driver = await this._selectDriver(request);

      const started = await this.coordinator.beginAttempt({
        job_id: reservation.job_id,
        reservation_token: reservation.reservation_token,
        terminal_id: request.terminal_id,
      });
      state.attempt_id = started.attempt.attempt_id;
      state.current = "PREFLIGHT";

      return await this._attemptCycle(driver, receipt, request, state);
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
      current: "FAILED_SAFE",
      phase: "RESERVATION",
      content_started: false,
      job_id,
      from_state: "FAILED_SAFE",
    };

    try {
      // Server-side safe-retry re-reservation: FAILED_SAFE -> RESERVED with a
      // fresh server-minted owner. The original reservation_owner is hidden
      // from projections (A.31.9 Level 1) and remains unchanged from the first
      // cycle, so no client-known token could pass a guarded transition — the
      // dedicated endpoint mints a new reservation cycle instead. The initiator
      // is audit metadata only and is never used as a token.
      const re_reserved = await this.coordinator.reReserve({
        job_id,
        initiator,
      });
      state.reservation_token = re_reserved.reservation_token;
      state.current = "RESERVED";

      const receipt = this.fetchReceipt
        ? await this.fetchReceipt(job_id)
        : await this._buildReceipt(
            {
              reference_doctype: snapshot.reference_doctype,
              reference_name: snapshot.reference_name,
            },
            { invoice_snapshot: snapshot }
          );

      // DECIDED C-5: retry skips the bind when the bound snapshot is reused.
      if (!this.fetchReceipt) {
        await this.coordinator.bindReceiptSnapshot({
          job_id,
          reservation_token: state.reservation_token,
          receipt,
        });
      }

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
      state.current = "PREFLIGHT";

      return await this._attemptCycle(driver, receipt, {}, state);
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
    return this.coordinator.cancelJob({ job_id, reason });
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

    return this.coordinator.fallbackToBrowser({ job_id, approved: true });
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

  /**
   * The single attempt cycle shared by requestPrint and retryJob: everything
   * from preflight onward routes through here, so the lifecycle and state walk
   * can never diverge between the two entry points.
   */
  async _attemptCycle(driver, receipt, request, state) {
    try {
      await this._preflight(driver, state);

      await this._transitionTo(state, "PRINTING");
      state.phase = "PRINT";

      const result = await this._executePrint(driver, receipt, request, state);
      return await this._settle(state, result, driver);
    } catch (raw) {
      return this._failureOutcome(state, raw);
    }
  }

  /**
   * Frozen driver lifecycle before dispatch: detect -> initialize -> getStatus.
   * Every failure here is a pre-output failure that keeps content unstarted and
   * settles FAILED_SAFE (the Job is still PREFLIGHT; PREFLIGHT -> FAILED_SAFE
   * is the legal path).
   */
  async _preflight(driver, state) {
    state.phase = "PREFLIGHT";

    let detected;
    try {
      detected = await driver.detect({ job_id: state.job_id });
    } catch (raw) {
      throw normalize(raw, "PREFLIGHT", { content_started: false });
    }
    if (!detected || !detected.available) {
      throw makeError("PDP_BRIDGE_UNAVAILABLE", {
        phase: "PREFLIGHT",
        metadata: { reason: detected?.reason || null },
      });
    }

    try {
      const initialized = await driver.initialize({
        job_id: state.job_id,
      });
      if (!initialized || !initialized.initialized) {
        throw makeError("PDP_PRINTER_NOT_READY", { phase: "PREFLIGHT" });
      }
    } catch (raw) {
      if (raw && raw.code && String(raw.code).startsWith("PDP_")) {
        throw raw;
      }
      throw normalize(raw, "PREFLIGHT", { content_started: false });
    }

    let status;
    try {
      status = await driver.getStatus({ job_id: state.job_id });
    } catch (raw) {
      throw normalize(raw, "PREFLIGHT", { content_started: false });
    }
    this._statusCodeFor(status);
  }

  /**
   * Map a preflight PrinterStatus to the canonical reserved code. A non-READY
   * status throws so the cycle settles FAILED_SAFE while the Job is PREFLIGHT.
   * PAPER_OUT and COVER_OPEN get their own codes; anything else is
   * PDP_PRINTER_NOT_READY (milestone-b §1.6 mapping).
   */
  _statusCodeFor(status) {
    if (!status || status.ready) {
      return null;
    }
    const state = status.state || "UNKNOWN_ERROR";
    if (state === "PAPER_OUT") {
      throw makeError("PDP_PRINTER_PAPER_OUT", { phase: "PREFLIGHT" });
    }
    if (state === "COVER_OPEN") {
      throw makeError("PDP_PRINTER_COVER_OPEN", { phase: "PREFLIGHT" });
    }
    throw makeError("PDP_PRINTER_NOT_READY", { phase: "PREFLIGHT" });
  }

  async _transitionTo(state, target_state) {
    await this.coordinator.transition({
      job_id: state.job_id,
      expected_from_state: state.current,
      target_state,
      reservation_token: state.reservation_token,
    });
    state.current = target_state;
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
      // A driver that throws after dispatch is authoritative about content
      // risk; do not let the manager's pre-throw state flatten it in the audit.
      const content_started =
        state.content_started || Boolean(raw?.content_may_have_printed);
      state.content_started = content_started;
      state.driver_error = normalize(raw, state.phase, { content_started });
      return {
        accepted: false,
        content_started,
        content_completed: false,
        verification_supported: false,
        final_status: null,
        metadata: {},
      };
    }
  }

  async _settle(state, result, driver) {
    let settled_status = this._settleStatus(result);

    // PRINTING -> FAILED_SAFE is forbidden (A.17 / constitution §7): once the
    // Job has entered PRINTING, a failure cannot be labelled safe even if the
    // driver reports content_started false, because the manager cannot prove
    // no content was issued. Escalate to the legal PRINTING -> UNCERTAIN exit.
    if (settled_status === "FAILED_SAFE" && state.current === "PRINTING") {
      settled_status = "UNCERTAIN";
    }

    await this.coordinator.completeAttempt({
      attempt_id: state.attempt_id,
      outcome: settled_status,
      content_started: result.content_started,
      content_completed: result.content_completed,
      error: state.driver_error || null,
    });

    const current = await this._walkSettlePath(state, settled_status);

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

  /**
   * Walk the tail of the valid path from the live state to the settled state
   * and update `state.current` on the way. A preflight failure walks
   * PREFLIGHT -> FAILED_SAFE; a completed dispatch walks PRINTING -> VERIFYING
   * -> SUCCEEDED (or PRINTING -> UNCERTAIN). Path steps already reached
   * (PRINTING after dispatch) are skipped; no new transitions are invented.
   */
  async _walkSettlePath(state, settled_status) {
    const path = SETTLE_PATHS[settled_status];
    const reached = path.indexOf(state.current);
    let current = reached >= 0 ? path[reached] : state.current;
    for (let i = reached + 1; i < path.length; i += 1) {
      await this.coordinator.transition({
        job_id: state.job_id,
        expected_from_state: current,
        target_state: path[i],
        reservation_token: state.reservation_token,
      });
      current = path[i];
    }
    state.current = current;
    return current;
  }

  _settleStatus(result) {
    // Browser handoff (BrowserDriver) is its own settled state — never a
    // physical success, never a plain failure.
    if (result.metadata && result.metadata.handoff) {
      return "FALLBACK_BROWSER";
    }
    // B-COMP Option A gate: SUCCEEDED requires full dispatch AND a bounded
    // post-dispatch READY status query. Dispatch without that approved
    // evidence settles UNCERTAIN (constitution §7: unknown = may have printed).
    if (
      result.accepted &&
      result.content_completed &&
      result.metadata?.post_status_checked === true &&
      result.final_status?.ready === true
    ) {
      return "SUCCEEDED";
    }
    if (result.content_started && !result.content_completed) {
      return "UNCERTAIN";
    }
    if (result.accepted && result.content_completed) {
      // Dispatch completed but no approved post-status evidence.
      return "UNCERTAIN";
    }
    if (result.content_started) {
      // Dispatch began but completion is unproven (accepted false path).
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

    // Preflight failures must leave the Job FAILED_SAFE (so safe retry and
    // browser fallback remain available); once the Job has entered PRINTING
    // (or content started) the failure is UNCERTAIN through the legal
    // PRINTING -> UNCERTAIN exit — PRINTING -> FAILED_SAFE is forbidden (A.17).
    const settled_status =
      state.current === "PRINTING" || state.content_started
        ? "UNCERTAIN"
        : "FAILED_SAFE";

    if (state.attempt_id) {
      try {
        await this.coordinator.completeAttempt({
          attempt_id: state.attempt_id,
          outcome: settled_status,
          content_started: state.content_started,
          error: domainError,
        });
      } catch {
        // Best effort: the attempt completion must not mask the primary error.
      }
    }

    // The walk is best-effort here: the primary error always wins.
    let status = settled_status;
    if (state.job_id) {
      try {
        status = await this._walkSettlePath(state, settled_status);
      } catch {
        // The Job state could not be advanced (e.g. a reservation conflict);
        // report the settled status anyway — the audit record is authoritative.
      }
    }

    return {
      job_id: state.job_id || null,
      status,
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
