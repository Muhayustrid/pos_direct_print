# POS Direct Print Agent Guide

Custom Frappe app (branch `version-16`) untuk direct thermal printing dari POS ERPNext v16 ke printer built-in iMin, dikembangkan secara spec-driven. Repo saat ini = skeleton Frappe + spec Milestone A yang **design-frozen**; DocType, API endpoint, frontend asset, dan test belum diimplementasikan. Spec dan dokumentasi ditulis dalam bahasa Indonesia — ikuti bahasa dokumen yang sudah ada.

## Instruksi Wajib

1. **SELALU** baca `specs/pos-direct-print/constitution.md` dan `specs/pos-direct-print/plan.md` sebelum mengerjakan task apa pun di app ini.
2. Kerjakan **HANYA** task yang diberikan secara eksplisit pada sesi berjalan dari `specs/pos-direct-print/tasks.md`. Otorisasi selalu mengikuti handoff terakhir di file itu (saat ini: **A1-01 saja**). Task dalam satu Batch boleh berurutan, tetapi transisi antar-Batch (A1 → A2 → A3) wajib menunggu review dan persetujuan eksplisit user.
3. **JANGAN** mengedit file di luar `apps/pos_direct_print/`. Semua extension harus melalui custom app ini; jangan patch ERPNext core, Frappe core, atau compiled asset ERPNext.
4. Jika menemukan konflik atau ambiguitas yang tidak bisa diselesaikan dari frozen spec + pola Frappe v16, **berhenti dan laporkan** sebagai change request — jangan menebak keputusan desain.
5. Ikuti konvensi di `.agents/skills/code-style/` (skills Frappe lain, termasuk `frappe-app-dev`, ada di direktori yang sama). Ringkasan arsitektur, DocType, dan invarian domain ada di `CLAUDE.md`.
6. Jangan commit atau push kecuali user memerintahkannya secara eksplisit.

## Environment, Test, dan Build

Jalankan command Frappe/ERPNext melalui development container berikut, bukan langsung dari host macOS:

```text
Container: frappe_docker_devcontainer-frappe-1
Bench root: /workspace/development/frappe-bench
Development/test site: development.localhost (app pos_direct_print sudah terpasang)
```

Command canonical:

```bash
# Focused backend test — ganti <PYTHON_TEST_MODULE> dengan module test task berjalan
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module <PYTHON_TEST_MODULE> \
     --failfast'

# Seluruh test app
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --test-category all'

# Lint dan format; command ini dapat memperbaiki file, jadi periksa diff sesudahnya
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench/apps/pos_direct_print && \
   pre-commit run --all-files'

# Jalankan setelah task mengubah DocType/schema/fixtures
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost migrate'

# Jalankan hanya ketika task mengubah frontend asset
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench build --app pos_direct_print'
```

Aturan verifikasi:

- Jalankan focused test untuk task aktif terlebih dahulu, kemudian regression test yang relevan.
- Jangan mengklaim test lulus jika tidak ada test yang collected/executed — repo ini belum punya test sampai task terkait membuatnya.
- `pre-commit run --all-files` dapat mengubah file; selalu periksa final diff setelah command selesai.
- Jangan menjalankan `bench migrate` atau `bench build` jika task tidak memerlukannya.

## Batas Milestone A

**JANGAN** mengimplementasikan iMin SDK V1 calls atau pekerjaan yang di-defer ke Milestone B/C/D (larangan ini berlaku pada **setiap** task Milestone A):

- **B/D:** iMin V1 JavaScript API, plugin initialization, actual printing/status, exact 58 mm formatting, cutter, QR, logo, physical retry, customer/internal-receipt delay, model detection, serta USB/SPI selection.
- **C:** robust multi-tab coordination, browser local-lock details, cross-tab signaling, sleep/wake recovery, advanced retry, bridge re-init, serta UNCERTAIN UX workflow.
- **D:** capability matrix D1/D1w/D4/M2/M2 Pro/S1, model-specific status normalization, ROM qualification, width/cutter capabilities, serta transport differences.

Daftar normatif lengkap ada pada A.25, A.26, dan A.27 di `docs/milestone-a-source.md` dan larangan per-task ada di `specs/pos-direct-print/tasks.md`. `docs/JSPrinterSDK_iMin/JSPrinterSDK_iMin_AI_AGENT.md` adalah referensi SDK untuk Milestone B+ — jangan memakainya untuk mengimplementasikan SDK pada Milestone A.

## Jebakan di Repo Ini

- Folder `pos_direct_print/doctype/pos_print_*` saat ini hanya berisi `__pycache__` sisa sesi sebelumnya; sumber DocType (`.py`/`.json`) belum ada — jangan menganggap DocType sudah terimplementasi.
- `.claude/worktrees/` adalah git worktree milik sesi agent lain — jangan membaca/mengedit file di dalamnya sebagai sumber kebenaran.
- Toolchain: Python `>=3.14`, Ruff (line-length 110, indent tab, double quote), ESLint + Prettier via pre-commit. Frappe dikelola oleh bench dan sengaja tidak ada di dependency `pyproject.toml`.
