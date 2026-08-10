/**
 * Fake foundation driver (Milestone A test double).
 *
 * Proves orchestration and normalization without device/plugin/Android/
 * printer (A-DOD-12). Behavior is scripted through the constructor so tests
 * can exercise the success path, content-risk failures, and raw exceptions.
 */

import { BaseDriver } from "./base_driver.mjs";

export const FAKE_DRIVER_KEY = "fake";

export class FakeDriver extends BaseDriver {
  /**
   * @param {object} script
   * @param {boolean} script.available detection/initialization availability
   * @param {"succeed"|"fail_after_content"|"fail_before_content"|"throw"} script.print_behavior
   */
  constructor(script = {}) {
    super(FAKE_DRIVER_KEY);
    this.script = {
      available: script.available !== false,
      print_behavior: script.print_behavior || "succeed",
    };
    this.print_calls = [];
    this.cut_calls = [];
  }

  detect() {
    return {
      available: this.script.available,
      reason: this.script.available ? null : "fake driver disabled by script",
      metadata: {},
    };
  }

  initialize(context) {
    if (!this.script.available) {
      return { initialized: false, driver_key: this.driver_key };
    }
    return super.initialize(context);
  }

  getCapabilities() {
    return {
      driver_key: this.driver_key,
      available: this.script.available,
      supports_status: true,
      supports_text: true,
      supports_columns: true,
      supports_image: false,
      supports_qr: false,
      supports_feed: true,
      supports_cut: false, // cutter unsupported -> controlled cut() outcome
      paper_width_mm: 58,
      transport: "UNKNOWN",
      metadata: {},
    };
  }

  getStatus() {
    return {
      state: this.script.available ? "READY" : "DISCONNECTED",
      ready: this.script.available,
      blocking: false,
      raw_code: null,
      raw_message: null,
      checked_at: null,
      metadata: {},
    };
  }

  print(receipt_document, job_context) {
    this.print_calls.push({ receipt_document, job_context });

    if (this.script.print_behavior === "throw") {
      // A-AT-15 source: a generic runtime exception crossing the boundary.
      throw new Error("fake driver exploded during print");
    }

    if (this.script.print_behavior === "fail_after_content") {
      return {
        accepted: true,
        content_started: true,
        content_completed: false,
        verification_supported: false,
        final_status: null,
        metadata: { failure: "post-content" },
      };
    }

    if (this.script.print_behavior === "fail_before_content") {
      return {
        accepted: false,
        content_started: false,
        content_completed: false,
        verification_supported: false,
        final_status: { state: "DISCONNECTED", ready: false, blocking: true },
        metadata: { failure: "pre-content" },
      };
    }

    return {
      accepted: true,
      content_started: true,
      content_completed: true,
      verification_supported: true,
      final_status: this.getStatus(),
      metadata: {},
    };
  }
}
