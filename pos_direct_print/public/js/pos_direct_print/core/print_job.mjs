/**
 * Pure domain state machine for the client (plan.md section 6/7).
 *
 * Mirrors the server table exactly — the server validator remains the final
 * authority; this module lets the client fail fast before spending a request
 * on a transition the server would reject. No printer SDK calls may live here.
 */

import { makeError } from "./errors.mjs";

export const STATES = Object.freeze([
  "CREATED",
  "RESERVED",
  "PREFLIGHT",
  "BLOCKED",
  "PRINTING",
  "VERIFYING",
  "FAILED_SAFE",
  "UNCERTAIN",
  "SUCCEEDED",
  "FALLBACK_BROWSER",
  "CANCELLED",
]);

export const TERMINAL_STATES = Object.freeze([
  "UNCERTAIN",
  "SUCCEEDED",
  "FALLBACK_BROWSER",
  "CANCELLED",
]);

// plan.md section 6 — complete transition table. Anything absent is invalid.
const TRANSITION_PAIRS = [
  ["CREATED", "RESERVED"],
  ["CREATED", "CANCELLED"],
  ["CREATED", "FAILED_SAFE"],
  ["RESERVED", "PREFLIGHT"],
  ["RESERVED", "FAILED_SAFE"],
  ["RESERVED", "CANCELLED"],
  ["PREFLIGHT", "PRINTING"],
  ["PREFLIGHT", "BLOCKED"],
  ["PREFLIGHT", "FAILED_SAFE"],
  ["PREFLIGHT", "FALLBACK_BROWSER"],
  ["PREFLIGHT", "CANCELLED"],
  ["BLOCKED", "PREFLIGHT"],
  ["BLOCKED", "FALLBACK_BROWSER"],
  ["BLOCKED", "CANCELLED"],
  ["BLOCKED", "FAILED_SAFE"],
  ["FAILED_SAFE", "RESERVED"],
  ["FAILED_SAFE", "FALLBACK_BROWSER"],
  ["FAILED_SAFE", "CANCELLED"],
  ["PRINTING", "VERIFYING"],
  ["PRINTING", "UNCERTAIN"],
  ["VERIFYING", "SUCCEEDED"],
  ["VERIFYING", "UNCERTAIN"],
];

export const VALID_TRANSITIONS = new Set(
  TRANSITION_PAIRS.map(([from, to]) => `${from}->${to}`)
);

// plan.md section 7 retry matrix — only FAILED_SAFE allows a same-job retry.
const RETRYABLE_STATES = new Set(["FAILED_SAFE", "BLOCKED"]);

export function canTransition(current_state, target_state) {
  return VALID_TRANSITIONS.has(`${current_state}->${target_state}`);
}

export function assertTransition(current_state, target_state) {
  const valid = canTransition(current_state, target_state);
  if (!valid) {
    throw makeError("PDP_JOB_INVALID_TRANSITION", {
      phase: "RESERVATION",
      metadata: { current_state, target_state },
    });
  }
  return { valid: true, from: current_state, to: target_state };
}

export function isTerminalState(state) {
  return TERMINAL_STATES.includes(state);
}

/**
 * Retry decision per the retry matrix plus the conservative content-risk rule.
 * A-DOD-08: once content may have printed, a same-job retry is never allowed —
 * the only continuation is a new REPRINT Job.
 */
export function isRetryAllowed(
  job_snapshot,
  latest_attempt,
  domain_error = null
) {
  const content_may_have_printed = deriveContentRisk(latest_attempt);

  if (content_may_have_printed) {
    return {
      allowed: false,
      retry_class: latest_attempt?.content_completed ? "NONE" : "REPRINT_ONLY",
      automatic: false,
      reason: "content_may_have_printed",
    };
  }

  if (!job_snapshot || !RETRYABLE_STATES.has(job_snapshot.status)) {
    return {
      allowed: false,
      retry_class: "NONE",
      automatic: false,
      reason: "PDP_JOB_INVALID_TRANSITION",
    };
  }

  const attempt_retry_class = latest_attempt?.retry_class || "NONE";
  if (attempt_retry_class === "NONE") {
    return {
      allowed: false,
      retry_class: "NONE",
      automatic: false,
      reason: "retry_class_none",
    };
  }

  const retry_class =
    domain_error?.retry_class && domain_error.retry_class !== "NONE"
      ? domain_error.retry_class
      : attempt_retry_class;

  return {
    allowed: true,
    retry_class,
    automatic: retry_class === "AUTO_SAFE",
    reason: null,
  };
}

export function deriveContentRisk(latest_attempt) {
  return Boolean(latest_attempt?.content_started);
}
