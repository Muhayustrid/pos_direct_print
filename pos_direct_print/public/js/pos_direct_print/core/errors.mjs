/**
 * Canonical error contract (A.11) and foundation error codes (A.11.3).
 *
 * The error format is frozen unless Open Decision A-OD-03 changes it. Every
 * module emits PrintDomainError upward; raw SDK/browser/server errors never
 * reach the POS UI.
 */

export const ERROR_CATEGORIES = Object.freeze([
  "CONFIGURATION",
  "VALIDATION",
  "CONCURRENCY",
  "TERMINAL",
  "BRIDGE",
  "PRINTER",
  "RECEIPT",
  "NETWORK",
  "PERMISSION",
  "INTERNAL",
]);

// Canonical lifecycle phases — same vocabulary as POS Print Attempt.phase_reached.
export const PHASES = Object.freeze([
  "RESERVATION",
  "RECEIPT",
  "PREFLIGHT",
  "PRINT",
  "VERIFY",
  "FALLBACK",
]);

export const RETRY_CLASSES = Object.freeze([
  "NONE",
  "AUTO_SAFE",
  "MANUAL_SAFE",
  "REPRINT_ONLY",
]);

export const ERROR_CODES = Object.freeze({
  // Configuration
  PDP_CONFIG_DISABLED: "CONFIGURATION",
  PDP_CONFIG_INVALID: "CONFIGURATION",

  // Terminal
  PDP_TERMINAL_NOT_FOUND: "TERMINAL",
  PDP_TERMINAL_DISABLED: "TERMINAL",
  PDP_TERMINAL_NOT_PAIRED: "TERMINAL",
  PDP_TERMINAL_NOT_QUALIFIED: "TERMINAL",

  // Job
  PDP_JOB_NOT_FOUND: "CONCURRENCY",
  PDP_JOB_CONFLICT: "CONCURRENCY",
  PDP_JOB_ALREADY_TERMINAL: "CONCURRENCY",
  PDP_JOB_INVALID_TRANSITION: "CONCURRENCY",
  PDP_JOB_RESERVATION_EXPIRED: "CONCURRENCY",
  PDP_JOB_RESERVATION_MISMATCH: "CONCURRENCY",

  // Receipt
  PDP_RECEIPT_BUILD_FAILED: "RECEIPT",
  PDP_RECEIPT_INVALID: "RECEIPT",

  // Driver
  PDP_DRIVER_NOT_FOUND: "BRIDGE",
  PDP_DRIVER_UNAVAILABLE: "BRIDGE",
  PDP_DRIVER_CAPABILITY_UNSUPPORTED: "BRIDGE",

  // Runtime printer classes (reserved now, populated from Milestone B)
  PDP_BRIDGE_UNAVAILABLE: "BRIDGE",
  PDP_PRINTER_NOT_READY: "PRINTER",
  PDP_PRINTER_PAPER_OUT: "PRINTER",
  PDP_PRINTER_COVER_OPEN: "PRINTER",
  PDP_PRINTER_OVERHEATED: "PRINTER",
  PDP_PRINTER_CUTTER_ERROR: "PRINTER",
  PDP_PRINT_COMMAND_FAILED: "PRINTER",
  PDP_PRINT_TIMEOUT: "PRINTER",
  PDP_PRINT_STATUS_UNKNOWN: "PRINTER",

  // Server
  PDP_SERVER_UNAVAILABLE: "NETWORK",
  PDP_PERMISSION_DENIED: "PERMISSION",
  PDP_INTERNAL_ERROR: "INTERNAL",
});

export class PrintDomainError extends Error {
  constructor(fields) {
    super(fields.code);
    this.name = "PrintDomainError";
    this.code = fields.code;
    this.category = fields.category || ERROR_CODES[fields.code] || "INTERNAL";
    this.phase = fields.phase || "RESERVATION";
    this.retry_class = fields.retry_class || "NONE";
    this.content_may_have_printed = Boolean(fields.content_may_have_printed);
    this.user_message_key =
      fields.user_message_key || `error.${fields.code.toLowerCase()}`;
    this.technical_message = fields.technical_message || null;
    this.cause = fields.cause !== undefined ? fields.cause : null;
    this.metadata = fields.metadata || {};
  }

  toJSON() {
    // `cause` stays opaque — it must never serialize into the POS-facing shape.
    return {
      code: this.code,
      category: this.category,
      phase: this.phase,
      retry_class: this.retry_class,
      content_may_have_printed: this.content_may_have_printed,
      user_message_key: this.user_message_key,
      technical_message: this.technical_message,
      metadata: this.metadata,
    };
  }
}

export function makeError(code, fields = {}) {
  return new PrintDomainError({ code, ...fields });
}

export function isPrintDomainError(value) {
  return value instanceof PrintDomainError;
}
