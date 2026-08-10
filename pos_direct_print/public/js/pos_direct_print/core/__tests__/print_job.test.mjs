import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canTransition,
  assertTransition,
  isTerminalState,
  isRetryAllowed,
  deriveContentRisk,
  STATES,
  TERMINAL_STATES,
  VALID_TRANSITIONS,
} from "../print_job.mjs";
import { PrintDomainError } from "../errors.mjs";

test("all 22 table transitions accepted", () => {
  assert.equal(VALID_TRANSITIONS.size, 22);
  for (const pair of VALID_TRANSITIONS) {
    const [from, to] = pair.split("->");
    assert.ok(canTransition(from, to), `${pair} must be valid`);
  }
});

test("every unlisted pair rejected", () => {
  let rejected = 0;
  for (const from of STATES) {
    for (const to of STATES) {
      if (!VALID_TRANSITIONS.has(`${from}->${to}`)) {
        assert.equal(
          canTransition(from, to),
          false,
          `${from}->${to} must be invalid`
        );
        assert.throws(() => assertTransition(from, to), PrintDomainError);
        rejected++;
      }
    }
  }
  assert.equal(rejected, STATES.length * STATES.length - 22);
});

test("assertTransition raises PDP_JOB_INVALID_TRANSITION with metadata", () => {
  try {
    assertTransition("UNCERTAIN", "PREFLIGHT");
    assert.fail("should have thrown");
  } catch (err) {
    assert.equal(err.code, "PDP_JOB_INVALID_TRANSITION");
    assert.deepEqual(err.metadata, {
      current_state: "UNCERTAIN",
      target_state: "PREFLIGHT",
    });
  }
});

test("terminal states have no outgoing transitions", () => {
  for (const state of TERMINAL_STATES) {
    assert.ok(isTerminalState(state));
    for (const to of STATES) {
      assert.equal(canTransition(state, to), false, `${state}->${to}`);
    }
  }
});

test("deriveContentRisk follows content_started", () => {
  assert.equal(deriveContentRisk({ content_started: 1 }), true);
  assert.equal(deriveContentRisk({ content_started: 0 }), false);
  assert.equal(deriveContentRisk(null), false);
});

test("content risk blocks same-job retry with REPRINT_ONLY", () => {
  // A-AT-12 client side: UNCERTAIN + content started = reprint only.
  const decision = isRetryAllowed(
    { status: "UNCERTAIN" },
    { content_started: 1 }
  );
  assert.equal(decision.allowed, false);
  assert.equal(decision.retry_class, "REPRINT_ONLY");
  assert.equal(decision.automatic, false);
});

test("failed-safe with AUTO_SAFE attempt allows automatic retry", () => {
  const decision = isRetryAllowed(
    { status: "FAILED_SAFE" },
    { content_started: 0, retry_class: "AUTO_SAFE" }
  );
  assert.equal(decision.allowed, true);
  assert.equal(decision.automatic, true);
});

test("manual-safe attempt allows manual retry only", () => {
  const decision = isRetryAllowed(
    { status: "BLOCKED" },
    { content_started: 0, retry_class: "MANUAL_SAFE" }
  );
  assert.equal(decision.allowed, true);
  assert.equal(decision.automatic, false);
  assert.equal(decision.retry_class, "MANUAL_SAFE");
});

test("terminal or non-retryable states deny retry", () => {
  for (const status of [
    "CREATED",
    "RESERVED",
    "PRINTING",
    "SUCCEEDED",
    "CANCELLED",
  ]) {
    const decision = isRetryAllowed(
      { status },
      { content_started: 0, retry_class: "AUTO_SAFE" }
    );
    assert.equal(decision.allowed, false, status);
  }
});
