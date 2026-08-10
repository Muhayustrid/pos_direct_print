# Desain Remediasi Audit Milestone A

**Tanggal:** 10 Agustus 2026  
**Status:** Disetujui untuk perencanaan  
**Scope:** Custom app `pos_direct_print` saja

## 1. Tujuan

Remediasi ini menutup temuan audit yang berada dalam custom app. Remediasi tidak mengubah source, asset, atau konfigurasi ERPNext dan Frappe.

Hasil wajib:

1. Operator hanya mengakses Job pada POS Profile yang berlaku untuk user tersebut.
2. Jalur retry server mengembalikan `retry_class` yang sesuai untuk `UNCERTAIN`.
3. Safe retry mengubah counter dan reservation dalam satu operasi database atomik.
4. Test membuktikan permission, retry classification, dan concurrent retry.
5. Dokumen mencatat otorisasi remediation tanpa menulis ulang riwayat handoff.
6. Verifikasi akhir memisahkan status app dari perubahan eksternal pada ERPNext.

## 2. Batas Scope

### 2.1 Dalam scope

- `pos_direct_print/core/security.py`
- `pos_direct_print/core/reservation.py`
- `pos_direct_print/core/retry.py`
- Test Python terkait permission, retry, dan concurrency
- `specs/pos-direct-print/tasks.md`
- `specs/pos-direct-print/progress.json`

### 2.2 Di luar scope

- Semua file dalam app `erpnext`
- Semua file dalam app `frappe`
- DocType field atau index baru
- API iMin, plugin printer, dan physical printing
- Retry scheduler, queue, delay, atau UX `UNCERTAIN`
- Refactor frontend yang tidak terkait temuan audit
- Pembersihan dua perubahan tracked ERPNext yang sudah ada

## 3. POS Profile Applicability

### 3.1 Aturan canonical

Custom app mengikuti semantics ERPNext v16 untuk `POS Profile.applicable_for_users`.

Sebuah POS Profile berlaku untuk user jika semua syarat berikut benar:

1. POS Profile ada.
2. POS Profile tidak disabled.
3. Company POS Profile sama dengan Company Job.
4. Jika profile mempunyai row `POS Profile User`, salah satu row harus menunjuk user.
5. Jika profile tidak mempunyai row `POS Profile User`, profile berlaku untuk semua user pada Company tersebut.

System Manager dan Administrator tetap unrestricted untuk read permission. Aturan creation tetap memvalidasi profile dan Company untuk menjaga data integrity.

### 3.2 Satu sumber aturan

`security.py` menyediakan helper kecil untuk menyelesaikan POS Profile yang berlaku bagi Operator. Query list dan direct permission memakai helper yang sama.

Query list Operator harus menambah kondisi berikut:

```text
requested_by = current_user
AND Company scope cocok
AND POS Profile berlaku untuk current_user
```

Direct permission memeriksa kondisi yang sama terhadap satu Job.

`create_original_job()` memanggil validator yang sama sebelum insert. Validator menolak profile disabled, Company mismatch, atau user tidak applicable.

Manager tetap memakai explicit `User Permission` pada POS Profile. Absence of permission tetap menghasilkan zero scope.

### 3.3 Error

Creation yang gagal memakai `frappe.PermissionError` dengan kode `PDP_PERMISSION_DENIED`. Error tidak mengungkap user lain yang terdaftar pada profile.

## 4. Retry Classification

### 4.1 Bentuk hasil

`evaluate_auto_retry()` selalu mengembalikan tiga field:

```python
{
    "allowed": bool,
    "reason": str | None,
    "retry_class": "AUTO_SAFE" | "MANUAL_SAFE" | "REPRINT_ONLY" | "NONE",
}
```

Aturan hasil:

| Kondisi | allowed | retry_class |
|---|---:|---|
| Job `UNCERTAIN`, content dimulai, completion tidak terbukti | false | `REPRINT_ONLY` |
| Content completed | false | `NONE` |
| Job bukan `FAILED_SAFE` tanpa content risk | false | `NONE` |
| Latest Attempt bukan `AUTO_SAFE` | false | nilai latest Attempt atau `NONE` |
| Limit retry tercapai | false | `NONE` |
| Semua syarat safe retry terpenuhi | true | `AUTO_SAFE` |

Production path memakai helper classification yang sama dengan state machine. Test tidak boleh menjadi satu-satunya caller helper tersebut.

### 4.2 Data latest Attempt

Evaluator membaca `retry_class`, `content_started`, dan `content_completed` dari latest Attempt. Evaluator tidak mengubah state.

## 5. Atomic Safe Retry

### 5.1 Masalah lama

Jalur lama menyimpan `safe_retry_count` sebelum reservation. Conflict dapat meninggalkan counter naik tanpa reservation jika caller tidak rollback.

### 5.2 Operasi baru

Safe retry memakai satu guarded SQL `UPDATE`. Operasi tersebut mengubah semua field berikut sekaligus:

- `status` menjadi `RESERVED`
- `safe_retry_count` bertambah satu
- `reservation_owner`
- `reserved_at`
- `reserved_until`

Guard wajib memeriksa:

- `name` cocok
- `status = FAILED_SAFE`
- `safe_retry_count` masih di bawah limit

Evaluator tetap memeriksa latest Attempt sebelum guarded update. Database state guard menjadi arbiter akhir untuk concurrent request.

Jika affected row count nol, fungsi mengembalikan `PDP_JOB_CONFLICT`. Counter dan reservation tetap tidak berubah.

### 5.3 Batas transaksi

Fungsi tidak memanggil `commit()`. Caller tetap memiliki transaction boundary. Fungsi juga tidak melakukan save terpisah sebelum guarded update.

## 6. Test Design

### 6.1 Permission

Tambah test berikut:

1. Operator melihat own Job pada profile yang mencantumkan user.
2. Operator tidak melihat own Job pada profile yang hanya mencantumkan user lain.
3. Operator melihat own Job pada profile tanpa row user.
4. Direct permission memberi hasil sama dengan list permission.
5. Original Job creation menolak user yang tidak applicable.
6. Original Job creation menolak Company mismatch dan disabled profile.

Test membuat POS Profile atau fixture terisolasi. Test tidak mengubah ERPNext source.

### 6.2 Retry classification

Tambah test berikut:

1. Job aktual `UNCERTAIN` dengan content started menghasilkan `REPRINT_ONLY`.
2. Attempt dengan content completed menghasilkan `NONE`.
3. Job `FAILED_SAFE` dengan `AUTO_SAFE` dan zero content risk menghasilkan `AUTO_SAFE`.
4. Test membuktikan production evaluator memakai classification helper.

### 6.3 Retry atomicity

Tambah test berikut:

1. Safe retry sukses mengubah status dan counter bersama.
2. Guard conflict tidak mengubah counter.
3. Dua thread safe retry menghasilkan satu winner.
4. Final status `RESERVED` dan final counter tepat satu.
5. Loser menerima `PDP_JOB_CONFLICT`.

Thread test memakai koneksi Frappe terpisah seperti test reservation yang sudah ada.

## 7. Dokumen Otorisasi

`tasks.md` mendapat section handoff baru setelah riwayat handoff lama. Section tersebut mengizinkan remediation berikut saja:

- Operator POS Profile applicability
- A-AT-12 production classification
- Atomic safe retry
- Test terkait
- Update verification evidence

Section tidak menyatakan bahwa checkpoint A1, A2, atau A3 pernah disetujui sebelumnya.

`progress.json` mendapat record remediation terpisah. Record tersebut tidak mengubah seluruh 29 task menjadi completed.

Record memuat:

- status remediation
- tanggal
- scope
- hasil focused test
- hasil full Python test
- hasil full JavaScript test
- status grep larangan
- catatan perubahan eksternal ERPNext

## 8. Verifikasi

Jalankan verifikasi dalam urutan berikut:

1. Jalankan focused permission tests.
2. Jalankan focused retry dan concurrency tests.
3. Jalankan seluruh Python app suite.
4. Jalankan seluruh JavaScript tests.
5. Jalankan grep larangan Milestone B, C, dan D.
6. Jalankan `git status` pada app `pos_direct_print`.
7. Jalankan `git status` terpisah pada app ERPNext dan Frappe.

Tidak perlu menjalankan `bench migrate` atau `bench build`. Remediasi tidak mengubah schema atau frontend asset.

## 9. Kriteria Selesai

Remediasi selesai hanya jika semua kondisi berikut benar:

1. Semua focused test lulus.
2. Full Python suite lulus tanpa skip baru.
3. Full JavaScript suite lulus tanpa skip baru.
4. Tidak ada implementasi Milestone B, C, atau D.
5. Diff hanya menyentuh custom app.
6. Status ERPNext dan Frappe dilaporkan tanpa mengubah file tersebut.
7. Retry conflict tidak dapat menaikkan counter tanpa reservation.
8. Operator list dan direct permission menegakkan POS Profile applicability yang sama.
