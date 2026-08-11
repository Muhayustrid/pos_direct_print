/**
 * Subsystem bootstrap (A.12.1).
 *
 * Initializes the direct-print subsystem once per Desk/browser lifecycle.
 * Calling initialize repeatedly must never stack POS overrides — the guard is
 * the whole point of this module. shutdown restores the override and releases
 * transient resources.
 */

import { CapabilityRegistry } from "../core/capability_registry.mjs";
import { makeError } from "../core/errors.mjs";
import { JobCoordinator } from "../core/job_coordinator.mjs";
import { PrintApi } from "../core/print_api.mjs";
import { PrintManager } from "../core/print_manager.mjs";
import { POSIntegrationAdapter } from "../integration/erpnext_v16_pos.mjs";
import { ReceiptBuilder } from "../receipt/receipt_builder.mjs";

export class SubsystemBootstrap {
  constructor() {
    this.state = null;
  }

  /**
   * @param {object} context BootstrapContext: current user, route, feature
   *   settings, asset version, plus injectable transports for tests.
   * @returns {object} BootstrapResult { initialized, integration_installed,
   *   active_driver, warnings }
   */
  initialize(context) {
    if (this.state && this.state.initialized) {
      // Idempotent: repeated initialization returns the live subsystem
      // acknowledgement and never reinstalls the POS override (A-DOD-03).
      return this.state.result;
    }

    if (!context || typeof context !== "object") {
      throw makeError("PDP_CONFIG_INVALID", {
        metadata: { reason: "bootstrap context is required" },
      });
    }

    const warnings = [];
    const settings = context.settings || {};
    if (!settings.receipt_schema_version) {
      warnings.push("receipt_schema_version missing from settings");
    }

    const api = context.api || new PrintApi({ call: context.rpc_call });
    const coordinator = context.coordinator || new JobCoordinator(api);
    const registry =
      context.registry ||
      new CapabilityRegistry({ allow_reregistration: true });

    const receipt_builder = new ReceiptBuilder();
    const manager = new PrintManager({
      coordinator,
      registry,
      resolveDriver:
        context.resolve_driver || ((record) => record.manifest.factory()),
      // Default canonical receipt construction; injectable for tests.
      buildReceipt:
        context.build_receipt ||
        ((snapshot, request) =>
          receipt_builder.build(snapshot, {
            paper_profile: request?.options?.paper_profile,
          })),
      default_driver_key:
        context.active_driver_key || settings.default_driver || null,
    });

    const adapter = new POSIntegrationAdapter({
      get_settings: context.get_settings || (() => settings),
    });
    adapter._setPrintApi(api);

    let integration_installed = false;
    if (context.pos_context && adapter.isSupported(context.pos_context)) {
      adapter.installOverride(manager, context.pos_context);
      integration_installed = true;
    } else {
      warnings.push("ERPNext POS prototype not available; override deferred");
    }

    this.state = {
      initialized: true,
      user: context.user || null,
      route: context.route || null,
      asset_version: context.asset_version || null,
      settings,
      api,
      coordinator,
      registry,
      manager,
      adapter,
      integration_installed,
      active_driver: context.active_driver_key || null,
      warnings,
    };
    // Cache the result object so repeated initialize calls return the very
    // same acknowledgement — idempotency by identity, not just by shape.
    this.state.result = this._result();

    return this.state.result;
  }

  shutdown() {
    if (!this.state) {
      return { shutdown: false };
    }
    const restored = this.state.adapter.restoreOverride();
    this.state = null;
    return { shutdown: true, override_restored: restored };
  }

  _result() {
    return {
      initialized: this.state.initialized,
      integration_installed: this.state.integration_installed,
      active_driver: this.state.active_driver,
      warnings: this.state.warnings,
    };
  }
}
