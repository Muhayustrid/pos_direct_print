# POS Direct Print Agent Guide

Project ini adalah custom Frappe app untuk direct thermal printing dari POS ERPNext v16 ke printer built-in iMin, dikembangkan secara spec-driven.

## Instruksi Wajib

1. **SELALU** baca `specs/pos-direct-print/constitution.md` dan `specs/pos-direct-print/plan.md` sebelum mengerjakan task apa pun di app ini.
2. Kerjakan **HANYA** task yang diberikan secara eksplisit pada sesi berjalan dari `specs/pos-direct-print/tasks.md`. **JANGAN** mengerjakan task lain di luar scope meskipun terlihat berhubungan.
3. **JANGAN** mengedit file di luar `apps/pos_direct_print/`. Semua extension harus dilakukan melalui custom app ini; jangan patch ERPNext core, Frappe core, atau compiled asset ERPNext.
4. Ikuti konvensi di `../.agents/skills/code-style/` untuk seluruh kode yang ditulis di app ini.

## Environment, Test, dan Build

Jalankan command Frappe/ERPNext melalui development container berikut, bukan langsung dari host macOS:

```text
Container: frappe_docker_devcontainer-frappe-1
Bench root: /workspace/development/frappe-bench
Development/test site: development.localhost
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

# Jalankan hanya ketika task mengubah frontend assets
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench build --app pos_direct_print'
```

Aturan verifikasi:

- Jalankan focused test untuk task aktif terlebih dahulu, kemudian regression test yang relevan.
- Jangan mengklaim test lulus jika tidak ada test yang collected/executed.
- `pre-commit run --all-files` dapat mengubah file; selalu periksa final diff setelah command selesai.
- Jangan menjalankan `bench migrate` atau `bench build` jika task tidak memerlukannya.
- Jangan commit atau push kecuali user memerintahkannya secara eksplisit.

## Batas Milestone A

**JANGAN** mengimplementasikan iMin SDK V1 calls atau pekerjaan yang di-defer ke Milestone B/C/D:

- **B/D:** iMin V1 JavaScript API, plugin initialization, actual printing/status, exact 58 mm formatting, cutter, QR, logo, physical retry, customer/internal-receipt delay, model detection, serta USB/SPI selection.
- **C:** robust multi-tab coordination, browser local-lock details, cross-tab signaling, sleep/wake recovery, advanced retry, bridge re-init, serta UNCERTAIN UX workflow.
- **D:** capability matrix D1/D1w/D4/M2/M2 Pro/S1, model-specific status normalization, ROM qualification, width/cutter capabilities, serta transport differences.

Daftar normatif lengkap ada pada A.25, A.26, dan A.27 di `docs/milestone-a-source.md` dan larangan task terkait ada di `specs/pos-direct-print/tasks.md`.
