/**
 * ReceiptBuilder (A.12.9) — ERPNext invoice snapshot -> canonical
 * ReceiptDocument (A.10.3). Must not know iMin (A-DOD-10). Also owns the
 * deterministic receipt hash (A-DOD-14 / A-AT-18).
 */

import { makeError } from "../core/errors.mjs";
import { DEFAULT_PAPER_PROFILE, layout } from "./receipt_layout.mjs";
import {
  RECEIPT_SCHEMA_VERSION,
  assertValidReceipt,
  validateReceipt,
} from "./receipt_document.mjs";

export class ReceiptBuilder {
  /**
   * @param {object} options
   * @param {string} options.default_locale locale recorded when the snapshot
   *   carries none (explicit, never the browser's implicit locale)
   * @param {string} options.default_currency fallback currency
   */
  constructor(options = {}) {
    this.default_locale = options.default_locale || "id-ID";
    this.default_currency = options.default_currency || "IDR";
  }

  /**
   * @param {object} snapshot normalized invoice snapshot
   * @param {object} context { paper_profile, locale, currency } overrides
   * @returns {object} validated ReceiptDocument
   */
  build(snapshot, context = {}) {
    if (!snapshot || typeof snapshot !== "object") {
      throw makeError("PDP_RECEIPT_INVALID", {
        phase: "RECEIPT",
        metadata: { reason: "invoice snapshot is required" },
      });
    }
    try {
      const currency =
        snapshot.currency || context.currency || this.default_currency;
      const locale = snapshot.locale || context.locale || this.default_locale;
      const paper_profile =
        context.paper_profile ||
        snapshot.paper_profile ||
        DEFAULT_PAPER_PROFILE;

      const document = {
        schema_version: RECEIPT_SCHEMA_VERSION,
        reference_doctype:
          snapshot.doctype || snapshot.reference_doctype || null,
        reference_name: snapshot.name || snapshot.reference_name || null,
        locale,
        currency,
        paper_profile,
        blocks: layout(
          this._view_model(snapshot, currency, locale),
          paper_profile
        ),
        metadata: {
          built_by: "pos_direct_print.receipt_builder",
          schema: RECEIPT_SCHEMA_VERSION,
        },
      };
      return assertValidReceipt(document);
    } catch (error) {
      if (error && error.code && String(error.code).startsWith("PDP_")) {
        throw error;
      }
      throw makeError("PDP_RECEIPT_BUILD_FAILED", {
        phase: "RECEIPT",
        metadata: { reason: String(error && error.message) },
      });
    }
  }

  validate(document) {
    return validateReceipt(document);
  }

  /**
   * Deterministic hash: identical semantic content + same schema yields the
   * identical hash; any material field change changes it (A-AT-18).
   */
  hash(document) {
    return hashReceipt(document);
  }

  _view_model(snapshot, currency, locale) {
    const items = Array.isArray(snapshot.items) ? snapshot.items : [];
    return {
      currency,
      locale,
      title_lines: [snapshot.company || snapshot.pos_profile || "POS RECEIPT"],
      info_lines: [
        snapshot.name ? `No: ${snapshot.name}` : null,
        snapshot.posting_date ? `Date: ${snapshot.posting_date}` : null,
        snapshot.customer ? `Customer: ${snapshot.customer}` : null,
      ].filter(Boolean),
      items: items.map((item) => ({
        item_name: item.item_name || item.item_code || "item",
        quantity: item.qty ?? 1,
        amount: item.amount ?? item.rate ?? 0,
      })),
      totals_lines: [
        snapshot.discount_amount
          ? { label: "Discount", amount: -snapshot.discount_amount }
          : null,
        { label: "TOTAL", amount: snapshot.grand_total ?? 0 },
      ].filter(Boolean),
      footer_lines: ["Thank you"],
    };
  }
}

/**
 * Canonical JSON: object keys sorted at every depth, arrays keep order
 * (receipt blocks are ordered), undefined omitted, numbers/strings/booleans
 * via JSON semantics. Same semantic input -> same string.
 */
export function canonicalize(value) {
  return JSON.stringify(_sorted(value));
}

function _sorted(value) {
  if (Array.isArray(value)) {
    return value.map(_sorted);
  }
  if (value && typeof value === "object") {
    const out = {};
    for (const key of Object.keys(value).sort()) {
      if (value[key] !== undefined) {
        out[key] = _sorted(value[key]);
      }
    }
    return out;
  }
  return value;
}

/**
 * FNV-1a over the canonical string — pure, deterministic, dependency-free.
 * Milestone A needs equality/sensitivity, not cryptographic strength; the
 * server-side hash (if added later) is a separate contract.
 */
export function hashReceipt(document) {
  assertValidReceipt(document);
  const canonical = canonicalize(document);
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < canonical.length; i += 1) {
    const byte = canonical.charCodeAt(i) & 0xff;
    h1 ^= byte;
    h1 = Math.imul(h1, 0x01000193) >>> 0;
    h2 =
      Math.imul(h2 ^ ((canonical.charCodeAt(i) >> 8) & 0xff), 0x01000193) >>> 0;
  }
  return `pdpr1:${h1.toString(16).padStart(8, "0")}${h2
    .toString(16)
    .padStart(8, "0")}`;
}
