# POS Direct Print Milestone A Plan

## Scope

Milestone A membangun foundation contracts dan tidak mencetak ke iMin. Implementasi mengikuti keputusan desain yang telah dibekukan dan tidak boleh menebak SDK-specific behavior.

## 1. Architecture Boundary

Alur logical canonical:

`ERPNext POS v16`

→ `erpnext_v16_pos` integration adapter

→ `PrintManager`

→ `JobCoordinator`

→ `ReceiptBuilder`

→ `BaseDriver`

→ concrete driver

Concrete driver pertama pada milestone berikutnya: `imin_v1`.

Fallback driver: `browser`.

POS integration hanya memanggil `PrintManager`, tidak pernah printer driver secara langsung. ERPNext-specific object knowledge hanya berada dalam `erpnext_v16_pos` integration adapter. Receipt components tidak mengetahui iMin, dan state-machine domain tidak memiliki printer SDK calls.

## 2. Canonical Identifiers

Gunakan tiga identifier yang terpisah:

| Concept | Field | Frappe document name | Final format |
|---|---|---|---|
| Logical Job | `job_id` | `POS Print Job.name = job_id` | `PDPJ-<ULID>` |
| Execution Attempt | `attempt_id` | `POS Print Attempt.name = attempt_id` | `PDPA-<ULID>` |
| Physical POS terminal | `terminal_id` | `POS Print Terminal.name = terminal_id` | `PDPTERM-<business-readable-code>` |

Seluruh identifier harus memenuhi uniqueness contract masing-masing. Job ID selalu globally unique dan bukan idempotency key.

## 3. Client Identity Contract

Milestone A menggunakan tiga identity levels:

### `paired_client_id`

Merepresentasikan satu browser installation/device profile dan bertahan melintasi browser reload.

### `client_session_id`

Merepresentasikan satu logical loaded POS session dan berubah ketika application lifecycle baru dimulai.

### `browser_tab_id`

Merepresentasikan satu tab/window dan berubah untuk setiap tab baru.

Ketiganya digunakan untuk audit dan menjadi foundation concurrency Milestone C.

## 4. Print Job State Machine

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

State mutation hanya boleh melalui validator/coordinator dan harus memenuhi transition table.

## 5. Terminal States

Terminal/final states:

- `UNCERTAIN`
- `SUCCEEDED`
- `FALLBACK_BROWSER`
- `CANCELLED`

`FAILED_SAFE` bukan final karena safe retry dapat dilakukan. `BLOCKED` bukan final karena condition dapat diperbaiki.

## 6. Complete State Transition Table

| From | To | Allowed | Trigger |
|---|---|---:|---|
| `CREATED` | `RESERVED` | Ya | Server reservation berhasil |
| `CREATED` | `CANCELLED` | Ya | User/system cancel sebelum reservation |
| `CREATED` | `FAILED_SAFE` | Ya | Fatal validation/config error tanpa output |
| `RESERVED` | `PREFLIGHT` | Ya | Attempt dimulai |
| `RESERVED` | `FAILED_SAFE` | Ya | Pre-output infrastructure failure |
| `RESERVED` | `CANCELLED` | Ya | User cancel sebelum printer operation |
| `PREFLIGHT` | `PRINTING` | Ya | Printer/driver declared ready |
| `PREFLIGHT` | `BLOCKED` | Ya | Recoverable condition requiring intervention |
| `PREFLIGHT` | `FAILED_SAFE` | Ya | Pre-output failure |
| `PREFLIGHT` | `FALLBACK_BROWSER` | Ya | Explicit approved fallback sebelum output |
| `PREFLIGHT` | `CANCELLED` | Ya | User cancels |
| `BLOCKED` | `PREFLIGHT` | Ya | Condition resolved + retry requested |
| `BLOCKED` | `FALLBACK_BROWSER` | Ya | Approved browser fallback |
| `BLOCKED` | `CANCELLED` | Ya | User abandons printing |
| `BLOCKED` | `FAILED_SAFE` | Ya | Block converts into nonrecoverable pre-output failure |
| `FAILED_SAFE` | `RESERVED` | Ya | Safe retry creates new Attempt/reservation cycle |
| `FAILED_SAFE` | `FALLBACK_BROWSER` | Ya | Approved fallback and no output risk |
| `FAILED_SAFE` | `CANCELLED` | Ya | User abandons |
| `PRINTING` | `VERIFYING` | Ya | All intended content commands completed |
| `PRINTING` | `UNCERTAIN` | Ya | Failure after physical output may have started |
| `VERIFYING` | `SUCCEEDED` | Ya | Verification criteria satisfied |
| `VERIFYING` | `UNCERTAIN` | Ya | Completion cannot be confidently established |

Semua transition yang tidak tercantum dalam tabel ini invalid.

## 7. Complete Retry Matrix

| State | Auto Retry | Manual Retry Same Job | New REPRINT Job |
|---|---:|---:|---:|
| `CREATED` | N/A | N/A | Tidak |
| `RESERVED` | Tidak | Conditional | Tidak |
| `PREFLIGHT` | Conditional | Ya | Tidak |
| `BLOCKED` | Tidak | Ya | Tidak |
| `FAILED_SAFE` | Ya, jika `retry_class = AUTO_SAFE` | Ya | Tidak |
| `PRINTING` | Tidak | Tidak | Tidak sebelum final |
| `VERIFYING` | Tidak | Tidak | Tidak sebelum final |
| `UNCERTAIN` | **Tidak** | **Tidak** | **Ya** |
| `SUCCEEDED` | Tidak | Tidak | Ya jika business policy mengizinkan |
| `FALLBACK_BROWSER` | Tidak | Tidak | Ya jika user memerlukan reprint |
| `CANCELLED` | Tidak | Tidak | New original/reprint request berdasarkan business context |

Retry aman menghasilkan Attempt baru dalam Job yang sama. Reprint selalu menghasilkan Job baru. Automatic retry juga wajib memenuhi seluruh rule dalam constitution.

## 8. Idempotency Contract

Setiap ORIGINAL print request wajib menghasilkan deterministic logical deduplication scope.

Idempotency key dibentuk dari semantic components minimum:

- schema version;
- reference doctype;
- reference name;
- terminal ID;
- job type;
- print purpose/version discriminator.

Komponen tersebut di-hash menjadi fixed-length value. Timestamp tidak boleh masuk ke original idempotency key. REPRINT wajib memperoleh discriminator terpisah agar tidak bertabrakan dengan original.

Idempotency key bukan Job ID. Job ID selalu globally unique.
