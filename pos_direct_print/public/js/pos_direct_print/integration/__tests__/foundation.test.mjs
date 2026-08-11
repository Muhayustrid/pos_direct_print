/**
 * A2-10 — client foundation integration suite (A-AT-04/05/06/13/15).
 *
 * Proves override idempotency, original-path restoration, disabled behavior,
 * fake-driver abstraction, and canonical error normalization — all without
 * device, plugin, Android, printer, network, or iMin (A-DOD-12).
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { SubsystemBootstrap } from "../../core/bootstrap.mjs";
import { CapabilityRegistry } from "../../core/capability_registry.mjs";
import { JobCoordinator } from "../../core/job_coordinator.mjs";
import { makeError } from "../../core/errors.mjs";
import { VALID_TRANSITIONS } from "../../core/print_job.mjs";
import { PrintManager } from "../../core/print_manager.mjs";
import { FakeDriver } from "../../drivers/fake_driver.mjs";
import {
  POSIntegrationAdapter,
  computeIdempotencyKey,
} from "../erpnext_v16_pos.mjs";

/** In-memory stand-in for the server transport — mirrors the RPC contract. */
class InMemoryApi {
  constructor() {
    this.jobs = new Map();
    this.attempts = new Map();
    this.sequence = 0;
  }

  async reservePrintJob(payload) {
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

  async startAttempt({ job_id }) {
    const job = this.jobs.get(job_id);
    if (job.status !== "RESERVED") {
      throw new Error(`PDP_JOB_CONFLICT: expected RESERVED, is ${job.status}`);
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

  async bindReceiptSnapshot({ job_id, receipt_snapshot, receipt_hash }) {
    const job = this.jobs.get(job_id);
    if (job.status !== "RESERVED") {
      throw new Error(`PDP_JOB_CONFLICT: expected RESERVED, is ${job.status}`);
    }
    job.receipt_snapshot = receipt_snapshot;
    job.receipt_hash = receipt_hash;
    return { status: job.status };
  }

  async transitionJob({ job_id, expected_from_state, target_state }) {
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

function makeFoundation(settings = {}) {
  const api = new InMemoryApi();
  const coordinator = new JobCoordinator(api);
  const registry = new CapabilityRegistry({ allow_reregistration: true });
  registry.registerDriver({
    driver_key: "fake",
    factory: () => new FakeDriver(settings.driver_script || {}),
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

  return { api, coordinator, registry, manager };
}

function makeSummary() {
  return {
    frm: {
      doc: {
        doctype: "POS Invoice",
        name: "POS-INV-001",
        owner: "op@example.test",
        pos_profile: "yusuf",
        company: "PT. JUARA ROTI INDONESIA",
      },
    },
    terminal_id: "TERM-1",
    pos_direct_print_idempotency_key: "idem-001",
    paired_client_id: "client-1",
  };
}

/** Default fake resolver: fixed terminal, no server or localStorage. */
async function fakeResolveTerminalContext() {
  return { pos_direct_print_terminal_id: "TERM-1" };
}

function makeRequest(manager, settings) {
  const prototype = {
    print_receipt() {
      return "original-printed";
    },
  };
  const adapter = new POSIntegrationAdapter({
    get_settings: () => settings,
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const handle = adapter.installOverride(manager, prototype);
  return { prototype, adapter, handle };
}

// ---------------------------------------------------------------- A-AT-04

test("A-AT-04: initializing three times still yields exactly one PrintRequest", async () => {
  const { manager } = makeFoundation();
  const prototype = {
    print_receipt() {
      return "original-printed";
    },
  };

  // Subsystem initialization called three times must install one override:
  // each initialize returns the same live handle and never repatches.
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const first = adapter.installOverride(manager, prototype);
  const second = adapter.installOverride(manager, prototype);
  const third = adapter.installOverride(manager, prototype);
  assert.equal(first, second);
  assert.equal(second, third);

  await prototype.print_receipt.call(makeSummary());

  assert.equal(manager.requests_received.length, 1);
  assert.equal(manager.requests_received[0].reference_name, "POS-INV-001");
});

test("bootstrap initialize is idempotent across repeated calls", () => {
  const bootstrap = new SubsystemBootstrap();
  const prototype = { print_receipt() {} };
  const context = {
    settings: { enabled: true, receipt_schema_version: 1 },
    pos_context: prototype,
  };

  const first = bootstrap.initialize(context);
  const second = bootstrap.initialize(context);
  const third = bootstrap.initialize(context);

  assert.equal(first.initialized, true);
  assert.equal(first.integration_installed, true);
  assert.equal(second, first);
  assert.equal(third, first);
});

// ---------------------------------------------------------------- A-AT-05

test("A-AT-05: restoring the override returns to the original print path", async () => {
  const { manager } = makeFoundation();
  let original_calls = 0;
  const prototype = {
    print_receipt() {
      original_calls++;
      return "original-printed";
    },
  };
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const handle = adapter.installOverride(manager, prototype);

  adapter.restoreOverride(handle);
  const result = prototype.print_receipt.call(makeSummary());

  assert.equal(result, "original-printed");
  assert.equal(original_calls, 1, "saved original path called exactly once");
  assert.equal(
    manager.requests_received.length,
    0,
    "orchestration bypassed after restore"
  );
});

// ---------------------------------------------------------------- A-AT-06

test("A-AT-06: disabled feature uses original behavior and never touches the driver", async () => {
  const { manager, registry } = makeFoundation();
  const driver = registry.getDriver("fake").manifest.factory();
  let original_calls = 0;
  const prototype = {
    print_receipt() {
      original_calls++;
      return "original-printed";
    },
  };
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: false }),
  });
  adapter.installOverride(manager, prototype);

  await prototype.print_receipt.call(makeSummary());

  assert.equal(original_calls, 1, "baseline ERPNext print used");
  assert.equal(
    manager.requests_received.length,
    0,
    "orchestration not invoked"
  );
  assert.equal(driver.print_calls.length, 0, "physical driver never called");
});

// ---------------------------------------------------------------- A-AT-13

test("A-AT-13: fake driver drives orchestration without any iMin dependency", async () => {
  const { manager } = makeFoundation();
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const outcome = await prototype.print_receipt.call(makeSummary());

  assert.equal(outcome.success, true);
  assert.equal(outcome.status, "SUCCEEDED");
  assert.equal(outcome.fallback_used, false);
});

test("A-AT-13: unsupported cutter yields a controlled outcome, not an exception", () => {
  const driver = new FakeDriver();
  const result = driver.cut({});

  assert.equal(result.accepted, false);
  assert.equal(result.content_started, false);
  assert.equal(result.metadata.error_code, "PDP_DRIVER_CAPABILITY_UNSUPPORTED");
});

test("capability registry duplicate policy and resolution", () => {
  const registry = new CapabilityRegistry({ allow_reregistration: true });
  const manifest = {
    driver_key: "fake",
    factory: () => new FakeDriver(),
    capabilities: { supports_text: true, paper_width_mm: 58 },
  };

  assert.equal(registry.registerDriver(manifest).registered, true);
  // Exact same instance under bootstrap policy: tolerated, not stacked.
  assert.equal(registry.registerDriver(manifest).duplicate, true);
  // A different registration for the same key: configuration conflict.
  assert.throws(
    () => registry.registerDriver({ ...manifest }),
    (err) => {
      return err.code === "PDP_CONFIG_INVALID";
    }
  );

  assert.equal(registry.hasDriver("fake"), true);
  assert.equal(registry.hasDriver("ghost"), false);
  assert.throws(
    () => registry.getDriver("ghost"),
    (err) => err.code === "PDP_DRIVER_NOT_FOUND"
  );

  const resolved = registry.resolveCapabilities(
    "fake",
    { paper_width_mm: 80 },
    { available: true }
  );
  assert.equal(resolved.paper_width_mm, 80);
  assert.equal(resolved.available, true);
});

// ---------------------------------------------------------------- A-AT-15

test("A-AT-15: raw driver exceptions normalize into a canonical user error", async () => {
  const { manager } = makeFoundation({
    driver_script: { print_behavior: "throw" },
  });
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const outcome = await prototype.print_receipt.call(makeSummary());

  assert.equal(outcome.success, false);
  assert.ok(outcome.error, "outcome carries a user error");
  assert.ok(outcome.error.code.startsWith("PDP_"), "canonical code");
  assert.ok(outcome.error.title_key, "message key present");
  const dump = JSON.stringify(outcome);
  assert.ok(
    !dump.includes("fake driver exploded"),
    "raw message never user-facing"
  );
  assert.ok(!dump.includes("\tat "), "no stack trace leaks");
});

test("content started without completion settles UNCERTAIN with reprint-only semantics", async () => {
  const { manager } = makeFoundation({
    driver_script: { print_behavior: "fail_after_content" },
  });
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const outcome = await prototype.print_receipt.call(makeSummary());

  assert.equal(outcome.status, "UNCERTAIN");
  assert.equal(outcome.success, false);
});

test("pre-content failure settles FAILED_SAFE", async () => {
  const { manager } = makeFoundation({
    driver_script: { print_behavior: "fail_before_content" },
  });
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const outcome = await prototype.print_receipt.call(makeSummary());

  assert.equal(outcome.status, "FAILED_SAFE");
  assert.equal(outcome.success, false);
});

// ---------------------------------------------------------------- A-AT-11

// ---------------------------------------------------------------- B4-01 context wiring

test("computeIdempotencyKey is stable for identical inputs", () => {
  const key = {
    schema_version: 1,
    reference_doctype: "POS Invoice",
    reference_name: "POS-INV-001",
    terminal_id: "TERM-1",
    job_type: "ORIGINAL",
  };
  assert.equal(computeIdempotencyKey(key), computeIdempotencyKey(key));
  assert.match(computeIdempotencyKey(key), /^pdpr1:[0-9a-f]{16}$/);
});

test("computeIdempotencyKey differs across invoices and terminals", () => {
  const base = {
    schema_version: 1,
    reference_doctype: "POS Invoice",
    terminal_id: "TERM-1",
    job_type: "ORIGINAL",
  };
  const a = computeIdempotencyKey({ ...base, reference_name: "POS-INV-001" });
  const b = computeIdempotencyKey({ ...base, reference_name: "POS-INV-002" });
  const c = computeIdempotencyKey({
    ...base,
    reference_name: "POS-INV-001",
    terminal_id: "TERM-2",
  });
  assert.notEqual(a, b);
  assert.notEqual(a, c);
});

test("fake resolver context reaches buildPrintRequest (B4-01)", async () => {
  const { manager } = makeFoundation();
  const calls = [];
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true, receipt_schema_version: 1 }),
    resolve_terminal_context: async (summary) => {
      calls.push({ pos_profile: summary.frm.doc.pos_profile });
      return {
        pos_direct_print_terminal_id: "TERM-RESOLVED",
        pos_direct_print_idempotency_key: "idem-resolved-1",
        paired_client_id: "client-resolved-1",
      };
    },
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const summary = {
    frm: {
      doc: {
        doctype: "POS Invoice",
        name: "POS-INV-CTX-1",
        owner: "op@example.test",
        pos_profile: "yusuf",
        company: "PT. JUARA ROTI INDONESIA",
      },
    },
  };

  await prototype.print_receipt.call(summary);

  assert.equal(calls.length, 1, "resolver invoked exactly once");
  const request = manager.requests_received[0];
  assert.equal(request.terminal_id, "TERM-RESOLVED");
  assert.equal(request.source, "POS_AUTO");
  assert.equal(request.job_type, "ORIGINAL");
  assert.equal(request.reference_name, "POS-INV-CTX-1");
});

test("default resolve_context caches per company|pos_profile and assigns idempotency key", async () => {
  const { manager } = makeFoundation();
  let resolver_calls = 0;
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true, receipt_schema_version: 1 }),
    resolve_terminal_context: async () => {
      resolver_calls += 1;
      return {
        pos_direct_print_terminal_id: "TERM-CACHED",
        pos_direct_print_idempotency_key: "idem-cached-1",
        paired_client_id: "client-cached-1",
      };
    },
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const summary = {
    frm: {
      doc: {
        doctype: "POS Invoice",
        name: "POS-INV-CACHE-1",
        owner: "op@example.test",
        pos_profile: "yusuf",
        company: "PT. JUARA ROTI INDONESIA",
      },
    },
  };

  await prototype.print_receipt.call(summary);
  await prototype.print_receipt.call({ ...summary });

  // The cache is keyed company|pos_profile: the second call reuses the entry.
  assert.equal(resolver_calls, 1, "resolver called once thanks to the cache");
  assert.equal(manager.requests_received.length, 2);
  assert.equal(manager.requests_received[0].terminal_id, "TERM-CACHED");
  assert.equal(manager.requests_received[1].terminal_id, "TERM-CACHED");
});

test("same profile, two invoices: resolver called once, idempotency keys differ", async () => {
  const { api, manager } = makeFoundation();
  let resolver_calls = 0;
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true, receipt_schema_version: 1 }),
    resolve_terminal_context: async () => {
      resolver_calls += 1;
      return {
        pos_direct_print_terminal_id: "TERM-CACHED",
        // Deliberately stale resolver-supplied key: the adapter must never
        // cache or trust it, or invoice B would inherit invoice A's key.
        pos_direct_print_idempotency_key: "stale-invoice-A-key",
        paired_client_id: "client-cached-1",
      };
    },
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const summaryA = {
    frm: {
      doc: {
        doctype: "POS Invoice",
        name: "POS-INV-LEAK-A",
        owner: "op@example.test",
        pos_profile: "yusuf",
        company: "PT. JUARA ROTI INDONESIA",
      },
    },
  };
  const summaryB = {
    ...summaryA,
    frm: { doc: { ...summaryA.frm.doc, name: "POS-INV-LEAK-B" } },
  };

  await prototype.print_receipt.call(summaryA);
  await prototype.print_receipt.call(summaryB);

  assert.equal(resolver_calls, 1, "terminal resolved once for the profile");
  assert.equal(
    manager.requests_received.length,
    2,
    "two invoices produce two requests"
  );
  assert.equal(api.jobs.size, 2, "distinct keys create distinct Jobs");
  const keys = [...api.jobs.values()].map((job) => job.idempotency_key);
  assert.equal(
    new Set(keys).size,
    2,
    "two invoices on one terminal never share an idempotency key"
  );
  assert.ok(
    keys.every((k) => k !== "stale-invoice-A-key"),
    "resolver-supplied key is never trusted"
  );
});

test("resolved context preserves terminal transport, driver_key, and paper_width_mm", async () => {
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true, receipt_schema_version: 1 }),
    resolve_terminal_context: async () => ({
      pos_direct_print_terminal_id: "TERM-T",
      pos_direct_print_transport: "USB",
      pos_direct_print_driver_key: "imin_v1",
      pos_direct_print_paper_width_mm: "58",
      paired_client_id: "client-t",
    }),
  });

  const summary = {
    frm: {
      doc: {
        doctype: "POS Invoice",
        name: "POS-INV-TRANSPORT",
        owner: "op@example.test",
        pos_profile: "yusuf",
        company: "PT. JUARA ROTI INDONESIA",
      },
    },
  };

  const ctx = await adapter.resolve_context(summary);

  assert.equal(ctx.pos_direct_print_terminal_id, "TERM-T");
  assert.equal(ctx.pos_direct_print_transport, "USB");
  assert.equal(ctx.pos_direct_print_driver_key, "imin_v1");
  assert.equal(ctx.pos_direct_print_paper_width_mm, "58");
  assert.ok(
    ctx.pos_direct_print_idempotency_key.startsWith("pdpr1:"),
    "key is still derived per invoice"
  );
});

test("resolver failure surfaces canonical error without touching original print", async () => {
  const { manager } = makeFoundation();
  let original_calls = 0;
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: async () => {
      throw makeError("PDP_TERMINAL_NOT_FOUND", {
        phase: "RESERVATION",
        metadata: { reason: "no terminal for profile" },
      });
    },
  });
  const prototype = {
    print_receipt() {
      original_calls++;
      return "original-printed";
    },
  };
  adapter.installOverride(manager, prototype);

  await assert.rejects(
    () => prototype.print_receipt.call(makeSummary()),
    (err) => err.code === "PDP_TERMINAL_NOT_FOUND"
  );
  assert.equal(
    original_calls,
    0,
    "original path never called on resolver failure"
  );
  assert.equal(manager.requests_received.length, 0, "orchestration bypassed");
});

test("disabled settings bypass resolver entirely (A-AT-06 regression)", async () => {
  const { manager } = makeFoundation();
  let original_calls = 0;
  let resolver_calls = 0;
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: false }),
    resolve_terminal_context: async () => {
      resolver_calls++;
      return {
        pos_direct_print_terminal_id: "TERM-1",
        pos_direct_print_idempotency_key: "idem-1",
        paired_client_id: "client-1",
      };
    },
  });
  const prototype = {
    print_receipt() {
      original_calls++;
      return "original-printed";
    },
  };
  adapter.installOverride(manager, prototype);

  await prototype.print_receipt.call(makeSummary());

  assert.equal(original_calls, 1, "baseline ERPNext print used");
  assert.equal(resolver_calls, 0, "resolver never called when disabled");
  assert.equal(
    manager.requests_received.length,
    0,
    "orchestration not invoked"
  );
});

test("A-AT-11: safe retry reuses the SAME Job with a new Attempt", async () => {
  const settings = {
    driver_script: { print_behavior: "fail_before_content" },
  };
  const { api, manager } = makeFoundation(settings);
  const adapter = new POSIntegrationAdapter({
    get_settings: () => ({ enabled: true }),
    resolve_terminal_context: fakeResolveTerminalContext,
  });
  const prototype = { print_receipt() {} };
  adapter.installOverride(manager, prototype);

  const failed = await prototype.print_receipt.call(makeSummary());
  assert.equal(failed.status, "FAILED_SAFE");
  const jobs_after_first = api.jobs.size;
  const requests_after_first = manager.requests_received.length;

  // Last attempt classified safe to retry (server-side classification in the
  // real flow), and the transient failure cleared.
  const first_attempt = await api.lastAttemptFor(failed.job_id);
  first_attempt.retry_class = "AUTO_SAFE";
  settings.driver_script.print_behavior = "succeed";

  const retried = await manager.retryJob(
    failed.job_id,
    "op@example.test",
    "operator retry"
  );

  assert.equal(retried.status, "SUCCEEDED");
  assert.equal(retried.success, true);
  assert.equal(retried.job_id, failed.job_id, "same Job, never a new one");
  assert.equal(api.jobs.size, jobs_after_first, "no new Job created");
  assert.equal(
    manager.requests_received.length,
    requests_after_first,
    "retry does not route through requestPrint"
  );
  const attempts = [...api.attempts.values()].filter(
    (a) => a.job === failed.job_id
  );
  assert.deepEqual(
    attempts.map((a) => a.attempt_no).sort(),
    [1, 2],
    "second Attempt under the same Job"
  );
});
