# Milestone B Plan: Single-device Happy Path

**Status:** READY FOR B1 / PARTIALLY READY

This plan is an implementation blueprint. It contains no production code.

Resolved gates, 2026-08-10:

1. `B-COMP` approved: Option A. See `contracts/print-completion.md`.
2. `B-AC-01` approved: minimal guarded refinement. See section 9.
3. Milestone B runtime: V1 plus `iMinprinterplugin` on one V1-qualified reference device; no fleet-wide SDK-generation assumption. See `research.md` sections 4.5 and 13.7.
4. Paper profile: parameterized normalized profile, no model hardcoding. See section 5 and `contracts/happy-path-receipt.md`.

Gate model:

- Category A blockers are clear, so generic implementation can start;
- Category B facts in `research.md` section 13 gate hardware-specific tasks;
- Category C facts gate physical UAT;
- Category D facts are diagnostic only.

## 1. Architecture integration

### 1.1 Modules reused without change

- `core/state_machine.py`
- `core/reservation.py`
- `core/retry.py`
- `core/reprint.py`
- `core/security.py`
- `core/print_api.py`, except approved `B-AC-01` refinement
- `core/projections.py`
- all four DocTypes and their controllers
- `core/print_job.mjs`
- `core/errors.mjs`
- `core/error_normalizer.mjs`
- `core/print_api.mjs`, except approved `B-AC-01` refinement
- `core/job_coordinator.mjs`, except approved `B-AC-01` refinement
- `core/capability_registry.mjs`
- `drivers/base_driver.mjs`
- `drivers/browser_driver.mjs`
- `drivers/fake_driver.mjs`
- `integration/erpnext_v16_pos.mjs`
- `receipt/receipt_document.mjs`
- `receipt/receipt_builder.mjs`
- `receipt/receipt_layout.mjs`
- `receipt/text_wrapper.mjs`
- `receipt/currency_formatter.mjs`

### 1.2 Modules extended

- `core/print_manager.mjs`: approved B-COMP Option A settlement evidence gate and approved B-AC-01 snapshot-binding step only.
- `core/bootstrap.mjs`: register the `imin_v1` driver with the existing `CapabilityRegistry`.
- `hooks.py`: add the app-owned frontend bundle that loads the POS bootstrap asset. No ERPNext or Frappe core file changes.
- `integration/erpnext_v16_pos.mjs` context wiring only: attach terminal and idempotency context to the POS summary through the existing adapter expectations.

### 1.3 New modules

| Planned file | Responsibility |
| --- | --- |
| `drivers/imin_v1_driver.mjs` | One `BaseDriver` implementation for the reference device. |
| `drivers/imin_sdk_adapter.mjs` | Only module allowed to touch the raw iMin SDK object. |
| `receipt/paper_profiles.mjs` | Reference-device paper profile consumed by `ReceiptBuilder` context. |
| `drivers/__tests__/imin_sdk_adapter.test.mjs` | Mock SDK boundary tests. |
| `drivers/__tests__/imin_v1_driver.test.mjs` | Driver lifecycle tests with mock SDK. |
| `receipt/__tests__/paper_profiles.test.mjs` | Profile and layout tests. |

### 1.4 Dependency graph

```text
erpnext_v16_pos.mjs
  -> print_manager.mjs
       -> job_coordinator.mjs -> print_api.mjs -> core/print_api.py
       -> receipt_builder.mjs -> receipt_layout.mjs / text_wrapper.mjs / paper_profiles.mjs
       -> capability_registry.mjs -> imin_v1_driver.mjs -> imin_sdk_adapter.mjs -> iMin SDK
```

### 1.5 Boundaries

- `PrintManager` owns orchestration, state settlement, and audit calls.
- `imin_v1_driver` owns preflight, dispatch, and result normalization.
- `imin_sdk_adapter` owns all raw SDK access.
- POS integration knows nothing about SDK, driver, or printer state.

### 1.6 Actual Milestone A implementation compatibility gate

Sanity audit against commit `6c96faa` found one implementation conflict that does not block B1-01 through B1-03 but must be remediated before B2 physical orchestration:

- `PrintManager.requestPrint` currently calls `driver.print()` immediately after `beginAttempt`; it does not invoke `detect`, `initialize`, or `getStatus`, and it persists `PREFLIGHT -> PRINTING -> VERIFYING` only after driver dispatch completes.
- Frozen Milestone A requires PrintManager to coordinate the attempt and drive state transitions; Milestone B requires detect/init/READY before `PREFLIGHT -> PRINTING`, then physical dispatch while the Job is `PRINTING`.

This is an implementation-to-frozen-contract mismatch, not a new architecture decision. B1 adapter work may proceed. Before B2-02/B2-04/B2-06, a separate authorized remediation must align `PrintManager` with the existing BaseDriver lifecycle and state machine; Milestone B must not hide that remediation inside the driver.

## 2. Data model

Milestone B uses the Milestone A data model without change.

No DocType, field, index, or permission change is proposed.

If implementation discovers a schema need, work stops and the need is recorded as an unresolved architecture change.

## 3. Driver lifecycle

Happy-path sequence:

1. Operator triggers receipt print in ERPNext POS v16.
2. `POSIntegrationAdapter` intercepts and builds a `PrintRequest`.
3. `PrintManager.requestPrint` reserves the Job. State moves `CREATED` to `RESERVED`.
4. `ReceiptBuilder` builds the minimal canonical `ReceiptDocument` and hash.
5. The approved `B-AC-01` binding stores `receipt_snapshot` and `receipt_hash` on the Job atomically under active reservation ownership, before any Attempt.
6. `CapabilityRegistry` selects configured `POS Print Terminal.driver_key = imin_v1` for the V1-qualified reference terminal. Android version is evidence, not a hardcoded selection rule.
7. `JobCoordinator.beginAttempt` starts an Attempt. State moves `RESERVED` to `PREFLIGHT`.
8. Driver `detect` checks bridge availability.
9. Driver `initialize` connects and initializes with the reference transport.
10. Driver `getStatus` confirms `READY`.
11. State moves `PREFLIGHT` to `PRINTING`.
12. Driver sets page format, text width, alignment, and style.
13. Driver passes logical receipt lines to the SDK adapter; the adapter strips existing trailing newlines and the pinned no-type `printText` path produces exactly one trailing newline in each outbound command.
14. Driver dispatches the approved final feed.
15. State moves `PRINTING` to `VERIFYING`.
16. `complete_attempt` records the `DriverPrintResult`.
17. State moves `VERIFYING` to `SUCCEEDED` only under the approved `B-COMP` evidence.

Every failure before step 13 settles to `FAILED_SAFE` and preserves browser fallback.

A failure during step 13 or step 14 settles to `UNCERTAIN` because output may have started.

## 4. SDK boundary

Only `imin_sdk_adapter.mjs` may reference:

- the `IminPrinter` constructor from the pinned asset;
- the SDK instance;
- `connect()`;
- `initPrinter(connectType)`;
- `getPrinterStatus(connectType)`;
- `setPageFormat(style)`;
- `setTextWidth(width)`;
- `setAlignment(alignment)`;
- `setTextSize(size)`;
- `setTextStyle(style)`;
- `printText(text)`;
- `printAndFeedPaper(value)`;
- `close()`, only after asset qualification proves its behavior.

Rules:

- raw SDK object never leaves the adapter;
- raw SDK errors enter the existing `ErrorNormalizer`;
- raw printer status values appear only inside driver metadata;
- POS UI receives only canonical domain states and user messages.

Forbidden SDK calls for Milestone B:

- bitmap printing;
- barcode printing;
- QR printing;
- double QR;
- cutter calls;
- label APIs;
- cash drawer;
- raw WebSocket protocol types.

## 5. Receipt scope

The minimal receipt contains:

1. company or store name;
2. invoice number;
3. posting date and time;
4. item name, quantity, unit price, and line total;
5. subtotal;
6. discount, when present;
7. grand total;
8. payment summary;
9. simple footer.

Excluded unless the reference device requires them:

- logo;
- QRIS;
- barcode;
- cutter;
- second copy;
- copy delay.

All layout is produced by existing `ReceiptLayout` and `TextWrapper`.

The driver does not use native `printColumnsText`.

### 5.1 Paper profile architecture

Printing is universal at the architecture level through a normalized `PaperProfile` and `DriverCapabilities`.

Canonical flow:

```text
ReceiptDocument
  -> normalized PaperProfile / DriverCapabilities
  -> layout / rendering
  -> imin_v1
```

Rules:

- no model name appears in business, POS, or receipt code;
- no `if model == X` branching exists in receipt rendering;
- Milestone B ships one parameterized reference profile, not one hardcoded model;
- full 58 mm and 80 mm qualification belongs to Milestone D.

## 6. Failure boundary

Milestone B handles only pre-output failures:

| Failure | Canonical handling | State |
| --- | --- | --- |
| Bridge unavailable | existing reserved bridge error class | `FAILED_SAFE` |
| Initialization failure | existing reserved printer error class | `FAILED_SAFE` |
| Printer not ready | existing reserved printer error class | `FAILED_SAFE` |
| Paper out before content | existing reserved paper error class | `FAILED_SAFE` |

Rules:

- use exact error codes already present in `core/errors.mjs`;
- do not add new error codes in Milestone B;
- if no existing code fits a failure, stop and record an unresolved contract question;
- all these failures keep `content_started` false;
- all these failures preserve browser fallback.

Mid-print failures produce `UNCERTAIN` and belong to Milestone C recovery workflows.

## 7. Testing

### 7.1 Automated tests without device

Required for every batch:

- pure unit tests for status mapping, paper profile, and line rendering;
- mock SDK adapter tests for connect, init, status, dispatch, and failure paths;
- driver lifecycle tests with injected fake SDK;
- orchestration tests using existing `FakeDriver` and fake transport;
- browser fallback tests extending existing suites.

### 7.2 Physical tests

Physical tests require the reference device and cannot be automated in this repository.

They are defined as the B6 checklist in `tasks.md`.

### 7.3 Test commands

Run focused module tests inside the devcontainer:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module <PYTHON_TEST_MODULE> \
     --failfast'
```

Run the full suite:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --test-category all'
```

Run the JavaScript suite from the app root:

```bash
find pos_direct_print/public/js/pos_direct_print \
  -path '*__tests__/*.test.mjs' -print -exec node --test {} +
```

A zero-test run does not prove success. Confirm collected and executed tests.

## 8. Asset loading

`hooks.py` gains an app-owned JavaScript bundle entry.

The bundle loads:

1. the POS bootstrap module;
2. the `imin_v1` driver registration;
3. the pinned iMin SDK asset approved during B1.

The SDK asset must be served from app assets, not from a remote CDN.

No ERPNext or Frappe core file is modified.

## 9. Architecture change B-AC-01 — APPROVED

Status: DECIDED — APPROVED as a minimal guarded refinement, 2026-08-10.

The built canonical `ReceiptDocument` and hash are bound to the reserved Job before physical output starts.

Approved sequence:

```text
reserve
  -> build canonical ReceiptDocument
  -> bind receipt_snapshot + receipt_hash
  -> start attempt
  -> preflight
  -> physical print
```

Approved binding rules:

- requires active valid reservation ownership;
- happens before Attempt creation and before any physical output;
- validates `ReceiptDocument` against schema version 1;
- verifies `receipt_hash` is the actual hash of the canonical snapshot, not a format-only check;
- server parses the canonical JSON snapshot, validates schema version 1, canonicalizes the parsed value with the same recursively sorted-key JSON algorithm, and recomputes the existing `pdpr1:` FNV-1a hash for exact equality; the B-AC-01 implementation must include shared cross-language hash vectors before enabling the endpoint;
- stores snapshot and hash atomically with a guarded `UPDATE` requiring `status = RESERVED`, a non-empty matching `reservation_owner`, and both binding fields empty;
- both fields become immutable once bound because the same mutation rejects rebinding;
- no permission-model change;
- no new persistence schema;
- preserves the existing `receipt_hash implies receipt_snapshot` rule.

Deferred inside this refinement: whether REPRINT reuses the parent snapshot or rebuilds from the invoice. That question belongs to the reprint contract milestone and stays unresolved here.

Frozen Milestone A contracts are not edited by this package. The exact proposed deltas, referencing B-AC-01, are:

1. `specs/pos-direct-print/contracts/print-api.md`: add one guarded mutation named as the B-AC-01 snapshot-binding operation; no existing A operation has a compatible write surface. Inputs: `job_id`, required non-empty active `reservation_token`, canonical JSON `receipt_snapshot`, `receipt_hash`. Behavior: parse and validate schema version 1; recompute the existing `pdpr1:` hash using the cross-language canonicalization vectors and require equality; execute one guarded `UPDATE` requiring `status = RESERVED`, matching `reservation_owner`, and both binding fields empty; reject rebinding or reservation mismatch with existing `PDP_JOB_CONFLICT` semantics. The endpoint must not expose snapshot/hash through Level-0 projections.
2. `specs/pos-direct-print/contracts/job-coordinator.md`: add the client call for the same operation between `reserve` and `beginAttempt` in the attempt cycle.
3. `specs/pos-direct-print/contracts/print-manager.md`: insert the binding step between receipt build and `beginAttempt` in `requestPrint` and `retryJob`.

No other Milestone A contract is changed. No schema, index, permission, or state-machine change is included.

## 10. Completion semantics

The driver returns a `DriverPrintResult`.

`verification_supported` is false for Milestone B unless `B-COMP-C` adds approved evidence.

`content_completed` means all commands were dispatched.

It never means paper finished printing.

`VERIFYING` to `SUCCEEDED` follows only the approved `B-COMP` option in `contracts/print-completion.md`.

Actual Milestone A `PrintManager._settleStatus` currently treats any `accepted && content_completed` result as `SUCCEEDED`. B2-06 must refine this single decision point (or supply an equivalent explicitly verified result contract) so post-dispatch READY evidence is required; relying only on driver convention would not satisfy B-AT-09.

## 11. Configuration

Reference-device values live in configuration/qualification data, not hardcoded branching:

- `POS Print Terminal.driver_key = imin_v1` for the qualified B terminal;
- Android version as evidence only, never `if android <= 11` runtime selection logic;
- connection type;
- parameterized paper profile;
- final feed value;
- SDK address if not default.

Values come from the qualified terminal profile during B1 hardware qualification and B6. Generic implementation uses injected placeholder profiles until the Category B facts arrive.

## 12. Explicit deferral to Milestone C

Milestone B must not implement:

- robust multi-tab coordination;
- cross-tab locking;
- full double-click protection;
- sleep and wake recovery;
- repeated bridge re-initialization policy;
- long-lived browser lifecycle recovery;
- sophisticated retry;
- mid-print failure recovery;
- paper-out during print;
- full `UNCERTAIN` user workflow;
- duplicate print recovery;
- soak and reliability behavior.

Milestone B may define stub boundaries where needed. It must not implement reliability behavior.

Handoff requirement for Milestone C: reliability policy must stay driver/runtime agnostic. `ws://127.0.0.1:8081` is V1 adapter evidence, not a universal printer-health contract. Every driver-specific runtime failure must normalize through its driver/adapter into canonical health/error semantics before reaching PrintManager or a future reliability layer.

## 13. Explicit deferral to Milestone D

Future Milestone D scope heading: **Multi-model + Multi-runtime + Device Qualification**.

Milestone B must not implement:

- D1, D1w, D4, M2, M2 Pro, or S1 capability matrices;
- generic multi-model support;
- runtime-generation detection/reconciliation;
- an `imin_v2` driver or V2 production assets;
- automatic model detection;
- ROM compatibility matrix;
- model-specific printer-status normalization;
- generic USB or SPI handling for all models;
- universal 58 mm and 80 mm profiles;
- cutter matrix;
- model-specific quirks.

Milestone D planning should carry forward V1 runtime, authoritative V2 runtime evidence, future `imin_v2` if needed, SDK generation, transport, paper profile, model/ROM qualification, normalized status, and capability matrix.

Milestone B implements only the configured `imin_v1` path needed for one V1-qualified reference device. It does not make V1 the permanent project-wide runtime.

## 14. Gate model

Milestone B uses a classified gate model, not one binary freeze. See `research.md` section 13.

- Category A is clear. Generic implementation may start.
- Category B facts gate hardware-specific tasks, marked `PENDING REFERENCE DEVICE INVENTORY`.
- Category C facts gate physical UAT.
- Category D facts are diagnostic only.

Hardware-specific values are not marked `DESIGN FROZEN` while their facts are unavailable. Generic work that does not need hardware facts is not held.
