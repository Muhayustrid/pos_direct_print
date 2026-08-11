/**
 * Task 3 — PrintManager lifecycle remediation (plan.md §1.6 / R-GAP-05).
 *
 * Locks the frozen driver lifecycle into orchestration: detect -> initialize ->
 * getStatus before PREFLIGHT -> PRINTING, dispatch while PRINTING, then the
 * B-COMP Option A settlement gate. Uses a recording stub driver so the exact
 * call order is observable, and the InMemoryApi pattern from
 * integration/__tests__/foundation.test.mjs so no server or device is needed.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { CapabilityRegistry } from "../capability_registry.mjs";
import { JobCoordinator } from "../job_coordinator.mjs";
import { VALID_TRANSITIONS } from "../print_job.mjs";
import { PrintManager } from "../print_manager.mjs";
import { makeError } from "../errors.mjs";
import { FakeDriver } from "../../drivers/fake_driver.mjs";
import { BrowserDriver } from "../../drivers/browser_driver.mjs";

/** In-memory transport mirroring the RPC contract (foundation pattern). */
class InMemoryApi {
  constructor() {
    this.jobs = new Map();
    this.attempts = new Map();
    this.sequence = 0;
    this.transitions = [];
    this.events = [];
  }

  async reservePrintJob(payload) {
    this.events.push("reserve");
    for (const job of this.jobs.values()) {
      if (job.idempotency_key === payload.idempotency_key) {
        return {
          job_id: job.job_id,
          reservation_token: job.reservation_owner,
          reserved_until: null,
          status: job.status,
          is_new_job: false,
        };
      }
    }
    const job_id = `JOB-${++this.sequence}`;
    const job = {
      job_id,
      status: "RESERVED",
      reservation_owner: payload.reservation_owner,
      idempotency_key: payload.idempotency_key,
      reference_doctype: payload.reference_doctype,
      reference_name: payload.reference_name,
      terminal: payload.terminal_id,
      source: payload.source,
      job_type: payload.job_type,
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

  async startAttempt({ job_id, reservation_token }) {
    this.events.push("beginAttempt");
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
      phase_reached: "RESERVATION",
      content_started: false,
    };
    this.attempts.set(attempt.attempt_id, attempt);
    return { job: { status: job.status }, attempt };
  }

  async reReserveJob({ job_id, initiator }) {
    this.events.push("reReserve");
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

  async bindReceiptSnapshot({
    job_id,
    reservation_token,
    receipt_snapshot,
    receipt_hash,
  }) {
    this.events.push("bind");
    this.bind_calls = this.bind_calls || [];
    this.bind_calls.push({
      job_id,
      reservation_token,
      receipt_snapshot,
      receipt_hash,
    });
    const job = this.jobs.get(job_id);
    if (job.status !== "RESERVED") {
      throw new Error(`PDP_JOB_CONFLICT: expected RESERVED, is ${job.status}`);
    }
    if (job.reservation_owner !== reservation_token) {
      throw new Error(`PDP_JOB_CONFLICT: reservation owner mismatch`);
    }
    if (this.fail_bind) {
      throw new Error("PDP_JOB_CONFLICT: bind failed");
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
    this.transitions.push({ job_id, expected_from_state, target_state });
    this.events.push(`transition:${target_state}`);
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
    this.events.push("completeAttempt");
    const attempt = this.attempts.get(attempt_id);
    attempt.outcome = outcome;
    attempt.content_started = Boolean(content_started);
    if (content_started) {
      this.jobs.get(attempt.job).content_may_have_printed = true;
    }
    return { status: this.jobs.get(attempt.job).status };
  }

  async releaseReservation({ job_id }) {
    const job = this.jobs.get(job_id);
    job.status = "CANCELLED";
    return { status: job.status };
  }

  async retrieveJob(job_id) {
    return { ...this.jobs.get(job_id) };
  }

  async lastAttemptFor(job_id) {
    const for_job = [...this.attempts.values()]
      .filter((a) => a.job === job_id)
      .sort((a, b) => a.attempt_no - b.attempt_no);
    return for_job.length ? for_job[for_job.length - 1] : null;
  }
}

/**
 * Recording driver: every contract call is appended to a shared trace, and the
 * extra script options script the B-COMP-A gate variants (paper-out preflight,
 * missing post-status evidence, unready post-status).
 */
class RecordingDriver extends FakeDriver {
  constructor(trace, script = {}) {
    super(script);
    this.trace = trace;
    this.script = {
      ...this.script,
      status_state: script.status_state || null,
      no_post_status: Boolean(script.no_post_status),
      unready_post: Boolean(script.unready_post),
    };
  }

  detect() {
    this.trace.push("detect");
    return super.detect();
  }

  initialize(context) {
    this.trace.push("initialize");
    return super.initialize(context);
  }

  getStatus() {
    // The driver-internal post-dispatch status query inside print() is the
    // B-COMP-A evidence, not an orchestration call — keep it out of the trace.
    if (!this._in_print) {
      this.trace.push("getStatus");
    }
    const result = super.getStatus();
    if (this.script.status_state) {
      const state = this.script.status_state;
      return {
        ...result,
        state,
        ready: state === "READY",
        blocking: state !== "READY",
      };
    }
    return result;
  }

  print(receipt_document, job_context) {
    this.trace.push("print");
    if (this.script.no_post_status) {
      return {
        accepted: true,
        content_started: true,
        content_completed: true,
        verification_supported: false,
        final_status: { state: "READY", ready: true, blocking: false },
        metadata: { driver_key: this.driver_key },
      };
    }
    if (this.script.unready_post) {
      return {
        accepted: true,
        content_started: true,
        content_completed: true,
        verification_supported: false,
        final_status: { state: "PAPER_OUT", ready: false, blocking: true },
        metadata: { driver_key: this.driver_key, post_status_checked: true },
      };
    }
    this._in_print = true;
    try {
      return super.print(receipt_document, job_context);
    } finally {
      this._in_print = false;
    }
  }
}

function makeFoundation(settings = {}) {
  const api = new InMemoryApi();
  const coordinator = new JobCoordinator(api);
  const registry = new CapabilityRegistry({ allow_reregistration: true });
  const trace = settings.trace || [];
  const factory = () =>
    new RecordingDriver(trace, settings.driver_script || {});
  registry.registerDriver({
    driver_key: "fake",
    factory,
    capabilities: {
      supports_text: true,
      supports_feed: true,
      paper_width_mm: 58,
    },
  });
  const manager = new PrintManager({
    coordinator,
    registry,
    resolveDriver: (record) => record.manifest.factory(),
    buildReceipt: (snapshot) => ({
      schema_version: 1,
      reference_doctype: "POS Invoice",
      reference_name: snapshot?.name,
      locale: "id-ID",
      currency: "IDR",
      paper_profile: "58mm",
      blocks: [],
      metadata: {},
    }),
    default_driver_key: "fake",
  });
  return { api, coordinator, registry, manager, trace };
}

function makeRequest() {
  return {
    reference_doctype: "POS Invoice",
    reference_name: "POS-INV-LC-1",
    terminal_id: "TERM-1",
    requested_by: "op@example.test",
    idempotency_key: "idem-lc-1",
  };
}

/** requestPrint through the manager directly (bypasses the POS adapter). */
function request(manager, overrides = {}) {
  return manager.requestPrint(
    { ...makeRequest(), ...overrides.request },
    {
      invoice_snapshot: { name: "POS-INV-LC-1" },
      idempotency_key: "idem-lc-1",
      reservation_owner: "client-1",
      ...(overrides.context || {}),
    }
  );
}

function transitionPairs(api) {
  return api.transitions.map(
    (t) => `${t.expected_from_state}->${t.target_state}`
  );
}

test("happy path: lifecycle call order and state walk are exact", async () => {
  const { api, manager, trace } = makeFoundation();
  const outcome = await request(manager);

  assert.equal(outcome.success, true);
  assert.equal(outcome.status, "SUCCEEDED");
  // Driver trace proves preflight before dispatch; the coordinator event
  // trace proves the exact lifecycle order (task brief step 1 case 1):
  // reserve -> bind -> beginAttempt -> detect -> initialize -> getStatus ->
  // transition(PREFLIGHT->PRINTING) -> print -> completeAttempt ->
  // transition(PRINTING->VERIFYING) -> transition(VERIFYING->SUCCEEDED).
  assert.deepEqual(trace, ["detect", "initialize", "getStatus", "print"]);
  assert.deepEqual(api.events, [
    "reserve",
    "bind",
    "beginAttempt",
    "transition:PRINTING",
    "completeAttempt",
    "transition:VERIFYING",
    "transition:SUCCEEDED",
  ]);
  assert.deepEqual(transitionPairs(api), [
    "PREFLIGHT->PRINTING",
    "PRINTING->VERIFYING",
    "VERIFYING->SUCCEEDED",
  ]);
  const snapshot = await api.retrieveJob(outcome.job_id);
  assert.equal(snapshot.status, "SUCCEEDED");
});

test("detect unavailable settles FAILED_SAFE and print is never called", async () => {
  const { manager, trace } = makeFoundation({
    driver_script: { available: false },
  });
  const outcome = await request(manager);

  assert.equal(outcome.status, "FAILED_SAFE");
  assert.equal(outcome.success, false);
  assert.equal(outcome.error.code, "PDP_BRIDGE_UNAVAILABLE");
  assert.deepEqual(trace, ["detect"]);
});

test("getStatus PAPER_OUT settles FAILED_SAFE before any dispatch", async () => {
  const { manager, trace } = makeFoundation({
    driver_script: { status_state: "PAPER_OUT" },
  });
  const outcome = await request(manager);

  assert.equal(outcome.status, "FAILED_SAFE");
  assert.equal(outcome.success, false);
  assert.equal(outcome.error.code, "PDP_PRINTER_PAPER_OUT");
  assert.deepEqual(trace, ["detect", "initialize", "getStatus"]);
  assert.ok(!trace.includes("print"));
});

test("dispatch complete but post_status_checked missing is UNCERTAIN, never SUCCEEDED", async () => {
  const { manager } = makeFoundation({
    driver_script: { no_post_status: true },
  });
  const outcome = await request(manager);

  assert.equal(outcome.status, "UNCERTAIN");
  assert.equal(outcome.success, false);
});

test("dispatch complete with post-status ready:false is UNCERTAIN", async () => {
  const { manager } = makeFoundation({
    driver_script: { unready_post: true },
  });
  const outcome = await request(manager);

  assert.equal(outcome.status, "UNCERTAIN");
  assert.equal(outcome.success, false);
});

test("retryJob re-runs the cycle and re-reserves FAILED_SAFE->RESERVED", async () => {
  const settings = {
    driver_script: { print_behavior: "fail_before_content" },
  };
  const { api, manager, trace } = makeFoundation(settings);
  const failed = await request(manager);
  assert.equal(failed.status, "FAILED_SAFE");

  const first_attempt = await api.lastAttemptFor(failed.job_id);
  first_attempt.retry_class = "AUTO_SAFE";
  settings.driver_script.print_behavior = "succeed";
  trace.length = 0;
  const transitions_before = api.transitions.length;
  const events_before = api.events.length;

  const retried = await manager.retryJob(
    failed.job_id,
    "op@example.test",
    "operator retry"
  );

  assert.equal(retried.status, "SUCCEEDED");
  assert.equal(retried.success, true);
  assert.equal(retried.job_id, failed.job_id, "same Job, never a new one");
  assert.ok(
    api.events.slice(events_before).includes("reReserve"),
    "retry re-reserves server-side instead of a FAILED_SAFE->RESERVED transition"
  );
  const new_transitions = api.transitions.slice(transitions_before);
  assert.deepEqual(
    new_transitions.map((t) => t.expected_from_state),
    ["PREFLIGHT", "PRINTING", "VERIFYING"]
  );
  assert.deepEqual(trace, ["detect", "initialize", "getStatus", "print"]);
  const attempts = [...api.attempts.values()].filter(
    (a) => a.job === failed.job_id
  );
  assert.deepEqual(
    attempts.map((a) => a.attempt_no).sort(),
    [1, 2],
    "second Attempt under the same Job"
  );
});

test("bind is called between reserve and beginAttempt with exact args", async () => {
  const { api, manager } = makeFoundation();
  const outcome = await request(manager);

  assert.equal(outcome.success, true);
  assert.equal(api.bind_calls.length, 1, "bind called exactly once");
  const call = api.bind_calls[0];
  assert.equal(call.job_id, outcome.job_id);
  assert.equal(call.reservation_token, "client-1");
  assert.ok(call.receipt_hash, "client computed the hash");
  const events = api.events;
  const reserve_at = events.indexOf("reserve");
  const bind_at = events.indexOf("bind");
  const begin_at = events.indexOf("beginAttempt");
  assert.ok(reserve_at < bind_at, "bind after reserve");
  assert.ok(bind_at < begin_at, "bind before beginAttempt");
});

test("bind failure settles FAILED_SAFE and creates no attempt", async () => {
  const { api, manager } = makeFoundation();
  api.fail_bind = true;
  const outcome = await request(manager);

  assert.equal(outcome.status, "FAILED_SAFE");
  assert.equal(outcome.success, false);
  assert.ok(outcome.error.code.includes("PDP_JOB_CONFLICT"));
  assert.ok(!api.events.includes("beginAttempt"), "no attempt created");
  assert.equal([...api.attempts.values()].length, 0);
});

test("retry re-reserve rejects wrong token but accepts initiator-distinct fresh token", async () => {
  const settings = {
    driver_script: { print_behavior: "fail_before_content" },
  };
  const { api, manager } = makeFoundation(settings);
  const failed = await request(manager);
  assert.equal(failed.status, "FAILED_SAFE");
  const first_attempt = await api.lastAttemptFor(failed.job_id);
  first_attempt.retry_class = "AUTO_SAFE";

  const old_owner = api.jobs.get(failed.job_id).reservation_owner;
  const re_reserved = await api.reReserveJob({
    job_id: failed.job_id,
    initiator: "operator@example.test",
  });
  assert.notEqual(re_reserved.reservation_token, "operator@example.test");
  assert.notEqual(re_reserved.reservation_token, old_owner);

  await assert.rejects(
    () =>
      api.startAttempt({
        job_id: failed.job_id,
        reservation_token: "wrong-token",
      }),
    (error) => error.message.includes("reservation owner mismatch")
  );

  const started = await api.startAttempt({
    job_id: failed.job_id,
    reservation_token: re_reserved.reservation_token,
  });
  assert.equal(started.job.status, "PREFLIGHT");

  // Keep manager referenced so this regression remains tied to its retry API
  // foundation rather than a standalone transport-only check.
  assert.ok(manager);
});

test("retryJob with fetchReceipt reuses the bound snapshot and skips bind", async () => {
  const settings = {
    driver_script: { print_behavior: "fail_before_content" },
  };
  const { api, manager, trace } = makeFoundation(settings);
  const failed = await request(manager);
  assert.equal(failed.status, "FAILED_SAFE");
  assert.equal(api.bind_calls.length, 1, "initial print bound once");

  const first_attempt = await api.lastAttemptFor(failed.job_id);
  first_attempt.retry_class = "AUTO_SAFE";
  settings.driver_script.print_behavior = "succeed";
  trace.length = 0;
  const bound_before = api.bind_calls.length;
  const fetch_receipt = async () => ({
    schema_version: 1,
    reference_name: "POS-INV-LC-1",
  });
  manager.fetchReceipt = fetch_receipt;

  const retried = await manager.retryJob(
    failed.job_id,
    "op@example.test",
    "operator retry"
  );

  assert.equal(retried.status, "SUCCEEDED");
  assert.equal(
    api.bind_calls.length,
    bound_before,
    "no bind on fetchReceipt retry"
  );
});

test("retryJob without fetchReceipt rebuilds and binds the new snapshot", async () => {
  const settings = {
    driver_script: { print_behavior: "fail_before_content" },
  };
  const { api, manager, trace } = makeFoundation(settings);
  const failed = await request(manager);
  assert.equal(failed.status, "FAILED_SAFE");
  assert.equal(api.bind_calls.length, 1);

  const first_attempt = await api.lastAttemptFor(failed.job_id);
  first_attempt.retry_class = "AUTO_SAFE";
  settings.driver_script.print_behavior = "succeed";
  trace.length = 0;
  const bound_before = api.bind_calls.length;

  const retried = await manager.retryJob(
    failed.job_id,
    "op@example.test",
    "operator retry"
  );

  assert.equal(retried.status, "SUCCEEDED");
  assert.equal(
    api.bind_calls.length,
    bound_before + 1,
    "rebuild path binds again"
  );
});

test("browser handoff result still settles FALLBACK_BROWSER", async () => {
  const { manager } = makeFoundation();
  const driver = new BrowserDriver();
  const result = driver.print({}, { approved: true });

  assert.equal(manager._settleStatus(result), "FALLBACK_BROWSER");
  assert.notEqual(manager._settleStatus(result), "SUCCEEDED");
});
