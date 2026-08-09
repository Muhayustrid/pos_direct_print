# POS Direct Print Agent Guide

Project ini adalah custom Frappe app untuk direct thermal printing dari POS ERPNext v16 ke printer built-in iMin, dikembangkan secara spec-driven.

## Instruksi Wajib

1. **SELALU** baca `specs/pos-direct-print/constitution.md` dan `specs/pos-direct-print/plan.md` sebelum mengerjakan task apa pun di app ini.
2. Kerjakan **HANYA** task yang diberikan secara eksplisit pada sesi berjalan dari `specs/pos-direct-print/tasks.md`. **JANGAN** mengerjakan task lain di luar scope meskipun terlihat berhubungan.
3. **JANGAN** mengedit file di luar `apps/pos_direct_print/`. Semua extension harus dilakukan melalui custom app ini; jangan patch ERPNext core, Frappe core, atau compiled asset ERPNext.
4. Ikuti konvensi di `../.agents/skills/code-style/` untuk seluruh kode yang ditulis di app ini.

## Test dan Build

**TBD — akan ditentukan saat Batch A1 mulai coding.**

## Batas Milestone A

**JANGAN** mengimplementasikan iMin SDK V1 calls atau pekerjaan yang di-defer ke Milestone B/C/D:

- **B/D:** iMin V1 JavaScript API, plugin initialization, actual printing/status, exact 58 mm formatting, cutter, QR, logo, physical retry, customer/internal-receipt delay, model detection, serta USB/SPI selection.
- **C:** robust multi-tab coordination, browser local-lock details, cross-tab signaling, sleep/wake recovery, advanced retry, bridge re-init, serta UNCERTAIN UX workflow.
- **D:** capability matrix D1/D1w/D4/M2/M2 Pro/S1, model-specific status normalization, ROM qualification, width/cutter capabilities, serta transport differences.

Daftar normatif lengkap ada pada A.25, A.26, dan A.27 di `docs/milestone-a-source.md` dan larangan task terkait ada di `specs/pos-direct-print/tasks.md`.
