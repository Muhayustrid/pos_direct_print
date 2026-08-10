/**
 * ReceiptDocument schema (A.10.3) — canonical intermediate representation.
 *
 * Milestone A locks the schema only: top-level fields and allowed block
 * categories. A ReceiptDocument must be deterministically serializable and
 * may never carry functions, DOM nodes, printer objects, or raw SDK
 * references (A-DOD-10/14).
 */

import { makeError } from "../core/errors.mjs";

export const RECEIPT_SCHEMA_VERSION = 1;

export const BLOCK_CATEGORIES_V1 = Object.freeze([
  "TEXT",
  "SEPARATOR",
  "COLUMNS",
  "SPACER",
  "IMAGE",
  "QR",
  "FEED",
  "CUT",
]);

const REQUIRED_TOP_FIELDS = Object.freeze([
  "schema_version",
  "reference_doctype",
  "reference_name",
  "locale",
  "currency",
  "paper_profile",
  "blocks",
  "metadata",
]);

/**
 * Structural validation of a ReceiptDocument against schema v1.
 * Returns { valid, errors } — the builder turns errors into
 * PDP_RECEIPT_INVALID.
 */
export function validateReceipt(doc) {
  const errors = [];
  if (!doc || typeof doc !== "object" || Array.isArray(doc)) {
    return { valid: false, errors: ["receipt document must be an object"] };
  }
  for (const field of REQUIRED_TOP_FIELDS) {
    if (!(field in doc)) {
      errors.push(`missing required field: ${field}`);
    }
  }
  if (doc.schema_version !== RECEIPT_SCHEMA_VERSION) {
    errors.push(`unsupported schema_version: ${doc.schema_version}`);
  }
  if (doc.blocks !== undefined) {
    if (!Array.isArray(doc.blocks)) {
      errors.push("blocks must be an ordered array");
    } else {
      doc.blocks.forEach((block, index) => {
        if (!block || typeof block !== "object") {
          errors.push(`block[${index}] must be an object`);
          return;
        }
        if (!BLOCK_CATEGORIES_V1.includes(block.type)) {
          errors.push(`block[${index}] has unknown category: ${block.type}`);
        }
      });
    }
  }
  if (doc.metadata !== undefined) {
    if (!doc.metadata || typeof doc.metadata !== "object") {
      errors.push("metadata must be an object");
    } else {
      scanForNonSerializable(doc.metadata, "metadata", errors);
    }
  }
  if (Array.isArray(doc.blocks)) {
    scanForNonSerializable(doc.blocks, "blocks", errors);
  }
  return { valid: errors.length === 0, errors };
}

export function assertValidReceipt(doc) {
  const { valid, errors } = validateReceipt(doc);
  if (!valid) {
    throw makeError("PDP_RECEIPT_INVALID", {
      phase: "RECEIPT",
      metadata: { errors },
    });
  }
  return doc;
}

/**
 * Walk a value tree and report anything that cannot be serialized: functions,
 * symbols, DOM/printer objects (anything exposing live handles is caught by
 * the function check at the boundary). Milestone A keeps this conservative.
 */
function scanForNonSerializable(value, path, errors) {
  const kind = typeof value;
  if (kind === "function" || kind === "symbol") {
    errors.push(`non-serializable ${kind} at ${path}`);
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, i) =>
      scanForNonSerializable(item, `${path}[${i}]`, errors)
    );
    return;
  }
  if (value && kind === "object") {
    for (const key of Object.keys(value)) {
      scanForNonSerializable(value[key], `${path}.${key}`, errors);
    }
  }
}
