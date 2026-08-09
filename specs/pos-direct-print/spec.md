# Milestone A — Foundation Specification

## A.0 Tujuan Milestone A

Milestone A membangun fondasi yang stabil untuk seluruh direct-print subsystem.

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

## Acceptance Criteria per Capability

### A-DOD-01 — App isolation

**Acceptance criteria:**

Tidak ada modification pada ERPNext/Frappe core.

Semua extension berasal dari custom app.

**Objective evidence:** repository diff ERPNext/Frappe = zero.

---

### A-DOD-02 — Core DocTypes available

**Acceptance criteria:**

Empat DocType tersedia:

- POS Print Settings
- POS Print Terminal
- POS Print Job
- POS Print Attempt

Semua required fields, unique constraints, values dan indexes sesuai specification.

---

### A-DOD-03 — POS override is idempotent

**Acceptance criteria:**

Memanggil subsystem initialization berulang kali tidak menggandakan prototype override.

Satu user action hanya menghasilkan satu invocation ke top-level print orchestration capability.

---

### A-DOD-04 — Original ERPNext print preserved

**Acceptance criteria:**

Original ERPNext Print Receipt behavior disimpan dan dapat dipanggil kembali.

Ketika direct printing disabled:

perilaku browser print tetap sama dengan baseline ERPNext.

---

### A-DOD-05 — Job state machine enforced

**Acceptance criteria:**

100% transition di tabel A.16 diterima.

100% transition di luar tabel ditolak.

Tidak ada direct state mutation tanpa state-validation dan coordination capability.

---

### A-DOD-06 — Concurrency-safe reservation

**Acceptance criteria:**

Dua request concurrent dengan idempotency key sama menghasilkan maksimal satu logical original Job.

---

### A-DOD-07 — Attempt audit deterministic

**Acceptance criteria:**

Setiap execution attempt mendapat:

- unique attempt ID;
- monotonically increasing attempt number;
- timestamps;
- terminal;
- driver;
- outcome.

---

### A-DOD-08 — UNCERTAIN safety rule enforced

**Acceptance criteria:**

Job `UNCERTAIN` tidak dapat:

- auto retry;
- manual retry sebagai Job yang sama;
- berpindah kembali ke PREFLIGHT/PRINTING.

---

### A-DOD-09 — Driver abstraction enforced

**Acceptance criteria:**

Top-level print orchestration capability tidak bergantung pada API iMin.

Dependency hanya terhadap canonical driver contract.

Test fake driver dapat dipasang tanpa mengubah top-level print orchestration capability.

---

### A-DOD-10 — Receipt abstraction enforced

**Acceptance criteria:**

Receipt construction capability menghasilkan serializable ReceiptDocument.

Tidak mengeluarkan ESC/POS bytes atau iMin command.

---

### A-DOD-11 — Canonical error normalization

**Acceptance criteria:**

Raw exception tidak muncul sebagai contract ke POS integration.

Setiap operational failure menjadi PrintDomainError canonical.

---

### A-DOD-12 — No iMin dependency required

**Acceptance criteria:**

Automated Milestone A tests dapat dijalankan tanpa:

- iMin device;
- iMin plugin;
- Android;
- printer.

---

### A-DOD-13 — Browser fallback boundary correct

**Acceptance criteria:**

Browser fallback hanya boleh dipilih ketika `content_may_have_printed = 0`.

Jika flag = 1, fallback otomatis maupun user-triggered harus ditolak.

---

### A-DOD-14 — Deterministic receipt hashing

**Acceptance criteria:**

ReceiptDocument identik menghasilkan hash identik.

Perubahan content atau schema yang material menghasilkan hash berbeda.

---

### A-DOD-15 — Permission Enforcement

**Acceptance criteria:**

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

### A-DOD-16 — Reprint Authorization Enforcement

**Acceptance criteria:**

Milestone A memenuhi REPRINT authorization jika:

1. POS Print Operator tidak dapat membuat REPRINT Job;

2. POS Print Manager dapat trigger REPRINT hanya terhadap Job dalam authorized POS Profile;

3. System Manager dapat trigger REPRINT globally subject to Company permission/system authority;

4. `reprint_reason` wajib untuk semua REPRINT termasuk System Manager;

5. REPRINT selalu menghasilkan Job baru;

6. parent Job tidak pernah dimodifikasi menjadi REPRINT;

7. unauthorized direct RPC/API request ditolak walaupun request dibentuk manual tanpa UI.

---

## Acceptance Tests — Given / When / Then

### A-AT-01 — App isolation

**Given** clean ERPNext v16 environment  
**When** direct-print Foundation dipasang  
**Then** tidak ada source file ERPNext/Frappe yang berubah  
**And** seluruh customization berasal dari custom app.

Supports: A-DOD-01.

---

### A-AT-02 — DocType schema

**Given** fresh site  
**When** custom app di-install/migrate  
**Then** keempat DocType tersedia  
**And** semua required field sesuai schema  
**And** unique constraint berlaku untuk `terminal_id`, `job_id`, `attempt_id`, dan `idempotency_key`.

Supports: A-DOD-02.

---

### A-AT-03 — Duplicate job ID

**Given** existing Job dengan `job_id = X`  
**When** system mencoba membuat Job kedua dengan `job_id = X`  
**Then** persistence ditolak.

Supports: A-DOD-02.

---

### A-AT-04 — Override idempotency

**Given** ERPNext POS loaded  
**When** direct-print subsystem diinisialisasi tiga kali  
**And** kasir menjalankan satu print action  
**Then** top-level print orchestration capability menerima tepat satu PrintRequest.

Supports: A-DOD-03.

---

### A-AT-05 — Restore original printing

**Given** direct-print override telah terpasang  
**When** subsystem dinonaktifkan/restored  
**And** kasir memilih Print Receipt  
**Then** saved original ERPNext print path dipanggil satu kali.

Supports: A-DOD-04.

---

### A-AT-06 — Feature disabled

**Given** POS Print Settings `enabled = 0`  
**When** kasir melakukan print  
**Then** custom physical driver tidak dipanggil  
**And** original ERPNext print behavior digunakan.

Supports: A-DOD-04.

---

### A-AT-07 — Valid transitions

**Given** Job berada di setiap source state pada tabel A.16  
**When** setiap transition yang ditandai valid dijalankan  
**Then** transition diterima.

Supports: A-DOD-05.

---

### A-AT-08 — Invalid transitions

**Given** Job `UNCERTAIN`  
**When** caller mencoba mengubah state menjadi `PREFLIGHT`  
**Then** operation ditolak dengan `PDP_JOB_INVALID_TRANSITION`  
**And** stored state tetap `UNCERTAIN`.

Supports: A-DOD-05 dan A-DOD-08.

---

### A-AT-09 — Concurrent reservation

**Given** dua browser request dengan idempotency key sama  
**When** keduanya melakukan reservation hampir bersamaan  
**Then** maksimal satu original Job dibuat  
**And** request lain menerima existing/conflict outcome sesuai reservation contract  
**And** tidak ada duplicate logical original Job.

Supports: A-DOD-06.

---

### A-AT-10 — Concurrent attempt numbering

**Given** Job mempunyai Attempt 1  
**When** dua retry request concurrent mencoba memulai Attempt berikutnya  
**Then** tidak pernah terdapat dua Attempt dengan `(job, attempt_no) = (X, 2)`.

Supports: A-DOD-07.

---

### A-AT-11 — Safe retry

**Given** Attempt gagal sebelum physical content dimulai  
**And** error `retry_class = AUTO_SAFE`  
**And** retry count masih di bawah batas  
**When** job coordination capability mengevaluasi retry  
**Then** Attempt baru dapat dibuat pada Job sama.

Supports: A-DOD-07 dan A-DOD-08.

---

### A-AT-12 — Uncertain cannot retry

**Given** Attempt mempunyai `content_started = 1`  
**And** print completion tidak dapat dibuktikan  
**When** Job berakhir `UNCERTAIN`  
**Then** retry class menjadi `REPRINT_ONLY` atau `NONE`  
**And** auto retry tidak dijalankan  
**And** manual same-job retry ditolak.

Supports: A-DOD-08.

---

### A-AT-13 — Fake driver

**Given** fake test driver memenuhi canonical driver contract  
**When** driver tersebut diregistrasikan sebagai active driver  
**Then** top-level print orchestration capability dapat berinteraksi dengannya tanpa dependency pada iMin API.

Supports: A-DOD-09 dan A-DOD-12.

---

### A-AT-14 — Receipt serializability

**Given** normalized invoice test fixture  
**When** receipt construction capability membuat ReceiptDocument  
**Then** document dapat diserialisasi sepenuhnya  
**And** tidak berisi function, DOM node, printer object, atau raw SDK reference.

Supports: A-DOD-10.

---

### A-AT-15 — Raw exception normalization

**Given** fake driver melempar generic runtime exception  
**When** exception melewati error normalization boundary  
**Then** POS-facing result berupa PrintDomainError canonical  
**And** raw stack trace tidak menjadi user-facing error.

Supports: A-DOD-11.

---

### A-AT-16 — Browser fallback safe

**Given** Job gagal sebelum content dimulai  
**And** `content_may_have_printed = 0`  
**When** user menyetujui Browser Fallback  
**Then** original ERPNext browser print path dapat dipanggil  
**And** Job berakhir `FALLBACK_BROWSER`.

Supports: A-DOD-13.

---

### A-AT-17 — Browser fallback unsafe

**Given** `content_may_have_printed = 1`  
**When** caller meminta Browser Fallback  
**Then** request ditolak  
**And** original browser print tidak dipanggil.

Supports: A-DOD-13.

---

### A-AT-18 — Deterministic hash

**Given** ReceiptDocument A dan B memiliki canonical content serta schema identik  
**When** hash keduanya dihitung  
**Then** hash A sama dengan hash B.

**Given** field material dalam B berubah  
**When** hash dihitung ulang  
**Then** hash berbeda.

Supports: A-DOD-14.

---

### A-AT-19 Operator Cannot Modify Terminal

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

### A-AT-20 Operator Job Isolation

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

### A-AT-21 Sensitive Job Fields

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

### A-AT-22 Manager Outlet Scope

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

### A-AT-23 Attempt Audit Immutability

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

trusted system-managed job coordination path masih dapat membuat/update Attempt.

Supports:

A-DOD-15.

---

### A-AT-24 Reprint Authorization

**Given**

completed Print Job milik Operator A

pada POS Profile Outlet A.

#### Case 1 — Operator

**When**

Operator A mencoba trigger REPRINT dengan valid reason.

**Then**

request ditolak karena Operator tidak mempunyai reprint authority.

#### Case 2 — Authorized Manager

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

#### Case 3 — Missing reason

**When**

Manager M trigger REPRINT tanpa reason.

**Then**

request ditolak.

#### Case 4 — Wrong outlet

**Given**

Manager M hanya mempunyai authority untuk Outlet B.

**When**

Manager M mencoba reprint Job Outlet A.

**Then**

request ditolak.

Supports:

A-DOD-16.

---

### A-AT-25 Permission Fail-Closed

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
