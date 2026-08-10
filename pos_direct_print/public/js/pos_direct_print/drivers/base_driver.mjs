/**
 * Abstract driver contract (A.12.13). Every printer driver must implement it.
 * Unsupported capabilities must produce controlled, capability-related
 * outcomes — never uncontrolled exceptions.
 */

import { makeError } from "../core/errors.mjs";

export class BaseDriver {
  constructor(driver_key) {
    if (!driver_key) {
      throw makeError("PDP_CONFIG_INVALID", {
        metadata: { reason: "driver_key is required" },
      });
    }
    this.driver_key = driver_key;
    this._initialized = false;
  }

  // Contract methods — subclasses override; base returns controlled defaults.

  detect(context) {
    return { available: false, reason: null, metadata: { context: !!context } };
  }

  initialize(context) {
    this._initialized = true;
    return { initialized: true, driver_key: this.driver_key };
  }

  getCapabilities() {
    throw makeError("PDP_DRIVER_CAPABILITY_UNSUPPORTED", {
      metadata: { driver_key: this.driver_key, method: "getCapabilities" },
    });
  }

  getStatus() {
    return {
      state: "UNKNOWN_ERROR",
      ready: false,
      blocking: false,
      raw_code: null,
      raw_message: null,
      checked_at: null,
      metadata: {},
    };
  }

  print(receipt_document, job_context) {
    return this._unsupportedResult("print");
  }

  feed(request) {
    return this._unsupportedResult("feed");
  }

  /**
   * Unsupported cutter must yield a controlled capability outcome, never an
   * uncontrolled exception.
   */
  cut(request) {
    return this._unsupportedResult("cut");
  }

  dispose() {
    this._initialized = false;
    return { disposed: true };
  }

  _unsupportedResult(method) {
    // Canonical DriverPrintResult (A.10.6) carrying a controlled
    // capability error in metadata; the normalizer lifts it into a
    // PrintDomainError at the orchestration boundary.
    return {
      accepted: false,
      content_started: false,
      content_completed: false,
      verification_supported: false,
      final_status: null,
      metadata: {
        error_code: "PDP_DRIVER_CAPABILITY_UNSUPPORTED",
        driver_key: this.driver_key,
        method,
      },
    };
  }
}
