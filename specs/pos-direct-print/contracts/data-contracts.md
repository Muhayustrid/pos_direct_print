# Canonical Data Contracts

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.10 Canonical Data Contracts

Bagian ini mendefinisikan shape data antar module.

Ini bukan implementation.

---

## A.10.1 PrintRequest

Mandatory properties:

| Property | Type | Meaning |
|---|---|---|
| `reference_doctype` | string | `POS Invoice` atau `Sales Invoice` |
| `reference_name` | string | Invoice/document name |
| `terminal_id` | string | Resolved terminal |
| `source` | enum | Source canonical |
| `job_type` | enum | ORIGINAL / REPRINT / TEST |
| `requested_by` | string | User ID |
| `driver_key` | string/null | Explicit driver override or null |
| `parent_job_id` | string/null | Reprint parent |
| `reprint_reason` | string/null | Reprint reason |
| `options` | object | Extensible print options |

PrintRequest tidak boleh membawa raw printer commands.

---

# A.10.2 Reservation

| Property | Type |
|---|---|
| `job_id` | string |
| `reservation_token` | opaque string |
| `reserved_until` | datetime |
| `is_new_job` | boolean |
| `status` | PrintJobState |

Reservation token hanya digunakan selama active reservation dan tidak disimpan plaintext ke audit field.

---

# A.10.3 ReceiptDocument

Canonical intermediate representation.

Top-level fields:

| Property | Type | Required |
|---|---|---:|
| `schema_version` | integer | Ya |
| `reference_doctype` | string | Ya |
| `reference_name` | string | Ya |
| `locale` | string | Ya |
| `currency` | string | Ya |
| `paper_profile` | string | Ya |
| `blocks` | ordered array | Ya |
| `metadata` | object | Ya |

Allowed block categories pada schema v1:

- `TEXT`
- `SEPARATOR`
- `COLUMNS`
- `SPACER`
- `IMAGE`
- `QR`
- `FEED`
- `CUT`

Milestone A hanya mengunci schema.

Milestone B baru memakai subset yang dibutuhkan untuk happy path.

ReceiptDocument tidak boleh menyimpan function/reference browser object.

Harus serializable deterministically.

---

# A.10.4 DriverCapabilities

Canonical shape:

| Property | Type |
|---|---|
| `driver_key` | string |
| `available` | boolean |
| `supports_status` | boolean |
| `supports_text` | boolean |
| `supports_columns` | boolean |
| `supports_image` | boolean |
| `supports_qr` | boolean |
| `supports_feed` | boolean |
| `supports_cut` | boolean |
| `paper_width_mm` | 58 / 80 / null |
| `transport` | USB / SPI / BLUETOOTH / UNKNOWN |
| `metadata` | object |

---

# A.10.5 PrinterStatus

Canonical normalized shape:

| Property | Type |
|---|---|
| `state` | PrinterState |
| `ready` | boolean |
| `blocking` | boolean |
| `raw_code` | string/null |
| `raw_message` | string/null |
| `checked_at` | datetime |
| `metadata` | object |

Canonical PrinterState values:

- `READY`
- `DISCONNECTED`
- `PAPER_LOW`
- `PAPER_OUT`
- `COVER_OPEN`
- `OVERHEATED`
- `CUTTER_ERROR`
- `INCOMPATIBLE`
- `INITIALIZATION_FAILED`
- `BRIDGE_UNAVAILABLE`
- `UNKNOWN_ERROR`

---

# A.10.6 DriverPrintResult

| Property | Type |
|---|---|
| `accepted` | boolean |
| `content_started` | boolean |
| `content_completed` | boolean |
| `verification_supported` | boolean |
| `final_status` | PrinterStatus/null |
| `metadata` | object |

`accepted = true` tidak otomatis berarti physical success.

---

# A.10.7 PrintOutcome

Return utama PrintManager.

| Property | Type |
|---|---|
| `job_id` | string |
| `status` | PrintJobState |
| `attempt_id` | string/null |
| `success` | boolean |
| `fallback_used` | boolean |
| `requires_user_action` | boolean |
| `error` | PrintDomainError/null |

---
