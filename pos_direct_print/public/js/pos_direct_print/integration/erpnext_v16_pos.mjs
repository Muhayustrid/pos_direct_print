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
    this.resolve_terminal_context =
      options.resolve_terminal_context ||
      this._defaultResolveTerminalContext.bind(this);
    // Per-session terminal resolution cache, keyed company|pos_profile.
    this._terminal_cache = new Map();
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
      if (this.override_handle.prototype === prototype) {
        return this.override_handle;
      }
      this.restoreOverride();
    }

    const original_method = prototype.print_receipt;
    const adapter = this;

    prototype.print_receipt = function intercepted_print_receipt(...args) {
      const settings = adapter._settings();
      if (!settings.enabled) {
        // A-AT-06: disabled feature behaves exactly like baseline ERPNext.
        return adapter.invokeOriginalPrint(original_method, this, args);
      }

      return Promise.resolve()
        .then(() => adapter.resolve_context(this))
        .then((ctx) => Object.assign(this, ctx))
        .then(() =>
          print_manager.requestPrint(
            adapter.buildPrintRequest(this, args, "POS_AUTO"),
            adapter._requestContext(this)
          )
        )
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
      driver_key: summary?.pos_direct_print_driver_key || null,
      parent_job_id: null,
      reprint_reason: null,
      options: {
        invocation_args: Array.isArray(invocation_args)
          ? invocation_args.length
          : 0,
        transport: summary?.pos_direct_print_transport || null,
        paper_profile:
          summary?.pos_direct_print_paper_width_mm === "58"
            ? "reference_58mm"
            : null,
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

  /**
   * Resolve the terminal + idempotency context for a POS summary (B4-01).
   * Returns { pos_direct_print_terminal_id, pos_direct_print_transport,
   * pos_direct_print_driver_key, pos_direct_print_paper_width_mm,
   * pos_direct_print_idempotency_key, paired_client_id }. Only terminal-scoped
   * data is cached per session keyed company|pos_profile; the idempotency key
   * is always computed per invoice so a different receipt on the same terminal
   * gets its own key and can never leak across invoices.
   */
  async resolve_context(summary) {
    const settings = this._settings();
    const doc = summary?.frm?.doc || summary?.doc;
    const cache_key =
      doc?.company && doc?.pos_profile
        ? `${doc.company}|${doc.pos_profile}`
        : null;

    // The cache holds TERMINAL-scoped data only (terminal_id, transport,
    // driver_key, paper_width_mm) — nothing invoice-specific. The idempotency
    // key is derived per invoice below and is never cached or trusted from the
    // resolver, so a second invoice on the same Company + POS Profile can never
    // inherit invoice A's key.
    let terminal;
    if (cache_key && this._terminal_cache.has(cache_key)) {
      terminal = this._terminal_cache.get(cache_key);
    } else {
      const resolved = await this.resolve_terminal_context(summary, settings);
      terminal = {
        pos_direct_print_terminal_id: resolved.pos_direct_print_terminal_id,
        pos_direct_print_transport: resolved.pos_direct_print_transport,
        pos_direct_print_driver_key: resolved.pos_direct_print_driver_key,
        pos_direct_print_paper_width_mm:
          resolved.pos_direct_print_paper_width_mm,
      };
      if (cache_key) {
        this._terminal_cache.set(cache_key, terminal);
      }
    }

    if (!terminal.pos_direct_print_terminal_id) {
      throw makeError("PDP_TERMINAL_NOT_FOUND", {
        phase: "RESERVATION",
        metadata: { reason: "terminal resolver returned no terminal" },
      });
    }

    return {
      pos_direct_print_terminal_id: terminal.pos_direct_print_terminal_id,
      pos_direct_print_transport: terminal.pos_direct_print_transport || null,
      pos_direct_print_driver_key: terminal.pos_direct_print_driver_key || null,
      pos_direct_print_paper_width_mm:
        terminal.pos_direct_print_paper_width_mm || null,
      pos_direct_print_idempotency_key: this._defaultIdempotencyKey(
        summary,
        settings,
        terminal
      ),
      paired_client_id: this._pairedClientId(),
    };
  }

  /**
   * Default terminal resolver: ask the server which enabled QUALIFIED terminal
   * serves that Company + POS Profile. No hardcoded terminal anywhere.
   */
  async _defaultResolveTerminalContext(summary, settings) {
    const doc = summary?.frm?.doc || summary?.doc;
    const pos_profile = doc?.pos_profile;
    const company = doc?.company;
    if (!pos_profile || !company) {
      throw makeError("PDP_TERMINAL_NOT_FOUND", {
        phase: "RESERVATION",
        metadata: { reason: "invoice snapshot lacks pos_profile/company" },
      });
    }
    const api = this._print_api;
    if (!api) {
      throw makeError("PDP_SERVER_UNAVAILABLE", {
        phase: "RESERVATION",
        metadata: { reason: "print api not wired to adapter" },
      });
    }
    const projection = await api.resolveTerminalForProfile(
      company,
      pos_profile
    );
    return {
      pos_direct_print_terminal_id: projection.terminal_id,
      pos_direct_print_transport: projection.transport,
      pos_direct_print_driver_key: projection.driver_key,
      pos_direct_print_paper_width_mm: projection.paper_width_mm,
    };
  }

  _defaultIdempotencyKey(summary, settings, resolved) {
    const doc = summary?.frm?.doc || summary?.doc;
    return computeIdempotencyKey({
      schema_version: settings.receipt_schema_version || 1,
      reference_doctype: doc?.doctype,
      reference_name: doc?.name,
      terminal_id: resolved.pos_direct_print_terminal_id,
      job_type: "ORIGINAL",
    });
  }

  /**
   * Browser-stable client identity: persisted once per browser installation.
   */
  _pairedClientId() {
    if (typeof localStorage === "undefined") {
      return "unpaired-local-storage";
    }
    let id = localStorage.getItem("pos_direct_print_paired_client_id");
    if (!id) {
      id = `pdp-${Math.random().toString(36).slice(2)}-${Date.now().toString(
        36
      )}`;
      localStorage.setItem("pos_direct_print_paired_client_id", id);
    }
    return id;
  }

  /**
   * Wire the transport so the default resolver can reach the server.
   */
  _setPrintApi(api) {
    this._print_api = api;
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

/**
 * Deterministic ORIGINAL idempotency key (plan.md §8): FNV-1a over the
 * semantic components joined with "|", no timestamp. The same logical intent
 * always yields the same key; a different invoice, terminal, or purpose
 * changes it. Reuses the pdpr1: FNV lane from receipt_builder.
 */
export function computeIdempotencyKey({
  schema_version,
  reference_doctype,
  reference_name,
  terminal_id,
  job_type,
  purpose = "ORIGINAL_PRINT",
}) {
  const canonical = [
    String(schema_version),
    String(reference_doctype),
    String(reference_name),
    String(terminal_id),
    String(job_type),
    String(purpose),
  ].join("|");

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
