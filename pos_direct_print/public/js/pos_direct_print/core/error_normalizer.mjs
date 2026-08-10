/**
 * Error normalizer (A.12.8).
 *
 * Every raw SDK/browser/server failure crossing into the print subsystem is
 * converted into a canonical PrintDomainError before it reaches the POS UI
 * (A-DOD-11). The content-risk absolute rule (A-DOD-08) lives here: once
 * content may have printed, the retry class can never be AUTO_SAFE or
 * MANUAL_SAFE.
 */

import {
  ERROR_CODES,
  RETRY_CLASSES,
  makeError,
  PrintDomainError,
} from "./errors.mjs";

const PDP_CODE_PATTERN = /(PDP_[A-Z0-9_]+)/;

// Categories whose pre-output failures may resolve themselves (printer,
// bridge, network). Safe to auto-retry while content has not started.
const AUTO_SAFE_CATEGORIES = new Set([
  "TERMINAL",
  "BRIDGE",
  "PRINTER",
  "NETWORK",
]);

export function normalize(rawError, phase, context = {}) {
  const content_started = Boolean(context.content_started);

  if (rawError instanceof PrintDomainError) {
    // Re-stamp lifecycle context onto an already-canonical error.
    if (
      rawError.phase === phase &&
      rawError.content_may_have_printed === content_started
    ) {
      return rawError;
    }
    return new PrintDomainError({
      ...rawError.toJSON(),
      phase,
      content_may_have_printed: content_started,
      cause: rawError.cause,
    });
  }

  const code = _extractCode(rawError);
  const category = ERROR_CODES[code] || "INTERNAL";

  return makeError(code, {
    category,
    phase,
    content_may_have_printed: content_started,
    technical_message: _safeMessage(rawError),
    cause: rawError,
  });
}

export function classifyRetry(domainError, attemptContext = {}) {
  const content_started =
    domainError.content_may_have_printed ||
    Boolean(attemptContext.content_started);

  // Absolute rule (A.11.2 normalizer contract): once output may exist, a
  // same-job retry can never be safe.
  if (content_started) {
    const completed = Boolean(
      attemptContext.content_completed ||
        domainError.metadata?.content_completed
    );
    return completed ? "NONE" : "REPRINT_ONLY";
  }

  if (!AUTO_SAFE_CATEGORIES.has(domainError.category)) {
    return "NONE";
  }
  return "AUTO_SAFE";
}

export function toUserError(domainError) {
  const allowed_actions = [];
  if (
    domainError.retry_class === "AUTO_SAFE" ||
    domainError.retry_class === "MANUAL_SAFE"
  ) {
    allowed_actions.push("retry");
  }
  if (domainError.retry_class === "REPRINT_ONLY") {
    allowed_actions.push("reprint");
  }
  allowed_actions.push("dismiss");

  // No stack trace, no cause chain — only message keys and actions.
  return {
    title_key: domainError.user_message_key,
    message_key: domainError.user_message_key,
    code: domainError.code,
    allowed_actions,
  };
}

function _extractCode(rawError) {
  const message = _safeMessage(rawError);
  if (message) {
    const match = message.match(PDP_CODE_PATTERN);
    if (match && ERROR_CODES[match[1]]) {
      return match[1];
    }
  }
  if (typeof rawError === "object" && rawError !== null) {
    // Server-side Frappe exceptions carry exc/_server_messages; extract a
    // canonical code when present, otherwise fall back to INTERNAL.
    const nested =
      rawError.exc_type === "PermissionError" ? "PDP_PERMISSION_DENIED" : null;
    if (nested) {
      return nested;
    }
  }
  return "PDP_INTERNAL_ERROR";
}

function _safeMessage(rawError) {
  if (rawError == null) {
    return null;
  }
  if (typeof rawError === "string") {
    return rawError;
  }
  if (typeof rawError.message === "string" && rawError.message) {
    return rawError.message;
  }
  return null;
}
