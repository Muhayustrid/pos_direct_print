# Milestone B Tasks

**Authorization:** B1 generic tasks and other READY NOW tasks may start after explicit batch approval. Hardware-specific and physical tasks remain unauthorized until their gates clear.

Package status: **READY FOR B1 / PARTIALLY READY**.

Resolved gates, 2026-08-10:

- `B-COMP` approved: Option A in `contracts/print-completion.md`;
- `B-AC-01` approved: minimal guarded refinement in `plan.md` section 9;
- Milestone B runtime: V1 plus `iMinprinterplugin` on one V1-qualified reference device; fleet project may contain other SDK generations deferred to Milestone D;
- paper profile: parameterized, no model hardcoding.

Readiness labels used below:

- `READY NOW`
- `READY AFTER B1`
- `BLOCKED BY REFERENCE DEVICE`
- `BLOCKED UNTIL PHYSICAL UAT`
- `BLOCKED BY UNRESOLVED DESIGN`

Hardware-dependent tasks carry `PENDING REFERENCE DEVICE INVENTORY` and never guess model names.

Sequencing rules:

- B1 through B5 run sequentially within Milestone B;
- B6 requires B1 through B5 complete and the physical reference device present;
- transitions between batches require explicit user review and approval;
- every task must leave the automated suite green;
- no task may modify ERPNext or Frappe core files.

## B1 — SDK Runtime Qualification

### B1-01: Pin and inventory the SDK asset

**Readiness:** READY NOW

**Scope:**

- select exactly one SDK V1 asset for Milestone B from the versioned `docs/iMinJSPrinterSDK/v1/` inventory;
- record current source path, recomputed checksum, byte size, version, export shape, and interface style;
- record that the local `v2/` tree is byte-identical V1.4.0 evidence and is not an authoritative distinct V2 implementation source;
- store the qualification record in `research.md` section 13.

**Explicit non-scope:** modifying anything under `docs/`; adding the asset to production hooks.

**Dependency:** none.

**Exit condition:** one asset pinned with checksum and interface evidence.

**Proves:** B-DOD-01 input.

**Passes:** B-AT-01 input.

### B1-02: SDK adapter boundary with mock

**Readiness:** READY NOW

**Scope:**

- define the mockable adapter interface in `imin_sdk_adapter.mjs`;
- implement a fake SDK boundary for tests only;
- assert the adapter never exposes raw SDK objects;
- normalize the primary candidate's void/fire-and-forget dispatch calls into controlled dispatch results;
- assert the outbound text command contains exactly one trailing newline and does not double-append it.

**Explicit non-scope:** real device behavior; reliability logic.

**Dependency:** B1-01.

**Exit condition:** mock adapter tests pass without device.

**Proves:** B-DOD-13, B-DOD-16.

**Passes:** B-AT-01, B-AT-02, B-AT-13, B-AT-20.

### B1-03: Bridge detection

**Readiness:** READY NOW

**Scope:**

- detect WebSocket support;
- detect SDK asset presence;
- detect connection success or failure.

**Explicit non-scope:** reconnection policy; multi-tab behavior.

**Dependency:** B1-02.

**Exit condition:** detection returns controlled results for available and unavailable cases.

**Proves:** B-DOD-01.

**Passes:** B-AT-01, B-AT-02.

### B1-04: Reference transport selection

**Readiness:** BLOCKED BY REFERENCE DEVICE — PENDING REFERENCE DEVICE INVENTORY

**Scope:**

- choose `USB`, `SPI`, or `Bluetooth` for the V1-qualified reference device;
- record exact model, Android version, browser/version, physical paper width, plugin/service availability, local endpoint behavior, READY result, feed behavior, and transport as qualification evidence;
- record the chosen transport and `driver_key = imin_v1` in terminal configuration; never derive driver generation solely from Android-version branching.

**Explicit non-scope:** transport switching; other models.

**Dependency:** B1-03 and reference device identification.

**Exit condition:** transport recorded and justified by device evidence.

**Proves:** B-DOD-02 input.

**Passes:** B-AT-03 input.

### B1-05: Initialization and READY qualification

**Readiness:** BLOCKED BY REFERENCE DEVICE — PENDING REFERENCE DEVICE INVENTORY

**Scope:**

- run connect, init, and status sequence on the reference device;
- confirm raw `READY` value;
- record cold-start connection time and any required delay.

**Explicit non-scope:** retry policy; recovery.

**Dependency:** B1-04.

**Exit condition:** qualification record filled in `research.md` section 13.

**Proves:** B-DOD-02, B-DOD-03.

**Passes:** B-AT-03, B-AT-05.

## B2 — iMin V1 Driver Happy Path

### B2-01: Driver skeleton

**Readiness:** READY AFTER B1

**Scope:**

- create `imin_v1_driver.mjs` extending `BaseDriver`;
- register it under key `imin_v1` in `CapabilityRegistry`;
- satisfy constructor and `driver_key` requirements.

**Explicit non-scope:** SDK calls; reliability.

**Dependency:** B1-02.

**Exit condition:** driver instantiates and registers; tests pass.

**Proves:** B-DOD-04 input.

**Passes:** B-AT-04 input.

### B2-02: detect and initialize

**Readiness:** BLOCKED BY MILESTONE A IMPLEMENTATION REMEDIATION — then READY AFTER B1; device initialization evidence PENDING REFERENCE DEVICE INVENTORY

**Scope:**

- map adapter bridge result to `detect`;
- map adapter init result to `initialize`;
- normalize initialization failure to existing error codes.

**Explicit non-scope:** re-initialization policy.

**Dependency:** B1-03, B1-05, B2-01, dan remediation actual Milestone A PrintManager lifecycle/state sequencing yang didokumentasikan di `plan.md` §1.6.

**Exit condition:** init success and failure tests pass with mock SDK.

**Proves:** B-DOD-02.

**Passes:** B-AT-03, B-AT-04, B-AT-14.

### B2-03: getStatus mapping

**Readiness:** READY NOW — provisional mapping must be confirmed by B1-05

**Scope:**

- map raw statuses to existing `PrinterState` vocabulary;
- preserve raw evidence in driver metadata only.

**Explicit non-scope:** full status matrix; status polling service.

**Dependency:** B1-05, B2-02.

**Exit condition:** READY, paper out, not ready, and unknown cases map correctly.

**Proves:** B-DOD-03, B-DOD-16.

**Passes:** B-AT-05, B-AT-06, B-AT-20.

### B2-04: print happy path

**Readiness:** BLOCKED BY MILESTONE A IMPLEMENTATION REMEDIATION — then READY AFTER B1

**Scope:**

- render minimal `ReceiptDocument` to text commands;
- dispatch style, text, and feed commands through the adapter;
- set `content_started` at first content dispatch and `content_completed` after final feed dispatch;
- produce the `DriverPrintResult`.

**Explicit non-scope:** physical completion proof; mid-print recovery.

**Dependency:** B2-03.

**Exit condition:** command sequence test passes and result shape matches Milestone A.

**Proves:** B-DOD-04, B-DOD-05 input.

**Passes:** B-AT-07 input, B-AT-15, B-AT-16.

### B2-05: feed, capabilities, cut, dispose

**Readiness:** READY AFTER B1 — final feed value PENDING REFERENCE DEVICE INVENTORY

**Scope:**

- implement `feed` with the approved final feed value;
- implement minimal `getCapabilities`;
- return controlled outcome from `cut`;
- implement `dispose` per asset qualification.

**Explicit non-scope:** cutter support; capability matrices.

**Dependency:** B2-04.

**Exit condition:** capability, cut, and dispose tests pass.

**Proves:** B-DOD-04.

**Passes:** B-AT-17, B-AT-18, B-AT-19.

### B2-06: completion criterion wiring

**Readiness:** BLOCKED BY MILESTONE A IMPLEMENTATION REMEDIATION — then READY AFTER B1

**Scope:**

- wire the approved B-COMP Option A evidence into the result and settlement flow;
- keep `verification_supported` false;
- settle `UNCERTAIN` after `content_started` when the physical result cannot be established.

**Explicit non-scope:** inventing a completion signal; same-job retry after content started.

**Dependency:** B2-04.

**Exit condition:** `SUCCEEDED` occurs only under approved evidence.

**Proves:** B-DOD-15.

**Passes:** B-AT-09.

## B3 — Minimal Reference Receipt

### B3-01: Paper profile

**Readiness:** READY NOW — parameterized structure; exact width PENDING REFERENCE DEVICE INVENTORY

**Scope:**

- define the parameterized reference paper profile in `paper_profiles.mjs`;
- include width, margins, and final feed as injected parameters, not hardcoded model values;
- provide a generic placeholder profile for automated tests.

**Explicit non-scope:** universal profiles; model-name branching.

**Dependency:** none.

**Exit condition:** profile tests pass with a parameterized profile.

**Proves:** B-DOD-05 input.

**Passes:** B-AT-07 input.

### B3-02: Minimal receipt layout

**Readiness:** READY NOW

**Scope:**

- build the minimal receipt fields listed in `plan.md` section 5;
- reuse existing layout, wrapper, and currency formatter;
- verify hash determinism.

**Explicit non-scope:** logo, QR, barcode, second copy.

**Dependency:** B3-01.

**Exit condition:** receipt tests pass and hash is deterministic.

**Proves:** B-DOD-05 input, B-DOD-08 input.

**Passes:** B-AT-16.

### B3-03: Line rendering for driver

**Readiness:** READY NOW

**Scope:**

- produce ordered text lines for driver dispatch;
- guarantee exactly one trailing newline per logical line;
- preserve block order.

**Explicit non-scope:** native columns; bitmap rendering.

**Dependency:** B3-02.

**Exit condition:** rendering tests pass.

**Proves:** B-DOD-05 input.

**Passes:** B-AT-15.

## B4 — ERPNext POS End-to-End Happy Path

### B4-01: Terminal and idempotency context

**Readiness:** READY NOW

**Scope:**

- attach terminal and idempotency context to the POS summary through existing adapter expectations;
- use existing settings and terminal APIs only.

**Explicit non-scope:** multi-terminal switching; pairing workflows.

**Dependency:** B1-04, B2 complete, B3 complete.

**Exit condition:** adapter receives complete context in tests.

**Proves:** B-DOD-06 input.

**Passes:** B-AT-08 input.

### B4-02: Receipt snapshot binding

**Readiness:** READY NOW

**Scope:**

- implement the approved `B-AC-01` refinement only;
- bind snapshot and hash to the Job before Attempt creation and before output;
- enforce a required non-empty matching reservation token while the Job is RESERVED;
- parse and validate canonical JSON schema version 1;
- recompute the existing `pdpr1:` hash server-side using shared cross-language canonicalization/hash vectors;
- store atomically through one guarded UPDATE requiring empty binding fields;
- reject rebinding so the bound snapshot/hash remain immutable.

**Explicit non-scope:** schema change; new projection fields; reprint snapshot policy.

**Dependency:** B4-01.

**Exit condition:** snapshot and hash persist under reservation ownership; tests pass.

**Proves:** B-DOD-08.

**Passes:** B-AT-08, B-AT-16.

### B4-03: Asset bundle and bootstrap registration

**Readiness:** READY AFTER B1 — needs the pinned SDK asset

**Scope:**

- add app-owned bundle entry in `hooks.py`;
- register `imin_v1` during idempotent bootstrap;
- preserve shutdown restore behavior.

**Explicit non-scope:** ERPNext or Frappe core changes.

**Dependency:** B4-01.

**Exit condition:** bootstrap loads once and registers the driver.

**Proves:** B-DOD-06 input, B-DOD-12.

**Passes:** B-AT-08 input, B-AT-13.

### B4-04: Physical end-to-end run

**Readiness:** BLOCKED UNTIL PHYSICAL UAT — PENDING REFERENCE DEVICE INVENTORY

**Scope:**

- run one real submitted POS Invoice through the full path;
- verify Job, Attempt, receipt hash, and physical receipt.

**Explicit non-scope:** reliability runs; multiple users.

**Dependency:** B4-02, B4-03, reference device.

**Exit condition:** physical receipt prints and audit records match.

**Proves:** B-DOD-06, B-DOD-07, B-DOD-09.

**Passes:** B-AT-08, B-AT-10, B-AT-11.

## B5 — Minimum Pre-output Failure Boundary

### B5-01: Pre-output failure mapping

**Readiness:** READY NOW

**Scope:**

- map bridge unavailable, init failure, not ready, and paper out to existing canonical errors;
- verify settlement to `FAILED_SAFE`;
- verify `content_started` remains false.

**Explicit non-scope:** mid-print failures; retry policy.

**Dependency:** B2 complete.

**Exit condition:** all four failure tests pass with mock SDK.

**Proves:** B-DOD-11.

**Passes:** B-AT-02, B-AT-04, B-AT-06.

### B5-02: Fallback preservation

**Readiness:** READY NOW

**Scope:**

- verify browser fallback after each pre-output failure;
- verify `FALLBACK_BROWSER` never becomes `SUCCEEDED`.

**Explicit non-scope:** fallback UX redesign.

**Dependency:** B5-01.

**Exit condition:** fallback tests pass.

**Proves:** B-DOD-10.

**Passes:** B-AT-12.

### B5-03: Boundary containment check

**Readiness:** READY NOW

**Scope:**

- assert no raw SDK object, raw status, or raw error leaves the driver in all failure paths.

**Explicit non-scope:** new telemetry.

**Dependency:** B5-01.

**Exit condition:** containment tests pass.

**Proves:** B-DOD-16.

**Passes:** B-AT-14, B-AT-20.

## B6 — Physical Device Acceptance

### B6-01: Device UAT checklist

**Readiness:** BLOCKED UNTIL PHYSICAL UAT — PENDING REFERENCE DEVICE INVENTORY

**Scope:** run each item below on the reference device and record evidence:

1. cold browser start;
2. login to ERPNext POS v16;
3. one real transaction;
4. physical print succeeds;
5. five sequential prints succeed;
6. short item names print correctly;
7. long item names wrap correctly;
8. large nominal values render in Rupiah;
9. Rupiah formatting matches locale expectations;
10. paper out before print fails safely;
11. browser fallback verification after a pre-output failure.

**Explicit non-scope:** reliability soak; sleep and wake; multi-tab.

**Dependency:** B1 through B5 complete.

**Exit condition:** all 11 items pass with recorded evidence.

**Proves:** B-DOD-01, B-DOD-02, B-DOD-03, B-DOD-05, B-DOD-06, B-DOD-09, B-DOD-10, B-DOD-11, B-DOD-14.

**Passes:** B-AT-01, B-AT-03, B-AT-05, B-AT-06, B-AT-07, B-AT-08, B-AT-09, B-AT-11, B-AT-12.

## Task count

- B1: 5 tasks
- B2: 6 tasks
- B3: 3 tasks
- B4: 4 tasks
- B5: 3 tasks
- B6: 1 task

Total: 22 coding and UAT tasks.

## Readiness summary

| Batch | Readiness |
| --- | --- |
| B1 | READY NOW: B1-01, B1-02, B1-03. BLOCKED BY REFERENCE DEVICE: B1-04, B1-05. |
| B2 | READY AFTER B1: B2-01, B2-05. BLOCKED BY MILESTONE A IMPLEMENTATION REMEDIATION: B2-02, B2-04, B2-06. READY NOW: B2-03 provisional mapping. |
| B3 | READY NOW: B3-01, B3-02, B3-03. |
| B4 | READY NOW: B4-01, B4-02. READY AFTER B1: B4-03. BLOCKED UNTIL PHYSICAL UAT: B4-04. |
| B5 | READY NOW: B5-01, B5-02, B5-03. |
| B6 | BLOCKED UNTIL PHYSICAL UAT. |

No task is BLOCKED BY UNRESOLVED DESIGN.
