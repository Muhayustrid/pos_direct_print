import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ERROR_CATEGORIES,
  ERROR_CODES,
  RETRY_CLASSES,
  makeError,
  PrintDomainError,
} from "../errors.mjs";
import { classifyRetry, normalize, toUserError } from "../error_normalizer.mjs";

test("canonical codes map onto the frozen category vocabulary", () => {
  for (const [code, category] of Object.entries(ERROR_CODES)) {
    assert.ok(code.startsWith("PDP_"), `${code} must carry the PDP prefix`);
    assert.ok(
      ERROR_CATEGORIES.includes(category),
      `${code} -> ${category} must be canonical`
    );
  }
});

test("PrintDomainError serializes without the raw cause", () => {
  const raw = new TypeError("boom from an SDK");
  const domainError = makeError("PDP_PRINT_COMMAND_FAILED", {
    cause: raw,
    phase: "PRINT",
  });
  const serialized = JSON.parse(JSON.stringify(domainError));

  assert.equal(serialized.code, "PDP_PRINT_COMMAND_FAILED");
  assert.equal(serialized.phase, "PRINT");
  assert.equal(serialized.category, "PRINTER");
  assert.ok(
    !("cause" in serialized),
    "raw cause must never serialize to the POS-facing shape"
  );
  assert.ok(!serialized.technical_message?.includes("boom from an SDK"));
});

test("normalize converts a raw exception into a canonical domain error", () => {
  // A-AT-15: a fake driver throwing a generic runtime exception must surface
  // as a canonical PrintDomainError, never the raw stack.
  const raw = new Error("bridge socket closed unexpectedly");
  const normalized = normalize(raw, "PRINT", { content_started: true });

  assert.ok(normalized instanceof PrintDomainError);
  assert.equal(normalized.code, "PDP_INTERNAL_ERROR");
  assert.equal(normalized.phase, "PRINT");
  assert.equal(normalized.content_may_have_printed, true);
  assert.equal(normalized.cause, raw, "cause stays opaque for diagnostics");
});

test("normalize preserves an already-canonical PDP code", () => {
  const raw = new Error("PDP_TERMINAL_DISABLED: terminal TERM-1 is disabled");
  const normalized = normalize(raw, "RESERVATION", {});
  assert.equal(normalized.code, "PDP_TERMINAL_DISABLED");
  assert.equal(normalized.category, "TERMINAL");
});

test("normalize maps Frappe PermissionError to the permission code", () => {
  const raw = { exc_type: "PermissionError", message: "Not permitted" };
  const normalized = normalize(raw, "RESERVATION", {});
  assert.equal(normalized.code, "PDP_PERMISSION_DENIED");
  assert.equal(normalized.category, "PERMISSION");
});

test("content-risk absolute rule blocks AUTO_SAFE and MANUAL_SAFE", () => {
  // A-AT-12: once content may have printed, retry is REPRINT_ONLY or NONE.
  for (const retry_class of RETRY_CLASSES) {
    const domainError = makeError("PDP_PRINT_COMMAND_FAILED", {
      retry_class,
      content_may_have_printed: true,
    });
    const classified = classifyRetry(domainError, { content_started: true });
    assert.ok(
      ["REPRINT_ONLY", "NONE"].includes(classified),
      `got ${classified}`
    );
  }
});

test("content started but unproven complete classifies REPRINT_ONLY", () => {
  const domainError = makeError("PDP_PRINT_TIMEOUT", {
    content_may_have_printed: true,
  });
  assert.equal(
    classifyRetry(domainError, { content_started: true }),
    "REPRINT_ONLY"
  );
});

test("content completed classifies NONE even under content risk", () => {
  const domainError = makeError("PDP_PRINT_COMMAND_FAILED", {
    content_may_have_printed: true,
  });
  assert.equal(
    classifyRetry(domainError, {
      content_started: true,
      content_completed: true,
    }),
    "NONE"
  );
});

test("pre-output failures in recoverable categories may auto-retry", () => {
  const domainError = makeError("PDP_PRINTER_NOT_READY", {
    content_may_have_printed: false,
  });
  assert.equal(
    classifyRetry(domainError, { content_started: false }),
    "AUTO_SAFE"
  );
});

test("configuration and validation errors never auto-retry", () => {
  for (const code of ["PDP_CONFIG_INVALID", "PDP_RECEIPT_INVALID"]) {
    const domainError = makeError(code);
    assert.equal(classifyRetry(domainError, {}), "NONE");
  }
});

test("toUserError exposes keys and actions without a stack trace", () => {
  const raw = new Error("very secret internal detail");
  const domainError = normalize(raw, "PRINT", {});
  const userError = toUserError(domainError);

  assert.ok(userError.title_key);
  assert.ok(Array.isArray(userError.allowed_actions));
  assert.ok(userError.allowed_actions.includes("dismiss"));
  const dump = JSON.stringify(userError);
  assert.ok(!dump.includes("secret internal detail"), "no internal text leaks");
  assert.ok(!dump.includes("at "), "no stack frames leak");
});
