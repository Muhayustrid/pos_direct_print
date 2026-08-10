/**
 * BrowserDriver (A.12.15) — canonical key `browser`.
 *
 * Not a physical driver: its output signals a browser print handoff to the
 * saved original ERPNext `print_receipt` path, never a confirmed physical
 * success (A-DOD-04/13). The handoff itself is performed by the POS
 * integration adapter — this driver records the decision as a canonical
 * DriverPrintResult so orchestration settles FALLBACK_BROWSER, not
 * SUCCEEDED.
 */

import { makeError } from "../core/errors.mjs";
import { BaseDriver } from "./base_driver.mjs";

export const BROWSER_DRIVER_KEY = "browser";

export class BrowserDriver extends BaseDriver {
  constructor() {
    super(BROWSER_DRIVER_KEY);
  }

  detect() {
    // The browser print path is structurally available wherever ERPNext POS
    // runs; availability is not a physical connection concern here.
    return { available: true, reason: null, metadata: {} };
  }

  getCapabilities() {
    return {
      driver_key: this.driver_key,
      available: true,
      supports_status: false,
      supports_text: false,
      supports_columns: false,
      supports_image: false,
      supports_qr: false,
      supports_feed: false,
      supports_cut: false,
      paper_width_mm: null,
      transport: "UNKNOWN",
      metadata: { handoff: true },
    };
  }

  getStatus() {
    // No physical device behind this driver — status is always the
    // handoff-ready equivalent of READY, never a printer state.
    return {
      state: "READY",
      ready: true,
      blocking: false,
      raw_code: null,
      raw_message: null,
      checked_at: null,
      metadata: { handoff: true },
    };
  }

  /**
   * @param {object} receipt_document canonical ReceiptDocument (unused for
   *   content: the original ERPNext path renders its own print view)
   * @param {object} job_context must carry `approved: true` — the boundary
   *   only hands off with explicit user approval and zero content risk
   *   (enforced upstream by PrintManager.fallbackToBrowser).
   * @returns {object} DriverPrintResult (A.10.6): accepted handoff, physical
   *   completion unknown, never `content_completed`.
   */
  print(receipt_document, job_context = {}) {
    if (!job_context.approved) {
      throw makeError("PDP_PERMISSION_DENIED", {
        phase: "FALLBACK",
        metadata: { driver_key: this.driver_key, reason: "approval required" },
      });
    }
    if (job_context.content_may_have_printed) {
      throw makeError("PDP_JOB_CONFLICT", {
        phase: "FALLBACK",
        content_may_have_printed: true,
        retry_class: "REPRINT_ONLY",
        metadata: { driver_key: this.driver_key, reason: "content risk" },
      });
    }
    return {
      accepted: true,
      content_started: false,
      content_completed: false,
      verification_supported: false,
      final_status: null,
      metadata: {
        handoff: "browser",
        original_path: "erpnext PointOfSale print_receipt",
      },
    };
  }
}
