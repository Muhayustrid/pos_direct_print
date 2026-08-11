/**
 * IminV1Driver (B-DRV) — key `imin_v1`.
 *
 * The only BaseDriver implementation for the V1-qualified reference device.
 * It touches the iMin SDK only through `imin_sdk_adapter.mjs` (B-DRV-02) and
 * satisfies every frozen BaseDriver method without uncontrolled exceptions
 * (B-DRV-01). Hardware unknowns are injected here; SPI stays a candidate
 * transport pending B1-04 qualification (B-DRV-06 note).
 */

import { BaseDriver } from "./base_driver.mjs";
import { IminSdkAdapter } from "./imin_sdk_adapter.mjs";
import {
  makeError,
  isPrintDomainError,
  PrintDomainError,
} from "../core/errors.mjs";
import { normalize } from "../core/error_normalizer.mjs";
import {
  REFERENCE_PROFILE,
  resolvePaperProfile,
} from "../receipt/paper_profiles.mjs";
import { renderReceiptLines } from "../receipt/receipt_lines.mjs";

export const IMIN_V1_DRIVER_KEY = "imin_v1";

const RAW_STATUSES = Object.freeze({
  0: { state: "READY", ready: true, blocking: false },
  7: { state: "PAPER_OUT", ready: false, blocking: true },
  3: { state: "COVER_OPEN", ready: false, blocking: true },
  8: { state: "PAPER_LOW", ready: false, blocking: false },
  [-1]: { state: "DISCONNECTED", ready: false, blocking: true },
  1: { state: "DISCONNECTED", ready: false, blocking: true },
  99: { state: "UNKNOWN_ERROR", ready: false, blocking: true },
});

export function mapStatus(raw_value) {
  const mapped = RAW_STATUSES[raw_value] || {
    state: "UNKNOWN_ERROR",
    ready: false,
    blocking: true,
  };
  return {
    ...mapped,
    raw_code: null,
    raw_message: null,
    checked_at: null,
    metadata: { raw_code: raw_value },
  };
}

export class IminV1Driver extends BaseDriver {
  /**
   * @param {object} options every hardware unknown is injected here:
   * @param {IminSdkAdapter} [options.sdk_adapter] test seam; default new IminSdkAdapter({ address, timeout_ms })
   * @param {"USB"|"SPI"|"Bluetooth"} [options.connection_type] GATED: SPI candidate; confirmed by B1-04 app-origin qualification
   * @param {object} [options.paper_profile] resolvePaperProfile() output; default REFERENCE_PROFILE
   * @param {string} [options.address] default "127.0.0.1"
   * @param {number} [options.timeout_ms] default 5000
   * @param {number} [options.post_connect_delay_ms] default 0 — calibration knob; nonzero only when B1-05 records a required delay
   */
  constructor(options = {}) {
    super(IMIN_V1_DRIVER_KEY);
    this.connection_type = options.connection_type || "SPI";
    this.paper_profile =
      options.paper_profile || resolvePaperProfile(REFERENCE_PROFILE.key);
    this.post_connect_delay_ms = options.post_connect_delay_ms || 0;
    this.sdk_adapter =
      options.sdk_adapter ||
      new IminSdkAdapter({
        address: options.address || "127.0.0.1",
        timeout_ms: options.timeout_ms || 5000,
      });
  }

  async detect(context) {
    const result = await this.sdk_adapter.detect();
    return result?.error
      ? { ...result, error: this._sanitizeError(result.error) }
      : result;
  }

  async initialize(context) {
    const result = this.sdk_adapter.initialize(this.connection_type);
    if (!result || !result.accepted) {
      throw this._sanitizeError(
        result.error ||
          makeError("PDP_PRINTER_NOT_READY", { phase: "PREFLIGHT" })
      );
    }

    if (this.post_connect_delay_ms > 0) {
      await new Promise((resolve) =>
        setTimeout(resolve, this.post_connect_delay_ms)
      );
    }

    const status = await this.getStatus();
    if (!status.ready) {
      throw makeError("PDP_PRINTER_NOT_READY", {
        phase: "PREFLIGHT",
        metadata: { state: status.state },
      });
    }
    this._initialized = true;
    return { initialized: true, driver_key: this.driver_key };
  }

  getCapabilities() {
    return {
      driver_key: this.driver_key,
      available: this._initialized,
      supports_status: true,
      supports_text: true,
      supports_columns: false,
      supports_image: false,
      supports_qr: false,
      supports_feed: true,
      supports_cut: false,
      paper_width_mm: this.paper_profile.width_mm,
      transport:
        this.connection_type === "Bluetooth"
          ? "BLUETOOTH"
          : this.connection_type,
      metadata: {},
    };
  }

  async getStatus() {
    const result = await this.sdk_adapter.getStatus(this.connection_type);
    if (!result.ok) {
      throw this._sanitizeError(
        result.error ||
          makeError("PDP_PRINT_STATUS_UNKNOWN", { phase: "PREFLIGHT" })
      );
    }
    return mapStatus(result.value);
  }

  async print(receipt_document, job_context) {
    const profile = resolvePaperProfile(
      receipt_document.paper_profile || this.paper_profile.key
    );
    const result = {
      accepted: false,
      content_started: false,
      content_completed: false,
      verification_supported: false,
      final_status: null,
      metadata: { driver_key: this.driver_key, post_status_checked: false },
    };

    try {
      const pre = await this.getStatus();
      if (pre.state === "PAPER_OUT") {
        throw makeError("PDP_PRINTER_PAPER_OUT", { phase: "PREFLIGHT" });
      }
      if (!pre.ready) {
        throw makeError("PDP_PRINTER_NOT_READY", { phase: "PREFLIGHT" });
      }

      this._require(this.sdk_adapter.setPageFormat(profile.page_format));
      this._require(this.sdk_adapter.setTextWidth(profile.text_width_dots));
      this._require(this.sdk_adapter.setAlignment(0)); // left default (B-RCP-06)
      this._require(this.sdk_adapter.setTextSize(1));
      this._require(this.sdk_adapter.setTextStyle(0));

      for (const line of renderReceiptLines(receipt_document, profile)) {
        if (line.kind === "feed") continue; // single final feed below
        if (line.kind === "style") {
          this._require(this.sdk_adapter.setTextStyle(line.bold ? 1 : 0));
          continue;
        }
        const dispatched = this.sdk_adapter.printText(line.text);
        result.content_started = true; // first content dispatch
        this._require(dispatched); // mid-print failure -> UNCERTAIN via manager
      }
      this._require(this.sdk_adapter.feed(profile.final_feed));
      result.content_completed = true;

      const post = await this.getStatus(); // bounded: adapter timeout; failure forbids SUCCEEDED
      result.metadata.post_status_checked = true;
      result.final_status = post;
      result.accepted = true;
      return result;
    } catch (raw) {
      if (isPrintDomainError(raw)) {
        if (result.content_started && !raw.content_may_have_printed) {
          throw normalize(raw, "PRINT", { content_started: true });
        }
        throw raw;
      }
      throw normalize(raw, result.content_started ? "PRINT" : "PREFLIGHT", {
        content_started: result.content_started,
      });
    }
  }

  async feed(request) {
    const result = await this.sdk_adapter.feed(
      request?.value ?? this.paper_profile.final_feed
    );
    return {
      accepted: result.accepted,
      content_started: false,
      content_completed: result.accepted,
      verification_supported: false,
      final_status: null,
      metadata: { driver_key: this.driver_key },
    };
  }

  cut(request) {
    // Controlled capability outcome — never throws (B-AT-18).
    return this._unsupportedResult("cut");
  }

  dispose() {
    this.sdk_adapter.dispose();
    this._initialized = false;
    return { disposed: true };
  }

  _require(dispatch) {
    if (!dispatch.accepted) {
      throw this._sanitizeError(dispatch.error);
    }
  }

  _sanitizeError(error) {
    // The adapter stores the raw SDK failure as the opaque `cause`. The SDK
    // instance must never escape the driver boundary (B-DOD-16), so strip the
    // cause chain from anything this driver rethrows.
    if (error && typeof error.toJSON === "function") {
      return new PrintDomainError({ ...error.toJSON(), cause: null });
    }
    return error;
  }
}
