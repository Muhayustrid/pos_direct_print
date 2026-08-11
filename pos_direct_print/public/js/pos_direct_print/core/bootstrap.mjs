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
import { resolvePaperProfile } from "../receipt/paper_profiles.mjs";
import { IminV1Driver } from "../drivers/imin_v1_driver.mjs";

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

    this._registerIminV1(registry, context, warnings);

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

  /**
   * Register the V1 driver only when the pinned SDK asset is actually
   * present at runtime. The UMD tail may install a Vue plugin (which would
   * be wrong here), so the loader hides `window.Vue` while the SDK loads.
   * Absence is a warning, never a bootstrap failure.
   */
  _registerIminV1(registry, context, warnings) {
    const runtime = context.runtime || globalThis;
    if (typeof runtime.IminPrinter !== "function") {
      warnings.push("iMin SDK unavailable; imin_v1 driver not registered");
      return;
    }
    const transport = context.terminal_transport || "SPI";
    registry.registerDriver({
      driver_key: "imin_v1",
      factory: () =>
        new IminV1Driver({
          connection_type: transport,
          paper_profile: resolvePaperProfile(
            context.paper_profile || "reference_58mm"
          ),
          address: context.sdk_address,
          timeout_ms: context.sdk_timeout_ms,
        }),
      capabilities: {
        supports_status: true,
        supports_text: true,
        supports_feed: true,
        supports_columns: false,
        supports_image: false,
        supports_qr: false,
        supports_cut: false,
        paper_width_mm: 58,
        transport,
      },
    });
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

/**
 * Module-level singleton so every loader/boot call shares one subsystem
 * and repeated boots return the identical result (A-DOD-03).
 */
const subsystem = new SubsystemBootstrap();

/**
 * Entry point for the classic script loader and tests. `initialize` is
 * idempotent, so calling bootSubsystem twice returns the same result.
 */
export function bootSubsystem(context) {
  return subsystem.initialize({
    ...context,
    settings: context.settings || { receipt_schema_version: 1 },
  });
}
