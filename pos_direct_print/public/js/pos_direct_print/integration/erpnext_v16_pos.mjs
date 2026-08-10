/**
 * ERPNext v16 POS integration adapter (A.12.2).
 *
 * The ONLY module allowed to know ERPNext POS runtime structure. It
 * intercepts `erpnext.PointOfSale.PastOrderSummary.prototype.print_receipt`,
 * preserves the original method, and is the single boundary back to original
 * browser print behavior.
 */

import { makeError } from "../core/errors.mjs";

export const POS_INVOICE_DOCTYPE = "POS Invoice";
export const SALES_INVOICE_DOCTYPE = "Sales Invoice";
export const ALLOWED_SOURCE_DOCTYPES = Object.freeze([
  POS_INVOICE_DOCTYPE,
  SALES_INVOICE_DOCTYPE,
]);

export class POSIntegrationAdapter {
  /**
   * @param {object} options
   * @param {Function} options.get_settings returns the runtime settings
   *   projection ({ enabled, allow_browser_fallback, ... }). Injectable so
   *   tests never need a live server.
   */
  constructor(options = {}) {
    this.get_settings = options.get_settings || (() => ({ enabled: true }));
    this.override_handle = null;
  }

  /**
   * @param {object} context runtime POS context; accepts either the
   *   PastOrderSummary prototype directly or a shape exposing it.
   */
  isSupported(context) {
    const prototype = _prototypeFrom(context);
    return Boolean(prototype && typeof prototype.print_receipt === "function");
  }

  /**
   * Patch exactly once. Calling install again returns the existing handle
   * without touching the prototype — this is what keeps repeated subsystem
   * initialization from stacking overrides (A-DOD-03).
   */
  installOverride(print_manager, pos_context) {
    if (!print_manager || typeof print_manager.requestPrint !== "function") {
      throw makeError("PDP_CONFIG_INVALID", {
        metadata: { reason: "print_manager.requestPrint is required" },
      });
    }

    const prototype = _prototypeFrom(pos_context);
    if (!this.isSupported(prototype)) {
      throw makeError("PDP_CONFIG_INVALID", {
        metadata: { reason: "print_receipt not found on POS prototype" },
      });
    }

    if (this.override_handle) {
      return this.override_handle;
    }

    const original_method = prototype.print_receipt;
    const adapter = this;

    prototype.print_receipt = function intercepted_print_receipt(...args) {
      const settings = adapter._settings();
      if (!settings.enabled) {
        // A-AT-06: disabled feature behaves exactly like baseline ERPNext.
        return adapter.invokeOriginalPrint(original_method, this, args);
      }

      const request = adapter.buildPrintRequest(this, args, "POS_AUTO");
      return print_manager
        .requestPrint(request, adapter._requestContext(this))
        .then((outcome) =>
          adapter._settleOutcome(outcome, original_method, this, args)
        );
    };

    this.override_handle = { prototype, original_method, installed: true };
    return this.override_handle;
  }

  restoreOverride(handle) {
    const target = handle || this.override_handle;
    if (!target || !target.installed) {
      return false;
    }
    target.prototype.print_receipt = target.original_method;
    target.installed = false;
    this.override_handle = null;
    return true;
  }

  /**
   * Runtime PastOrderSummary context -> canonical PrintRequest (A.10.1).
   * Never carries raw printer commands.
   */
  buildPrintRequest(summary, invocation_args, trigger_source) {
    const doc = summary?.frm?.doc || summary?.doc;
    if (!doc || !doc.name) {
      throw makeError("PDP_RECEIPT_INVALID", {
        phase: "RECEIPT",
        metadata: { reason: "no invoice document in POS context" },
      });
    }
    const reference_doctype = doc.doctype;
    if (!ALLOWED_SOURCE_DOCTYPES.includes(reference_doctype)) {
      throw makeError("PDP_RECEIPT_INVALID", {
        phase: "RECEIPT",
        metadata: { doctype: reference_doctype },
      });
    }

    const terminal_id =
      summary?.terminal_id || summary?.pos_direct_print_terminal_id;
    if (!terminal_id) {
      throw makeError("PDP_TERMINAL_NOT_FOUND", {
        phase: "RESERVATION",
        metadata: { reason: "no terminal bound to POS context" },
      });
    }

    return {
      reference_doctype,
      reference_name: doc.name,
      terminal_id,
      source: trigger_source,
      job_type: "ORIGINAL",
      requested_by: doc.owner || null,
      driver_key: null,
      parent_job_id: null,
      reprint_reason: null,
      options: {
        invocation_args: Array.isArray(invocation_args)
          ? invocation_args.length
          : 0,
      },
    };
  }

  /**
   * The ONLY approved path back to original ERPNext print behavior —
   * browser handoff, never proof of physical print.
   */
  invokeOriginalPrint(original_method, summary, invocation_args) {
    if (typeof original_method !== "function") {
      throw makeError("PDP_INTERNAL_ERROR", {
        metadata: { reason: "original print method unavailable" },
      });
    }
    const result = original_method.apply(summary, invocation_args || []);
    return Promise.resolve(result).then((value) => ({
      handed_off: true,
      original_result: value,
    }));
  }

  _settings() {
    try {
      return this.get_settings() || { enabled: true };
    } catch {
      // Settings failure must not strand the cashier: fall back to the
      // baseline behavior by treating the feature as disabled.
      return { enabled: false };
    }
  }

  _requestContext(summary) {
    return {
      invoice_snapshot: summary?.frm?.doc || summary?.doc || null,
      idempotency_key: summary?.pos_direct_print_idempotency_key || null,
      reservation_owner: summary?.paired_client_id || null,
    };
  }

  _settleOutcome(outcome, original_method, summary, args) {
    // Browser handoff is allowed only while physical content cannot have
    // been printed (constitution). Milestone A surfaces outcomes to the
    // caller; the original path stays the fallback boundary.
    if (outcome && outcome.fallback_used) {
      return this.invokeOriginalPrint(original_method, summary, args);
    }
    return outcome;
  }
}

function _prototypeFrom(context) {
  if (!context) {
    return null;
  }
  // Accept the prototype directly, or a runtime shape exposing it.
  if (typeof context.print_receipt === "function") {
    return context;
  }
  return context.prototype || context.PastOrderSummary || null;
}
