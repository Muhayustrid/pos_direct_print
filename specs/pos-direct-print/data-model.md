# POS Direct Print — Data Model and Permission Model

Dokumen ini memuat data model Milestone A (A.4–A.9) dan definisi DocType dari Permission Model A.31. Definition of Done serta acceptance tests permission ditempatkan di `spec.md`; task permission dan final handoff gate ditempatkan di `tasks.md` agar tidak diduplikasi.

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

---

# A.31 Permission Model — Milestone A

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

> **Acceptance-test home:** `spec.md` adalah rumah canonical untuk definisi DOD/test A.31.27–A.31.35. Seluruh definisi tetap disertakan lengkap di sini karena Permission Model harus berdiri sendiri dan lengkap.

## Catatan Penempatan A.31

A.31.27–A.31.35 (Definition of Done dan acceptance tests permission) ditempatkan di `spec.md`, sedangkan required additions untuk handoff A.28/A.29 ditempatkan di `tasks.md`. Bagian tersebut sengaja tidak diduplikasi di sini; file ini mempertahankan definisi DocType, seluruh matrix permission, field sensitivity, row-level scope, authorization, dan design-freeze permission.

---

# A.31.36 Permission Design Freeze

Setelah section A.31 diterima, AI coding agent tidak diberikan kebebasan untuk:

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
