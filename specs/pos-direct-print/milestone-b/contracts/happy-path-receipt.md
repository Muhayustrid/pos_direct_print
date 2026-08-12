# Contract B-RCP: Minimal Reference Receipt

**Status:** RESOLVED. The paper profile is parameterized. Exact width values come from the reference device before physical UAT.

**Refinement of:** none. This is a new Milestone B contract.

**Depends on frozen Milestone A contracts:**

- `receipt-builder.md`
- `receipt-layout.md`
- `text-wrapper.md`
- `currency-formatter.md`
- `data-contracts.md`

## B-RCP-01 Purpose

Define the minimal receipt that Milestone B prints on the reference device.

The receipt is produced by the existing `ReceiptBuilder` pipeline.

The driver only receives a validated schema-version-1 `ReceiptDocument`.

## B-RCP-02 Required fields

The minimal receipt contains, in order:

1. company or store name;
2. invoice number;
3. posting date and time;
4. one line per item: name, quantity, unit price, line total;
5. subtotal;
6. discount line, only when present;
7. grand total;
8. payment summary;
9. one footer line.

Nothing else is required for Milestone B.

## B-RCP-03 Excluded content

Milestone B must not include:

- logo or bitmap;
- QRIS or QR code;
- barcode;
- cutter command;
- second copy;
- delay between copies.

These belong to later milestones.

## B-RCP-04 Block categories used

The existing Milestone A `ReceiptBuilder` currently produces these block categories for the reference receipt:

- `TEXT`
- `SEPARATOR`
- `COLUMNS`
- `FEED`

`COLUMNS` is a canonical `ReceiptDocument` layout block only. Milestone B line rendering flattens it to ordered text lines; the driver must not call the SDK-native `printColumnsText` operation.

`SPACER`, `IMAGE`, `QR`, and `CUT` blocks are not required for the reference receipt.

## B-RCP-05 Paper profile

The profile supplies:

- paper width as a parameter;
- usable character columns for wrapping as a parameter;
- final feed value as a parameter.

Architecture rules:

- the profile is parameterized and never keyed by model name;
- no `if model == X` logic exists in receipt or POS code;
- canonical flow is `ReceiptDocument` to normalized `PaperProfile` / `DriverCapabilities` to layout and rendering to `imin_v1`;
- automated tests use a generic placeholder profile;
- exact physical values come from the reference device qualification before physical UAT;
- full 58 mm and 80 mm qualification belongs to Milestone D.

The profile is consumed by `ReceiptBuilder.build(snapshot, context)` through `context.paper_profile`.

## B-RCP-06 Text line rules

The driver receives rendered logical lines and dispatches them with:

- left alignment as the default;
- the adapter/pinned SDK combination producing exactly one trailing newline per outbound command;
- wrapping handled by the existing `TextWrapper` before dispatch;
- canonical `COLUMNS` blocks flattened by the line renderer;
- no native SDK column calls.

## B-RCP-07 Determinism

The same invoice snapshot produces the same `ReceiptDocument` and the same `hashReceipt` value.

Any non-deterministic input, such as render time, must not enter the receipt content.

## B-RCP-08 Language and currency

The minimal receipt uses:

- the snapshot locale, default `id-ID`;
- the snapshot currency, default `IDR`;
- the existing `currency_formatter` for nominal values.

## B-RCP-09 Acceptance evidence

Physical acceptance prints at least:

- one short-item receipt;
- one long-item receipt that exercises wrapping;
- one large-nominal receipt that exercises Rupiah formatting.

These runs are part of the B6 checklist.
