# Milestone A — Foundation Specification
## ERPNext v16 × iMin Direct Print

**Status dokumen:** Draft for design freeze  
**Scope:** Foundation saja  
**Out of scope:** pemanggilan iMin Printer SDK nyata, model-specific printer behavior, retry reliability penuh, multi-model qualification, fleet deployment.

---

# A.0 Tujuan Milestone A

Milestone A membangun fondasi yang stabil untuk seluruh subsystem `pos_direct_print`.

Pada akhir Milestone A harus sudah ada kontrak tetap untuk:

1. identitas terminal;
2. identitas print job;
3. audit attempt;
4. state machine;
5. error taxonomy;
6. receipt intermediate representation;
7. driver interface;
8. POS v16 interception interface;
9. server-side reservation contract;
10. browser fallback boundary.

Milestone A **belum mencetak ke iMin**.

Milestone B nanti baru membuat single-device happy path menggunakan `imin_v1`.

---

# A.1 Boundary Arsitektur

Alur logical yang dikunci sejak Milestone A:

**ERPNext POS v16**

→ `erpnext_v16_pos` integration adapter

→ `PrintManager`

→ `JobCoordinator`

→ `ReceiptBuilder`

→ `BaseDriver`

→ driver konkret

Driver konkret pertama nanti:

`imin_v1`

Fallback driver:

`browser`

---

# A.2 Prinsip Non-Negotiable

Keputusan berikut dianggap final untuk semua milestone berikutnya.

### A.2.1 Tidak mengubah ERPNext core

Semua integrasi dilakukan dari custom Frappe app.

Tidak boleh ada patch langsung pada:

- ERPNext POS source;
- Frappe core;
- compiled asset ERPNext.

### A.2.2 Interception point

Interception canonical ERPNext v16:

`erpnext.PointOfSale.PastOrderSummary.prototype.print_receipt`

Original method harus disimpan sebagai browser fallback.

### A.2.3 Invoice dan printing terpisah

Keberhasilan transaksi/invoice tidak bergantung pada printer.

Print failure tidak boleh:

- rollback invoice;
- cancel invoice;
- menandai payment gagal;
- mengubah grand total;
- menjalankan submit ulang.

### A.2.4 Job dan Attempt adalah konsep berbeda

**POS Print Job** = logical printing request.

**POS Print Attempt** = satu percobaan eksekusi terhadap logical job tersebut.

Satu Job dapat mempunyai lebih dari satu Attempt hanya untuk retry yang secara eksplisit dianggap aman.

### A.2.5 UNCERTAIN tidak boleh retry sebagai attempt yang sama

Jika physical output mungkin sudah dimulai dan completion tidak dapat dibuktikan:

`UNCERTAIN`

Job tersebut tidak boleh di-auto-retry.

Jika kasir memilih mencetak lagi:

dibuat **POS Print Job baru** dengan `job_type = REPRINT`.

### A.2.6 Browser fallback tidak dianggap physical-print success

Browser API tidak dapat membuktikan kertas benar-benar keluar.

Karena itu browser fallback memiliki outcome khusus dan tidak boleh disamakan dengan `SUCCEEDED`.

---

# A.3 Canonical Identifiers

Tiga identifier berbeda digunakan.

### Job ID

Identitas logical job.

Field:

`job_id`

### Attempt ID

Identitas individual attempt.

Field:

`attempt_id`

### Terminal ID

Identitas logical physical POS terminal.

Field:

`terminal_id`

Nama internal Frappe document untuk ketiganya harus sama dengan identifier tersebut.

Dengan demikian:

- `POS Print Job.name = job_id`
- `POS Print Attempt.name = attempt_id`
- `POS Print Terminal.name = terminal_id`

Format identifier final masih termasuk Open Decision A-OD-01.

---

# A.4 Custom Doctype Inventory — Milestone A

Milestone A membutuhkan empat DocType.

1. `POS Print Settings`
2. `POS Print Terminal`
3. `POS Print Job`
4. `POS Print Attempt`

Tidak dibuat DocType terpisah untuk:

- printer capability;
- error log;
- receipt;
- retry;
- lock.

Alasannya:

- capability menjadi bagian Terminal;
- error detail menjadi bagian Attempt;
- receipt document menjadi snapshot Job;
- retry direpresentasikan Attempt;
- distributed reservation direpresentasikan Job.

---

# A.5 Data Model — POS Print Settings

## A.5.1 Characteristics

Type:

**Single DocType**

Purpose:

global configuration dan safe defaults untuk subsystem direct printing.

Tidak memiliki autoname.

---

## A.5.2 Fields

| Fieldname | Label | Frappe Type | Required | Default | Index | Description |
|---|---|---|---:|---|---|---|
| `enabled` | Enabled | Check | Ya | 0 | Tidak | Master switch subsystem |
| `operating_mode` | Operating Mode | Select | Ya | OFF | Tidak | `OFF`, `PILOT`, `ON` |
| `default_driver` | Default Driver | Data | Ya | browser | Tidak | Canonical driver key |
| `terminal_required` | Terminal Required | Check | Ya | 1 | Tidak | Printing harus mempunyai terminal identity |
| `allow_browser_fallback` | Allow Browser Fallback | Check | Ya | 1 | Tidak | Izinkan fallback ke original ERPNext print |
| `browser_fallback_confirmation` | Browser Fallback Requires Confirmation | Check | Ya | 1 | Tidak | User harus approve fallback |
| `reservation_ttl_seconds` | Reservation TTL Seconds | Int | Ya | 120 | Tidak | Masa berlaku reservation |
| `local_lock_ttl_seconds` | Local Lock TTL Seconds | Int | Ya | 30 | Tidak | Dasar lock sisi browser |
| `max_safe_auto_retries` | Max Safe Auto Retries | Int | Ya | 1 | Tidak | Maksimum auto retry untuk error yang terbukti pre-output |
| `safe_retry_delay_ms` | Safe Retry Delay | Int | Ya | 1000 | Tidak | Delay antar safe retry |
| `job_retention_days` | Job Retention Days | Int | Ya | 180 | Tidak | Retention audit job |
| `attempt_retention_days` | Attempt Retention Days | Int | Ya | 180 | Tidak | Retention audit attempt |
| `receipt_schema_version` | Receipt Schema Version | Int | Ya | 1 | Tidak | Canonical ReceiptDocument schema |
| `debug_logging` | Debug Logging | Check | Ya | 0 | Tidak | Verbose technical log |
| `settings_schema_version` | Settings Schema Version | Int | Ya | 1 | Tidak | Versioning settings |

---

## A.5.3 Validation

Constraints:

- `reservation_ttl_seconds > 0`
- `local_lock_ttl_seconds > 0`
- `max_safe_auto_retries >= 0`
- `safe_retry_delay_ms >= 0`
- `job_retention_days >= 1`
- `attempt_retention_days >= 1`
- `receipt_schema_version >= 1`

`default_driver` tidak menggunakan Select karena future drivers harus dapat ditambahkan tanpa schema migration.

---

# A.6 Data Model — POS Print Terminal

## A.6.1 Purpose

Mewakili **satu logical physical POS printing endpoint**.

Terminal bukan User.

Terminal bukan browser tab.

Terminal bukan POS Profile.

Satu terminal dapat digunakan oleh session/user berbeda, tetapi hanya merepresentasikan satu physical endpoint.

---

## A.6.2 Autoname

Document `name` berasal dari:

`terminal_id`

`terminal_id` harus unique.

---

## A.6.3 Fields

| Fieldname | Frappe Type | Required | Default | Index | Description |
|---|---|---:|---|---|---|
| `terminal_id` | Data | Ya | — | UNIQUE | Canonical terminal identifier |
| `terminal_label` | Data | Ya | — | Search | Human-readable name |
| `enabled` | Check | Ya | 1 | Index | Terminal aktif |
| `company` | Link → Company | Ya | — | Index | Company owner |
| `pos_profile` | Link → POS Profile | Ya | — | Index | POS Profile default |
| `driver_key` | Data | Ya | imin_v1 | Index | Current printer driver |
| `device_model` | Data | Tidak | — | Search | Exact model setelah diketahui |
| `device_serial` | Data | Tidak | — | Index | Serial number jika tersedia |
| `android_version` | Data | Tidak | — | Tidak | Android release |
| `rom_build` | Data | Tidak | — | Tidak | ROM/build fingerprint |
| `plugin_version` | Data | Tidak | — | Tidak | iMin plugin version |
| `browser_version` | Data | Tidak | — | Tidak | Chrome/browser version |
| `webview_version` | Data | Tidak | — | Tidak | Android WebView version |
| `transport` | Select | Ya | UNKNOWN | Index | `UNKNOWN`, `USB`, `SPI`, `BLUETOOTH` |
| `paper_width_mm` | Select | Ya | UNKNOWN | Index | `UNKNOWN`, `58`, `80` |
| `cutter_capability` | Select | Ya | UNKNOWN | Tidak | `UNKNOWN`, `SUPPORTED`, `UNSUPPORTED` |
| `qualification_status` | Select | Ya | UNVERIFIED | Index | `UNVERIFIED`, `QUALIFIED`, `BLOCKED` |
| `qualification_revision` | Data | Tidak | — | Tidak | Version/ID qualification |
| `capability_schema_version` | Int | Ya | 1 | Tidak | Version capability data |
| `capabilities_json` | Long Text | Tidak | — | Tidak | Serialized normalized capabilities |
| `last_seen_at` | Datetime | Tidak | — | Index | Last browser/device heartbeat |
| `last_health_state` | Select | Ya | UNKNOWN | Index | `UNKNOWN`, `READY`, `DEGRADED`, `OFFLINE` |
| `paired_client_id` | Data | Tidak | — | Index | Logical browser installation identity |
| `pairing_status` | Select | Ya | UNPAIRED | Index | `UNPAIRED`, `PAIRED`, `REVOKED` |
| `notes` | Small Text | Tidak | — | Tidak | Operational note |

---

## A.6.4 Required indexes

Single-column:

- unique `terminal_id`
- `enabled`
- `company`
- `pos_profile`
- `driver_key`
- `qualification_status`
- `paired_client_id`

Composite database indexes:

### IDX-TERM-01

`company, pos_profile, enabled`

Purpose:

lookup active terminals for a POS Profile.

### IDX-TERM-02

`paired_client_id, enabled`

Purpose:

resolve browser installation → terminal.

---

## A.6.5 Uniqueness policy

`device_serial` **tidak** database-unique.

Alasannya:

beberapa model/ROM mungkin tidak memberikan serial secara konsisten.

Sebaliknya duplicate serial dapat ditandai lewat validation/administrative warning nanti.

`paired_client_id` juga tidak database-unique pada Milestone A karena pairing policy multi-session akan difinalkan di Milestone C.

---

# A.7 Data Model — POS Print Job

## A.7.1 Purpose

Mewakili **satu logical printing intent**.

Contoh:

“Cetak original receipt untuk POS Invoice INV-0001.”

Job bukan satu API invocation dan bukan satu printer attempt.

---

## A.7.2 Autoname

`name = job_id`

`job_id` unique.

---

## A.7.3 Fields

| Fieldname | Frappe Type | Required | Default | Index | Description |
|---|---|---:|---|---|---|
| `job_id` | Data | Ya | — | UNIQUE | Canonical logical job ID |
| `idempotency_key` | Data | Ya | — | UNIQUE | Server deduplication key |
| `reference_doctype` | Link → DocType | Ya | — | Index | Target document type |
| `reference_name` | Dynamic Link | Ya | — | Index | Target document name |
| `company` | Link → Company | Ya | — | Index | Company |
| `pos_profile` | Link → POS Profile | Tidak | — | Index | Source POS Profile |
| `terminal` | Link → POS Print Terminal | Ya | — | Index | Physical terminal |
| `requested_by` | Link → User | Ya | — | Index | Requesting user |
| `source` | Select | Ya | — | Index | Request source |
| `job_type` | Select | Ya | ORIGINAL | Index | `ORIGINAL`, `REPRINT`, `TEST` |
| `parent_job` | Link → POS Print Job | Tidak | — | Index | Required for reprint |
| `reprint_reason` | Small Text | Tidak | — | Tidak | Required for REPRINT |
| `driver_key` | Data | Ya | — | Index | Driver chosen for job |
| `status` | Select | Ya | CREATED | Index | Canonical state machine |
| `status_reason_code` | Data | Tidak | — | Index | Last normalized reason |
| `reservation_owner` | Data | Tidak | — | Index | Reservation client/session identity |
| `reserved_at` | Datetime | Tidak | — | Index | Reservation start |
| `reserved_until` | Datetime | Tidak | — | Index | Reservation expiry |
| `attempt_count` | Int | Ya | 0 | Tidak | Number of started attempts |
| `safe_retry_count` | Int | Ya | 0 | Tidak | Automatic safe retries |
| `content_may_have_printed` | Check | Ya | 0 | Index | Safety-critical physical output flag |
| `receipt_schema_version` | Int | Ya | 1 | Tidak | ReceiptDocument schema |
| `receipt_hash` | Data | Tidak | — | Index | Hash canonical ReceiptDocument |
| `receipt_snapshot` | Long Text | Tidak | — | Tidak | Canonical serialized ReceiptDocument |
| `started_at` | Datetime | Tidak | — | Index | First physical attempt start |
| `finished_at` | Datetime | Tidak | — | Index | Terminal job completion |
| `last_error_code` | Data | Tidak | — | Index | Last normalized error |
| `last_error_phase` | Select | Tidak | — | Index | Error lifecycle phase |
| `last_error_detail` | Long Text | Tidak | — | Tidak | Technical error description |
| `fallback_used` | Check | Ya | 0 | Index | Browser fallback chosen |
| `browser_fallback_at` | Datetime | Tidak | — | Tidak | Fallback handoff timestamp |
| `metadata_json` | Long Text | Tidak | — | Tidak | Extensible non-query metadata |

---

## A.7.4 `source` values

Canonical values:

- `POS_AUTO`
- `POS_MANUAL`
- `REPRINT_UI`
- `TEST_UI`
- `API`

No arbitrary strings.

---

## A.7.5 `last_error_phase` values

- `VALIDATION`
- `RESERVATION`
- `RECEIPT`
- `PREFLIGHT`
- `PRINT`
- `VERIFY`
- `FALLBACK`

---

## A.7.6 Required indexes

Single:

- unique `job_id`
- unique `idempotency_key`
- `status`
- `terminal`
- `reference_doctype`
- `reference_name`
- `parent_job`
- `requested_by`
- `last_error_code`

Composite:

### IDX-JOB-01

`reference_doctype, reference_name, job_type`

Purpose:

invoice print history.

### IDX-JOB-02

`terminal, status`

Purpose:

active terminal job lookup.

### IDX-JOB-03

`terminal, creation`

Purpose:

operational print history.

### IDX-JOB-04

`reference_doctype, reference_name, creation`

Purpose:

audit lookup.

### IDX-JOB-05

`status, reserved_until`

Purpose:

reservation expiry cleanup.

---

## A.7.7 Validation rules

If `job_type = REPRINT`:

- `parent_job` required;
- `reprint_reason` required.

If `status = RESERVED` or later:

- `reservation_owner` required.

If `receipt_hash` exists:

- `receipt_snapshot` must exist.

If `content_may_have_printed = 1`:

job may never enter an automatic retry path.

---

# A.8 Data Model — POS Print Attempt

## A.8.1 Purpose

Mencatat satu physical execution attempt.

Retry aman menghasilkan Attempt baru di Job yang sama.

Reprint menghasilkan Job baru.

---

## A.8.2 Autoname

`name = attempt_id`

---

## A.8.3 Fields

| Fieldname | Frappe Type | Required | Default | Index | Description |
|---|---|---:|---|---|---|
| `attempt_id` | Data | Ya | — | UNIQUE | Canonical attempt ID |
| `job` | Link → POS Print Job | Ya | — | Index | Parent logical job |
| `attempt_no` | Int | Ya | — | Index | 1-based attempt sequence |
| `terminal` | Link → POS Print Terminal | Ya | — | Index | Terminal used |
| `driver_key` | Data | Ya | — | Index | Driver |
| `outcome` | Select | Ya | STARTED | Index | Attempt result |
| `phase_reached` | Select | Ya | RESERVATION | Index | Furthest lifecycle phase |
| `content_started` | Check | Ya | 0 | Index | At least one physical content command may have started |
| `content_completed` | Check | Ya | 0 | Tidak | All intended content commands completed |
| `normalized_status_before` | Data | Tidak | — | Index | Canonical printer state |
| `normalized_status_after` | Data | Tidak | — | Index | Canonical printer state |
| `raw_status_before` | Small Text | Tidak | — | Tidak | Driver-specific raw status |
| `raw_status_after` | Small Text | Tidak | — | Tidak | Driver-specific raw status |
| `error_code` | Data | Tidak | — | Index | Canonical error code |
| `error_detail` | Long Text | Tidak | — | Tidak | Technical detail |
| `retry_class` | Select | Ya | NONE | Index | Retry policy classification |
| `client_session_id` | Data | Tidak | — | Index | Browser login/session lifecycle ID |
| `browser_tab_id` | Data | Tidak | — | Index | Browser tab identity |
| `paired_client_id` | Data | Tidak | — | Index | Browser installation identity |
| `driver_version` | Data | Tidak | — | Tidak | Driver implementation version |
| `asset_version` | Data | Tidak | — | Tidak | Loaded app asset version |
| `started_at` | Datetime | Ya | — | Index | Attempt start |
| `finished_at` | Datetime | Tidak | — | Index | Attempt end |
| `duration_ms` | Int | Tidak | — | Tidak | Measured duration |
| `metadata_json` | Long Text | Tidak | — | Tidak | Driver-specific supporting metadata |

---

## A.8.4 `outcome` values

- `STARTED`
- `BLOCKED`
- `FAILED_SAFE`
- `UNCERTAIN`
- `SUCCEEDED`
- `FALLBACK_BROWSER`
- `CANCELLED`

---

## A.8.5 `phase_reached`

- `RESERVATION`
- `RECEIPT`
- `PREFLIGHT`
- `PRINT`
- `VERIFY`
- `FALLBACK`

---

## A.8.6 `retry_class`

- `NONE`
- `AUTO_SAFE`
- `MANUAL_SAFE`
- `REPRINT_ONLY`

Semantics:

### NONE

Tidak retry.

### AUTO_SAFE

System boleh membuat Attempt baru otomatis jika retry limit belum tercapai.

### MANUAL_SAFE

User harus menekan Retry.

### REPRINT_ONLY

Job yang sama tidak boleh dicoba lagi.

User harus membuat REPRINT Job.

---

## A.8.7 Database indexes

Unique:

`attempt_id`

Composite unique:

### IDX-ATT-UNIQUE-01

`job, attempt_no`

Composite normal:

### IDX-ATT-01

`job, started_at`

### IDX-ATT-02

`terminal, started_at`

### IDX-ATT-03

`outcome, started_at`

### IDX-ATT-04

`error_code, started_at`

---

# A.9 Relationships

Canonical relationship:

`POS Print Terminal`

1 → many

`POS Print Job`

1 → many

`POS Print Attempt`

Invoice/document relationship:

`POS Invoice / Sales Invoice`

1 → many

`POS Print Job`

Reprint:

`POS Print Job ORIGINAL`

1 → many

`POS Print Job REPRINT`

melalui:

`parent_job`.

---

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

# A.12 JS Module Contracts

---

# A.12.1 `bootstrap`

Purpose:

initialize subsystem once per Desk/browser lifecycle.

Functions:

### `initialize`

Input:

BootstrapContext containing:

- current user;
- current route;
- feature settings;
- app asset version.

Returns:

BootstrapResult:

- initialized;
- integration_installed;
- active_driver;
- warnings.

May raise:

- `PDP_CONFIG_INVALID`
- `PDP_INTERNAL_ERROR`

Must be idempotent.

Calling initialize twice must not install two POS overrides.

### `shutdown`

Input:

none.

Return:

void/result acknowledgement.

Responsibilities:

- restore override if necessary;
- release transient client resources.

---

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

# A.12.3 `core/print_manager`

Purpose:

top-level orchestration.

POS integration may call PrintManager.

POS integration may not call printer driver directly.

### `requestPrint`

Input:

PrintRequest.

Return:

Promise-like asynchronous `PrintOutcome`.

Responsibilities conceptually:

1. validate request;
2. resolve terminal;
3. reserve job;
4. build ReceiptDocument;
5. select driver;
6. coordinate attempt;
7. drive state transitions;
8. normalize errors;
9. produce PrintOutcome.

Possible errors/outcomes:

all canonical domain errors.

### `retryJob`

Input:

- `job_id`
- retry initiator;
- retry reason.

Return:

PrintOutcome.

Precondition:

job state must allow retry.

Invalid use:

`UNCERTAIN` must throw/return `PDP_JOB_INVALID_TRANSITION`.

### `cancelJob`

Input:

- job_id;
- reason.

Return:

PrintJobSnapshot.

Only valid from cancellable states.

### `fallbackToBrowser`

Input:

- job_id;
- explicit user approval flag.

Return:

PrintOutcome.

Must reject if:

`content_may_have_printed = true`.

### `getJobStatus`

Input:

job_id.

Return:

PrintJobSnapshot.

---

# A.12.4 `core/print_job`

Pure domain/state-machine component.

Must contain no printer SDK calls.

### `canTransition`

Input:

- current_state;
- target_state.

Return:

boolean.

### `assertTransition`

Input:

- current_state;
- target_state.

Return:

transition validity result.

Error:

`PDP_JOB_INVALID_TRANSITION`.

### `isTerminalState`

Input:

state.

Return:

boolean.

### `isRetryAllowed`

Input:

- job snapshot;
- latest attempt;
- domain error.

Return:

RetryDecision:

- allowed;
- retry_class;
- automatic;
- reason.

### `deriveContentRisk`

Input:

latest attempt.

Return:

boolean `content_may_have_printed`.

---

# A.12.5 `core/job_coordinator`

Purpose:

server-backed job reservation and lifecycle coordination.

### `reserve`

Input:

PrintRequest + client concurrency context.

Return:

Reservation.

Errors:

- `PDP_JOB_CONFLICT`
- `PDP_JOB_RESERVATION_EXPIRED`
- `PDP_TERMINAL_DISABLED`

### `beginAttempt`

Input:

- job_id;
- reservation token;
- client context.

Return:

AttemptSnapshot.

### `transition`

Input:

- job_id;
- expected_from_state;
- target_state;
- reservation token;
- transition metadata.

Return:

updated PrintJobSnapshot.

Transition must be atomic.

If actual state does not equal expected state:

`PDP_JOB_CONFLICT`.

### `completeAttempt`

Input:

- attempt_id;
- outcome;
- content flags;
- printer states;
- error if any.

Return:

AttemptSnapshot.

### `release`

Input:

job_id + reservation token.

Return:

acknowledgement.

---

# A.12.6 `core/print_api`

Purpose:

thin Frappe RPC transport.

No business rules.

### Required operations

- get settings;
- resolve terminal;
- reserve print job;
- start attempt;
- transition job;
- complete attempt;
- release reservation;
- retrieve job.

All RPC failures must be normalized before reaching POS UI.

---

# A.12.7 `core/capability_registry`

Milestone A provides generic registry only.

### `registerDriver`

Input:

DriverManifest.

Return:

registration result.

Duplicate driver key:

reject unless exact same registration instance is explicitly allowed by bootstrap policy.

### `getDriver`

Input:

driver_key.

Return:

driver factory/reference.

Error:

`PDP_DRIVER_NOT_FOUND`.

### `hasDriver`

Input:

driver_key.

Return:

boolean.

### `resolveCapabilities`

Input:

- driver;
- terminal;
- runtime capabilities.

Return:

DriverCapabilities.

---

# A.12.8 `core/error_normalizer`

### `normalize`

Input:

- raw error;
- lifecycle phase;
- context including content_started flag.

Return:

PrintDomainError.

### `classifyRetry`

Input:

PrintDomainError + attempt context.

Return:

retry class.

Absolute rule:

if `content_may_have_printed = true`:

return must never be `AUTO_SAFE` or `MANUAL_SAFE`.

Must be `REPRINT_ONLY` or `NONE`.

### `toUserError`

Input:

PrintDomainError.

Return:

safe user-facing structure containing:

- title/message key;
- allowed actions;
- no stack trace.

---

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

# A.12.10 `receipt/receipt_layout`

Purpose:

logical receipt values → ordered receipt blocks.

### `layout`

Input:

- ReceiptViewModel;
- PaperProfile.

Return:

ordered ReceiptDocument blocks.

No printer calls.

---

# A.12.11 `receipt/text_wrapper`

### `wrap`

Input:

- text;
- maximum logical width;
- WrapPolicy.

Return:

ordered array of strings.

### `truncate`

Input:

- text;
- max width;
- truncation policy.

Return:

string.

Must never split Unicode code point incorrectly.

Precise character-width policy for thermal font belongs to Milestone D.

---

# A.12.12 `receipt/currency_formatter`

### `format`

Input:

- numeric amount;
- currency;
- locale;
- format policy.

Return:

string.

Must be deterministic.

No dependency on browser locale defaults without explicit locale.

---

# A.12.13 `drivers/base_driver`

Abstract driver contract.

Every printer driver must implement it.

### `detect`

Input:

DriverContext.

Return:

DetectionResult:

- available;
- reason;
- metadata.

### `initialize`

Input:

DriverContext.

Return:

InitializationResult.

### `getCapabilities`

Input:

none/runtime context if required.

Return:

DriverCapabilities.

### `getStatus`

Return:

PrinterStatus.

### `print`

Input:

- ReceiptDocument;
- DriverJobContext.

Return:

DriverPrintResult.

### `feed`

Input:

normalized feed request.

Return:

DriverOperationResult.

### `cut`

Input:

cut request.

Return:

DriverOperationResult.

Unsupported cutter:

must result in capability-related controlled outcome, never uncontrolled exception.

### `dispose`

Input:

none.

Return:

cleanup acknowledgement.

---

# A.12.14 `drivers/imin_v1_driver`

Milestone A **tidak mengimplementasikan SDK-specific behavior**.

Contract Milestone A hanya mengunci:

- `driver_key = imin_v1`;
- harus memenuhi seluruh BaseDriver contract;
- raw iMin status tidak boleh keluar dari driver;
- SDK-specific exceptions harus dinormalisasi;
- printer connection/bridge objects tidak boleh diberikan kepada PrintManager.

Exact V1 bridge calls, initialization strategy, model mappings, status conversion, paper width dan cutter behavior menjadi Milestone B/D.

---

# A.12.15 `drivers/browser_driver`

Canonical key:

`browser`

BrowserDriver berbeda dengan physical driver.

Its output indicates:

**browser print handoff**, bukan confirmed physical success.

### `print`

Input:

browser fallback context.

Return outcome equivalent to:

- fallback handoff accepted;
- physical completion unknown.

BrowserDriver harus memakai saved original ERPNext `print_receipt` path.

---

# A.13 Client Identity Contract

Milestone A mendefinisikan tiga identity level.

### paired_client_id

Satu browser installation/device profile.

Persist across browser reload.

### client_session_id

Satu logical loaded POS session.

Berubah ketika application lifecycle baru dimulai.

### browser_tab_id

Satu tab/window.

Berubah untuk tab baru.

Digunakan untuk audit dan Milestone C concurrency.

---

# A.14 Print Job State Machine

Canonical states:

1. `CREATED`
2. `RESERVED`
3. `PREFLIGHT`
4. `BLOCKED`
5. `PRINTING`
6. `VERIFYING`
7. `FAILED_SAFE`
8. `UNCERTAIN`
9. `SUCCEEDED`
10. `FALLBACK_BROWSER`
11. `CANCELLED`

---

# A.15 Terminal States

Terminal/final:

- `UNCERTAIN`
- `SUCCEEDED`
- `FALLBACK_BROWSER`
- `CANCELLED`

`FAILED_SAFE` bukan final karena safe retry dapat dilakukan.

`BLOCKED` bukan final karena condition dapat diperbaiki.

---

# A.16 State Transition Table

| From | To | Allowed | Trigger |
|---|---|---:|---|
| CREATED | RESERVED | Ya | Server reservation berhasil |
| CREATED | CANCELLED | Ya | User/system cancel sebelum reservation |
| CREATED | FAILED_SAFE | Ya | Fatal validation/config error tanpa output |
| RESERVED | PREFLIGHT | Ya | Attempt dimulai |
| RESERVED | FAILED_SAFE | Ya | Pre-output infrastructure failure |
| RESERVED | CANCELLED | Ya | User cancel sebelum printer operation |
| PREFLIGHT | PRINTING | Ya | Printer/driver declared ready |
| PREFLIGHT | BLOCKED | Ya | Recoverable condition requiring intervention |
| PREFLIGHT | FAILED_SAFE | Ya | Pre-output failure |
| PREFLIGHT | FALLBACK_BROWSER | Ya | Explicit approved fallback sebelum output |
| PREFLIGHT | CANCELLED | Ya | User cancels |
| BLOCKED | PREFLIGHT | Ya | Condition resolved + retry requested |
| BLOCKED | FALLBACK_BROWSER | Ya | Approved browser fallback |
| BLOCKED | CANCELLED | Ya | User abandons printing |
| BLOCKED | FAILED_SAFE | Ya | Block converts into nonrecoverable pre-output failure |
| FAILED_SAFE | RESERVED | Ya | Safe retry creates new Attempt/reservation cycle |
| FAILED_SAFE | FALLBACK_BROWSER | Ya | Approved fallback and no output risk |
| FAILED_SAFE | CANCELLED | Ya | User abandons |
| PRINTING | VERIFYING | Ya | All intended content commands completed |
| PRINTING | UNCERTAIN | Ya | Failure after physical output may have started |
| VERIFYING | SUCCEEDED | Ya | Verification criteria satisfied |
| VERIFYING | UNCERTAIN | Ya | Completion cannot be confidently established |

All other transitions:

**invalid**.

---

# A.17 Explicit Forbidden Transitions

Particularly important:

`UNCERTAIN → PREFLIGHT` — forbidden

`UNCERTAIN → PRINTING` — forbidden

`UNCERTAIN → SUCCEEDED` — forbidden after state persisted

`SUCCEEDED → PRINTING` — forbidden

`FALLBACK_BROWSER → PRINTING` — forbidden

`CANCELLED → PRINTING` — forbidden

`PRINTING → FAILED_SAFE` — forbidden

Reason:

once printing phase starts, failure cannot be labelled “safe” unless driver can prove no content was issued.

System rule is conservative:

**unknown = may have printed.**

---

# A.18 Retry Matrix

| State | Auto Retry | Manual Retry Same Job | New REPRINT Job |
|---|---:|---:|---:|
| CREATED | N/A | N/A | Tidak |
| RESERVED | Tidak | Conditional | Tidak |
| PREFLIGHT | Conditional | Ya | Tidak |
| BLOCKED | Tidak | Ya | Tidak |
| FAILED_SAFE | Ya, jika retry_class=AUTO_SAFE | Ya | Tidak |
| PRINTING | Tidak | Tidak | Tidak sebelum final |
| VERIFYING | Tidak | Tidak | Tidak sebelum final |
| UNCERTAIN | **Tidak** | **Tidak** | **Ya** |
| SUCCEEDED | Tidak | Tidak | Ya jika business policy mengizinkan |
| FALLBACK_BROWSER | Tidak | Tidak | Ya jika user memerlukan reprint |
| CANCELLED | Tidak | Tidak | New original/reprint request berdasarkan business context |

---

# A.19 Automatic Retry Rule

Auto retry hanya sah jika seluruh kondisi berikut benar:

1. latest error `retry_class = AUTO_SAFE`;
2. `content_started = 0`;
3. `content_may_have_printed = 0`;
4. `safe_retry_count < max_safe_auto_retries`;
5. reservation/job masih valid atau dapat di-reserve ulang;
6. job bukan terminal state.

Jika salah satu false:

tidak boleh auto retry.

---

# A.20 Idempotency Contract

Setiap ORIGINAL print request harus menghasilkan deterministic logical deduplication scope.

Idempotency key harus mencakup minimal:

- reference doctype;
- reference name;
- terminal;
- job type;
- print purpose/version discriminator.

Idempotency key **bukan** job ID.

Job ID harus selalu globally unique.

Exact construction format menjadi Open Decision A-OD-02.

---

# A.21 Server Atomicity Contract

Operation berikut wajib transactional/atomic:

### Reserve job

Dua concurrent requests dengan idempotency key sama:

maksimal satu logical Job aktif/original yang dibuat.

### Transition job

Transition menggunakan optimistic expected state.

Client mengirim:

`expected_from_state`.

Jika database state berbeda:

return `PDP_JOB_CONFLICT`.

Client tidak boleh overwrite state terakhir secara buta.

### Attempt number

`attempt_no` harus unique per Job.

Concurrent retry tidak boleh menghasilkan dua `attempt_no = 2`.

---

# A.22 Definition of Done — Milestone A

## A-DOD-01 — App isolation

Tidak ada modification pada file ERPNext/Frappe core.

Semua extension berasal dari custom app.

**Objective evidence:** repository diff ERPNext/Frappe = zero.

---

## A-DOD-02 — Core DocTypes available

Empat DocType tersedia:

- POS Print Settings
- POS Print Terminal
- POS Print Job
- POS Print Attempt

Semua required fields, unique constraints, values dan indexes sesuai specification.

---

## A-DOD-03 — POS override is idempotent

Memanggil subsystem initialization berulang kali tidak menggandakan prototype override.

Satu user action hanya menghasilkan satu invocation ke PrintManager.

---

## A-DOD-04 — Original ERPNext print preserved

Original `print_receipt` reference disimpan dan dapat dipanggil kembali.

Ketika direct printing disabled:

perilaku browser print tetap sama dengan baseline ERPNext.

---

## A-DOD-05 — Job state machine enforced

100% transition di tabel A.16 diterima.

100% transition di luar tabel ditolak.

Tidak ada direct state mutation tanpa validator/coordinator.

---

## A-DOD-06 — Concurrency-safe reservation

Dua request concurrent dengan idempotency key sama menghasilkan maksimal satu logical original Job.

---

## A-DOD-07 — Attempt audit deterministic

Setiap execution attempt mendapat:

- unique attempt ID;
- monotonically increasing attempt number;
- timestamps;
- terminal;
- driver;
- outcome.

---

## A-DOD-08 — UNCERTAIN safety rule enforced

Job `UNCERTAIN` tidak dapat:

- auto retry;
- manual retry sebagai Job yang sama;
- berpindah kembali ke PREFLIGHT/PRINTING.

---

## A-DOD-09 — Driver abstraction enforced

PrintManager tidak bergantung pada API iMin.

Dependency hanya terhadap BaseDriver contract.

Test fake driver dapat dipasang tanpa mengubah PrintManager.

---

## A-DOD-10 — Receipt abstraction enforced

ReceiptBuilder menghasilkan serializable ReceiptDocument.

Tidak mengeluarkan ESC/POS bytes atau iMin command.

---

## A-DOD-11 — Canonical error normalization

Raw exception tidak muncul sebagai contract ke POS integration.

Setiap operational failure menjadi PrintDomainError canonical.

---

## A-DOD-12 — No iMin dependency required

Automated Milestone A tests dapat dijalankan tanpa:

- iMin device;
- iMin plugin;
- Android;
- printer.

---

## A-DOD-13 — Browser fallback boundary correct

Browser fallback hanya boleh dipilih ketika `content_may_have_printed = 0`.

Jika flag = 1, fallback otomatis maupun user-triggered harus ditolak.

---

## A-DOD-14 — Deterministic receipt hashing

ReceiptDocument identik menghasilkan hash identik.

Perubahan content atau schema yang material menghasilkan hash berbeda.

---

# A.23 Acceptance Tests — Given / When / Then

## A-AT-01 — App isolation

**Given** clean ERPNext v16 environment  
**When** `pos_direct_print` Foundation dipasang  
**Then** tidak ada source file ERPNext/Frappe yang berubah  
**And** seluruh customization berasal dari custom app.

Supports: A-DOD-01.

---

# A-AT-02 — DocType schema

**Given** fresh site  
**When** custom app di-install/migrate  
**Then** keempat DocType tersedia  
**And** semua required field sesuai schema  
**And** unique constraint berlaku untuk `terminal_id`, `job_id`, `attempt_id`, dan `idempotency_key`.

Supports: A-DOD-02.

---

# A-AT-03 — Duplicate job ID

**Given** existing Job dengan `job_id = X`  
**When** system mencoba membuat Job kedua dengan `job_id = X`  
**Then** persistence ditolak.

Supports: A-DOD-02.

---

# A-AT-04 — Override idempotency

**Given** ERPNext POS loaded  
**When** direct-print bootstrap diinisialisasi tiga kali  
**And** kasir menjalankan satu print action  
**Then** PrintManager menerima tepat satu PrintRequest.

Supports: A-DOD-03.

---

# A-AT-05 — Restore original printing

**Given** direct-print override telah terpasang  
**When** subsystem dinonaktifkan/restored  
**And** kasir memilih Print Receipt  
**Then** saved original ERPNext print path dipanggil satu kali.

Supports: A-DOD-04.

---

# A-AT-06 — Feature disabled

**Given** POS Print Settings `enabled = 0`  
**When** kasir melakukan print  
**Then** custom physical driver tidak dipanggil  
**And** original ERPNext print behavior digunakan.

Supports: A-DOD-04.

---

# A-AT-07 — Valid transitions

**Given** Job berada di setiap source state pada tabel A.16  
**When** setiap transition yang ditandai valid dijalankan  
**Then** transition diterima.

Supports: A-DOD-05.

---

# A-AT-08 — Invalid transitions

**Given** Job `UNCERTAIN`  
**When** caller mencoba mengubah state menjadi `PREFLIGHT`  
**Then** operation ditolak dengan `PDP_JOB_INVALID_TRANSITION`  
**And** stored state tetap `UNCERTAIN`.

Supports: A-DOD-05 dan A-DOD-08.

---

# A-AT-09 — Concurrent reservation

**Given** dua browser request dengan idempotency key sama  
**When** keduanya melakukan reservation hampir bersamaan  
**Then** maksimal satu original Job dibuat  
**And** request lain menerima existing/conflict outcome sesuai reservation contract  
**And** tidak ada duplicate logical original Job.

Supports: A-DOD-06.

---

# A-AT-10 — Concurrent attempt numbering

**Given** Job mempunyai Attempt 1  
**When** dua retry request concurrent mencoba memulai Attempt berikutnya  
**Then** tidak pernah terdapat dua Attempt dengan `(job, attempt_no) = (X, 2)`.

Supports: A-DOD-07.

---

# A-AT-11 — Safe retry

**Given** Attempt gagal sebelum physical content dimulai  
**And** error `retry_class = AUTO_SAFE`  
**And** retry count masih di bawah batas  
**When** JobCoordinator mengevaluasi retry  
**Then** Attempt baru dapat dibuat pada Job sama.

Supports: A-DOD-07 dan A-DOD-08.

---

# A-AT-12 — Uncertain cannot retry

**Given** Attempt mempunyai `content_started = 1`  
**And** print completion tidak dapat dibuktikan  
**When** Job berakhir `UNCERTAIN`  
**Then** retry class menjadi `REPRINT_ONLY` atau `NONE`  
**And** auto retry tidak dijalankan  
**And** manual same-job retry ditolak.

Supports: A-DOD-08.

---

# A-AT-13 — Fake driver

**Given** fake test driver memenuhi BaseDriver contract  
**When** driver tersebut diregistrasikan sebagai active driver  
**Then** PrintManager dapat berinteraksi dengannya tanpa dependency pada iMin API.

Supports: A-DOD-09 dan A-DOD-12.

---

# A-AT-14 — Receipt serializability

**Given** normalized invoice test fixture  
**When** ReceiptBuilder membuat ReceiptDocument  
**Then** document dapat diserialisasi sepenuhnya  
**And** tidak berisi function, DOM node, printer object, atau raw SDK reference.

Supports: A-DOD-10.

---

# A-AT-15 — Raw exception normalization

**Given** fake driver melempar generic runtime exception  
**When** exception melewati error normalization boundary  
**Then** POS-facing result berupa PrintDomainError canonical  
**And** raw stack trace tidak menjadi user-facing error.

Supports: A-DOD-11.

---

# A-AT-16 — Browser fallback safe

**Given** Job gagal sebelum content dimulai  
**And** `content_may_have_printed = 0`  
**When** user menyetujui Browser Fallback  
**Then** original ERPNext browser print path dapat dipanggil  
**And** Job berakhir `FALLBACK_BROWSER`.

Supports: A-DOD-13.

---

# A-AT-17 — Browser fallback unsafe

**Given** `content_may_have_printed = 1`  
**When** caller meminta Browser Fallback  
**Then** request ditolak  
**And** original browser print tidak dipanggil.

Supports: A-DOD-13.

---

# A-AT-18 — Deterministic hash

**Given** ReceiptDocument A dan B memiliki canonical content serta schema identik  
**When** hash keduanya dihitung  
**Then** hash A sama dengan hash B.

**Given** field material dalam B berubah  
**When** hash dihitung ulang  
**Then** hash berbeda.

Supports: A-DOD-14.

---

# A.24 Open Design Decisions

Bagian ini **harus dibekukan sebelum Codex mengerjakan Milestone A**.

Saya sertakan recommended default supaya Anda cukup menerima/mengubah.

---

## A-OD-01 — Identifier format

### Recommended

Job:

`PDPJ-<ULID>`

Attempt:

`PDPA-<ULID>`

Terminal:

`PDPTERM-<business-readable-code>`

Contoh terminal secara konseptual:

`PDPTERM-SBY01-KASIR01`

### Why

ULID:

- globally unique;
- sortable by time;
- tidak bergantung database sequence;
- aman untuk concurrent multi-outlet deployment.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-02 — Idempotency key construction

Recommended semantic components:

`schema-version + reference_doctype + reference_name + terminal_id + job_type + purpose`

Lalu di-hash menjadi fixed-length value.

Timestamp **tidak boleh** ikut original idempotency key karena akan menghancurkan deduplication.

REPRINT harus mendapatkan discriminator terpisah sehingga reprint valid tidak bertabrakan dengan original.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-03 — Error-code naming convention

Recommended:

`PDP_<DOMAIN>_<ERROR>`

Contoh:

`PDP_PRINTER_PAPER_OUT`

Semua uppercase ASCII.

Tidak menggunakan numeric-only codes.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-04 — Driver key convention

Recommended lowercase snake-case identifiers:

- `imin_v1`
- `browser`
- future: `escpos_network`
- future: `bluetooth_escpos`

Driver key dianggap stable API identifier.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-05 — POS custom event namespace

Walaupun Milestone A tidak membutuhkan realtime event bus besar, namespace harus dikunci agar milestone berikut tidak improvisasi.

Recommended prefix:

`pos_direct_print:`

Reserved event names:

- `pos_direct_print:job_created`
- `pos_direct_print:job_state_changed`
- `pos_direct_print:attempt_started`
- `pos_direct_print:attempt_finished`
- `pos_direct_print:terminal_state_changed`
- `pos_direct_print:error`

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-06 — Original print deduplication scope

Recommended policy:

Satu invoice boleh mempunyai maksimal satu concurrently-active `ORIGINAL` print job per terminal.

Setelah original Job `SUCCEEDED`, user yang ingin print lagi harus menggunakan REPRINT path.

Ini memberikan audit yang paling jelas.

Alternative:

manual Print Receipt setelah success boleh dianggap new ORIGINAL.

Saya **tidak merekomendasikan** alternative tersebut.

**Need decision.**

---

# A-OD-07 — REPRINT reason policy

Recommended:

Reprint selalu membutuhkan `reprint_reason`.

Milestone awal:

free-text required.

Milestone operational readiness dapat menambahkan selectable reason categories.

**Need decision:** required / optional.

---

# A-OD-08 — Job retention

Current recommended defaults:

- Job: 180 hari.
- Attempt: 180 hari.

Alternative:

365 hari jika audit receipt perlu satu tahun.

**Need business decision.**

---

# A-OD-09 — Receipt snapshot retention

Recommended:

simpan canonical ReceiptDocument pada Job.

Keuntungannya:

- audit;
- deterministic reprint;
- troubleshooting;
- comparison after template upgrade.

Tradeoff:

database storage lebih besar.

Saya merekomendasikan **YES**.

**Need decision.**

---

# A-OD-10 — Browser fallback policy

Recommended:

- tersedia;
- requires explicit confirmation;
- hanya boleh jika `content_may_have_printed = 0`.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-11 — Terminal qualification in Foundation

Recommended:

`UNVERIFIED` terminal masih boleh digunakan di DEV/TEST tetapi tidak di production mode `ON`.

Pada production:

harus `QUALIFIED`.

Exact production enforcement baru aktif di Milestone D/E.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-12 — Test Job audit

Recommended:

`TEST` print juga disimpan dalam POS Print Job/Attempt.

Tujuannya:

hardware qualification mempunyai historical evidence.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-13 — Physical-success semantics

Recommended:

`SUCCEEDED` hanya berarti direct printer driver berhasil melewati completion criteria.

Browser print **tidak pernah** diberi status `SUCCEEDED`.

Ia berakhir:

`FALLBACK_BROWSER`.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-14 — Server clock authority

Recommended:

semua authoritative timestamps berasal dari server/Frappe.

Browser timestamps hanya disimpan sebagai diagnostic metadata.

Ini mencegah masalah jam Android device salah.

**Need decision:** ACCEPT / CHANGE.

---

# A-OD-15 — Canonical timezone policy

Recommended:

audit timestamps tersimpan mengikuti standard datetime handling Frappe/server.

Rendering ke user mengikuti timezone site/user.

Tidak menyimpan local Android clock sebagai authoritative field.

**Need decision:** ACCEPT / CHANGE.

---

# A.25 Items Explicitly Deferred to Milestone B

Codex **tidak boleh menebak/mengerjakan** hal berikut saat coding Milestone A:

- iMin V1 JavaScript API calls;
- iMin plugin initialization;
- actual receipt printing;
- actual `getPrinterStatus`;
- 58 mm exact item formatting;
- cutter implementation;
- QR;
- logo;
- physical retry;
- delay customer/internal receipt;
- model detection;
- USB vs SPI selection.

Semua itu Milestone B atau D.

---

# A.26 Items Explicitly Deferred to Milestone C

- robust multi-tab coordination;
- browser local lock implementation detail;
- cross-tab signaling;
- sleep/wake recovery;
- advanced retry;
- bridge re-init strategy;
- UNCERTAIN UX workflow.

Foundation hanya menyiapkan identity/state contract.

---

# A.27 Items Explicitly Deferred to Milestone D

- D1/D1w/D4/M2/M2 Pro/S1 capability matrix;
- model-specific status normalization;
- ROM qualification;
- width-specific capability;
- cutter capabilities;
- transport differences.

---

# A.28 Suggested Codex Handoff Sequence

Jangan memberikan Milestone A+B sekaligus kepada Codex.

Milestone A sendiri saya sarankan dibagi menjadi tiga coding batches.

---

## Codex Batch A1 — Persistence Foundation

Scope:

- custom app skeleton;
- four DocTypes;
- constraints;
- database indexes;
- server-side job/attempt domain;
- state transition validator;
- reservation primitives;
- automated backend tests.

Explicitly exclude:

POS prototype override dan printer integration.

### Exit condition

A-DOD-01, 02, 05, 06, 07, 08 terpenuhi pada backend/domain level.

---

## Codex Batch A2 — Client Foundation

Scope:

- bootstrap;
- ERPNext v16 integration adapter;
- PrintManager contract;
- JobCoordinator client;
- Print API transport;
- BaseDriver;
- fake driver;
- capability registry;
- error normalizer.

Still exclude:

actual iMin SDK.

### Exit condition

A-DOD-03, 04, 09, 11, 12 terpenuhi.

---

## Codex Batch A3 — Receipt + Foundation Integration Tests

Scope:

- ReceiptDocument schema;
- ReceiptBuilder;
- receipt layout abstractions;
- text wrapper contract;
- currency formatter;
- deterministic receipt hash;
- browser fallback boundary;
- integrated automated tests.

### Exit condition

A-DOD-10, 13, 14 terpenuhi dan seluruh A acceptance suite hijau.

---

# A.29 Milestone A Final Handoff Gate

Milestone A specification dianggap **READY FOR CODEX** hanya jika:

1. seluruh A-OD-01 sampai A-OD-15 sudah diputuskan;
2. nama empat DocType diterima final;
3. state names diterima final;
4. error-code prefix diterima final;
5. identifier convention diterima final;
6. idempotency semantics diterima final;
7. reprint semantics diterima final;
8. browser fallback semantics diterima final;
9. Codex diinstruksikan tidak mengimplementasikan iMin SDK pada Milestone A.

Setelah design freeze, keputusan tersebut tidak boleh diubah diam-diam oleh coding agent.

Perubahan harus kembali menjadi architecture decision/change request.

---

# A.30 Recommended Design Freeze

Jika seluruh rekomendasi di bagian A.24 diterima tanpa perubahan, maka Milestone A dapat ditandai:

**DESIGN FROZEN — READY FOR CODEX BATCH A1**

dan urutan implementasinya:

**A1 Persistence → A2 Client Foundation → A3 Receipt/Foundation Integration**

Baru setelah seluruh acceptance test Milestone A lulus:

**mulai Milestone B — Single-device Happy Path.**
# Tambahan ke "Milestone A — Foundation Specification"

## A.31 Permission Model — Milestone A

Permission model ini merupakan bagian dari **security boundary** `pos_direct_print`.

Tujuan utamanya:

* data receipt tidak bocor lintas outlet;
* kasir tidak dapat mengubah konfigurasi printer;
* kasir tidak dapat menandai terminal sebagai `QUALIFIED`;
* audit Print Job dan Print Attempt tidak dapat dimanipulasi melalui UI;
* REPRINT mempunyai authorization eksplisit;
* access control berlaku pada server, bukan sekadar filter tampilan.

---

# A.31.1 Canonical Roles

Milestone A menetapkan tiga role yang relevan.

## 1. `System Manager`

Existing Frappe administrative role.

Purpose:

* konfigurasi subsystem;
* registrasi dan maintenance terminal;
* qualification terminal;
* troubleshooting;
* melihat audit seluruh company/outlet;
* administrasi global.

`System Manager` dianggap global administrative authority.

Namun **full administrative access tidak berarti boleh mengedit audit trail secara manual**.

`POS Print Job` dan `POS Print Attempt` tetap immutable melalui standard DocType UI bahkan untuk System Manager.

Hal ini disengaja untuk menjaga audit integrity.

---

## 2. `POS Print Operator`

**Custom role baru.**

Purpose:

kasir/operator yang menggunakan direct-print subsystem.

Role ini hanya mengatur permission terhadap custom printing subsystem.

Role ERPNext yang diperlukan untuk menjalankan POS tetap dikelola secara terpisah.

Assignment `POS Print Operator` tidak otomatis memberikan akses ke POS ERPNext.

Sebaliknya, mempunyai akses POS ERPNext tidak otomatis memberikan akses ke custom printing subsystem.

### Capabilities

Operator dapat:

* meminta ORIGINAL print melalui POS;
* melihat status Job miliknya yang berada dalam outlet/POS Profile yang diizinkan;
* melakukan manual safe retry jika state machine mengizinkan;
* menerima sanitized printer/job status dari Print API;
* menggunakan browser fallback ketika policy mengizinkan.

Operator tidak dapat:

* mengubah Settings;
* membuat atau mengubah Terminal;
* mengubah qualification;
* mengubah capability;
* membaca device serial/ROM/raw capability data;
* membuat Print Job secara manual dari DocType form;
* mengubah Print Job record;
* menghapus Print Job;
* mengubah Print Attempt;
* menghapus Print Attempt;
* menjalankan REPRINT.

---

## 3. `POS Print Manager`

**Custom role baru.**

Purpose:

supervisor/outlet manager yang mempunyai authority terhadap printing operations.

Primary additional capability:

**authorize/trigger REPRINT.**

Manager dapat:

* melihat Print Job dalam outlet/POS Profile yang menjadi scope authority-nya;
* melihat operational Print Attempt dalam scope yang sama;
* melakukan REPRINT dengan mandatory reason;
* melakukan manual safe recovery actions yang memang diizinkan state machine.

Manager tidak dapat:

* mengubah POS Print Settings;
* mengubah Terminal qualification;
* mengubah driver configuration;
* mengubah capability data;
* mengubah audit Job/Attempt secara manual;
* menghapus Job/Attempt.

`POS Print Manager` tidak dianggap otomatis mempunyai `POS Print Operator` pada level Frappe role inheritance.

Jika seorang supervisor juga menggunakan POS sebagai kasir, user tersebut diberikan kedua role.

---

# A.31.2 Tidak Menggunakan Existing ERPNext Role sebagai Printing Authority

Permission custom subsystem **tidak boleh bergantung hanya** pada role seperti Sales User, Sales Manager, Accounts User, atau role ERPNext lain.

Reason:

role tersebut mempunyai scope business yang lebih luas daripada printer subsystem.

Canonical authority:

| Responsibility               | Role               |
| ---------------------------- | ------------------ |
| Ordinary direct printing     | POS Print Operator |
| Reprint authority            | POS Print Manager  |
| System/device administration | System Manager     |

Existing ERPNext permissions tetap berlaku sebagai lapisan permission terhadap invoice/POS itu sendiri.

Custom print permissions tidak boleh memperluas permission invoice yang sudah dimiliki user.

---

# A.31.3 System-Managed Records

`POS Print Job` dan `POS Print Attempt` dikategorikan sebagai:

**SYSTEM-MANAGED AUDIT RECORDS**

Artinya tidak ada interactive user role yang diberikan standard DocType:

* Create;
* Write;
* Delete.

Record hanya boleh dibuat atau diubah oleh trusted backend services milik `pos_direct_print` setelah permission, scope, state transition, dan request validation berhasil.

Ini termasuk request yang berasal dari:

* POS Print Operator;
* POS Print Manager;
* System Manager.

Role user menentukan apakah action boleh diminta.

Backend service yang melakukan persistence.

User tidak melakukan direct document mutation.

---

# A.31.4 Permission Matrix — POS Print Settings

`POS Print Settings` merupakan Single DocType.

`is_submittable = false`.

| Role               | Read | Create | Write | Delete | Submit |
| ------------------ | ---: | -----: | ----: | -----: | -----: |
| System Manager     |  YES |    N/A |   YES |     NO |    N/A |
| POS Print Manager  |   NO |     NO |    NO |     NO |    N/A |
| POS Print Operator |   NO |     NO |    NO |     NO |    N/A |

### Runtime settings access

Operator dan Manager tidak membutuhkan direct DocType read permission.

Client memperoleh **sanitized runtime settings projection** melalui Print API.

Projection hanya boleh berisi data yang diperlukan client, misalnya:

* subsystem enabled;
* operating mode;
* browser fallback availability;
* safe retry limits;
* current receipt schema version.

Internal settings yang tidak diperlukan browser tidak dikirim.

### Security rule

Hanya System Manager yang dapat mengubah:

* `enabled`;
* `operating_mode`;
* `default_driver`;
* retry configuration;
* retention configuration;
* browser fallback policy;
* debug logging;
* schema versions.

---

# A.31.5 Permission Matrix — POS Print Terminal

`POS Print Terminal` bukan submittable.

| Role               |                     Read | Create | Write | Delete | Submit |
| ------------------ | -----------------------: | -----: | ----: | -----: | -----: |
| System Manager     |                      YES |    YES |   YES |     NO |    N/A |
| POS Print Manager  |              YES, scoped |     NO |    NO |     NO |    N/A |
| POS Print Operator | NO direct DocType access |     NO |    NO |     NO |    N/A |

### Deletion policy

Terminal **tidak boleh hard-delete melalui standard application UI**.

Jika terminal pensiun:

`enabled = 0`

dan apabila diperlukan:

`pairing_status = REVOKED`.

Reason:

historical Print Job/Attempt harus tetap mempunyai valid terminal reference.

---

# A.31.6 Terminal Field Sensitivity

Terminal fields dibagi menjadi dua permission levels.

## Permission Level 0 — Operational

Readable oleh:

* System Manager;
* scoped POS Print Manager.

Fields:

* `terminal_id`
* `terminal_label`
* `enabled`
* `company`
* `pos_profile`
* `qualification_status`
* `last_seen_at`
* `last_health_state`

Manager membutuhkan `qualification_status` untuk mengetahui apakah terminal layak dipakai, tetapi tidak mempunyai Write permission.

---

## Permission Level 1 — Device Administration

Readable/writable hanya oleh:

**System Manager**

Fields:

* `driver_key`
* `device_model`
* `device_serial`
* `android_version`
* `rom_build`
* `plugin_version`
* `browser_version`
* `webview_version`
* `transport`
* `paper_width_mm`
* `cutter_capability`
* `qualification_revision`
* `capability_schema_version`
* `capabilities_json`
* `paired_client_id`
* `pairing_status`
* `notes`

POS Print Manager tidak membutuhkan raw device fingerprint untuk operational management.

POS Print Operator tidak mendapatkan direct Terminal document access sama sekali.

---

# A.31.7 Operator Terminal Runtime Projection

Walaupun Operator tidak mempunyai direct DocType Read permission terhadap Terminal, POS runtime tetap membutuhkan informasi terminal tertentu.

Backend boleh mengembalikan **TerminalRuntimeProjection**.

Allowed fields:

* terminal ID;
* terminal label;
* driver key;
* qualification state;
* health state;
* paper profile jika dibutuhkan client;
* safe normalized capabilities yang diperlukan PrintManager.

Tidak boleh mengembalikan:

* device serial;
* ROM build;
* browser version history;
* WebView version;
* raw capability JSON;
* pairing internals;
* notes administratif.

---

# A.31.8 Permission Matrix — POS Print Job

`POS Print Job` bukan submittable.

Record adalah system-managed audit record.

| Role               |              Read |    Create |     Write | Delete | Submit |
| ------------------ | ----------------: | --------: | --------: | -----: | -----: |
| System Manager     |          YES, all | NO manual | NO manual |     NO |    N/A |
| POS Print Manager  |       YES, scoped | NO manual | NO manual |     NO |    N/A |
| POS Print Operator | YES, own + scoped | NO manual | NO manual |     NO |    N/A |

Job creation dilakukan melalui trusted backend operation seperti:

* original print request;
* authorized reprint request;
* test print request.

Tidak melalui standard DocType Create.

---

# A.31.9 Job Field Sensitivity

## Permission Level 0 — Operational Job Data

Readable sesuai row-level scope.

Fields:

* `job_id`
* `reference_doctype`
* `reference_name`
* `company`
* `pos_profile`
* `terminal`
* `requested_by`
* `source`
* `job_type`
* `parent_job`
* `reprint_reason`
* `driver_key`
* `status`
* `status_reason_code`
* `attempt_count`
* `safe_retry_count`
* `content_may_have_printed`
* `started_at`
* `finished_at`
* `last_error_code`
* `last_error_phase`
* `fallback_used`
* `browser_fallback_at`

POS Print Operator hanya dapat membaca Level 0.

---

## Permission Level 1 — Sensitive Audit Data

Readable oleh:

* System Manager;
* scoped POS Print Manager.

Not readable by:

* POS Print Operator.

Fields:

* `idempotency_key`
* `reservation_owner`
* `reserved_at`
* `reserved_until`
* `receipt_schema_version`
* `receipt_hash`
* `receipt_snapshot`
* `last_error_detail`
* `metadata_json`

Reason:

`receipt_snapshot` dapat berisi:

* item;
* quantity;
* selling price;
* discount;
* tax;
* payment information;
* receipt metadata.

Technical reservation identifiers juga tidak diperlukan kasir.

---

# A.31.10 POS Print Job Row-Level Rule — Operator

A user dengan `POS Print Operator` hanya boleh membaca Job jika **seluruh kondisi berikut terpenuhi**:

1. `requested_by = current user`;

2. Job berada pada POS Profile yang valid untuk user;

3. Company Job berada dalam Company yang dapat diakses user;

4. Job bukan berada pada Terminal/POS Profile di luar authorized scope.

Dengan demikian operator outlet A tidak boleh membaca:

* Job user lain;
* Job outlet B;
* Job terminal B;
* receipt snapshot seluruh perusahaan.

Operator yang bekerja pada lebih dari satu POS Profile dapat melihat **job miliknya sendiri** pada seluruh POS Profile yang memang valid untuk dirinya.

---

# A.31.11 POS Print Job Row-Level Rule — Manager

`POS Print Manager` dapat membaca Job user lain, tetapi hanya dalam explicitly authorized POS Profile scope.

Canonical authorization mechanism:

**Frappe User Permission terhadap POS Profile.**

Setiap POS Print Manager wajib mempunyai explicit allowed POS Profile.

Tidak ada implicit:

> tidak punya User Permission berarti boleh semua.

Untuk custom subsystem, absence of manager POS Profile scope berarti:

**zero outlet-scoped access.**

Company dari authorized POS Profile juga harus berada dalam company permission user.

System Manager dikecualikan dari restriction tersebut.

---

# A.31.12 Outlet Boundary

Milestone A tidak membuat custom `Outlet` DocType baru.

Canonical outlet/security boundary menggunakan:

**POS Profile**

dan secondary boundary:

**Company**

Reason:

physical terminal sudah terikat ke `company` dan `pos_profile`.

Karena satu Company dapat mempunyai banyak outlet, **Company saja tidak cukup** sebagai row-level security boundary.

Security scope:

`Company + POS Profile`

Terminal kemudian harus berada pada POS Profile tersebut.

---

# A.31.13 POS Profile Scope — Operator

Untuk Operator, authorized POS Profile berasal dari POS configuration yang memang membuat user applicable terhadap profile tersebut.

Custom subsystem tidak boleh membuat independent operator-to-outlet mapping yang dapat bertentangan dengan ERPNext POS configuration.

Jika user tidak valid untuk POS Profile tersebut:

direct-print request untuk profile tersebut ditolak.

---

# A.31.14 POS Profile Scope — Manager

Manager scope berbeda dengan cashier assignment.

Karena supervisor mungkin mengawasi outlet tanpa bertransaksi sebagai kasir, manager authority menggunakan:

**explicit Frappe User Permission → POS Profile**

bukan kewajiban menjadi cashier/applicable user pada POS Profile.

Ini memisahkan:

* ability to transact as cashier;
* ability to supervise printing.

---

# A.31.15 Security Enforcement Mechanism

List View filter **bukan security mechanism**.

Client-side filtering juga bukan security mechanism.

Milestone A wajib menggunakan server-side enforcement.

Untuk custom DocTypes yang mempunyai row-level access:

1. **permission query condition**
   digunakan untuk membatasi list/search/report queries;

dan

2. **document-level has-permission enforcement**
   digunakan untuk direct document access.

Keduanya harus menggunakan rule source yang sama.

Tidak boleh terjadi:

list tersembunyi tetapi user masih dapat membuka document secara langsung menggunakan URL/API.

Standard Frappe User Permission digunakan sebagai input authority scope bila relevan, tetapi custom query/document permission tetap menjadi authoritative enforcement bagi subsystem.

---

# A.31.16 Permission Matrix — POS Print Attempt

`POS Print Attempt` adalah immutable audit trail.

Tidak submittable.

| Role               |                     Read |    Create |     Write | Delete | Submit |
| ------------------ | -----------------------: | --------: | --------: | -----: | -----: |
| System Manager     |                 YES, all | NO manual | NO manual |     NO |    N/A |
| POS Print Manager  |              YES, scoped |        NO |        NO |     NO |    N/A |
| POS Print Operator | NO direct DocType access |        NO |        NO |     NO |    N/A |

Tidak ada role interactive yang boleh membuat Attempt melalui standard DocType API/UI.

Attempt hanya dibuat oleh JobCoordinator/backend service.

---

# A.31.17 Attempt Field Sensitivity

## Permission Level 0 — Operational Audit

Readable oleh:

* System Manager;
* scoped POS Print Manager.

Fields:

* `attempt_id`
* `job`
* `attempt_no`
* `terminal`
* `driver_key`
* `outcome`
* `phase_reached`
* `content_started`
* `content_completed`
* `normalized_status_before`
* `normalized_status_after`
* `error_code`
* `retry_class`
* `started_at`
* `finished_at`
* `duration_ms`

---

## Permission Level 1 — Technical Diagnostic Data

Readable only by:

**System Manager**

Fields:

* `raw_status_before`
* `raw_status_after`
* `error_detail`
* `client_session_id`
* `browser_tab_id`
* `paired_client_id`
* `driver_version`
* `asset_version`
* `metadata_json`

POS Print Manager tidak membutuhkan raw browser/device identifiers untuk melakukan approval REPRINT.

---

# A.31.18 Attempt Row-Level Rule

POS Print Manager dapat membaca Attempt hanya jika parent Job dapat dibaca oleh Manager tersebut berdasarkan rule A.31.11.

Attempt tidak menentukan scope sendiri secara independen.

Canonical rule:

**Attempt access inherits parent Job security scope.**

System Manager dapat membaca seluruh Attempt.

Operator tidak mendapatkan direct Attempt DocType access.

Operational error yang dibutuhkan Operator dikirim sebagai sanitized `PrintOutcome`, bukan dengan memberikan akses audit trail.

---

# A.31.19 REPRINT Authorization

Milestone A menetapkan policy:

### POS Print Operator

**TIDAK boleh trigger REPRINT.**

Operator dapat:

* retry Job yang dinyatakan `MANUAL_SAFE`;
* meminta bantuan supervisor jika physical output perlu dicetak ulang.

---

### POS Print Manager

**BOLEH trigger REPRINT** hanya jika:

1. parent Job dapat dibaca Manager berdasarkan authorized POS Profile scope;
2. parent Job adalah valid print Job;
3. state machine/business policy mengizinkan reprint;
4. `reprint_reason` tidak kosong;
5. target terminal berada dalam authorized scope.

REPRINT dibuat sebagai:

**Job baru**

dengan:

* `job_type = REPRINT`;
* `parent_job = original/previous job`;
* `reprint_reason = mandatory`;
* `requested_by = manager yang melakukan approval/action`.

Tidak boleh mengubah existing Job menjadi REPRINT.

---

### System Manager

Dapat trigger REPRINT untuk seluruh permitted companies/outlets.

`reprint_reason` tetap mandatory.

System Manager tidak mempunyai bypass terhadap mandatory audit reason.

---

# A.31.20 No Direct REPRINT Document Creation

Memberikan role `POS Print Manager` **tidak** memberikan standard Create permission pada POS Print Job.

REPRINT harus melalui dedicated trusted backend action.

Backend action wajib melakukan:

* role check;
* parent Job permission check;
* company check;
* POS Profile scope check;
* terminal scope check;
* state/business-rule check;
* mandatory reason validation.

Baru setelah seluruh check lolos backend membuat REPRINT Job.

---

# A.31.21 Safe Retry vs REPRINT Permission

Permission harus membedakan:

## Retry

Meneruskan logical Job yang sama karena output terbukti belum dimulai.

Operator boleh melakukan manual safe retry jika:

`retry_class = MANUAL_SAFE`.

Tidak membutuhkan POS Print Manager.

---

## Reprint

Membuat logical Job baru karena previous output mungkin/sudah dicetak.

Requires:

`POS Print Manager`

atau:

`System Manager`.

Dengan demikian kasir tidak dapat menggunakan tombol Print berulang sebagai mekanisme menghasilkan duplicate receipt tanpa audit authority.

---

# A.31.22 System Manager Audit Immutability

Walaupun System Manager merupakan administrative authority:

### POS Print Job

manual:

* Create: denied
* Write: denied
* Delete: denied

### POS Print Attempt

manual:

* Create: denied
* Write: denied
* Delete: denied

Reason:

audit record tidak boleh berubah hanya karena administrator membuka form.

Jika suatu hari dibutuhkan exceptional audit correction, mekanismenya harus menjadi explicit maintenance procedure dan bukan bagian Milestone A.

---

# A.31.23 Direct API Security

Semua API operation yang menghasilkan perubahan harus melakukan authorization sendiri.

Tidak boleh mengandalkan fakta bahwa tombol UI disembunyikan.

Minimum authorization:

### ORIGINAL request

Caller:

* POS Print Operator;
* POS Print Manager yang juga mempunyai appropriate POS usage authority;
* System Manager untuk test/admin context.

Validate:

* invoice permission;
* POS Profile authorization;
* terminal authorization.

### Safe retry

Validate:

* caller dapat membaca Job;
* retry state valid;
* content risk aman.

### REPRINT

Validate:

* POS Print Manager atau System Manager;
* parent Job scope;
* mandatory reason.

### Terminal configuration

System Manager only.

### Qualification mutation

System Manager only.

---

# A.31.24 Permission Fail-Closed Rule

Jika authorization information:

* missing;
* malformed;
* inconsistent;
* cannot be resolved;

access harus:

**DENIED**

bukan diberikan secara default.

Contoh:

POS Print Manager tidak memiliki POS Profile User Permission.

Result:

manager tidak dapat melihat semua outlet.

Result yang benar:

**manager tidak melihat outlet mana pun sampai scope dikonfigurasi.**

---

# A.31.25 Cross-Company Protection

Tidak ada custom printing permission yang boleh memperluas Company access user.

Jika user tidak memiliki akses Company B:

memiliki terminal ID atau job ID dari Company B tidak memberikan access.

Effective access adalah intersection:

**Frappe company permission**

AND

**POS Direct Print role**

AND

**POS Profile scope**

AND, jika Operator:

**requested_by = current user**

---

# A.31.26 Permission Summary

| Capability                     |                Operator |        Print Manager | System Manager |
| ------------------------------ | ----------------------: | -------------------: | -------------: |
| Run normal direct print        |                     YES |          Conditional |      YES/admin |
| Read own Jobs                  |                     YES |                  YES |            YES |
| Read other cashier Jobs        |                      NO | Within scoped outlet |            YES |
| Read receipt_snapshot          |                      NO | Within scoped outlet |            YES |
| Manual safe retry              |  YES, own permitted job |           YES scoped |            YES |
| Trigger REPRINT                |                      NO |           YES scoped |            YES |
| Reprint without reason         |                      NO |                   NO |             NO |
| Read Attempt DocType           |                      NO |           YES scoped |            YES |
| Read raw Attempt diagnostics   |                      NO |                   NO |            YES |
| Read Terminal operational data | Runtime projection only |           YES scoped |            YES |
| Read device serial/ROM         |                      NO |                   NO |            YES |
| Change Terminal                |                      NO |                   NO |            YES |
| Change qualification           |                      NO |                   NO |            YES |
| Change capabilities            |                      NO |                   NO |            YES |
| Change Settings                |                      NO |                   NO |            YES |
| Manually edit Job              |                      NO |                   NO |             NO |
| Manually delete Job            |                      NO |                   NO |             NO |
| Manually edit Attempt          |                      NO |                   NO |             NO |
| Manually delete Attempt        |                      NO |                   NO |             NO |

---

# A.31.27 A-DOD-15 — Permission Enforcement

Milestone A memenuhi permission enforcement jika seluruh kondisi berikut dapat dibuktikan otomatis:

1. POS Print Operator tidak dapat Create/Write/Delete POS Print Terminal;

2. POS Print Operator tidak dapat mengubah:

   * `qualification_status`;
   * `driver_key`;
   * capability fields;
   * device metadata;

3. POS Print Operator hanya dapat membaca POS Print Job yang:

   * `requested_by` adalah user tersebut;
   * berada dalam authorized Company;
   * berada dalam authorized POS Profile;

4. POS Print Operator tidak dapat membaca `receipt_snapshot`;

5. POS Print Manager dapat membaca Job lintas cashier hanya dalam explicitly authorized POS Profile;

6. POS Print Manager tidak dapat mengubah Terminal configuration atau qualification;

7. POS Print Attempt tidak dapat Create/Write/Delete secara manual oleh role interactive mana pun;

8. POS Print Manager hanya dapat membaca Attempt whose parent Job berada dalam authorized scope;

9. raw Attempt diagnostic fields hanya dapat dibaca System Manager;

10. direct document URL/API access menghasilkan permission yang sama dengan List View/query access.

---

# A.31.28 A-DOD-16 — Reprint Authorization Enforcement

Milestone A memenuhi REPRINT authorization jika:

1. POS Print Operator tidak dapat membuat REPRINT Job;

2. POS Print Manager dapat trigger REPRINT hanya terhadap Job dalam authorized POS Profile;

3. System Manager dapat trigger REPRINT globally subject to Company permission/system authority;

4. `reprint_reason` wajib untuk semua REPRINT termasuk System Manager;

5. REPRINT selalu menghasilkan Job baru;

6. parent Job tidak pernah dimodifikasi menjadi REPRINT;

7. unauthorized direct RPC/API request ditolak walaupun request dibentuk manual tanpa UI.

---

# A.31.29 Acceptance Test — A-AT-19 Operator Cannot Modify Terminal

**Given**

user mempunyai `POS Print Operator`

dan terminal berada pada POS Profile user tersebut.

**When**

user mencoba mengubah `qualification_status` dari `UNVERIFIED` menjadi `QUALIFIED`

melalui:

* document form;
* standard document API;
* direct RPC payload.

**Then**

semua mutation ditolak

**And**

stored `qualification_status` tetap `UNVERIFIED`.

**And**

user juga tidak dapat mengubah:

* `driver_key`;
* `capabilities_json`;
* `device_serial`;
* `rom_build`.

Supports:

A-DOD-15.

---

# A.31.30 Acceptance Test — A-AT-20 Operator Job Isolation

**Given**

Operator A bekerja pada POS Profile Outlet A

dan Operator B bekerja pada POS Profile Outlet B

dan masing-masing mempunyai Print Job.

**When**

Operator A menjalankan:

* Print Job list query;
* direct read by Job ID terhadap Job Operator B;
* standard document API fetch terhadap Job Operator B.

**Then**

Operator A hanya menerima Job miliknya sendiri yang berada dalam authorized scope

**And**

Job Operator B tidak muncul pada list

**And**

direct access terhadap Job Operator B ditolak.

Supports:

A-DOD-15.

---

# A.31.31 Acceptance Test — A-AT-21 Sensitive Job Fields

**Given**

POS Print Operator mempunyai Job sendiri

dan Job tersebut mempunyai populated:

* `receipt_snapshot`;
* `idempotency_key`;
* `metadata_json`;
* `last_error_detail`.

**When**

Operator membaca Job melalui allowed interface.

**Then**

operational Level 0 fields dapat dibaca

**And**

sensitive Level 1 fields tidak tersedia kepada Operator.

Supports:

A-DOD-15.

---

# A.31.32 Acceptance Test — A-AT-22 Manager Outlet Scope

**Given**

Manager M mempunyai:

`POS Print Manager`

dan explicit User Permission hanya untuk:

`POS Profile Outlet A`.

**And**

Job terdapat pada Outlet A dan Outlet B.

**When**

Manager M melakukan Job list query.

**Then**

Job Outlet A dapat dibaca

**And**

Job Outlet B tidak muncul.

**When**

Manager M melakukan direct document request terhadap Job Outlet B.

**Then**

request ditolak.

Supports:

A-DOD-15.

---

# A.31.33 Acceptance Test — A-AT-23 Attempt Audit Immutability

**Given**

existing POS Print Attempt.

**When**

POS Print Operator mencoba Create/Write/Delete Attempt.

**Then**

operation ditolak.

**When**

POS Print Manager mencoba Create/Write/Delete Attempt.

**Then**

operation ditolak.

**When**

System Manager mencoba mengubah Attempt melalui ordinary DocType mutation interface.

**Then**

operation juga ditolak.

**And**

backend JobCoordinator masih dapat membuat/update Attempt melalui trusted system-managed path.

Supports:

A-DOD-15.

---

# A.31.34 Acceptance Test — A-AT-24 Reprint Authorization

**Given**

completed Print Job milik Operator A

pada POS Profile Outlet A.

### Case 1 — Operator

**When**

Operator A mencoba trigger REPRINT dengan valid reason.

**Then**

request ditolak karena Operator tidak mempunyai reprint authority.

### Case 2 — Authorized Manager

**Given**

Manager M mempunyai POS Print Manager authority untuk Outlet A.

**When**

Manager M trigger REPRINT dengan non-empty reason.

**Then**

Job baru dibuat dengan:

* `job_type = REPRINT`;
* `parent_job` menunjuk previous Job;
* `requested_by = Manager M`;
* `reprint_reason` berisi supplied reason.

**And**

previous Job tidak dimodifikasi.

### Case 3 — Missing reason

**When**

Manager M trigger REPRINT tanpa reason.

**Then**

request ditolak.

### Case 4 — Wrong outlet

**Given**

Manager M hanya mempunyai authority untuk Outlet B.

**When**

Manager M mencoba reprint Job Outlet A.

**Then**

request ditolak.

Supports:

A-DOD-16.

---

# A.31.35 Acceptance Test — A-AT-25 Permission Fail-Closed

**Given**

user mempunyai `POS Print Manager`

tetapi tidak mempunyai authorized POS Profile User Permission.

**When**

user melakukan scoped Print Job query.

**Then**

hasil berisi zero outlet Jobs.

**And**

system tidak menginterpretasikan missing scope sebagai unrestricted access.

Supports:

A-DOD-15.

---

# Required Addition to A.28 — Suggested Codex Handoff Sequence

Pada bagian:

## Codex Batch A1 — Persistence Foundation

tambahkan ke **Scope**:

* creation/configuration of custom roles `POS Print Operator` and `POS Print Manager`;
* DocType permission matrices;
* field permission levels;
* row-level permission query conditions;
* document-level permission enforcement;
* Company + POS Profile scope enforcement;
* system-managed Job/Attempt mutation boundary;
* REPRINT authorization;
* automated permission and authorization tests defined in A.31.

Tambahkan ke **Exit condition**:

A-DOD-15 dan A-DOD-16 harus terpenuhi selain Definition of Done Batch A1 yang sudah disebutkan.

Permission setup merupakan bagian dari Persistence Foundation dan **tidak boleh ditunda ke milestone terpisah**.

---

# Required Addition to A.29 — Milestone A Final Handoff Gate

Tambahkan poin baru:

**10. Permission model untuk keempat custom DocType sudah didefinisikan, diterima final, dan mencakup role-level permission, field-level sensitivity, row-level Company/POS Profile restriction, audit immutability, serta REPRINT authority.**

Tambahkan requirement:

Milestone A tidak boleh ditandai `READY FOR CODEX BATCH A1` apabila permission model A.31 belum dianggap design-frozen.

---

# A.31.36 Permission Design Freeze

Setelah section A.31 diterima, Codex tidak diberikan kebebasan untuk:

* mengganti custom role names;
* memberikan Create/Write pada Job kepada kasir;
* memberikan manual Write kepada Print Attempt;
* menjadikan List View filter sebagai satu-satunya security;
* menghapus POS Profile row-level restriction;
* memberikan REPRINT authority kepada Operator;
* membuat System Manager dapat mengedit audit Job/Attempt melalui ordinary UI;
* mengekspos `receipt_snapshot`, raw terminal data, atau raw attempt diagnostics kepada Operator;
* menganggap missing manager scope berarti unrestricted access.

Perubahan terhadap policy tersebut harus dianggap sebagai:

**architecture decision change**

dan bukan implementation detail.