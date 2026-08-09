# POS Direct Print Constitution — Milestone A

Dokumen ini menetapkan prinsip yang tidak dapat dinegosiasikan. Implementasi dan perubahan desain wajib mematuhinya.

## 1. Isolasi dari ERPNext dan Frappe Core

Seluruh integrasi wajib berasal dari custom Frappe app. Dilarang melakukan patch langsung pada:

- source ERPNext POS;
- Frappe core;
- compiled asset ERPNext.

## 2. Interception Canonical dan Fallback

Interception canonical ERPNext v16 adalah:

`erpnext.PointOfSale.PastOrderSummary.prototype.print_receipt`

Original method wajib disimpan sebagai browser fallback.

## 3. Invoice dan Printing Harus Terpisah

Keberhasilan transaksi atau invoice tidak boleh bergantung pada printer. Print failure tidak boleh:

- me-rollback invoice;
- membatalkan invoice;
- menandai payment gagal;
- mengubah grand total;
- menjalankan submit ulang.

## 4. Job dan Attempt Adalah Konsep Berbeda

`POS Print Job` adalah logical printing request. `POS Print Attempt` adalah satu percobaan eksekusi terhadap logical job tersebut.

Satu Job hanya boleh mempunyai lebih dari satu Attempt untuk retry yang secara eksplisit dinyatakan aman.

## 5. UNCERTAIN Bersifat Final untuk Same-Job Retry

Jika physical output mungkin sudah dimulai dan completion tidak dapat dibuktikan, outcome wajib `UNCERTAIN`. Job tersebut tidak boleh di-auto-retry atau dicoba ulang sebagai Job yang sama.

Jika kasir memilih mencetak lagi, sistem wajib membuat `POS Print Job` baru dengan `job_type = REPRINT`.

## 6. Browser Fallback Bukan Physical-Print Success

Browser API tidak dapat membuktikan bahwa kertas benar-benar keluar. Browser fallback wajib memiliki outcome khusus dan tidak boleh disamakan dengan `SUCCEEDED`.

## 7. Forbidden State Transitions

Transition berikut selalu dilarang:

- `UNCERTAIN → PREFLIGHT`;
- `UNCERTAIN → PRINTING`;
- `UNCERTAIN → SUCCEEDED` setelah state tersimpan;
- `SUCCEEDED → PRINTING`;
- `FALLBACK_BROWSER → PRINTING`;
- `CANCELLED → PRINTING`;
- `PRINTING → FAILED_SAFE`.

Setelah printing phase dimulai, failure tidak boleh diberi label safe kecuali driver dapat membuktikan bahwa tidak ada content yang diterbitkan. Aturan konservatif sistem adalah: **unknown = may have printed**.

## 8. Automatic Retry

Auto retry hanya sah jika seluruh kondisi berikut benar:

1. latest error memiliki `retry_class = AUTO_SAFE`;
2. `content_started = 0`;
3. `content_may_have_printed = 0`;
4. `safe_retry_count < max_safe_auto_retries`;
5. reservation/job masih valid atau dapat di-reserve ulang;
6. Job bukan terminal state.

Jika satu saja kondisi tersebut false, auto retry dilarang.

## 9. Server Atomicity

### 9.1 Reserve Job

Reserve job wajib transactional dan atomic. Untuk dua concurrent requests dengan idempotency key yang sama, maksimal satu logical Job aktif/original boleh dibuat.

### 9.2 Transition Job

Transition job wajib transactional dan atomic serta menggunakan optimistic expected state. Client wajib mengirim `expected_from_state`.

Jika database state berbeda dari expected state, server wajib mengembalikan `PDP_JOB_CONFLICT`. Client dilarang menimpa state terbaru secara buta.

### 9.3 Attempt Number

Alokasi `attempt_no` wajib transactional dan atomic. `attempt_no` harus unique per Job. Concurrent retry tidak boleh menghasilkan dua record dengan `attempt_no = 2` untuk Job yang sama.
