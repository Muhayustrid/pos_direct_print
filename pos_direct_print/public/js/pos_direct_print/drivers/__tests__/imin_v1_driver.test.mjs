import assert from "node:assert/strict";
import { test } from "node:test";

import {
  IminV1Driver,
  IMIN_V1_DRIVER_KEY,
  mapStatus,
} from "../imin_v1_driver.mjs";
import { IminSdkAdapter } from "../imin_sdk_adapter.mjs";
import { makePaperProfile } from "../../receipt/paper_profiles.mjs";
import { toUserError } from "../../core/error_normalizer.mjs";

function makeFakeRuntime(script = {}) {
  const instances = [];

  class FakeIminPrinter {
    constructor(address) {
      this.address = address;
      this.calls = [];
      this.outbound_commands = [];
      this.print_count = 0;
      instances.push(this);
    }

    connect() {
      return Promise.resolve(true);
    }

    initPrinter(value) {
      this._call("initPrinter", value);
    }

    getPrinterStatus(value) {
      this._call("getPrinterStatus", value);
      const status = script.statuses?.shift() ?? script.status ?? 0;
      return Promise.resolve({ value: String(status) });
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
      this.print_count += 1;
      if (script.throw_on_print_text === this.print_count) {
        throw new Error("raw printText failure");
      }
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

function makeAdapter(script = {}) {
  const { runtime, instances } = makeFakeRuntime(script);
  const adapter = new IminSdkAdapter({ runtime, timeout_ms: 5000 });
  return { adapter, runtime, instances };
}

// Production defaults wait on real hardware (cold-start READY polling, queue
// drain before the post-dispatch status sample). Tests assert command order,
// not wall-clock, so every driver here runs with the waits collapsed.
function makeDriver(options = {}) {
  return new IminV1Driver({
    ready_timeout_ms: 0,
    post_print_settle_ms: 0,
    ...options,
  });
}

function receipt(blocks = [], paper_profile = "test") {
  return {
    schema_version: 1,
    reference_doctype: "POS Invoice",
    reference_name: "INV-0001",
    locale: "id-ID",
    currency: "IDR",
    paper_profile,
    blocks,
    metadata: {},
  };
}

const TEST_PROFILE = makePaperProfile({
  key: "test",
  logical_width: 8,
  final_feed: 2,
});

test("mapStatus maps provisional raw values and keeps raw code in metadata", () => {
  const cases = [
    [0, "READY", true],
    [3, "COVER_OPEN", false],
    [7, "PAPER_OUT", false],
    [8, "PAPER_LOW", false],
    [-1, "DISCONNECTED", false],
    [1, "DISCONNECTED", false],
    [99, "UNKNOWN_ERROR", false],
    ["garbage", "UNKNOWN_ERROR", false],
  ];

  for (const [raw, state, ready] of cases) {
    const status = mapStatus(raw);
    assert.equal(status.state, state, `raw=${raw}`);
    assert.equal(status.ready, ready, `raw=${raw}`);
    assert.equal(status.raw_code, null);
    assert.equal(status.metadata.raw_code, raw);
  }
});

test("initialize succeeds only after READY status", async () => {
  const { adapter } = makeAdapter();
  const driver = makeDriver({
    sdk_adapter: adapter,
    paper_profile: TEST_PROFILE,
  });

  const result = await driver.initialize();
  assert.deepEqual(result, {
    initialized: true,
    driver_key: IMIN_V1_DRIVER_KEY,
  });
  assert.equal((await driver.getStatus()).state, "READY");
});

test("initialize failure is normalized and dispatches no content", async () => {
  const { adapter, instances } = makeAdapter({ throw_on: "initPrinter" });
  const driver = makeDriver({ sdk_adapter: adapter });

  await assert.rejects(driver.initialize(), (error) => {
    assert.equal(error.code, "PDP_PRINTER_NOT_READY");
    assert.equal(error.content_may_have_printed, false);
    return true;
  });
});

test("print dispatches setup, style-before-text pairs, one newline, and final feed", async () => {
  const { adapter, instances } = makeAdapter();
  const driver = makeDriver({
    sdk_adapter: adapter,
    paper_profile: TEST_PROFILE,
  });
  await driver.initialize();

  const result = await driver.print(
    receipt(
      [
        { type: "TEXT", text: "one", bold: false },
        { type: "TEXT", text: "two", bold: true },
        { type: "TEXT", text: "three\n", bold: true },
      ],
      TEST_PROFILE // pass object so resolvePaperProfile returns it directly
    )
  );
  const commands = instances[0].calls.map(({ method, value }) => [
    method,
    value,
  ]);

  // Calls before setup: adapter initPrinter (initialize) then getPrinterStatus
  // twice (initialize READY check + print preflight).
  assert.deepEqual(commands[0], ["initPrinter", "SPI"]);
  assert.deepEqual(commands[1], ["getPrinterStatus", "SPI"]);
  assert.deepEqual(commands[2], ["getPrinterStatus", "SPI"]);

  const expectedSetup = [
    ["setAlignment", 0],
    ["setTextSize", 24],
    ["setTextStyle", 0],
  ];
  const expectedContent = [
    ["printText", "one"],
    ["setTextStyle", 1],
    ["printText", "two"],
    ["printText", "three"],
  ];
  const expectedFeed = ["printAndFeedPaper", 2];

  const setupStart = 3; // skip init and the two status calls
  for (let i = 0; i < expectedSetup.length; i++) {
    assert.deepEqual(commands[setupStart + i], expectedSetup[i]);
  }
  const contentStart = setupStart + expectedSetup.length;
  for (let i = 0; i < expectedContent.length; i++) {
    assert.deepEqual(commands[contentStart + i], expectedContent[i]);
  }
  // Final feed is second-to-last; the last call is the post-dispatch
  // getPrinterStatus (B-COMP Option A evidence query).
  assert.deepEqual(commands.at(-2), expectedFeed);
  assert.deepEqual(commands.at(-1), ["getPrinterStatus", "SPI"]);

  assert.deepEqual(instances[0].outbound_commands, [
    "one\n",
    "two\n",
    "three\n",
  ]);
  assert.equal(result.content_started, true);
  assert.equal(result.content_completed, true);
  assert.equal(result.verification_supported, false);
  assert.equal(result.metadata.post_status_checked, true);
});

test("paper out before dispatch throws without content risk", async () => {
  const { adapter, instances } = makeAdapter({ status: 7 });
  const driver = makeDriver({ sdk_adapter: adapter });
  await driver.initialize().catch(() => {});

  await assert.rejects(
    driver.print(receipt([{ type: "TEXT", text: "nope" }])),
    (error) => {
      assert.equal(error.code, "PDP_PRINTER_PAPER_OUT");
      assert.equal(error.content_may_have_printed, false);
      assert.equal(instances[0].outbound_commands.length, 0);
      return true;
    }
  );
});

test("mid-dispatch failure carries content risk and no SDK object", async () => {
  const { adapter, instances } = makeAdapter({ throw_on_print_text: 2 });
  const driver = makeDriver({ sdk_adapter: adapter });
  await driver.initialize();

  await assert.rejects(
    driver.print(
      receipt([
        { type: "TEXT", text: "one" },
        { type: "TEXT", text: "two" },
      ])
    ),
    (error) => {
      assert.equal(error.content_may_have_printed, true);
      assert.equal(error.phase, "PRINT");
      assert.equal(error.metadata.content_started, undefined);
      assert.equal(error.metadata.content_completed, undefined);
      assert.equal(error.cause === instances[0], false);
      return true;
    }
  );
});

test("error cause chain carries no SDK object or raw text", async () => {
  const { adapter, instances } = makeAdapter({ throw_on: "printText" });
  const driver = makeDriver({ sdk_adapter: adapter });
  await driver.initialize();

  await assert.rejects(
    driver.print(receipt([{ type: "TEXT", text: "boom" }])),
    (error) => {
      assert.equal(error.cause, null);
      assert.equal(
        JSON.stringify(error).includes("raw printText failure"),
        false
      );
      assert.equal(JSON.stringify(error).includes("stack"), false);
      return true;
    }
  );
});

test("mid-dispatch adapter error keeps content_started risk on the error", async () => {
  const { adapter, instances } = makeAdapter({ throw_on: "printText" });
  const driver = makeDriver({ sdk_adapter: adapter });
  await driver.initialize();

  // The adapter emits a PRINT-phase error (PRINTER category); once a line was
  // dispatched the driver re-stamps content risk so PrintManager settles
  // UNCERTAIN (B-DRV-07 failure rule).
  await assert.rejects(
    driver.print(receipt([{ type: "TEXT", text: "boom" }])),
    (error) => {
      assert.equal(error.content_may_have_printed, true);
      assert.equal(error.phase, "PRINT");
      return true;
    }
  );
});

test("post-status not READY returns accepted content-complete result with evidence", async () => {
  // statuses consumed in order: initialize (READY), print preflight (READY), post (7)
  const { adapter } = makeAdapter({ statuses: [0, 0, 7] });
  const driver = makeDriver({ sdk_adapter: adapter });
  await driver.initialize();

  const result = await driver.print(
    receipt([{ type: "TEXT", text: "done" }], TEST_PROFILE)
  );
  assert.equal(result.accepted, true);
  assert.equal(result.content_started, true);
  assert.equal(result.content_completed, true);
  assert.equal(result.metadata.post_status_checked, true);
  assert.equal(result.final_status.ready, false);
  assert.equal(result.final_status.metadata.raw_code, 7);
});

test("initialize polls past a cold-start DISCONNECTED status until READY", async () => {
  // -1 twice (service still binding the SPI head), then READY.
  const { adapter, instances } = makeAdapter({ statuses: [-1, -1, 0] });
  const driver = makeDriver({
    sdk_adapter: adapter,
    ready_timeout_ms: 2000,
    ready_poll_interval_ms: 0,
    reinit_after_polls: 2,
  });

  const result = await driver.initialize();
  assert.equal(result.initialized, true);

  const methods = instances[0].calls.map((call) => call.method);
  // Re-init fires on the 2nd not-ready poll (reinit_after_polls: 2).
  assert.deepEqual(methods, [
    "initPrinter",
    "getPrinterStatus",
    "getPrinterStatus",
    "initPrinter",
    "getPrinterStatus",
  ]);
});

test("initialize stops polling on a physical fault instead of burning the budget", async () => {
  const { adapter, instances } = makeAdapter({ status: 7 }); // PAPER_OUT
  const driver = makeDriver({
    sdk_adapter: adapter,
    ready_timeout_ms: 2000,
    ready_poll_interval_ms: 0,
  });

  await assert.rejects(driver.initialize(), (error) => {
    assert.equal(error.code, "PDP_PRINTER_NOT_READY");
    assert.equal(error.content_may_have_printed, false);
    return true;
  });
  // One status sample only: PAPER_OUT will not clear by polling.
  assert.equal(
    instances[0].calls.filter((call) => call.method === "getPrinterStatus")
      .length,
    1
  );
});

test("print waits for the queue to drain before sampling post-dispatch status", async () => {
  const { adapter } = makeAdapter();
  const driver = makeDriver({
    sdk_adapter: adapter,
    paper_profile: TEST_PROFILE,
    post_print_settle_ms: 40,
  });
  await driver.initialize();

  const started = Date.now();
  const result = await driver.print(receipt([], TEST_PROFILE));
  assert.ok(
    Date.now() - started >= 35,
    "post-dispatch status sample must follow the settle wait"
  );
  assert.equal(result.metadata.post_status_checked, true);
});

test("profile-gated setup commands are skipped when the profile leaves them null", async () => {
  const { adapter, instances } = makeAdapter();
  const driver = makeDriver({ sdk_adapter: adapter, paper_profile: TEST_PROFILE });
  await driver.initialize();
  await driver.print(receipt([{ type: "TEXT", text: "x" }], TEST_PROFILE));

  const methods = instances[0].calls.map((call) => call.method);
  assert.equal(methods.includes("setPageFormat"), false);
  assert.equal(methods.includes("setTextWidth"), false);
  // Documented-semantics commands still go out.
  assert.equal(methods.includes("setAlignment"), true);
  assert.equal(methods.includes("setTextStyle"), true);
});

test("profile-gated setup commands are sent when the profile sets them", async () => {
  const { adapter, instances } = makeAdapter();
  const profile = makePaperProfile({
    key: "test",
    logical_width: 8,
    final_feed: 2,
    page_format: 1,
    text_width_dots: 384,
  });
  const driver = makeDriver({ sdk_adapter: adapter, paper_profile: profile });
  await driver.initialize();
  await driver.print(receipt([{ type: "TEXT", text: "x" }], profile));

  const commands = instances[0].calls.map(({ method, value }) => [
    method,
    value,
  ]);
  assert.ok(
    commands.some(([m, v]) => m === "setPageFormat" && v === 1),
    "setPageFormat sent with the profile value"
  );
  assert.ok(
    commands.some(([m, v]) => m === "setTextWidth" && v === 384),
    "setTextWidth sent with the profile value"
  );
});

test("cut returns controlled unsupported result", () => {
  const { adapter } = makeAdapter();
  const driver = makeDriver({ sdk_adapter: adapter });
  const result = driver.cut();
  assert.equal(result.accepted, false);
  assert.equal(result.metadata.error_code, "PDP_DRIVER_CAPABILITY_UNSUPPORTED");
});

test("dispose releases adapter and allows detect again", async () => {
  const { adapter } = makeAdapter();
  const driver = makeDriver({ sdk_adapter: adapter });
  await driver.initialize();
  assert.deepEqual(driver.dispose(), { disposed: true });
  assert.equal((await driver.detect()).available, true);
});

test("driver boundaries do not return the SDK instance", async () => {
  const { adapter, instances } = makeAdapter();
  const driver = makeDriver({
    sdk_adapter: adapter,
    paper_profile: TEST_PROFILE,
  });

  const detect = await driver.detect();
  assert.equal(detect === instances[0], false);
  assert.equal(detect.metadata === instances[0], false);

  const init = await driver.initialize();
  assert.equal(init === instances[0], false);

  const caps = driver.getCapabilities();
  assert.equal(caps === instances[0], false);
});

test("detect bridge failure returns normalized error without SDK object", async () => {
  const { runtime, instances } = makeFakeRuntime();
  const adapter = new IminSdkAdapter({
    runtime: { WebSocket: class {} }, // no IminPrinter -> bridge unavailable
  });
  const driver = makeDriver({ sdk_adapter: adapter });

  const result = await driver.detect();
  assert.equal(result.available, false);
  assert.equal(result.reason, "SDK_ASSET_UNAVAILABLE");
  assert.equal(result.error.code, "PDP_BRIDGE_UNAVAILABLE");
  assert.equal(result.error.cause, null);
  assert.equal(result.error === instances[0], false);
});

// ---------------------------------------------------------------- Task 8 (B5)
// Pre-output failures keep content risk false and never dispatch receipt text.

test("B5: bridge unavailable maps to PDP_BRIDGE_UNAVAILABLE without content risk", async () => {
  const adapter = new IminSdkAdapter({
    runtime: { WebSocket: undefined, IminPrinter: undefined },
    timeout_ms: 5000,
  });
  const driver = makeDriver({ sdk_adapter: adapter });

  const result = await driver.detect();
  assert.equal(result.available, false);
  assert.equal(result.error.code, "PDP_BRIDGE_UNAVAILABLE");
  assert.equal(result.error.phase, "PREFLIGHT");
  assert.equal(result.error.content_may_have_printed, false);
  assert.equal(result.error.metadata.reason, "WEBSOCKET_UNAVAILABLE");
  assert.equal(result.error.cause, null);
});

test("B5: initialization failure maps to PDP_PRINTER_NOT_READY without dispatch", async () => {
  const { adapter, instances } = makeAdapter({ throw_on: "initPrinter" });
  const driver = makeDriver({ sdk_adapter: adapter });

  await assert.rejects(driver.initialize(), (error) => {
    assert.equal(error.code, "PDP_PRINTER_NOT_READY");
    assert.equal(error.phase, "PREFLIGHT");
    assert.equal(error.content_may_have_printed, false);
    return true;
  });
  assert.equal(instances[0].outbound_commands.length, 0);
});

test("B5: not-ready raw statuses map to PDP_PRINTER_NOT_READY before dispatch", async () => {
  for (const raw of [-1, 1, 3, 8, 99]) {
    const { adapter, instances } = makeAdapter({ status: raw });
    const driver = makeDriver({ sdk_adapter: adapter });
    await driver.initialize().catch(() => {});

    await assert.rejects(
      driver.print(receipt([{ type: "TEXT", text: "nope" }])),
      (error) => {
        assert.equal(error.code, "PDP_PRINTER_NOT_READY", `raw=${raw}`);
        assert.equal(error.phase, "PREFLIGHT", `raw=${raw}`);
        assert.equal(error.content_may_have_printed, false, `raw=${raw}`);
        return true;
      }
    );
    assert.equal(
      instances[0].outbound_commands.length,
      0,
      `raw=${raw} dispatched no content`
    );
  }
});

test("B5: toUserError exposes only message keys, code, and actions", async () => {
  const { adapter } = makeAdapter({ status: 7 });
  const driver = makeDriver({ sdk_adapter: adapter });
  await driver.initialize().catch(() => {});

  await assert.rejects(
    driver.print(receipt([{ type: "TEXT", text: "nope" }])),
    (error) => {
      const user_error = toUserError(error);
      assert.deepEqual(Object.keys(user_error).sort(), [
        "allowed_actions",
        "code",
        "message_key",
        "title_key",
      ]);
      assert.equal(user_error.code, "PDP_PRINTER_PAPER_OUT");
      assert.deepEqual(user_error.allowed_actions, ["dismiss"]);
      assert.equal(JSON.stringify(user_error).includes("raw"), false);
      assert.equal(JSON.stringify(user_error).includes("stack"), false);
      return true;
    }
  );
});

test("B5: raw status values stay in driver metadata only", () => {
  const status = mapStatus(7);
  assert.equal(status.state, "PAPER_OUT");
  assert.equal(status.raw_code, null);
  assert.equal(status.raw_message, null);
  assert.equal(status.metadata.raw_code, 7);
  assert.equal(JSON.stringify(status).includes('"raw_code":7'), true);
  assert.equal(JSON.stringify(status).includes('"raw_message"'), true);
});
