# Milestone A Design Decision Research

Seluruh recommended defaults A-OD-01 sampai A-OD-15 diterima tanpa perubahan. Tidak ada redesign.

## A-OD-01 — Identifier Format

**Question:** Apakah format identifier recommended diterima atau diubah?

**Options:**

- Terima format recommended:
  - Job: `PDPJ-<ULID>`
  - Attempt: `PDPA-<ULID>`
  - Terminal: `PDPTERM-<business-readable-code>`, contoh `PDPTERM-SBY01-KASIR01`
- Ubah format identifier.

**Final decision:** **DECIDED — accepted default.** Gunakan `PDPJ-<ULID>` untuk Job, `PDPA-<ULID>` untuk Attempt, dan `PDPTERM-<business-readable-code>` untuk Terminal.

**Reason:** ULID globally unique, sortable by time, tidak bergantung pada database sequence, dan aman untuk concurrent multi-outlet deployment. Terminal tetap business-readable.

## A-OD-02 — Idempotency Key Construction

**Question:** Apakah konstruksi semantic idempotency key recommended diterima atau diubah?

**Options:**

- Gunakan komponen `schema-version + reference_doctype + reference_name + terminal_id + job_type + purpose`, lalu hash menjadi fixed-length value; timestamp tidak ikut; REPRINT memakai discriminator terpisah.
- Ubah komponen atau konstruksi key.

**Final decision:** **DECIDED — accepted default.** Bentuk key dari `schema-version + reference_doctype + reference_name + terminal_id + job_type + purpose`, lalu hash menjadi fixed-length value. Timestamp dilarang dalam original idempotency key. REPRINT wajib memiliki discriminator terpisah.

**Reason:** Komponen semantic mempertahankan deduplication yang deterministic; timestamp akan menghancurkan deduplication; discriminator REPRINT mencegah reprint valid bertabrakan dengan original.

## A-OD-03 — Error-Code Naming Convention

**Question:** Apakah convention error code recommended diterima atau diubah?

**Options:**

- Gunakan `PDP_<DOMAIN>_<ERROR>`, uppercase ASCII, bukan numeric-only; contoh `PDP_PRINTER_PAPER_OUT`.
- Gunakan convention lain.

**Final decision:** **DECIDED — accepted default.** Gunakan `PDP_<DOMAIN>_<ERROR>` dalam uppercase ASCII dan larang numeric-only codes.

**Reason:** Convention memberikan namespace dan domain yang jelas, stabil, serta mudah dibaca dan dicari.

## A-OD-04 — Driver Key Convention

**Question:** Apakah convention driver key recommended diterima atau diubah?

**Options:**

- Gunakan lowercase snake-case stable identifiers: `imin_v1`, `browser`, dan untuk future driver misalnya `escpos_network`, `bluetooth_escpos`.
- Gunakan convention lain.

**Final decision:** **DECIDED — accepted default.** Driver key menggunakan lowercase snake-case dan diperlakukan sebagai stable API identifier.

**Reason:** Bentuk ini konsisten, extensible, dan tidak memerlukan schema migration ketika driver baru ditambahkan.

## A-OD-05 — POS Custom Event Namespace

**Question:** Namespace dan reserved event names mana yang digunakan?

**Options:**

- Gunakan prefix `pos_direct_print:` dengan reserved events:
  - `pos_direct_print:job_created`
  - `pos_direct_print:job_state_changed`
  - `pos_direct_print:attempt_started`
  - `pos_direct_print:attempt_finished`
  - `pos_direct_print:terminal_state_changed`
  - `pos_direct_print:error`
- Gunakan namespace atau daftar event lain.

**Final decision:** **DECIDED — accepted default.** Gunakan prefix dan seluruh reserved event names di atas.

**Reason:** Namespace yang dibekukan mencegah milestone berikutnya mengimprovisasi event naming dan menghindari collision.

## A-OD-06 — Original Print Deduplication Scope

**Question:** Setelah original print success, apakah print berikutnya menjadi REPRINT atau boleh menjadi ORIGINAL baru?

**Options:**

- Recommended: satu invoice maksimal mempunyai satu concurrently-active `ORIGINAL` print job per terminal; setelah Job `SUCCEEDED`, print berikutnya wajib melalui REPRINT path.
- Alternative: manual Print Receipt setelah success boleh menjadi new ORIGINAL.

**Final decision:** **DECIDED — accepted default.** Batasi satu concurrently-active `ORIGINAL` per invoice per terminal. Setelah original Job `SUCCEEDED`, user wajib menggunakan REPRINT path.

**Reason:** Policy ini menghasilkan audit paling jelas. Alternative new ORIGINAL setelah success tidak direkomendasikan karena mengaburkan original-versus-reprint history.

## A-OD-07 — REPRINT Reason Policy

**Question:** Apakah `reprint_reason` required atau optional?

**Options:**

- Required: pada milestone awal berupa required free text; category selectable dapat ditambahkan saat operational readiness.
- Optional.

**Final decision:** **DECIDED — accepted default.** Setiap REPRINT wajib memiliki `reprint_reason`; pada milestone awal gunakan required free text.

**Reason:** Mandatory reason mempertahankan accountability dan audit reprint, sambil menunda category taxonomy sampai operational readiness.

## A-OD-08 — Job Retention

**Question:** Berapa lama Job dan Attempt disimpan?

**Options:**

- Recommended default: Job 180 hari dan Attempt 180 hari.
- Alternative: 365 hari jika audit receipt perlu satu tahun.

**Final decision:** **DECIDED — accepted default.** Simpan Job selama 180 hari dan Attempt selama 180 hari.

**Reason:** Ini adalah default retention yang direkomendasikan; 365 hari hanya diperlukan bila business audit menetapkan kebutuhan satu tahun.

## A-OD-09 — Receipt Snapshot Retention

**Question:** Apakah canonical ReceiptDocument disimpan pada Job?

**Options:**

- Yes: simpan canonical ReceiptDocument pada Job.
- No: jangan simpan snapshot untuk mengurangi database storage.

**Final decision:** **DECIDED — accepted default.** Simpan canonical ReceiptDocument pada Job.

**Reason:** Snapshot mendukung audit, deterministic reprint, troubleshooting, dan comparison setelah template upgrade. Tradeoff yang diterima adalah database storage lebih besar.

## A-OD-10 — Browser Fallback Policy

**Question:** Apakah browser fallback tersedia dan dengan batasan apa?

**Options:**

- Recommended: browser fallback tersedia, membutuhkan explicit confirmation, dan hanya boleh jika `content_may_have_printed = 0`.
- Ubah availability, confirmation, atau safety boundary.

**Final decision:** **DECIDED — accepted default.** Browser fallback tersedia, wajib explicit confirmation, dan hanya boleh ketika `content_may_have_printed = 0`.

**Reason:** Policy mempertahankan recovery path tanpa menciptakan duplicate physical output ketika content mungkin telah tercetak.

## A-OD-11 — Terminal Qualification in Foundation

**Question:** Apakah terminal `UNVERIFIED` boleh digunakan dan kapan `QUALIFIED` diwajibkan?

**Options:**

- Recommended: `UNVERIFIED` boleh di DEV/TEST, tetapi tidak dalam production mode `ON`; production wajib `QUALIFIED`; exact enforcement diaktifkan pada Milestone D/E.
- Ubah qualification policy.

**Final decision:** **DECIDED — accepted default.** Izinkan `UNVERIFIED` hanya di DEV/TEST. Dalam production mode `ON`, terminal wajib `QUALIFIED`; exact production enforcement tetap dijadwalkan untuk Milestone D/E.

**Reason:** Foundation dapat dikembangkan dan diuji tanpa mengendurkan qualification gate untuk production.

## A-OD-12 — Test Job Audit

**Question:** Apakah `TEST` print dicatat sebagai POS Print Job/Attempt?

**Options:**

- Yes: simpan `TEST` print dalam POS Print Job/Attempt.
- No: jangan simpan test print dalam audit records.

**Final decision:** **DECIDED — accepted default.** Semua `TEST` print disimpan dalam POS Print Job/Attempt.

**Reason:** Hardware qualification membutuhkan historical evidence.

## A-OD-13 — Physical-Success Semantics

**Question:** Kapan status `SUCCEEDED` boleh digunakan, dan bagaimana browser print direpresentasikan?

**Options:**

- Recommended: `SUCCEEDED` hanya untuk direct printer driver yang melewati completion criteria; browser print tidak pernah `SUCCEEDED` dan berakhir `FALLBACK_BROWSER`.
- Samakan browser handoff dengan `SUCCEEDED`.

**Final decision:** **DECIDED — accepted default.** Gunakan `SUCCEEDED` hanya setelah direct driver memenuhi completion criteria. Browser print selalu berakhir `FALLBACK_BROWSER`, tidak pernah `SUCCEEDED`.

**Reason:** Browser API hanya membuktikan handoff, bukan physical completion.

## A-OD-14 — Server Clock Authority

**Question:** Clock mana yang authoritative untuk timestamps?

**Options:**

- Recommended: seluruh authoritative timestamps berasal dari server/Frappe; browser timestamps hanya diagnostic metadata.
- Gunakan browser atau Android clock sebagai authoritative source.

**Final decision:** **DECIDED — accepted default.** Server/Frappe adalah authority untuk seluruh authoritative timestamps. Browser timestamps hanya boleh disimpan sebagai diagnostic metadata.

**Reason:** Policy mencegah error akibat jam Android device yang salah.

## A-OD-15 — Canonical Timezone Policy

**Question:** Bagaimana audit timestamps disimpan dan ditampilkan?

**Options:**

- Recommended: simpan audit timestamps sesuai standard datetime handling Frappe/server; render menurut timezone site/user; jangan gunakan local Android clock sebagai authoritative field.
- Gunakan timezone atau local device clock sebagai authoritative storage.

**Final decision:** **DECIDED — accepted default.** Simpan audit timestamps mengikuti standard datetime handling Frappe/server, render ke user menurut timezone site/user, dan larang local Android clock sebagai authoritative field.

**Reason:** Policy menjaga canonical audit time yang konsisten sekaligus menampilkan waktu sesuai konteks user.
