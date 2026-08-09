# Receipt Builder Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.9 `receipt/receipt_builder`

Purpose:

ERPNext document snapshot → canonical ReceiptDocument.

Must not know iMin.

### `build`

Input:

- normalized invoice snapshot;
- receipt build context.

Return:

ReceiptDocument.

Errors:

- `PDP_RECEIPT_BUILD_FAILED`
- `PDP_RECEIPT_INVALID`

### `validate`

Input:

ReceiptDocument.

Return:

validation result.

### `hash`

Input:

ReceiptDocument.

Return:

deterministic hash string.

Identical semantic input + same receipt schema must yield identical canonical representation/hash.

---
