# Error Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.11 Error Contract

Semua module mengeluarkan normalized domain error kepada layer di atas.

Raw SDK/browser/server errors tidak boleh langsung dipakai oleh POS UI.

---

## A.11.1 PrintDomainError fields

| Property | Type |
|---|---|
| `code` | canonical string |
| `category` | canonical enum |
| `phase` | canonical lifecycle phase |
| `retry_class` | NONE/AUTO_SAFE/MANUAL_SAFE/REPRINT_ONLY |
| `content_may_have_printed` | boolean |
| `user_message_key` | string |
| `technical_message` | string/null |
| `cause` | opaque/raw error |
| `metadata` | object |

---

# A.11.2 Error categories

- `CONFIGURATION`
- `VALIDATION`
- `CONCURRENCY`
- `TERMINAL`
- `BRIDGE`
- `PRINTER`
- `RECEIPT`
- `NETWORK`
- `PERMISSION`
- `INTERNAL`

---

# A.11.3 Foundation error codes

Canonical baseline:

### Configuration

- `PDP_CONFIG_DISABLED`
- `PDP_CONFIG_INVALID`

### Terminal

- `PDP_TERMINAL_NOT_FOUND`
- `PDP_TERMINAL_DISABLED`
- `PDP_TERMINAL_NOT_PAIRED`
- `PDP_TERMINAL_NOT_QUALIFIED`

### Job

- `PDP_JOB_NOT_FOUND`
- `PDP_JOB_CONFLICT`
- `PDP_JOB_ALREADY_TERMINAL`
- `PDP_JOB_INVALID_TRANSITION`
- `PDP_JOB_RESERVATION_EXPIRED`
- `PDP_JOB_RESERVATION_MISMATCH`

### Receipt

- `PDP_RECEIPT_BUILD_FAILED`
- `PDP_RECEIPT_INVALID`

### Driver

- `PDP_DRIVER_NOT_FOUND`
- `PDP_DRIVER_UNAVAILABLE`
- `PDP_DRIVER_CAPABILITY_UNSUPPORTED`

### Runtime printer classes

Reserved now:

- `PDP_BRIDGE_UNAVAILABLE`
- `PDP_PRINTER_NOT_READY`
- `PDP_PRINTER_PAPER_OUT`
- `PDP_PRINTER_COVER_OPEN`
- `PDP_PRINTER_OVERHEATED`
- `PDP_PRINTER_CUTTER_ERROR`
- `PDP_PRINT_COMMAND_FAILED`
- `PDP_PRINT_TIMEOUT`
- `PDP_PRINT_STATUS_UNKNOWN`

### Server

- `PDP_SERVER_UNAVAILABLE`
- `PDP_PERMISSION_DENIED`
- `PDP_INTERNAL_ERROR`

Prefix **PDP** = POS Direct Print.

Error format is frozen unless Open Decision A-OD-03 changes it.

---
