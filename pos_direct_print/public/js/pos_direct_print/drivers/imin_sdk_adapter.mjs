import { normalize } from "../core/error_normalizer.mjs";
import { makeError } from "../core/errors.mjs";

export class IminSdkAdapter {
  #runtime;
  #address;
  #timeout_ms;
  #instance = null;

  constructor({
    runtime = globalThis,
    address = "127.0.0.1",
    timeout_ms = 5000,
  } = {}) {
    this.#runtime = runtime;
    this.#address = address;
    this.#timeout_ms = timeout_ms;
  }

  async detect() {
    if (!this.#runtime.WebSocket && !this.#runtime.MozWebSocket) {
      return bridgeUnavailable("WEBSOCKET_UNAVAILABLE");
    }
    if (typeof this.#runtime.IminPrinter !== "function") {
      return bridgeUnavailable("SDK_ASSET_UNAVAILABLE");
    }

    try {
      const instance = this.#requireInstance();
      const connected = await withTimeout(instance.connect(), this.#timeout_ms);
      if (!connected) {
        return bridgeUnavailable("CONNECTION_FAILED");
      }
      return {
        available: true,
        reason: null,
        error: null,
        metadata: { address: this.#address },
      };
    } catch (error) {
      const reason =
        error?.code === "PDP_PRINT_TIMEOUT"
          ? "CONNECTION_TIMEOUT"
          : this.#instance
          ? "CONNECTION_FAILED"
          : "SDK_CONSTRUCTION_FAILED";
      return bridgeUnavailable(reason, error);
    }
  }

  initialize(connection_type) {
    return this.#dispatch(
      "initPrinter",
      [connection_type],
      "PREFLIGHT",
      "PDP_PRINTER_NOT_READY"
    );
  }

  async getStatus(connection_type) {
    try {
      const instance = this.#requireInstance();
      const status = await withTimeout(
        instance.getPrinterStatus(connection_type),
        this.#timeout_ms
      );
      const raw = status?.value;
      const value =
        typeof raw === "number"
          ? raw
          : typeof raw === "string" && /^-?\d+$/u.test(raw)
          ? Number(raw)
          : NaN;
      if (!Number.isFinite(value)) {
        throw makeError("PDP_PRINT_STATUS_UNKNOWN", { phase: "PREFLIGHT" });
      }
      return { ok: true, value, error: null, metadata: {} };
    } catch (error) {
      return statusFailure(error);
    }
  }

  setPageFormat(style) {
    return this.#dispatch("setPageFormat", [style]);
  }

  setTextWidth(width) {
    return this.#dispatch("setTextWidth", [width]);
  }

  setAlignment(alignment) {
    return this.#dispatch("setAlignment", [alignment]);
  }

  setTextSize(size) {
    return this.#dispatch("setTextSize", [size]);
  }

  setTextStyle(style) {
    return this.#dispatch("setTextStyle", [style]);
  }

  printText(line) {
    const normalized_line = String(line).replace(/[\r\n]+$/u, "");
    return this.#dispatch("printText", [normalized_line], "PRINT");
  }

  feed(value) {
    return this.#dispatch("printAndFeedPaper", [value], "PRINT");
  }

  dispose() {
    this.#instance = null;
    return { disposed: true };
  }

  #dispatch(
    method,
    args,
    phase = "PREFLIGHT",
    code = "PDP_PRINT_COMMAND_FAILED"
  ) {
    try {
      this.#requireInstance()[method](...args);
      return { accepted: true, error: null, metadata: {} };
    } catch (error) {
      return dispatchFailure(error, phase, code);
    }
  }

  #requireInstance() {
    if (!this.#instance) {
      const Sdk = this.#runtime.IminPrinter;
      if (typeof Sdk !== "function") {
        throw makeError("PDP_BRIDGE_UNAVAILABLE", { phase: "PREFLIGHT" });
      }
      this.#instance = new Sdk(this.#address);
    }
    return this.#instance;
  }
}

function bridgeUnavailable(reason, raw_error = null) {
  const tagged = makeError("PDP_BRIDGE_UNAVAILABLE", {
    phase: "PREFLIGHT",
    cause: raw_error,
    metadata: { reason },
  });
  return {
    available: false,
    reason,
    error: normalize(tagged, "PREFLIGHT", { content_started: false }),
    metadata: {},
  };
}

function dispatchFailure(raw_error, phase, code) {
  const tagged = makeError(code, { phase, cause: raw_error });
  return {
    accepted: false,
    error: normalize(tagged, phase, { content_started: phase === "PRINT" }),
    metadata: {},
  };
}

function statusFailure(raw_error) {
  const code =
    raw_error?.code === "PDP_PRINT_TIMEOUT"
      ? "PDP_PRINT_TIMEOUT"
      : "PDP_PRINT_STATUS_UNKNOWN";
  const tagged = makeError(code, { phase: "PREFLIGHT", cause: raw_error });
  return {
    ok: false,
    value: null,
    error: normalize(tagged, "PREFLIGHT", { content_started: false }),
    metadata: {},
  };
}

function withTimeout(promise, timeout_ms) {
  let timer;
  const timeout = new Promise((resolve, reject) => {
    timer = setTimeout(
      () => reject(makeError("PDP_PRINT_TIMEOUT", { phase: "PREFLIGHT" })),
      timeout_ms
    );
  });
  return Promise.race([Promise.resolve(promise), timeout]).finally(() =>
    clearTimeout(timer)
  );
}
