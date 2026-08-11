# Milestone B Research: Single-device Happy Path

**Status:** COMPLETE FOR DESIGN INPUT

**Design readiness:** READY FOR B1 / PARTIALLY READY

Generic SDK, runtime, adapter, receipt, and mock work can start. Hardware-specific qualification and physical UAT wait for the reference device. See section 13 for the classified blockers and section 16 for the readiness summary.

**Baseline:** commit `6c96faaf327b41366b4b889067eb1050650e564d` on 2026-08-10

## 1. Purpose

This document records evidence needed for Milestone B.

Milestone B must print one ERPNext POS v16 transaction on one iMin reference device.

Milestone B does not redesign Milestone A.

## 2. Source priority

Research used sources in this order:

1. Official iMin JavaScript Printer SDK documentation.
2. Curated local documentation.
3. Local iMin demo and SDK assets.
4. Frozen Milestone A specifications, contracts, implementation, and tests.

### 2.1 Official sources

- <https://oss-sg.imin.sg/docs/en/JSPrinterSDK.html>
- <https://oss-sg.imin.sg/docs/en/Printer.html>
- <https://oss-sg.imin.sg/docs/demo/iMinJSPrinterSDK.zip>

The official HTML page is the authoritative API reference.

The official demo bundle gives implementation evidence where the HTML page is silent.

Demo behavior does not become a contract without an explicit Milestone B decision.

### 2.2 Local sources

- `docs/JSPrinterSDK_iMin/JSPrinterSDK_iMin_AI_AGENT.md`
- `docs/iMinJSPrinterSDK/v1/js-demo/JSPrintDemoDoc.pdf`
- `docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js`
- `docs/iMinJSPrinterSDK/v1/js-demo/html-demo/index.html`
- `docs/iMinJSPrinterSDK/v1/js-demo/html-demo/chunk-print.js`
- `docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-customer-odoo.js`
- `docs/iMinJSPrinterSDK/v1/vue-demo/vue2-demo/src/App.vue`
- `docs/iMinJSPrinterSDK/v1/vue-demo/vue2-demo/src/assets/imin-printer.esm.browser.js`
- `docs/iMinJSPrinterSDK/v1/vue-demo/vue3-demo/src/App.vue`
- `docs/iMinJSPrinterSDK/v1/vue-demo/vue3-demo/src/assets/imin-js-printer.vue3.js`
- `docs/iMinJSPrinterSDK/v1/uni-app-demo/iMin-uniApp-Print-v1.0.1-2026-01-22.zip`
- `docs/iMinJSPrinterSDK/v2/` (read-only reconnaissance only; not Milestone B implementation input)

No file under `docs/` was changed.

### 2.3 Milestone A sources

Research covered:

- `AGENTS.md`
- `specs/pos-direct-print/constitution.md`
- `specs/pos-direct-print/research.md`
- `specs/pos-direct-print/spec.md`
- `specs/pos-direct-print/plan.md`
- `specs/pos-direct-print/data-model.md`
- `specs/pos-direct-print/tasks.md`
- `specs/pos-direct-print/progress.json`
- all 17 files under `specs/pos-direct-print/contracts/`
- all Milestone A production files under `pos_direct_print/`
- all Milestone A Python and JavaScript tests
- commit `d7bf87a` and merge commit `6c96faa`

The audit evidence records 131 Python tests and 42 JavaScript tests.

## 3. Frozen Milestone A dependencies

Milestone B must reuse these boundaries:

- POS interception through `POSIntegrationAdapter` only.
- Browser fallback through the saved ERPNext print method only.
- Orchestration through `PrintManager` only.
- Persistence transitions through `JobCoordinator` and `PrintApi` only.
- Receipt creation through `ReceiptBuilder` and `ReceiptDocument` only.
- Driver behavior through `BaseDriver` only.
- Errors through the existing error taxonomy and `ErrorNormalizer` only.
- Job and Attempt audit records through the existing permission model only.
- Existing state transitions, retry rules, and `UNCERTAIN` semantics.

Milestone B must not call iMin APIs from POS integration.

Milestone B must not introduce a second orchestration path.

## 4. Runtime and JavaScript bridge

### 4.1 Proven official behavior

The shipped SDK asset exposes the `IminPrinter` constructor.

The UMD bundle assigns it to `window.IminPrinter`.

The constructor accepts an address.

The default address is `127.0.0.1`.

The SDK opens `ws://<address>:8081/websocket`.

Image upload uses `http://<address>:8081/upload`.

The SDK therefore uses a local WebSocket service.

It is not a JavaScript object injected by Android WebView.

`connect()` provides the runtime availability signal.

The SDK rejects when the browser lacks WebSocket support.

### 4.2 Demo behavior

The HTML demo creates this variable:

```js
var IminPrintInstance = new IminPrinter(
  localStorage.getItem("IP") || "127.0.0.1"
);
```

`IminPrintInstance` is a demo variable.

It is not the global object exported by the SDK asset.

The demo calls `connect()` before `initPrinter()`.

### 4.3 Bridge-unavailable detection for Milestone B

The minimum evidence chain is:

1. `window.WebSocket` exists.
2. the approved SDK asset loaded and exposes `window.IminPrinter`.
3. SDK construction succeeds.
4. `connect()` resolves `true` within the SDK timeout.

Failure at steps 1 through 4 is bridge or runtime unavailability.

The failure must normalize to `PDP_BRIDGE_UNAVAILABLE` before content starts.

### 4.4 Reload behavior

The page owns the SDK instance and WebSocket connection.

A browser reload destroys page JavaScript state.

The new page must create a new SDK instance and connect again.

No source proves that a reload clears native printer buffers.

The official documentation states that `initPrinter()` does not clear buffered data.

Milestone B must not treat reload as a print-recovery operation.

### 4.5 SDK generation decision

Decision record, revised 2026-08-10:

- Milestone B runtime target is iMin JS Printer SDK V1 plus `iMinprinterplugin` on one V1-qualified reference device;
- the project fleet is not assumed to be uniformly Android 11 or lower and may contain more than one SDK/runtime generation;
- Android version is qualification evidence, never the production source of truth for driver selection;
- runtime selection follows configured and qualified terminal data, beginning with `POS Print Terminal.driver_key` plus related capability/qualification evidence;
- Milestone B selects only `imin_v1` and does not design or implement `imin_v2`;
- future SDK generations, including V2, and detection/reconciliation policy belong to Milestone D.

Official `Printer.html` currently describes V1 for Android 11 and below with `iMinprinterplugin`, and V2 for Android 13 and above without that plugin. It does not document Android 12 coverage. These compatibility ranges guide qualification; they do not justify hardcoded `if android_version` driver selection.

## 5. Initialization

### 5.1 Official API

The official reference shows:

```js
IminPrintInstance.initPrinter(connectType)
```

Supported connection types are:

- `USB`
- `SPI`
- `Bluetooth`

The shipped SDK uses `PrinterType.USB`, `PrinterType.SPI`, and `PrinterType.Bluetooth`.

The official HTML example uses `IminPrintInstance.PrintConnectType.SPI`.

This naming difference is an asset-versus-reference conflict.

### 5.2 Semantics

The official HTML page states that initialization resets printer logic settings.

Examples include layout and bold state.

The same page states that initialization does not clear buffer data.

Unfinished print jobs may continue after initialization.

The shipped JavaScript method sends a command and returns no completion proof.

No official API documents an initialization completion callback.

### 5.3 Delay

The official API reference does not require a delay.

The uni-app demo waits 500 ms after `connect()`.

The demo describes this as connection stabilization.

This delay is a demo pattern, not an official contract.

Milestone B must not add a fixed delay until the reference device needs it.

### 5.4 Minimal qualification sequence

The minimum sequence supported by evidence is:

1. load the approved SDK asset;
2. construct the SDK instance;
3. call `connect()`;
4. require `connect() === true`;
5. call `initPrinter(REFERENCE_CONNECT_TYPE)`;
6. call `getPrinterStatus(REFERENCE_CONNECT_TYPE)`;
7. require normalized status `READY`.

`REFERENCE_CONNECT_TYPE` remains unresolved until the device is identified.

## 6. Printer status

### 6.1 API shape

The official HTML page presents a callback form.

The shipped SDK v1.4.0 returns a Promise.

The Promise resolves an object containing `value` and `text`.

This is a source conflict.

Milestone B must pin one SDK asset and test its exact interface.

### 6.2 Raw status evidence

The official material and SDK source provide these values:

- `0`: normal, present in the SDK enum and all demos.
- `-1`: printer not connected.
- `1`: printer not powered on.
- `3`: print head open.
- `7`: no paper feed.
- `8`: paper running out.
- `99`: other errors.

The official HTML status table omits `0`.

The SDK source names `0` as `NORMAL`.

All official demos use `status.value === 0` as normal.

### 6.3 Milestone B READY definition

Milestone B may define `READY` as raw numeric or string value `0` only after:

1. the exact SDK asset is pinned;
2. the reference device returns `0` during qualification;
3. paper is loaded;
4. the cover is closed;
5. a physical test print succeeds.

Until these checks pass, the mapping remains unresolved.

### 6.4 Minimum statuses

Milestone B must distinguish:

- `READY`;
- `BRIDGE_UNAVAILABLE`;
- `INITIALIZATION_FAILED`;
- `PAPER_OUT` before output;
- other not-ready states.

Suggested mappings use existing Milestone A values:

- raw `0` to `READY`, after qualification;
- raw `7` to `PAPER_OUT`;
- failed connection to `BRIDGE_UNAVAILABLE`;
- initialization exception or failed post-init status to `INITIALIZATION_FAILED` or `UNKNOWN_ERROR`;
- raw `3`, `8`, `99`, `-1`, and `1` to existing conservative states.

Milestone D owns the full cross-model status matrix.

## 7. Text printing

### 7.1 APIs

The official reference documents:

```js
printText(text)
printText(text, type)
printColumnsText(texts, widths, alignments, sizes, width)
setAlignment(alignment)
setTextSize(size)
setTextTypeface(typeface)
setTextStyle(style)
setTextLineSpacing(space)
setTextWidth(width)
```

### 7.2 Newline and buffering

The official reference states that short text may remain buffered.

For `printText(text, 0)`, it requires a trailing newline for immediate printing.

The shipped no-type method appends a newline internally.

The shipped typed method contains inconsistent trailing-character logic.

The local demo often appends `\n` explicitly, but doing that with the shipped no-type method would append a second newline.

Milestone B must avoid the ambiguous typed overload for receipt lines.

For the primary UMD candidate, the adapter accepts a logical line with trailing newlines removed and calls the no-type `printText(line)` path; the pinned SDK then appends exactly one `\n` to the outbound command.

The canonical command payload, not the pre-SDK argument, must contain exactly one trailing `\n`.

Tests must inspect the controlled outbound command and assert exact order and newline content.

### 7.3 Columns and wrapping

The SDK source and demos agree on this actual order:

```js
printColumnsText(texts, widths, alignments, sizes, width)
```

The official prose lists `width` and `size` inconsistently.

Milestone B does not need native column printing.

Existing `ReceiptLayout` and `TextWrapper` can produce fixed-width lines.

This avoids a disputed SDK signature.

Milestone B may revisit native columns after reference-device evidence.

### 7.4 Style

Printer style is stateful.

Initialization resets style settings without clearing buffered content.

Milestone B must set required style before each receipt section.

The minimal profile uses left alignment and monospace text where supported.

No logo, QR, barcode, or cutter is required.

## 8. Paper format

Official API:

```js
setPageFormat(style)
```

Documented values are:

- `0`: 80 mm;
- `1`: 58 mm.

Local demo evidence uses:

- 576 dots for 80 mm;
- 384 dots for 58 mm.

Decision record, 2026-08-10: printing design is universal at the architecture level through a normalized `PaperProfile` and `DriverCapabilities`.

Rules:

- no model name is hardcoded in business, POS, or receipt code;
- no `if model == X then 58 mm` style logic is allowed;
- canonical flow is `ReceiptDocument` to normalized `PaperProfile` / `DriverCapabilities` to layout and rendering to `imin_v1`;
- Milestone B uses a parameterized normalized paper profile;
- the exact physical paper width of the reference device is not an architecture blocker;
- the exact width must be known before final receipt layout qualification and physical UAT;
- full cross-width and cross-model qualification stays deferred to Milestone D.

## 9. Feed and receipt end

Official APIs:

```js
printAndLineFeed()
printAndFeedPaper(value)
```

`printAndLineFeed()` advances one line.

`printAndFeedPaper(value)` accepts values from 0 through 255.

The documentation does not define the unit mapping precisely.

A final feed is needed so the last content clears the print head.

The exact feed value requires reference-device UAT.

A feed command proves dispatch only.

It does not prove physical completion.

## 10. Completion semantics

### 10.1 Proven facts

No documented text-print method provides:

- a print job identifier;
- a completion callback;
- a hardware completion event;
- a paper-motion acknowledgment;
- a physical-output acknowledgment.

`printText()` returns after command dispatch.

`printAndFeedPaper()` returns after command dispatch.

`printSingleBitmap()` resolves after upload and command dispatch.

None proves that paper finished printing.

`initPrinter()` can preserve unfinished buffered content.

### 10.2 Evidence for `PRINTING` to `VERIFYING`

The following evidence is sufficient to enter `VERIFYING`:

1. preflight status was `READY`;
2. every minimal receipt command was dispatched in order;
3. each content line ended with a newline;
4. the final feed command was dispatched;
5. no synchronous SDK error occurred;
6. no connection-loss signal occurred before final dispatch.

This evidence proves complete command dispatch.

It does not prove physical output.

### 10.3 Evidence for `VERIFYING` to `SUCCEEDED`

The SDK V1 sources do not provide strong physical-completion evidence.

A post-dispatch `READY` status is a weak operational signal.

It does not prove that all paper output finished.

Decision record, 2026-08-10: **Option A approved.**

- **B-COMP-A (APPROVED):** allow `SUCCEEDED` after full dispatch, final feed, no synchronous SDK error or connection loss before the end of dispatch, and a bounded post-dispatch `READY` status check. `SUCCEEDED` is the best-available SDK-confirmed operational completion, not physical-completion proof. `verification_supported` remains false. Errors after `content_started` settle `UNCERTAIN` with no same-job retry.
- **B-COMP-B (REJECTED):** blocks the happy-path Definition of Done.
- **B-COMP-C (REJECTED):** no approved evidence source; gating belongs to later milestones.

Physical UAT observation cannot serve as runtime evidence for every Job.

It can only validate the chosen operational criterion on the reference device.

## 11. Demo analysis

### 11.1 Actual SDK asset

`docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js` is an unminified SDK bundle.

It identifies itself as version 1.4.0.

It exports `IminPrinter`.

It uses a local WebSocket and HTTP upload service.

### 11.2 Initialization pattern

The demos use this sequence:

1. construct `IminPrinter`;
2. call `connect()`;
3. call `initPrinter()`;
4. poll `getPrinterStatus()`;
5. treat value `0` as normal.

Some demos add 500 ms before initialization.

This delay is not official API behavior.

### 11.3 Printing pattern

The demos set style before text.

They use text, columns, bitmap, feed, and cutter methods.

Receipt demos often append explicit newlines.

Styled receipt demos often render a bitmap.

Milestone B will not use bitmap printing.

Bitmap rendering adds unnecessary browser and completion ambiguity.

### 11.4 Completion pattern

The SDK Promise for bitmap printing resolves after dispatch.

The demos then issue feed or cut commands.

`imin-customer-odoo.js` states that resolve means queued commands, not printed paper.

That file uses status polling and a 200 ms delay as a workaround.

Neither operation proves physical completion.

### 11.5 Cleanup pattern

The SDK source contains `close()`.

The official HTML API page does not document it.

The uni-app demo calls `close()` during component destruction.

Milestone B may use `close()` only after pinning and qualifying the asset.

### 11.6 Model branches

The SDK includes model-specific features such as double QR and cutters.

The demos contain asset differences around `partialCutPaper()`.

Milestone B excludes these paths.

Milestone D owns model capability matrices.

## 12. Conflicts

### R-CONFLICT-01: global object

- Curated document: `window.IminPrintInstance`.
- SDK asset: `window.IminPrinter` constructor.
- Demo: creates local `IminPrintInstance`.
- Decision: pin SDK asset and construct an owned instance.

### R-CONFLICT-02: status API style

- Official HTML: callback example.
- SDK v1.4.0: Promise return.
- Decision: unresolved until asset is pinned.

### R-CONFLICT-03: READY status

- Official HTML table: omits `0`.
- SDK enum and demos: `0` is normal.
- Decision: qualify `0` on reference device before freezing.

### R-CONFLICT-04: text newline behavior

- Official prose: trailing newline flushes typed text.
- SDK variants: inconsistent typed-overload logic.
- Decision: use explicit newline with the simple text path.

### R-CONFLICT-05: column argument order

- Official prose and example disagree.
- SDK source and demos use sizes before total width.
- Decision: do not use native columns in Milestone B.

### R-CONFLICT-06: cleanup

- Official HTML: no cleanup method.
- SDK source: `close()` exists.
- Decision: asset qualification must verify cleanup behavior.

### R-CONFLICT-07: completion

- No source proves physical completion.
- Demos use delay and status polling.
- Decision: unresolved architecture decision B-COMP.

## 13. Reference device qualification record

Decision record, 2026-08-10: requirements are classified into four groups. A single undifferentiated blocker list is no longer used.

Reference device policy: Milestone B needs one physical reference device to prove the happy path. The architecture must not depend permanently on one model. The reference device validates physical behavior, transport, bridge behavior, layout, timing, and status semantics. It is not a reason to hardcode the system around one model. Unknown hardware facts are marked `PENDING REFERENCE DEVICE INVENTORY`, never guessed.

### 13.1 Category A — mandatory before any B implementation

Only items that make even generic SDK, runtime, and mock implementation impossible without assumptions belong here.

| Requirement | State |
| --- | --- |
| B-COMP completion criterion approved | DECIDED — APPROVED: Option A |
| B-AC-01 receipt snapshot binding approved | DECIDED — APPROVED |
| Milestone B runtime target = SDK V1 + plugin on one V1-qualified reference device | DECIDED |
| Parameterized PaperProfile architecture approved | DECIDED |

No remaining Category A blocker exists.

### 13.2 Category B — mandatory before hardware-specific B tasks

| Requirement | State |
| --- | --- |
| Exact reference device model | PENDING REFERENCE DEVICE INVENTORY |
| Actual transport for runtime initialization | PENDING REFERENCE DEVICE INVENTORY |
| Exact physical paper width for the final receipt profile | PENDING REFERENCE DEVICE INVENTORY |
| Hardware-specific initialization evidence, including raw READY value | PENDING REFERENCE DEVICE INVENTORY |

### 13.3 Category C — mandatory before physical UAT

| Requirement | State |
| --- | --- |
| Exact Android version as qualification evidence | PENDING REFERENCE DEVICE INVENTORY |
| Browser name and version running ERPNext POS v16 | PENDING REFERENCE DEVICE INVENTORY |
| `iMinprinterplugin` version or local service confirmation | PENDING REFERENCE DEVICE INVENTORY |
| Actual `READY = 0` verification on the device | PENDING REFERENCE DEVICE INVENTORY |
| Actual local WebSocket endpoint verification | PENDING REFERENCE DEVICE INVENTORY |
| Final feed value | PENDING REFERENCE DEVICE INVENTORY |
| Cold-start connection timing and any required post-connect delay | PENDING REFERENCE DEVICE INVENTORY |
| Actual physical wrapping and layout verification | PENDING REFERENCE DEVICE INVENTORY |

### 13.4 Category D — diagnostic and qualification metadata

| Requirement | State |
| --- | --- |
| ROM or build identifier | optional evidence |
| WebView version, only if the POS page runs inside one | optional evidence |
| Printer firmware version | optional evidence |
| Extra timing metrics | optional evidence |

## 13.5 SDK asset pin

B1 owns the SDK asset pin. The pin is a B1 implementation prerequisite, not a documentation blocker.

Candidate based on the local inventory:

- primary candidate: `docs/iMinJSPrinterSDK/v1/js-demo/html-demo/imin-printer.js`, UMD build, version 1.4.0, global `IminPrinter`, matches plain browser script loading;
- alternative: `docs/iMinJSPrinterSDK/v1/vue-demo/vue2-demo/src/assets/imin-printer.esm.browser.js`, same version, ESM, different `printText` clamping and extra `partialCutPaper`;
- alternative: the uni-app fork inside `docs/iMinJSPrinterSDK/v1/uni-app-demo/`, version `1.4.0-uniapp`, guarded init and status timeout, different interface semantics.

B1 must record for the pinned asset: exact file, version, checksum, asset loading strategy, and expected exported API shape. The primary candidate is expected because Milestone B loads a browser script, but the pin decision belongs to B1-01 with the recorded evidence.

Static audit evidence for the current primary candidate at the versioned V1 path:

- version `1.4.0`, MIT banner, UMD export to browser global `window.IminPrinter`;
- size 29,162 bytes;
- SHA-256 recomputed from current bytes: `d874f3fa2dafa0a729ae0f8f28b4e76825542f64a95c075692ab203a3503fd9a`;
- this matches the previous audit digest exactly; only the inventory path changed;
- `connect()` is Promise-based with an internal five-second timeout;
- `getPrinterStatus()` is Promise-based and may remain pending without a matching callback, so B-RUN-05's injected timeout is mandatory;
- initialization, style, text, and feed calls are void/fire-and-forget;
- the same-directory file named `imin-printer.min.js` is not assumed to be a distinct optimized build; B1 must compare its checksum/content before considering it;
- browser loading has no required third-party dependency, but the bundle auto-installs itself if `window.Vue` already exists;
- the SDK hardcodes `ws://` and `http://` local-service transports. HTTPS-served POS compatibility is a physical-environment qualification item because browser mixed-content policy may block the local bridge.

No file under `docs/` is copied or modified by this decision.

### 13.6 V2 inventory reconnaissance (read-only)

Official iMin documentation distinguishes a V2 runtime for Android 13 and above that does not require `iMinprinterplugin`. However, the current local `docs/iMinJSPrinterSDK/v2/` tree does **not** contain distinct V2 JavaScript bytes:

- `v2/js-demo/html-demo/imin-printer.js` is byte-identical to the V1 UMD asset: version 1.4.0, 29,162 bytes, SHA-256 `d874f3fa2dafa0a729ae0f8f28b4e76825542f64a95c075692ab203a3503fd9a`;
- `diff -qr` finds no content differences between the V1 and V2 trees except a V1-only `.DS_Store`;
- therefore the local folder label is not evidence of a distinct V2 runtime/API and must not be used to design or implement `imin_v2`.

No material BaseDriver conflict can be proven from current V2-local bytes. Existing methods (`detect`, `initialize`, `getStatus`, `print`, `feed`, `cut`, `dispose`, `getCapabilities`) remain a suitable abstraction seam at this reconnaissance depth. Real V2 implementation planning must begin only after an authoritative distinct V2 asset/interface is obtained and qualified in Milestone D.

Official/source conflict record:

- official `Printer.html`: V2 = Android 13+, no `iMinprinterplugin`;
- current local `v2/` JavaScript: same V1.4.0 local-WebSocket implementation as `v1/`;
- resolution: do not assume the local `v2/` folder contains V2; do not resolve API shape by guesswork.

### 13.7 Driver selection principle

Milestone B uses configured `POS Print Terminal.driver_key = imin_v1` for its V1-qualified reference terminal. No production rule may select SDK generation solely from Android version. Android version, plugin/service presence, transport, capabilities, and qualification status are evidence attached to a terminal; future reconciliation/detection policy belongs to Milestone D.

## 14. Milestone A implementation gaps relevant to B

### R-GAP-01: receipt snapshot persistence

Milestone A defines `receipt_snapshot` and `receipt_hash` fields.

Current `PrintManager` builds the receipt after Job reservation.

Current RPC contracts do not persist the built receipt on the Job.

Milestone B end-to-end audit cannot prove frozen snapshot behavior without a contract refinement.

This is proposed architecture change `B-AC-01`.

It does not require a schema change.

Approval was granted on 2026-08-10 because Milestone A contracts are frozen.

### R-GAP-02: POS terminal context

`POSIntegrationAdapter` expects terminal and idempotency context on the POS summary.

No current module attaches that context in a real POS session.

Milestone B may add wiring through existing settings and terminal APIs.

This is an extension, not a persistence change.

### R-GAP-03: frontend asset entry

The current hook file does not load the POS bootstrap asset.

Milestone B needs an app-owned asset entry.

This must not modify ERPNext or Frappe core.

### R-GAP-04: stale project text

`AGENTS.md` contains stale statements about missing implementation.

This package relies on audited repository state instead.

This package does not modify `AGENTS.md`.

### R-GAP-05: actual PrintManager lifecycle/state sequencing

Actual commit `6c96faa` `PrintManager.requestPrint` reserves, builds the receipt, starts the Attempt, and calls `driver.print()` without invoking `detect`, `initialize`, or `getStatus`. It transitions `PREFLIGHT -> PRINTING -> VERIFYING` only after driver dispatch returns.

The frozen BaseDriver lifecycle and Milestone A PrintManager responsibilities require orchestration to coordinate driver lifecycle and state transitions. Milestone B's physical-risk boundary requires READY before `PREFLIGHT -> PRINTING`, then dispatch while the Job is `PRINTING`.

This is an actual implementation-to-frozen-contract mismatch, not a new Milestone B architecture decision. It does not block B1-01 through B1-03. B2-02, B2-04, and B2-06 remain blocked until a separately authorized Milestone A implementation remediation aligns the code with the frozen lifecycle/state semantics.

## 15. Architecture changes

### B-AC-01: bind receipt snapshot to reserved Job

**Status:** DECIDED — APPROVED as a minimal guarded refinement, 2026-08-10.

**Approved sequence:** reserve → build canonical `ReceiptDocument` → bind `receipt_snapshot` + `receipt_hash` → start attempt → preflight → physical print.

**Approved binding rules:**

- requires active valid reservation ownership;
- happens before Attempt creation and before any physical output;
- validates `ReceiptDocument` against schema version 1;
- verifies `receipt_hash` is the actual hash of the canonical snapshot, not just a format check;
- server parses the canonical JSON, validates schema version 1, canonicalizes parsed data with the same recursively sorted-key JSON algorithm, and recomputes the existing `pdpr1:` FNV-1a hash; cross-language hash vectors are required before endpoint enablement;
- stores snapshot and hash atomically through a guarded UPDATE requiring RESERVED state, a non-empty matching reservation token, and empty binding fields;
- both fields become immutable because the guarded mutation rejects rebinding;
- no permission-model change;
- no new persistence schema.

**Deferred within this refinement:** whether REPRINT reuses the parent snapshot or rebuilds from the invoice. That decision belongs to the reprint contract milestone and is not resolved here.

**Schema impact:** none.

**Permission impact:** none.

**Frozen-contract impact:** guarded refinement of `print-api.md` and `job-coordinator.md`.

### B-AC-02: completion criterion

**Status:** DECIDED — APPROVED as B-COMP Option A, 2026-08-10.

**Schema impact:** none.

**State-machine impact:** none.

**Frozen-contract impact:** DriverPrintResult interpretation refinement only.

## 16. Research conclusion

Research supports a single-device driver design.

Research does not support a physical-completion claim from SDK returns.

All design decisions are resolved:

- B-COMP: Option A approved. See `contracts/print-completion.md`.
- B-AC-01: approved as a minimal guarded refinement. See section 15.
- Milestone B runtime: V1 plus `iMinprinterplugin` on one V1-qualified reference device; fleet/runtime generation remains heterogeneous. See sections 4.5 and 13.7.
- Paper profile: parameterized normalized profile, no model hardcoding. See section 8.

Reference-device hardware facts remain pending and are classified in section 13.

Milestone B status is **READY FOR B1 / PARTIALLY READY**. Generic B1 work can start. Hardware-specific tasks wait for Category B facts. Physical UAT waits for Category C facts.

### 16.1 Task readiness summary

| Batch | Readiness |
| --- | --- |
| B1 | READY NOW: B1-01, B1-02, B1-03. PENDING REFERENCE DEVICE INVENTORY: B1-04, B1-05. |
| B2 | READY NOW: B2-01, B2-03 mapping structure, B2-04 dispatch sequence, B2-06. READY AFTER B1: B2-02. Hardware values pending: B2-05 feed value. |
| B3 | READY NOW: B3-01 parameterized profile, B3-02, B3-03. Final width pending before B6. |
| B4 | READY NOW: B4-01, B4-02, B4-03. BLOCKED UNTIL PHYSICAL UAT: B4-04. |
| B5 | READY NOW: B5-01, B5-02, B5-03. |
| B6 | BLOCKED UNTIL PHYSICAL UAT. |

### 16.2 Architecture changes to frozen Milestone A

The only change to frozen Milestone A contracts is the approved B-AC-01 minimal guarded refinement of `print-api.md`, `job-coordinator.md`, and `print-manager.md` ordering. No other Milestone A change is introduced by this package. Exact proposed deltas are reported separately and reference B-AC-01.
