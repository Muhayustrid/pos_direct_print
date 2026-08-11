/**
 * A3-07 — browser fallback boundary suite (A-AT-16, A-AT-17).
 *
 * Proves the saved original ERPNext browser print path is reachable only
 * with explicit approval and zero content risk, and that a browser handoff
 * is never reported as physical success.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { CapabilityRegistry } from "../../core/capability_registry.mjs";
import { JobCoordinator } from "../../core/job_coordinator.mjs";
import { VALID_TRANSITIONS } from "../../core/print_job.mjs";
import { PrintManager } from "../../core/print_manager.mjs";
import {
  BrowserDriver,
  BROWSER_DRIVER_KEY,
} from "../../drivers/browser_driver.mjs";
import { FakeDriver } from "../../drivers/fake_driver.mjs";
import { POSIntegrationAdapter } from "../erpnext_v16_pos.mjs";

/** Minimal in-memory transport stand-in mirroring the RPC contract. */
class InMemoryApi {
  constructor() {
    this.jobs = new Map();
    this.attempts = new Map();
    this.sequence = 0;
  }

  async reservePrintJob(payload) {
    const job_id = `JOB-${++this.sequence}`;
    const job = {
      job_id,
      status: "RESERVED",
      reservation_owner: payload.reservation_owner,
      idempotency_key: payload.idempotency_key,
      reference_doctype: payload.reference_doctype,
      reference_name: payload.reference_name,
      terminal: payload.terminal_id,
      driver_key: payload.driver_key,
      content_may_have_printed: false,
    };
    this.jobs.set(job_id, job);
    return {
      job_id,
      reservation_token: job.reservation_owner,
      reserved_until: null,
      status: "RESERVED",
      is_new_job: true,
    };
  }

  async reReserveJob({ job_id, initiator }) {
    const job = this.jobs.get(job_id);
    if (job.status !== "FAILED_SAFE") {
      throw new Error(
        `PDP_JOB_CONFLICT: expected FAILED_SAFE, is ${job.status}`
      );
    }
    const owner = `RETRY-${++this.sequence}`;
    if (owner === initiator) {
      throw new Error(
        "PDP_JOB_CONFLICT: retry owner must differ from initiator"
      );
    }
    job.reservation_owner = owner;
    job.status = "RESERVED";
    return {
      job_id,
      reservation_token: owner,
      reserved_until: null,
      status: job.status,
    };
  }

  async startAttempt({ job_id, reservation_token }) {
    const job = this.jobs.get(job_id);
    if (job.status !== "RESERVED") {
      throw new Error(`PDP_JOB_CONFLICT: expected RESERVED, is ${job.status}`);
    }
    if (job.reservation_owner !== reservation_token) {
      throw new Error(`PDP_JOB_CONFLICT: reservation owner mismatch`);
    }
    job.status = "PREFLIGHT";
    const attempt_no =
      [...this.attempts.values()].filter((a) => a.job === job_id).length + 1;
    const attempt = {
      attempt_id: `ATT-${job_id}-${attempt_no}`,
      job: job_id,
      attempt_no,
      outcome: "STARTED",
      content_started: false,
    };
    this.attempts.set(attempt.attempt_id, attempt);
    return { job: { status: job.status }, attempt };
  }

  async bindReceiptSnapshot({
    job_id,
    reservation_token,
    receipt_snapshot,
    receipt_hash,
  }) {
    const job = this.jobs.get(job_id);
    if (job.status !== "RESERVED") {
      throw new Error(`PDP_JOB_CONFLICT: expected RESERVED, is ${job.status}`);
    }
    if (job.reservation_owner !== reservation_token) {
      throw new Error(`PDP_JOB_CONFLICT: reservation owner mismatch`);
    }
    job.receipt_snapshot = receipt_snapshot;
    job.receipt_hash = receipt_hash;
    return { status: job.status };
  }

  async transitionJob({
    job_id,
    expected_from_state,
    target_state,
    reservation_token,
  }) {
    const job = this.jobs.get(job_id);
    if (!VALID_TRANSITIONS.has(`${expected_from_state}->${target_state}`)) {
      throw new Error(
        `PDP_JOB_INVALID_TRANSITION: ${expected_from_state}->${target_state}`
      );
    }
    if (job.status !== expected_from_state) {
      throw new Error(
        `PDP_JOB_CONFLICT: expected ${expected_from_state}, is ${job.status}`
      );
    }
    if (job.reservation_owner !== reservation_token) {
      throw new Error(`PDP_JOB_CONFLICT: reservation owner mismatch`);
    }
    job.status = target_state;
    return { status: job.status };
  }

  async completeAttempt({ attempt_id, outcome, content_started }) {
    const attempt = this.attempts.get(attempt_id);
    attempt.outcome = outcome;
    attempt.content_started = Boolean(content_started);
    if (content_started) {
      this.jobs.get(attempt.job).content_may_have_printed = true;
    }
    return { status: this.jobs.get(attempt.job).status };
  }

  async retrieveJob(job_id) {
    return { ...this.jobs.get(job_id) };
  }
}

function makeFoundation(settings = {}) {
  const api = new InMemoryApi();
  const coordinator = new JobCoordinator(api);
  const registry = new CapabilityRegistry({ allow_reregistration: true });
  registry.registerDriver({
    driver_key: "fake",
    factory: () => new FakeDriver(settings.driver_script || {}),
    capabilities: { supports_text: true, paper_width_mm: 58 },
  });
  const manager = new PrintManager({
    coordinator,
    registry,
    resolveDriver: (record) => record.manifest.factory(),
    buildReceipt: () => ({
      schema_version: 1,
      reference_doctype: "POS Invoice",
      reference_name: "POS-INV-FB-1",
      locale: "id-ID",
      currency: "IDR",
      paper_profile: "58mm",
      blocks: [],
      metadata: {},
    }),
    default_driver_key: "fake",
  });
  return { api, manager };
}

function makeSummary() {
  return {
    frm: {
      doc: {
        doctype: "POS Invoice",
        name: "POS-INV-FB-1",
        owner: "op@example.test",
        pos_profile: "yusuf",
        company: "PT. JUARA ROTI INDONESIA",
      },
    },
    terminal_id: "TERM-1",
    pos_direct_print_idempotency_key: "idem-fb-1",
    paired_client_id: "client-1",
  };
}

// ---------------------------------------------------------------- A-AT-16

test("A-AT-16: approved fallback after pre-content failure hands off to the original path", async () => {
  const { api, manager } = makeFoundation({
    driver_script: { print_behavior: "fail_before_content" },
  });
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: async () => ({
      pos_direct_print_terminal_id: "TERM-1",
    }),
  });
  let original_calls = 0;
  const prototype = {
    print_receipt() {
      original_calls++;
      return "original-printed";
    },
  };
  adapter.installOverride(manager, prototype);

  const failed = await prototype.print_receipt.call(makeSummary());
  assert.equal(failed.status, "FAILED_SAFE");
  const snapshot = await api.retrieveJob(failed.job_id);
  assert.equal(snapshot.content_may_have_printed, false);

  // User approves the fallback: the Job may move FAILED_SAFE ->
  // FALLBACK_BROWSER through the transition table.
  await manager.fallbackToBrowser(failed.job_id, true);
  const settled = await api.retrieveJob(failed.job_id);
  assert.equal(settled.status, "FALLBACK_BROWSER");

  // The adapter boundary then invokes the saved original ERPNext path.
  const outcome = { status: "FALLBACK_BROWSER", fallback_used: true };
  const handoff = await adapter._settleOutcome(
    outcome,
    prototype ? adapter.override_handle.original_method : null,
    makeSummary(),
    []
  );
  assert.equal(handoff.handed_off, true);
  assert.equal(original_calls, 1, "original path called exactly once");
});

test("browser handoff is never reported as physical success", async () => {
  const { manager } = makeFoundation({
    driver_script: { print_behavior: "fail_before_content" },
  });
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: async () => ({
      pos_direct_print_terminal_id: "TERM-1",
    }),
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const failed = await prototype.print_receipt.call(makeSummary());
  const result = new BrowserDriver().print({}, { approved: true });

  assert.equal(result.accepted, true);
  assert.equal(result.content_started, false);
  assert.equal(result.content_completed, false, "physical completion unknown");
  assert.equal(manager._settleStatus(result), "FALLBACK_BROWSER");
  assert.equal(manager._settleStatus(result) === "SUCCEEDED", false);
  void failed;
});

// ---------------------------------------------------------------- A-AT-17

test("A-AT-17: fallback with content risk is denied and original path never called", async () => {
  const { api, manager } = makeFoundation({
    driver_script: { print_behavior: "fail_after_content" },
  });
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: async () => ({
      pos_direct_print_terminal_id: "TERM-1",
    }),
  });
  let original_calls = 0;
  const prototype = {
    print_receipt() {
      original_calls++;
      return "original-printed";
    },
  };
  adapter.installOverride(manager, prototype);

  const uncertain = await prototype.print_receipt.call(makeSummary());
  assert.equal(uncertain.status, "UNCERTAIN");
  const snapshot = await api.retrieveJob(uncertain.job_id);
  assert.equal(snapshot.content_may_have_printed, true);

  await assert.rejects(
    () => manager.fallbackToBrowser(uncertain.job_id, true),
    (err) =>
      err.code === "PDP_JOB_CONFLICT" && err.retry_class === "REPRINT_ONLY"
  );
  assert.equal(original_calls, 0, "original browser print never invoked");
});

test("fallback without approval is denied even with zero content risk", async () => {
  const { manager } = makeFoundation({
    driver_script: { print_behavior: "fail_before_content" },
  });
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: async () => ({
      pos_direct_print_terminal_id: "TERM-1",
    }),
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const failed = await prototype.print_receipt.call(makeSummary());
  await assert.rejects(
    () => manager.fallbackToBrowser(failed.job_id, false),
    (err) => err.code === "PDP_PERMISSION_DENIED"
  );
});

test("BrowserDriver enforces approval and content-risk gates at the driver boundary", () => {
  const driver = new BrowserDriver();
  assert.equal(driver.driver_key, BROWSER_DRIVER_KEY);

  assert.throws(
    () => driver.print({}, { approved: false }),
    (err) => err.code === "PDP_PERMISSION_DENIED"
  );
  assert.throws(
    () => driver.print({}, { approved: true, content_may_have_printed: true }),
    (err) => err.code === "PDP_JOB_CONFLICT"
  );

  const capabilities = driver.getCapabilities();
  assert.equal(capabilities.supports_cut, false);
  assert.equal(capabilities.metadata.handoff, true);
});
