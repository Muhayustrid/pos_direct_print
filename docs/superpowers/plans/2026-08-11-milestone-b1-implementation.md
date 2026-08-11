# Milestone B1 SDK Runtime Qualification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin one iMin SDK V1 asset and build a mockable SDK adapter with controlled bridge detection.

**Architecture:** `imin_sdk_adapter.mjs` becomes the only module that handles raw iMin SDK values and objects. Tests inject a fake SDK runtime, inspect outbound commands, and never open a real WebSocket.

**Tech Stack:** ES2022 modules, Node.js `node:test`, `node:assert/strict`, iMin JavaScript Printer SDK V1.4.0, Prettier, ESLint.

## Global Constraints

- Implement only B1-01, B1-02, and B1-03 from `specs/pos-direct-print/milestone-b/tasks.md`.
- Do not implement B1-04, B1-05, B2 through B6, Milestone C, or Milestone D.
- Do not change ERPNext core, Frappe core, or compiled ERPNext assets.
- Do not add production hooks or bootstrap registration.
- Do not open a real WebSocket in automated tests.
- Do not add error codes. Use the frozen taxonomy in `core/errors.mjs`.
- Do not expose raw SDK objects, WebSocket handles, raw errors, or stack traces.
- Treat successful dispatch as command acceptance only, not physical print completion.
- Keep source files under 300 lines when practical.
- Run JavaScript tests from the app root with Node.js.
- Run lint and format through the development container.

## File Structure

- Create `pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js` as the exact vendored copy of the pinned source asset.
- Modify `specs/pos-direct-print/milestone-b/research.md` to record final B1-01 evidence.
- Create `pos_direct_print/public/js/pos_direct_print/drivers/imin_sdk_adapter.mjs` for the raw SDK boundary.
- Create `pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs` for fake-runtime tests.

---

### Task 1: B1-01 Pin and Inventory the SDK Asset

**Files:**
- Create: `pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js`
- Modify: `specs/pos-direct-print/milestone-b/research.md:643-668`

**Interfaces:**
- Consumes: `docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js` as read-only source evidence.
- Produces: an app-owned SDK asset with SHA-256 `d874f3fa2dafa0a729ae0f8f28b4e76825542f64a95c075692ab203a3503fd9a`.
- Produces: a qualification record for Tasks 2 and 3.

- [ ] **Step 1: Recompute source inventory evidence**

Run:

```bash
shasum -a 256 docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js
wc -c docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js
grep -n "IminPrinter.version\|global.IminPrinter\|getPrinterStatus =\|printText =" \
  docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js
```

Expected:

```text
d874f3fa2dafa0a729ae0f8f28b4e76825542f64a95c075692ab203a3503fd9a
29162 bytes
UMD global export: IminPrinter
version: 1.4.0
getPrinterStatus: Promise
printText and style/feed calls: void/fire-and-forget
```

- [ ] **Step 2: Verify the local V2 tree is not a distinct source**

Run:

```bash
diff -qr docs/iMinJSPrinterSDK/v1 docs/iMinJSPrinterSDK/v2
shasum -a 256 docs/iMinJSPrinterSDK/v2/js-demo/html-demo/imin-printer.js
```

Expected: no content difference except the documented V1-only `.DS_Store`. The V2 asset hash must equal the V1 hash.

- [ ] **Step 3: Vendor the exact pinned bytes**

Run:

```bash
mkdir -p pos_direct_print/public/js/lib/imin/1.4.0
cp docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js \
  pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js
cmp -s docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js \
  pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js
shasum -a 256 pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js
```

Expected: `cmp` exits 0 and the vendored hash matches the source hash.

- [ ] **Step 4: Replace section 13.5 with the final pin record**

Record these exact facts in `research.md`:

```markdown
### 13.5 SDK asset pin — B1-01 complete

- source: `docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js`;
- app-owned asset: `pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js`;
- version: `1.4.0`;
- byte size: `29,162`;
- SHA-256: `d874f3fa2dafa0a729ae0f8f28b4e76825542f64a95c075692ab203a3503fd9a`;
- export shape: UMD constructor at `window.IminPrinter`;
- status interface: `getPrinterStatus(connectType)` returns a Promise;
- dispatch interface: initialization, style, text, and feed calls are void/fire-and-forget;
- connect interface: `connect()` returns a Promise and has an internal five-second timeout;
- production loading: deferred to B4-03. B1 does not add hooks;
- local `v2/` evidence: byte-identical V1.4.0, not an authoritative V2 implementation.
```

- [ ] **Step 5: Verify the task diff**

Run:

```bash
git diff --check
git diff -- specs/pos-direct-print/milestone-b/research.md
git status --short
```

Expected: only the vendored asset and B1-01 research record change.

- [ ] **Step 6: Commit B1-01**

```bash
git add \
  pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js \
  specs/pos-direct-print/milestone-b/research.md
git commit -m "chore: pin iMin SDK V1 asset"
```

---

### Task 2: B1-02 Build the Mockable SDK Adapter Boundary

**Files:**
- Create: `pos_direct_print/public/js/pos_direct_print/drivers/imin_sdk_adapter.mjs`
- Create: `pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs`

**Interfaces:**
- Consumes: `normalize(rawError, phase, context)` from `core/error_normalizer.mjs`.
- Consumes: `makeError(code, fields)` from `core/errors.mjs`.
- Produces: `new IminSdkAdapter({ runtime, address, timeout_ms })`.
- Produces: `initialize(connection_type)`, `getStatus(connection_type)`, `setPageFormat(style)`, `setTextWidth(width)`, `setAlignment(alignment)`, `setTextSize(size)`, `setTextStyle(style)`, `printText(line)`, `feed(value)`, and `dispose()`.
- Produces: dispatch result `{ accepted, error, metadata }` and status result `{ ok, value, error, metadata }`.

- [ ] **Step 1: Write fake-runtime helpers and failing construction tests**

Start the test file with:

```javascript
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
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```bash
node --test \
  pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs
```

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `imin_sdk_adapter.mjs`.

- [ ] **Step 3: Add the adapter class and controlled result helpers**

Create `imin_sdk_adapter.mjs` with this public structure:

```javascript
import { normalize } from "../core/error_normalizer.mjs";
import { makeError } from "../core/errors.mjs";

export class IminSdkAdapter {
  #runtime;
  #address;
  #timeout_ms;
  #instance = null;

  constructor({ runtime = globalThis, address = "127.0.0.1", timeout_ms = 5000 } = {}) {
    this.#runtime = runtime;
    this.#address = address;
    this.#timeout_ms = timeout_ms;
  }

  initialize(connection_type) {
    return this.#dispatch("initPrinter", [connection_type], "PREFLIGHT", "PDP_PRINTER_NOT_READY");
  }

  async getStatus(connection_type) {
    try {
      const instance = this.#requireInstance();
      const status = await withTimeout(
        instance.getPrinterStatus(connection_type),
        this.#timeout_ms
      );
      const value = Number(status?.value);
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

  #dispatch(method, args, phase = "PREFLIGHT", code = "PDP_PRINT_COMMAND_FAILED") {
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

function dispatchFailure(raw_error, phase, code) {
  const tagged = makeError(code, { phase, cause: raw_error });
  return {
    accepted: false,
    error: normalize(tagged, phase, { content_started: phase === "PRINT" }),
    metadata: {},
  };
}

function statusFailure(raw_error) {
  const code = raw_error?.code === "PDP_PRINT_TIMEOUT"
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
  return Promise.race([Promise.resolve(promise), timeout]).finally(() => clearTimeout(timer));
}
```

The implementation may move private helpers, but it must keep these public names and result fields.

- [ ] **Step 4: Add failing dispatch, newline, status, and containment tests**

Append these tests:

```javascript
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
  const result = await new IminSdkAdapter({ runtime, timeout_ms: 5 }).getStatus("SPI");

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
```

- [ ] **Step 5: Run focused tests and make them pass**

Run:

```bash
node --test \
  pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs
```

Expected: all Task 2 tests pass. No test opens a real WebSocket.

- [ ] **Step 6: Run existing JavaScript regression tests**

Run:

```bash
find pos_direct_print/public/js/pos_direct_print \
  -path '*__tests__/*.test.mjs' -print -exec node --test {} +
```

Expected: 42 existing tests plus the new Task 2 tests pass with zero failures.

- [ ] **Step 7: Commit B1-02**

```bash
git add \
  pos_direct_print/public/js/pos_direct_print/drivers/imin_sdk_adapter.mjs \
  pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs
git commit -m "feat: add iMin SDK adapter boundary"
```

---

### Task 3: B1-03 Add Controlled Bridge Detection

**Files:**
- Modify: `pos_direct_print/public/js/pos_direct_print/drivers/imin_sdk_adapter.mjs`
- Modify: `pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs`

**Interfaces:**
- Consumes: `new IminSdkAdapter({ runtime, address, timeout_ms })` from Task 2.
- Produces: `await detect()` with `{ available, reason, error, metadata }`.
- Produces reasons: `WEBSOCKET_UNAVAILABLE`, `SDK_ASSET_UNAVAILABLE`, `SDK_CONSTRUCTION_FAILED`, `CONNECTION_FAILED`, and `CONNECTION_TIMEOUT`.

- [ ] **Step 1: Add failing bridge detection tests**

Append these tests:

```javascript
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
  assert.equal(JSON.stringify(result).includes("raw constructor failure"), false);
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
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
node --test \
  pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs
```

Expected: new tests fail because `detect` does not exist.

- [ ] **Step 3: Implement `detect()` above lifecycle operations**

Add this public method near the top of `IminSdkAdapter`:

```javascript
async detect() {
  if (!this.#runtime.WebSocket && !this.#runtime.MozWebSocket) {
    return bridgeUnavailable("WEBSOCKET_UNAVAILABLE");
  }
  if (typeof this.#runtime.IminPrinter !== "function") {
    return bridgeUnavailable("SDK_ASSET_UNAVAILABLE");
  }

  try {
    const instance = this.#requireInstance();
    const connected = await withTimeout(
      instance.connect(),
      this.#timeout_ms
    );
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
    const reason = error?.code === "PDP_PRINT_TIMEOUT"
      ? "CONNECTION_TIMEOUT"
      : this.#instance
        ? "CONNECTION_FAILED"
        : "SDK_CONSTRUCTION_FAILED";
    return bridgeUnavailable(reason, error);
  }
}
```

Add this file-local helper:

```javascript
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
```

Use a local construction flag if private-field state cannot distinguish construction failure from connection failure cleanly. Do not expose the SDK instance to solve that distinction.

- [ ] **Step 4: Run focused and full JavaScript tests**

Run:

```bash
node --test \
  pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs
find pos_direct_print/public/js/pos_direct_print \
  -path '*__tests__/*.test.mjs' -print -exec node --test {} +
```

Expected: all adapter tests and all existing JavaScript tests pass with zero failures.

- [ ] **Step 5: Run required format and lint checks**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench/apps/pos_direct_print && \
   pre-commit run prettier --all-files && \
   pre-commit run eslint --all-files'
```

Inspect formatter changes:

```bash
git diff --check
git status --short
git diff --stat
```

Expected: Prettier and ESLint pass. Diff includes only B1 files and tracked Milestone B documentation.

- [ ] **Step 6: Re-run tests after formatter changes**

Run:

```bash
node --test \
  pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs
find pos_direct_print/public/js/pos_direct_print \
  -path '*__tests__/*.test.mjs' -print -exec node --test {} +
```

Expected: all tests pass with zero failures. Record exact test counts.

- [ ] **Step 7: Check milestone boundaries**

Run:

```bash
git diff --name-only 11d2ed8..HEAD
git diff 11d2ed8..HEAD -- \
  pos_direct_print/public/js/pos_direct_print \
  specs/pos-direct-print/milestone-b/research.md
```

Confirm all statements:

```text
No B1-04 or B1-05 hardware value was guessed.
No imin_v1_driver.mjs exists.
No production hook or bootstrap file changed.
No retry, multi-tab, recovery, model detection, or capability matrix code exists.
No ERPNext or Frappe core file changed.
```

- [ ] **Step 8: Commit B1-03**

```bash
git add \
  pos_direct_print/public/js/pos_direct_print/drivers/imin_sdk_adapter.mjs \
  pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_sdk_adapter.test.mjs
git commit -m "feat: detect iMin V1 bridge availability"
```

- [ ] **Step 9: Stop for the B1 checkpoint**

Report:

```text
B1-01, B1-02, and B1-03 complete.
B1-04 and B1-05 remain blocked by reference-device inventory.
Milestone C and Milestone D remain untouched.
```

Do not start B2 or any physical-device task without a new explicit user approval.
