# Contract B-DRV: imin_v1 Driver

**Status:** GENERIC DESIGN FROZEN — hardware qualification values pending reference device (B-COMP Option A approved)

**Refinement of:** none. This is a new Milestone B contract.

**Depends on frozen Milestone A contracts:**

- `base-driver.md`
- `data-contracts.md`
- `error-contract.md`
- `error-normalizer.md`
- `capability-registry.md`
- `print-manager.md`

## B-DRV-01 Identity

The driver registers under the reserved key `imin_v1` and is selected from the qualified terminal's `POS Print Terminal.driver_key`. Android version is qualification evidence, not a hardcoded driver-selection branch.

This contract does not claim that `imin_v1` is the permanent or only project runtime. Other SDK generations and future drivers belong to Milestone D.

It extends `BaseDriver` and satisfies every frozen `BaseDriver` method.

It must never raise an uncontrolled exception from a contract method.

## B-DRV-02 SDK access

The driver touches the SDK only through `imin_sdk_adapter.mjs` (contract B-RUN).

It never imports or references the SDK asset directly.

## B-DRV-03 Method-to-SDK mapping

| BaseDriver method | Adapter operations used | Result |
| --- | --- | --- |
| `detect(context)` | bridge availability | `{ available, reason, metadata }` |
| `initialize(context)` | initialize, then status query | `{ initialized, driver_key }` or normalized error |
| `getCapabilities()` | none | minimal reference capabilities |
| `getStatus()` | status query | canonical `PrinterState` result |
| `print(receiptDocument, jobContext)` | page format, text width, alignment, style, text lines, feed | `DriverPrintResult` |
| `feed(request)` | feed | `DriverPrintResult` |
| `cut(request)` | none | controlled unsupported outcome |
| `dispose()` | optional close | `{ disposed }` |

## B-DRV-04 detect

`detect` returns available only when the adapter reports the bridge available.

Unavailable results carry the canonical bridge reason and keep `available: false`.

## B-DRV-05 initialize

`initialize` succeeds only when:

1. the adapter initialize succeeds; and
2. an immediate status query returns the qualified READY value.

Any failure raises a normalized domain error. Initialization failure never dispatches content.

## B-DRV-06 getStatus mapping

The driver maps normalized numeric status to the existing `PrinterState` vocabulary:

| Normalized raw | Canonical state | ready |
| --- | --- | --- |
| 0, after qualification | `READY` | true |
| 7 | `PAPER_OUT` | false |
| 3 | `COVER_OPEN` | false |
| 8 | `PAPER_LOW` | false |
| -1 or 1 | `DISCONNECTED` | false |
| 99 | `UNKNOWN_ERROR` | false |

Raw value appears only inside `metadata`.

These mappings are provisional until B1-05 qualification confirms them. PENDING REFERENCE DEVICE INVENTORY.

## B-DRV-07 print

`print` runs this sequence:

1. confirm preflight status is `READY`;
2. set page format and text width from the reference profile;
3. set alignment and style;
4. pass each logical receipt line to the adapter; the adapter/pinned SDK combination must produce exactly one trailing newline in the outbound command;
5. dispatch the approved final feed;
6. return a `DriverPrintResult`.

Rules:

- `content_started` becomes true at the first content line dispatch;
- `content_completed` becomes true only after the final feed dispatch succeeds;
- a failure before step 4 keeps `content_started` false and settles `FAILED_SAFE`;
- a failure during or after step 4 sets `content_started` true and settles `UNCERTAIN`;
- `verification_supported` remains false under approved B-COMP Option A;
- the post-dispatch status check is bounded in time, and its failure does not allow `SUCCEEDED`.

The driver must not use native column, bitmap, barcode, QR, cutter, label, or cash drawer operations.

## B-DRV-08 feed and cut

`feed` dispatches the approved feed value and returns a `DriverPrintResult`.

`cut` returns the controlled unsupported outcome because the reference profile has no cutter.

## B-DRV-09 capabilities

`getCapabilities` returns only the reference profile:

- driver key `imin_v1`;
- paper width from the reference profile;
- text printing supported;
- feed supported;
- cutter unsupported;
- logo, barcode, and QR unsupported.

No model capability matrix is returned.

## B-DRV-10 dispose

`dispose` releases the SDK handle according to B-RUN-07.

After dispose, a later `detect` may run again.

## B-DRV-11 Error normalization

Every SDK or printer failure becomes a canonical `PrintDomainError` from the frozen taxonomy.

The driver must not invent new error codes.
