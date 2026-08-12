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

/**
 * Settled states where a physical copy may already exist, so another copy is
 * legal only as a REPRINT. FAILED_SAFE is deliberately absent: nothing was
 * printed, so the cashier may simply print again.
 */
const REPRINTABLE_OUTCOME_STATUSES = Object.freeze([
  "SUCCEEDED",
  "UNCERTAIN",
  "FALLBACK_BROWSER",
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
    this.reprint_handle = null;
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
        .then((outcome) => adapter._syncReprintSlot(this, outcome))
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
    this.restoreReprintButton();
    return true;
  }

  /**
   * Add a Reprint button to the Past Order Summary (A.31.19-A.31.21).
   *
   * A repeated ORIGINAL print is refused by design: the idempotency key is
   * derived from the invoice and terminal with no timestamp, so a second click
   * joins the settled Job instead of printing again. A second physical copy is
   * legal only as a REPRINT — a new Job, with an authorized requester and a
   * mandatory reason. This button is that path.
   *
   * The button is rendered hidden and takes over the Print Receipt slot once a
   * print settles with content possibly on paper, so the button row keeps its
   * original layout: exactly one of the two is ever visible.
   *
   * Renders only for POS Print Manager / System Manager: Operator has no
   * reprint authority (the server enforces this too — the hidden button is
   * convenience, never the control).
   */
  installReprintButton(print_manager, pos_context) {
    const prototype = _prototypeFrom(pos_context);
    if (!prototype || typeof prototype.add_summary_btns !== "function") {
      return false;
    }
    if (this.reprint_handle) {
      if (this.reprint_handle.prototype === prototype) {
        return true;
      }
      this.restoreReprintButton();
    }
    if (!this._hasReprintRole()) {
      return false;
    }

    const original_add_summary_btns = prototype.add_summary_btns;
    const adapter = this;

    prototype.add_summary_btns = function patched_add_summary_btns(map) {
      const result = original_add_summary_btns.call(this, map);
      adapter._appendReprintButton(this, print_manager);
      return result;
    };

    this.reprint_handle = {
      prototype,
      original_add_summary_btns,
      installed: true,
    };
    return true;
  }

  restoreReprintButton() {
    const target = this.reprint_handle;
    if (!target || !target.installed) {
      return false;
    }
    target.prototype.add_summary_btns = target.original_add_summary_btns;
    target.installed = false;
    this.reprint_handle = null;
    return true;
  }

  /**
   * Ask for the mandatory reason, then run the reprint through PrintManager.
   * Resolves with the PrintOutcome, or null when the operator dismisses the
   * prompt. Never falls back to browser print: a reprint the cashier could not
   * authorize is not a reprint.
   */
  requestReprint(summary, print_manager) {
    const doc = summary?.frm?.doc || summary?.doc;
    if (!doc || !doc.name) {
      return Promise.reject(
        makeError("PDP_RECEIPT_INVALID", {
          phase: "RECEIPT",
          metadata: { reason: "no invoice document in POS context" },
        })
      );
    }

    return this._promptReprintReason().then((reason) => {
      if (!reason) {
        return null;
      }
      return print_manager.reprintInvoice(
        {
          reference_doctype: doc.doctype,
          reference_name: doc.name,
          terminal_id:
            summary?.terminal_id ||
            summary?.pos_direct_print_terminal_id ||
            null,
        },
        { invoice_snapshot: doc, reason }
      );
    });
  }

  _appendReprintButton(summary, print_manager) {
    const container = summary?.$summary_btns;
    if (!container || typeof container.append !== "function") {
      return;
    }
    // The summary re-renders its buttons on every order; only add ours when the
    // current render actually offers printing.
    if (!container.find(".print-btn").length) {
      return;
    }
    if (container.find(".pdp-reprint-btn").length) {
      return;
    }

    const label = _translate("Reprint");
    // Hidden until a print settles with content possibly on paper: Reprint then
    // takes over the Print Receipt slot, so the row keeps its original layout.
    const button = _jquery(
      `<div class="summary-btn btn btn-default pdp-reprint-btn" style="display: none;">${label}</div>`
    );
    if (!button) {
      return;
    }
    const adapter = this;
    button.on("click", () => {
      adapter.requestReprint(summary, print_manager).catch((error) => {
        adapter._showReprintError(error);
      });
    });
    container.append(button);
  }

  /**
   * One slot, two buttons. Print Receipt stays while a fresh copy is still
   * legal; Reprint replaces it once content may already be on paper, because
   * from that point a repeated ORIGINAL print is refused by idempotency and
   * REPRINT is the only sanctioned second copy. A FAILED_SAFE outcome printed
   * nothing, so Print Receipt stays and the cashier can simply print again.
   */
  _syncReprintSlot(summary, outcome) {
    const container = summary?.$summary_btns;
    if (!container || typeof container.find !== "function") {
      return outcome;
    }
    const reprint_btn = container.find(".pdp-reprint-btn");
    if (!reprint_btn.length) {
      return outcome;
    }
    if (!_mayHavePrinted(outcome)) {
      return outcome;
    }
    _setVisible(container.find(".print-btn"), false);
    _setVisible(reprint_btn, true);
    return outcome;
  }

  _promptReprintReason() {
    if (typeof frappe === "undefined" || typeof frappe.prompt !== "function") {
      return Promise.reject(
        makeError("PDP_CONFIG_INVALID", {
          metadata: { reason: "frappe.prompt unavailable for reprint reason" },
        })
      );
    }
    return new Promise((resolve) => {
      frappe.prompt(
        {
          fieldname: "reason",
          fieldtype: "Small Text",
          label: _translate("Reprint reason"),
          reqd: 1,
        },
        (values) => resolve((values?.reason || "").trim()),
        _translate("Reprint receipt"),
        _translate("Reprint")
      );
      // A dismissed dialog never calls back; the promise stays pending and the
      // click is simply abandoned, which is the intended no-op.
    });
  }

  _showReprintError(error) {
    const message =
      error && error.code
        ? `${error.code}: ${error.user_message || error.message_key || ""}`
        : String(error?.message || error);
    if (
      typeof frappe !== "undefined" &&
      typeof frappe.msgprint === "function"
    ) {
      frappe.msgprint({
        title: _translate("Reprint failed"),
        message,
        indicator: "red",
      });
      return;
    }
    console.warn("pos_direct_print: reprint failed", message);
  }

  _hasReprintRole() {
    if (
      typeof frappe === "undefined" ||
      !frappe.user ||
      typeof frappe.user.has_role !== "function"
    ) {
      return false; // fail closed: no role information means no button
    }
    return (
      frappe.user.has_role("POS Print Manager") ||
      frappe.user.has_role("System Manager")
    );
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

/** Desk translation when available; the raw string otherwise (tests, node). */
function _translate(text) {
  return typeof __ === "function" ? __(text) : text;
}

/** Desk jQuery when available; null otherwise so callers degrade quietly. */
function _jquery(html) {
  const $ = typeof window !== "undefined" ? window.$ || window.jQuery : null;
  return $ ? $(html) : null;
}

/**
 * True when the outcome means paper may already carry this receipt, so only a
 * REPRINT may produce another copy. A failed reservation (no status at all) and
 * FAILED_SAFE both printed nothing.
 *
 * PDP_JOB_CONFLICT counts too: it means a settled Job already owns this exact
 * intent, which is what a reopened past order looks like. Print Receipt there
 * would only earn the same conflict, so hand the slot to Reprint.
 */
function _mayHavePrinted(outcome) {
  if (!outcome) {
    return false;
  }
  if (REPRINTABLE_OUTCOME_STATUSES.includes(outcome.status)) {
    return true;
  }
  return outcome.error?.code === "PDP_JOB_CONFLICT";
}

/** Toggle a jQuery-like set, tolerating the absence of Desk's helpers. */
function _setVisible(node, visible) {
  if (!node || !node.length) {
    return;
  }
  if (typeof node.toggle === "function") {
    node.toggle(visible);
    return;
  }
  if (typeof node.css === "function") {
    node.css("display", visible ? "" : "none");
  }
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
