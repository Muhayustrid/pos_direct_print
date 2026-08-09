# ERPNext v16 POS Integration Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.2 `integration/erpnext_v16_pos`

Purpose:

ERPNext-specific adapter only.

It may know ERPNext POS object structure.

Other modules may not.

### `isSupported`

Input:

runtime POS context.

Return:

boolean.

### `installOverride`

Input:

- PrintManager reference;
- original POS prototype.

Return:

OverrideHandle.

Requirements:

- save original `print_receipt`;
- patch exactly once;
- expose restoration handle.

Errors:

- `PDP_CONFIG_INVALID`
- `PDP_INTERNAL_ERROR`

### `restoreOverride`

Input:

OverrideHandle.

Return:

boolean indicating restoration.

### `buildPrintRequest`

Input:

PastOrderSummary runtime context + trigger source.

Return:

PrintRequest.

Errors:

- `PDP_RECEIPT_INVALID`
- `PDP_TERMINAL_NOT_FOUND`

### `invokeOriginalPrint`

Input:

original method handle + original invocation context.

Return:

browser print handoff result.

This is the only approved path from custom subsystem back to original ERPNext print behavior.

---
