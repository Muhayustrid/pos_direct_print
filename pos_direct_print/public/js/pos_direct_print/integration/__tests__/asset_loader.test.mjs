import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

import { bootSubsystem, SubsystemBootstrap } from "../../core/bootstrap.mjs";
import { CapabilityRegistry } from "../../core/capability_registry.mjs";

const SDK_URL = "/assets/pos_direct_print/js/lib/imin/1.4.0/imin-printer.js";
const LOADER_URL =
  "/assets/pos_direct_print/js/pos_direct_print/core/bootstrap.mjs";
const sdk_source = readFileSync(
  new URL("../../../lib/imin/1.4.0/imin-printer.js", import.meta.url),
  "utf8"
);
const loader_source = readFileSync(
  new URL("../../web/pos_direct_print.js", import.meta.url),
  "utf8"
);

function make_loader_window({ vue } = {}) {
  const window = { console };
  window.window = window;
  window.self = window;
  if (vue) window.Vue = vue;

  const context = vm.createContext(window);
  const evaluate_sdk = vm.runInContext(
    `(function (source) {
      var evaluate = new Function("window", "self", source);
      evaluate.call(window, window, self);
    })`,
    context
  );
  let sdk_scripts = 0;
  const document = {
    createElement(tag) {
      assert.equal(tag, "script");
      return { async: true, onerror: null, onload: null, src: "" };
    },
    head: {
      appendChild(script) {
        assert.equal(script.src, SDK_URL);
        sdk_scripts++;
        evaluate_sdk(sdk_source);
        script.onload();
      },
    },
  };
  window.document = document;
  return {
    window,
    context,
    get sdk_scripts() {
      return sdk_scripts;
    },
  };
}

async function settle_loader() {
  await new Promise((resolve) => setImmediate(resolve));
}

test("loader hides Vue while evaluating the SDK and restores its identity", async () => {
  const calls = [];
  const vue = {
    use() {
      calls.push(arguments);
      throw new Error("Vue.use must not run");
    },
  };
  const shim = make_loader_window({ vue });

  vm.runInContext(loader_source, shim.context);

  assert.equal(shim.window.Vue, vue);
  assert.equal(calls.length, 0);
  assert.equal(typeof shim.window.IminPrinter, "function");
  await settle_loader();
});

test("loader exposes the SDK when Vue is absent", async () => {
  const shim = make_loader_window();

  vm.runInContext(loader_source, shim.context);

  assert.equal(typeof shim.window.IminPrinter, "function");
  await settle_loader();
});

test("bootSubsystem returns the same result object on repeated calls", () => {
  const context = {
    runtime: { IminPrinter: function IminPrinter() {} },
    settings: { receipt_schema_version: 1 },
  };

  const first = bootSubsystem(context);
  const second = bootSubsystem(context);

  assert.equal(first.initialized, true);
  assert.equal(second, first);
});

test("bootstrap succeeds with a warning when the SDK is absent", () => {
  const registry = new CapabilityRegistry();
  const bootstrap = new SubsystemBootstrap();

  const result = bootstrap.initialize({
    registry,
    runtime: {},
    settings: { receipt_schema_version: 1 },
  });

  assert.equal(result.initialized, true);
  assert.equal(registry.hasDriver("imin_v1"), false);
  assert.ok(
    result.warnings.some((warning) => warning.includes("SDK unavailable"))
  );
});

test("loader boot flag appends the SDK script only once", async () => {
  const shim = make_loader_window();

  vm.runInContext(loader_source, shim.context);
  vm.runInContext(loader_source, shim.context);

  assert.equal(shim.window.__pos_direct_print_booted, true);
  assert.equal(shim.sdk_scripts, 1);
  await settle_loader();
});

// Keep this URL assertion close to the loader test: Frappe's build must not
// rewrite the dynamic import target into a hashed chunk (C-8). The loader
// stores the literal URL and feeds it to import(), so the built bundle must
// still contain the raw path.
test("loader retains the pinned bootstrap URL", () => {
  assert.ok(
    loader_source.includes(LOADER_URL),
    `expected loader source to contain ${LOADER_URL}`
  );
  assert.match(loader_source, /import\(\s*BOOTSTRAP_URL\s*\)/u);
});
