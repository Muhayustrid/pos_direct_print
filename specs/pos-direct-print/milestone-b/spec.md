# Milestone B Specification: Single-device Happy Path

**Status:** READY FOR B1 / PARTIALLY READY

**Design freeze:** generic design frozen; hardware-specific values pending reference device

Resolved decisions, 2026-08-10:

- `B-COMP` print completion criterion: DECIDED — APPROVED, Option A. See `contracts/print-completion.md`. Not reopened.
- `B-AC-01` receipt snapshot binding: DECIDED — APPROVED as a minimal guarded refinement. See `research.md` section 15 and `plan.md` section 9.
- Milestone B runtime: iMin JS Printer SDK V1 plus `iMinprinterplugin` on one V1-qualified reference device. Fleet project may contain other SDK generations; future runtime support belongs to Milestone D. See `research.md` sections 4.5 and 13.7.
- Paper profile: parameterized normalized profile, no model hardcoding. See `contracts/happy-path-receipt.md`.

Remaining blockers are classified in `research.md` section 13:

- Category B facts gate hardware-specific tasks;
- Category C facts gate physical UAT;
- Category D facts are diagnostic only.

Hardware-specific decisions are not marked `DESIGN FROZEN` while their facts are unavailable. Generic work that does not need hardware facts is not held.

## 1. Goal

One ERPNext POS v16 transaction produces one physical receipt on one iMin reference device.

The print path is:

```text
ERPNext POS v16
  -> POSIntegrationAdapter
  -> PrintManager
  -> JobCoordinator
  -> ReceiptBuilder / ReceiptDocument
  -> BaseDriver
  -> imin_v1
  -> iMin JavaScript Printer SDK V1
  -> iMinprinterplugin / local print service
  -> built-in thermal printer
```

POS integration must never call the iMin SDK directly.

## 2. Scope

Milestone B includes:

- one V1-qualified physical reference device;
- one driver key `imin_v1`;
- one minimal receipt layout;
- minimum pre-output failure handling;
- physical UAT on the reference device;
- automated tests against a mock SDK boundary.

Milestone B excludes Milestone C reliability work and Milestone D multi-model/multi-runtime/device-qualification architecture. See `plan.md` sections 12 and 13.

## 3. Milestone A dependencies

These contracts are frozen and binding:

- `specs/pos-direct-print/constitution.md`
- `specs/pos-direct-print/contracts/base-driver.md`
- `specs/pos-direct-print/contracts/browser-driver.md`
- `specs/pos-direct-print/contracts/capability-registry.md`
- `specs/pos-direct-print/contracts/data-contracts.md`
- `specs/pos-direct-print/contracts/error-contract.md`
- `specs/pos-direct-print/contracts/error-normalizer.md`
- `specs/pos-direct-print/contracts/job-coordinator.md`
- `specs/pos-direct-print/contracts/print-api.md`
- `specs/pos-direct-print/contracts/print-job.md`
- `specs/pos-direct-print/contracts/print-manager.md`
- `specs/pos-direct-print/contracts/pos-integration.md`
- `specs/pos-direct-print/contracts/receipt-builder.md`
- `specs/pos-direct-print/contracts/receipt-layout.md`
- `specs/pos-direct-print/contracts/text-wrapper.md`
- `specs/pos-direct-print/data-model.md`

The existing state machine, retry matrix, permission model, and audit semantics are binding without redesign.

## 4. Definition of Done

| ID | Requirement |
| --- | --- |
| B-DOD-01 | The iMin bridge is detected on the reference device. |
| B-DOD-02 | The driver initializes the printer on the reference device. |
| B-DOD-03 | Printer `READY` is recognized on the reference device. |
| B-DOD-04 | `imin_v1` satisfies every existing `BaseDriver` method without uncontrolled exceptions. |
| B-DOD-05 | One minimal `ReceiptDocument` prints physically on the reference device. |
| B-DOD-06 | One real ERPNext POS v16 transaction prints physically through the full canonical path. |
| B-DOD-07 | Job and Attempt audit records follow the Milestone A contract. |
| B-DOD-08 | `receipt_hash` and receipt snapshot behavior follow Milestone A after `B-AC-01` is approved. |
| B-DOD-09 | Printing never modifies, submits, cancels, or reopens the invoice. |
| B-DOD-10 | The Milestone A browser fallback still works. |
| B-DOD-11 | Pre-output failures are never marked as physical success. |
| B-DOD-12 | No ERPNext or Frappe core file changes. |
| B-DOD-13 | Automated tests run without a physical device using the mock SDK boundary. |
| B-DOD-14 | Physical reference-device UAT passes the B6 checklist. |
| B-DOD-15 | The completion criterion for `SUCCEEDED` is the approved `B-COMP` option, and no other. |
| B-DOD-16 | Raw SDK objects, errors, and statuses never leave the driver boundary. |

## 5. Acceptance tests

### B-AT-01 bridge available

- Given the approved SDK asset is loaded on the reference device
- And the local print service is running
- When `detect(context)` runs
- Then the result is `available: true`
- And the result carries bridge evidence in metadata.

### B-AT-02 bridge unavailable

- Given the local print service is not reachable
- When `detect(context)` runs
- Then the result is `available: false`
- And the orchestration settles to `FAILED_SAFE` before any content dispatch
- And browser fallback remains allowed.

### B-AT-03 initialization success

- Given the bridge is available
- When `initialize(context)` runs with the reference transport
- Then the result is `initialized: true`
- And a following `getStatus()` returns `READY`.

### B-AT-04 initialization failure

- Given the bridge is available but initialization fails
- When `initialize(context)` runs
- Then the driver raises a normalized domain error
- And no print command is dispatched
- And the orchestration settles to `FAILED_SAFE`.

### B-AT-05 READY status

- Given the printer is initialized with paper loaded and cover closed
- When `getStatus()` runs
- Then the state is `READY`
- And `ready` is `true`
- And the raw status evidence is preserved in metadata.

### B-AT-06 paper out before print

- Given the printer reports paper out before content dispatch
- When `print(receiptDocument, jobContext)` runs
- Then no content command is dispatched
- And the normalized error identifies paper out
- And the Job settles to `FAILED_SAFE`
- And `content_started` remains false.

### B-AT-07 minimal receipt physical print

- Given the reference device is qualified
- When one minimal `ReceiptDocument` is printed
- Then the physical receipt contains company name, invoice number, timestamp, items, quantities, prices, totals, payment summary, and footer
- And the Job reaches the approved completion outcome.

### B-AT-08 POS end-to-end print

- Given one submitted POS Invoice in ERPNext POS v16
- When the operator triggers print receipt
- Then the path runs POS integration, PrintManager, JobCoordinator, ReceiptBuilder, `imin_v1`, and physical print
- And one physical receipt appears
- And the Job and Attempt records exist.

### B-AT-09 Job SUCCEEDED only after completion criterion

- Given the approved `B-COMP` criterion
- When the driver finishes dispatch
- Then the Job transitions `PRINTING` to `VERIFYING`
- And the Job transitions `VERIFYING` to `SUCCEEDED` only when the approved evidence is present
- And no other evidence produces `SUCCEEDED`.

### B-AT-10 Attempt audit correctness

- Given one print attempt
- When the attempt completes
- Then `attempt_no` is sequential under the Job
- And outcome, `content_started`, `content_completed`, error code, and error detail match the driver result
- And the Attempt remains immutable for all roles.

### B-AT-11 invoice unchanged

- Given one submitted POS Invoice
- When printing succeeds or fails
- Then the invoice `docstatus`, payment entries, and line items are unchanged.

### B-AT-12 browser fallback preserved

- Given a pre-output failure with `content_may_have_printed` false
- When the operator approves browser fallback
- Then the saved ERPNext print method runs
- And the Job settles to `FALLBACK_BROWSER`
- And the Job is never `SUCCEEDED`.

### B-AT-13 automated tests without device

- Given the mock SDK adapter
- When the full automated suite runs
- Then all driver, orchestration, receipt, and failure tests pass
- And no test requires a physical iMin device.

### B-AT-14 SDK error normalization

- Given an SDK failure at any lifecycle point
- When the driver handles the failure
- Then the result is a canonical `PrintDomainError` from the frozen taxonomy
- And raw SDK error text never reaches the POS UI.

### B-AT-15 receipt command sequence

- Given a minimal `ReceiptDocument`
- When the driver renders it
- Then each logical text line produces one outbound SDK command with exactly one trailing newline
- And the test inspects the outbound command so SDK-added newlines cannot double-append
- And style commands precede the text they affect
- And the final feed command is dispatched last.

### B-AT-16 receipt hash determinism

- Given one invoice snapshot
- When `ReceiptBuilder.build` runs twice
- Then both documents validate against schema version 1
- And `hashReceipt` returns the same value for both.

### B-AT-17 minimal capabilities

- Given the qualified reference device
- When `getCapabilities()` runs
- Then it returns the reference paper profile and supported features
- And unsupported features return controlled capability outcomes.

### B-AT-18 cutter unsupported

- Given the reference device profile without cutter support
- When `cut(request)` runs
- Then the result is a controlled `DriverPrintResult`
- And no uncontrolled exception is thrown.

### B-AT-19 dispose behavior

- Given an initialized driver instance
- When `dispose()` runs
- Then the driver releases its SDK handle according to the pinned asset behavior
- And a later `detect(context)` can run again.

### B-AT-20 boundary containment

- Given any driver method
- When it returns or throws
- Then no raw SDK object, WebSocket handle, or raw status value appears outside driver metadata approved by `B-DOD-16`.

## 6. Traceability

| B-DOD | B-AT | Task |
| --- | --- | --- |
| B-DOD-01 | B-AT-01, B-AT-02 | B1 |
| B-DOD-02 | B-AT-03, B-AT-04 | B1, B2 |
| B-DOD-03 | B-AT-05, B-AT-06 | B1, B2 |
| B-DOD-04 | B-AT-03, B-AT-05, B-AT-15, B-AT-17, B-AT-18, B-AT-19 | B2 |
| B-DOD-05 | B-AT-07, B-AT-15 | B3, B6 |
| B-DOD-06 | B-AT-08 | B4, B6 |
| B-DOD-07 | B-AT-08, B-AT-10 | B4 |
| B-DOD-08 | B-AT-16 | B4, gated by B-AC-01 |
| B-DOD-09 | B-AT-11 | B4, B6 |
| B-DOD-10 | B-AT-12 | B5 |
| B-DOD-11 | B-AT-02, B-AT-04, B-AT-06 | B5 |
| B-DOD-12 | B-AT-13 | all |
| B-DOD-13 | B-AT-13 | B1, B2, B3, B5 |
| B-DOD-14 | B-AT-07, B-AT-08, B-AT-11 | B6 |
| B-DOD-15 | B-AT-09 | B2, gated by B-COMP |
| B-DOD-16 | B-AT-14, B-AT-20 | B1, B2 |

## 6.1 Cross-milestone handoff notes

Milestone C reliability policy must remain driver/runtime agnostic. V1's local `ws://127.0.0.1:8081` behavior is adapter evidence, not a universal health contract. Driver/runtime-specific failures normalize to existing canonical health/error semantics before reaching PrintManager or reliability logic.

Future Milestone D planning scope: **Multi-model + Multi-runtime + Device Qualification** — V1 runtime, authoritative V2 runtime evidence, future `imin_v2` if needed, SDK generation, transport, paper profile, model/ROM qualification, status normalization, and capability matrix. Milestone B neither implements nor designs those features.

## 7. Design freeze checklist

| Check | Category | State |
| --- | --- | --- |
| Completion criterion B-COMP approved | A | DECIDED — APPROVED: Option A, 2026-08-10 |
| B-AC-01 receipt snapshot binding approved | A | DECIDED — APPROVED: minimal guarded refinement, 2026-08-10 |
| Milestone B runtime = V1 + plugin on one V1-qualified reference device; no fleet-wide generation assumption | A | DECIDED |
| Parameterized PaperProfile architecture | A | RESOLVED in `contracts/happy-path-receipt.md` |
| Minimal receipt fields approved | A | RESOLVED in `contracts/happy-path-receipt.md` |
| Failure boundary scope approved | A | RESOLVED in `plan.md` section 10 |
| Deferral lists C and D approved | A | RESOLVED in `plan.md` sections 12 and 13 |
| SDK asset pinned and checksummed | B1 work | B1-01 owns the pin |
| Reference device model identified | B | PENDING REFERENCE DEVICE INVENTORY |
| Reference transport identified | B | PENDING REFERENCE DEVICE INVENTORY |
| Exact physical paper width | B | PENDING REFERENCE DEVICE INVENTORY |
| READY raw value qualified on device | B and C | PENDING REFERENCE DEVICE INVENTORY |
| Android version, browser, plugin version, endpoint, feed, timing | C | PENDING REFERENCE DEVICE INVENTORY |
| ROM, WebView, firmware, extra metrics | D | diagnostic only |

Status: **READY FOR B1 / PARTIALLY READY**. Category A is clear. B1-01 through B1-03 may proceed. B2 physical orchestration remains blocked until the actual Milestone A `PrintManager` lifecycle/state-sequencing mismatch recorded in `plan.md` §1.6 is remediated. Hardware-specific values and B6 wait for the classified device facts.
