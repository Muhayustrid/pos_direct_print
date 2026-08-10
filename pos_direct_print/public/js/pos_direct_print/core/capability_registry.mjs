/**
 * Generic capability registry (A.12.7). Milestone A provides the generic
 * registry only — no model-specific capability matrices (Milestone D).
 */

import { makeError } from "./errors.mjs";

export const CANONICAL_TRANSPORTS = Object.freeze([
  "USB",
  "SPI",
  "BLUETOOTH",
  "UNKNOWN",
]);
export const CANONICAL_PAPER_WIDTHS = Object.freeze([58, 80]);

const CAPABILITY_FLAGS = Object.freeze([
  "supports_status",
  "supports_text",
  "supports_columns",
  "supports_image",
  "supports_qr",
  "supports_feed",
  "supports_cut",
]);

export class CapabilityRegistry {
  /**
   * @param {object} options
   * @param {boolean} options.allow_reregistration bootstrap policy: permit an
   *   exact-same registration instance to be registered twice (idempotent
   *   subsystem bootstrap).
   */
  constructor(options = {}) {
    this.drivers = new Map();
    this.allow_reregistration = Boolean(options.allow_reregistration);
  }

  registerDriver(manifest) {
    if (
      !manifest ||
      typeof manifest.driver_key !== "string" ||
      !manifest.driver_key
    ) {
      throw makeError("PDP_CONFIG_INVALID", {
        metadata: { reason: "driver_key is required" },
      });
    }
    if (typeof manifest.factory !== "function") {
      throw makeError("PDP_CONFIG_INVALID", {
        metadata: { reason: "factory must be a function" },
      });
    }

    const existing = this.drivers.get(manifest.driver_key);
    if (existing) {
      // Duplicate policy: the exact same registration instance is only
      // tolerated under the explicit bootstrap policy; anything else is
      // a configuration conflict.
      if (existing.manifest === manifest && this.allow_reregistration) {
        return {
          registered: false,
          duplicate: true,
          driver_key: manifest.driver_key,
        };
      }
      throw makeError("PDP_CONFIG_INVALID", {
        metadata: {
          reason: `driver already registered: ${manifest.driver_key}`,
        },
      });
    }

    this.drivers.set(manifest.driver_key, {
      manifest,
      capabilities: normalizeCapabilities(
        manifest.capabilities || {},
        manifest.driver_key
      ),
    });
    return {
      registered: true,
      duplicate: false,
      driver_key: manifest.driver_key,
    };
  }

  hasDriver(driver_key) {
    return this.drivers.has(driver_key);
  }

  getDriver(driver_key) {
    const record = this.drivers.get(driver_key);
    if (!record) {
      throw makeError("PDP_DRIVER_NOT_FOUND", { metadata: { driver_key } });
    }
    return record;
  }

  /**
   * Merge the registered baseline with terminal overrides and runtime
   * detection. Baseline < terminal paper width < runtime availability.
   */
  resolveCapabilities(driver_key, terminal = null, runtime = null) {
    const record = this.getDriver(driver_key);
    const resolved = { ...record.capabilities };

    if (terminal && CANONICAL_PAPER_WIDTHS.includes(terminal.paper_width_mm)) {
      resolved.paper_width_mm = terminal.paper_width_mm;
    }
    if (runtime && typeof runtime === "object") {
      if (typeof runtime.available === "boolean") {
        resolved.available = runtime.available;
      }
      for (const flag of CAPABILITY_FLAGS) {
        if (typeof runtime[flag] === "boolean") {
          resolved[flag] = runtime[flag];
        }
      }
    }

    return Object.freeze({ ...resolved, driver_key });
  }

  listDrivers() {
    return Array.from(this.drivers.keys());
  }
}

export function normalizeCapabilities(capabilities, driver_key) {
  const normalized = { driver_key, available: false };
  for (const flag of CAPABILITY_FLAGS) {
    normalized[flag] = Boolean(capabilities[flag]);
  }
  normalized.paper_width_mm = CANONICAL_PAPER_WIDTHS.includes(
    capabilities.paper_width_mm
  )
    ? capabilities.paper_width_mm
    : null;
  normalized.transport = CANONICAL_TRANSPORTS.includes(capabilities.transport)
    ? capabilities.transport
    : "UNKNOWN";
  normalized.metadata = capabilities.metadata || {};
  return Object.freeze(normalized);
}
