import assert from "node:assert/strict";
import { test } from "node:test";

import { IminSdkAdapter } from "../imin_sdk_adapter.mjs";

function makeRuntime(script = {}) {
  const instances = [];

  class FakeIminPrinter {
    constructor(address) {
      this.address = address;
      this.calls = [];
      this.outbound_commands = [];
      instances.push(this);
    }

    connect() {
      return script.connect || Promise.resolve(true);
    }

    initPrinter(connection_type) {
      this._call("initPrinter", connection_type);
    }

    getPrinterStatus(connection_type) {
      this._call("getPrinterStatus", connection_type);
      return script.status || Promise.resolve({ value: "0", text: "normal" });
    }

    setPageFormat(value) {
      this._call("setPageFormat", value);
    }

    setTextWidth(value) {
      this._call("setTextWidth", value);
    }

    setAlignment(value) {
      this._call("setAlignment", value);
    }

    setTextSize(value) {
      this._call("setTextSize", value);
    }

    setTextStyle(value) {
      this._call("setTextStyle", value);
    }

    printText(line) {
      this._call("printText", line);
      this.outbound_commands.push(`${line}\n`);
    }

    printAndFeedPaper(value) {
      this._call("printAndFeedPaper", value);
    }

    _call(method, value) {
      if (script.throw_on === method) {
        throw new Error(`raw ${method} failure`);
      }
      this.calls.push({ method, value });
    }
  }

  return {
    runtime: { WebSocket: class {}, IminPrinter: FakeIminPrinter },
    instances,
  };
}

test("adapter does not expose an SDK instance", () => {
  const { runtime } = makeRuntime();
  const adapter = new IminSdkAdapter({ runtime });

  assert.equal(adapter.sdk, undefined);
  assert.equal(adapter.instance, undefined);
  assert.equal(JSON.stringify(adapter).includes("outbound_commands"), false);
});

test("void SDK calls become controlled dispatch results", () => {
  const { runtime, instances } = makeRuntime();
  const adapter = new IminSdkAdapter({ runtime });

  assert.equal(adapter.initialize("SPI").accepted, true);
  assert.equal(adapter.setPageFormat(1).accepted, true);
  assert.equal(adapter.setTextWidth(384).accepted, true);
  assert.equal(adapter.setAlignment(0).accepted, true);
  assert.equal(adapter.setTextSize(24).accepted, true);
  assert.equal(adapter.setTextStyle(1).accepted, true);
  assert.equal(adapter.feed(80).accepted, true);
  assert.deepEqual(
    instances[0].calls.map(({ method }) => method),
    [
      "initPrinter",
      "setPageFormat",
      "setTextWidth",
      "setAlignment",
      "setTextSize",
      "setTextStyle",
      "printAndFeedPaper",
    ]
  );
});

test("logical text always produces exactly one outbound newline", () => {
  for (const input of ["item", "item\n", "item\r\n", "item\n\n"]) {
    const { runtime, instances } = makeRuntime();
    const adapter = new IminSdkAdapter({ runtime });

    assert.equal(adapter.printText(input).accepted, true);
    assert.deepEqual(instances[0].outbound_commands, ["item\n"]);
  }
});

test("status coerces numeric strings", async () => {
  const { runtime } = makeRuntime({
    status: Promise.resolve({ value: "7", text: "paper out" }),
  });
  const result = await new IminSdkAdapter({ runtime }).getStatus("SPI");

  assert.equal(result.ok, true);
  assert.equal(result.value, 7);
  assert.equal(result.error, null);
});

test("status timeout returns a canonical controlled failure", async () => {
  const { runtime } = makeRuntime({ status: new Promise(() => {}) });
  const result = await new IminSdkAdapter({ runtime, timeout_ms: 5 }).getStatus(
    "SPI"
  );

  assert.equal(result.ok, false);
  assert.equal(result.error.code, "PDP_PRINT_TIMEOUT");
  assert.equal(JSON.stringify(result).includes("raw"), false);
});

test("synchronous SDK errors never escape the adapter", () => {
  const { runtime } = makeRuntime({ throw_on: "printText" });
  const result = new IminSdkAdapter({ runtime }).printText("item");

  assert.equal(result.accepted, false);
  assert.equal(result.error.code, "PDP_PRINT_COMMAND_FAILED");
  assert.equal(result.error.content_may_have_printed, true);
  assert.equal(JSON.stringify(result).includes("raw printText failure"), false);
  assert.equal(JSON.stringify(result).includes("stack"), false);
});

test("dispose drops the SDK reference without calling unqualified close", () => {
  const { runtime, instances } = makeRuntime();
  const adapter = new IminSdkAdapter({ runtime });
  adapter.initialize("SPI");

  assert.deepEqual(adapter.dispose(), { disposed: true });
  adapter.initialize("SPI");
  assert.equal(instances.length, 2);
});

test("detect rejects missing WebSocket support without SDK construction", async () => {
  let constructed = false;
  class FakeIminPrinter {
    constructor() {
      constructed = true;
    }
  }
  const adapter = new IminSdkAdapter({
    runtime: { IminPrinter: FakeIminPrinter },
  });

  const result = await adapter.detect();

  assert.equal(result.available, false);
  assert.equal(result.reason, "WEBSOCKET_UNAVAILABLE");
  assert.equal(result.error.code, "PDP_BRIDGE_UNAVAILABLE");
  assert.equal(constructed, false);
});

test("detect rejects a missing SDK asset", async () => {
  const adapter = new IminSdkAdapter({ runtime: { WebSocket: class {} } });
  const result = await adapter.detect();

  assert.equal(result.available, false);
  assert.equal(result.reason, "SDK_ASSET_UNAVAILABLE");
  assert.equal(result.error.code, "PDP_BRIDGE_UNAVAILABLE");
});

test("detect contains constructor failures", async () => {
  class BrokenSdk {
    constructor() {
      throw new Error("raw constructor failure");
    }
  }
  const adapter = new IminSdkAdapter({
    runtime: { WebSocket: class {}, IminPrinter: BrokenSdk },
  });

  const result = await adapter.detect();

  assert.equal(result.available, false);
  assert.equal(result.reason, "SDK_CONSTRUCTION_FAILED");
  assert.equal(
    JSON.stringify(result).includes("raw constructor failure"),
    false
  );
});

test("detect reports successful connection", async () => {
  const { runtime } = makeRuntime();
  const result = await new IminSdkAdapter({ runtime }).detect();

  assert.equal(result.available, true);
  assert.equal(result.reason, null);
  assert.equal(result.error, null);
  assert.deepEqual(result.metadata, { address: "127.0.0.1" });
});

test("detect reports connect false as unavailable", async () => {
  const { runtime } = makeRuntime({ connect: Promise.resolve(false) });
  const result = await new IminSdkAdapter({ runtime }).detect();

  assert.equal(result.available, false);
  assert.equal(result.reason, "CONNECTION_FAILED");
  assert.equal(result.error.code, "PDP_BRIDGE_UNAVAILABLE");
});

test("detect time-boxes a pending connection", async () => {
  const { runtime } = makeRuntime({ connect: new Promise(() => {}) });
  const result = await new IminSdkAdapter({ runtime, timeout_ms: 5 }).detect();

  assert.equal(result.available, false);
  assert.equal(result.reason, "CONNECTION_TIMEOUT");
  assert.equal(result.error.code, "PDP_BRIDGE_UNAVAILABLE");
});
