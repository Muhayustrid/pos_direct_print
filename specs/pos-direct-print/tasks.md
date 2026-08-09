# Milestone A — Implementation Tasks

Dokumen ini merestrukturisasi urutan handoff A.28 menjadi task granular. Satu sesi hanya boleh mengerjakan task yang diberikan secara eksplisit. Task berikut belum memberi izin untuk mulai coding pada sesi dokumentasi ini.

## Larangan Normatif yang Berlaku pada Setiap Task

Setiap task di bawah membawa larangan eksplisit yang sama:

- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


## Batch A1 — Persistence Foundation


### A1-01 — POS Print Settings persistence

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Buat Single DocType beserta seluruh field, default, validation, dan policy konfigurasi sesuai data model. Bukti memenuhi **A-DOD-01, A-DOD-02, A-DOD-15**.
- **Acceptance tests:** **A-AT-01, A-AT-02**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-02 — POS Print Terminal persistence

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Buat DocType, autoname, field, enum, IDX-TERM-01/02, uniqueness policy, dan deletion-by-disable policy. Bukti memenuhi **A-DOD-02, A-DOD-15**.
- **Acceptance tests:** **A-AT-02, A-AT-19**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-03 — POS Print Job persistence

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Buat system-managed audit DocType dengan seluruh field, enum, IDX-JOB-01..05, uniqueness, validation, dan immutable manual mutation boundary. Bukti memenuhi **A-DOD-02, A-DOD-06, A-DOD-08, A-DOD-15, A-DOD-16**.
- **Acceptance tests:** **A-AT-02, A-AT-03, A-AT-09, A-AT-20, A-AT-21, A-AT-24, A-AT-25**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-04 — POS Print Attempt persistence

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Buat immutable system-managed audit DocType dengan seluruh field, enum, IDX-ATT-UNIQUE-01 dan IDX-ATT-01..04. Bukti memenuhi **A-DOD-02, A-DOD-07, A-DOD-15**.
- **Acceptance tests:** **A-AT-02, A-AT-10, A-AT-23**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-05 — Custom roles and DocType permission matrices

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Buat/configure role `POS Print Operator` dan `POS Print Manager`; terapkan seluruh matrix permission keempat DocType, non-submittable rules, serta System Manager audit immutability. Bukti memenuhi **A-DOD-15, A-DOD-16**.
- **Acceptance tests:** **A-AT-19, A-AT-23, A-AT-24**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-06 — Field sensitivity and sanitized projections

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Terapkan permission Level 0/1 pada Terminal, Job, Attempt serta sanitized runtime settings, terminal, status, dan outcome projections tanpa mengekspos field terlarang. Bukti memenuhi **A-DOD-15**.
- **Acceptance tests:** **A-AT-19, A-AT-21**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-07 — Row-level Company and POS Profile enforcement

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Terapkan operator own-job scope, explicit manager User Permission scope, parent-Job Attempt inheritance, cross-company intersection, permission query condition, document-level enforcement, dan fail-closed behavior dari satu rule source. Bukti memenuhi **A-DOD-15**.
- **Acceptance tests:** **A-AT-20, A-AT-22, A-AT-23, A-AT-25**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-08 — REPRINT authorization boundary

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Sediakan trusted backend action yang memvalidasi role, parent permission, Company, POS Profile, terminal, state/business rule, mandatory reason, lalu membuat Job baru tanpa direct DocType Create. Bukti memenuhi **A-DOD-08, A-DOD-16**.
- **Acceptance tests:** **A-AT-12, A-AT-24**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-09 — Print Job state transition validator

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Terapkan seluruh transition valid A.16, tolak seluruh transition lain dan forbidden transitions, serta jaga conservative content-risk rule. Bukti memenuhi **A-DOD-05, A-DOD-08**.
- **Acceptance tests:** **A-AT-07, A-AT-08, A-AT-12**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-10 — Atomic reservation and attempt numbering

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Terapkan idempotent atomic reservation, optimistic expected state, reservation conflicts, unique monotonic attempt numbering, dan atomic persistence contracts. Bukti memenuhi **A-DOD-06, A-DOD-07**.
- **Acceptance tests:** **A-AT-09, A-AT-10**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A1-11 — Backend persistence and permission test suite

- **Batch:** A1 — Persistence Foundation
- **Exit condition:** Buktikan DocType schema, indexes/constraints, state rules, concurrency, retry safety, role/field/row/API permissions, audit immutability, and REPRINT authorization secara otomatis. Bukti memenuhi **A-DOD-01, A-DOD-02, A-DOD-05, A-DOD-06, A-DOD-07, A-DOD-08, A-DOD-15, A-DOD-16**.
- **Acceptance tests:** **A-AT-01, A-AT-02, A-AT-03, A-AT-07, A-AT-08, A-AT-09, A-AT-10, A-AT-11, A-AT-12, A-AT-19, A-AT-20, A-AT-21, A-AT-22, A-AT-23, A-AT-24, A-AT-25**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


## Batch A2 — Client Foundation


### A2-01 — Idempotent subsystem bootstrap

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan contract initialize/shutdown sekali per browser lifecycle tanpa duplicate override. Bukti memenuhi **A-DOD-03, A-DOD-12**.
- **Acceptance tests:** **A-AT-04**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-02 — ERPNext v16 POS integration adapter

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan adapter canonical interception, penyimpanan/restoration original print path, PrintRequest construction, dan satu-satunya browser-return boundary. Bukti memenuhi **A-DOD-03, A-DOD-04**.
- **Acceptance tests:** **A-AT-04, A-AT-05, A-AT-06**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-03 — PrintManager orchestration contract

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan orchestration melalui domain contracts tanpa dependensi API iMin dan tanpa POS-to-driver direct call. Bukti memenuhi **A-DOD-09, A-DOD-11, A-DOD-12**.
- **Acceptance tests:** **A-AT-11, A-AT-12, A-AT-13, A-AT-15**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-04 — JobCoordinator client contract

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan client coordination untuk reserve, begin attempt, transition, complete, dan release melalui transport yang terotorisasi. Bukti memenuhi **A-DOD-05, A-DOD-06, A-DOD-07, A-DOD-08**.
- **Acceptance tests:** **A-AT-07, A-AT-08, A-AT-09, A-AT-10, A-AT-11, A-AT-12**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-05 — Thin Print API transport

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan operasi RPC wajib tanpa business rules, dengan authorization server-side dan normalization sebelum POS UI. Bukti memenuhi **A-DOD-11, A-DOD-15, A-DOD-16**.
- **Acceptance tests:** **A-AT-15, A-AT-19, A-AT-20, A-AT-22, A-AT-24, A-AT-25**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-06 — BaseDriver abstraction

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan abstract driver contract dan controlled unsupported-capability outcomes tanpa SDK-specific behavior. Bukti memenuhi **A-DOD-09, A-DOD-12**.
- **Acceptance tests:** **A-AT-13**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-07 — Fake foundation driver

- **Batch:** A2 — Client Foundation
- **Exit condition:** Sediakan fake driver untuk membuktikan orchestration dan normalization tanpa device/plugin/Android/printer. Bukti memenuhi **A-DOD-09, A-DOD-11, A-DOD-12**.
- **Acceptance tests:** **A-AT-13, A-AT-15**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-08 — Capability registry

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan generic registration, duplicate policy, lookup, existence, dan normalized capability resolution. Bukti memenuhi **A-DOD-09, A-DOD-12**.
- **Acceptance tests:** **A-AT-13**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-09 — Error normalizer

- **Batch:** A2 — Client Foundation
- **Exit condition:** Implementasikan canonical domain-error mapping, retry classification, content-risk absolute rule, dan safe user error. Bukti memenuhi **A-DOD-08, A-DOD-11**.
- **Acceptance tests:** **A-AT-12, A-AT-15**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A2-10 — Client foundation integration tests

- **Batch:** A2 — Client Foundation
- **Exit condition:** Buktikan override, original path, disabled behavior, fake-driver abstraction, canonical errors, dan no-iMin dependency. Bukti memenuhi **A-DOD-03, A-DOD-04, A-DOD-09, A-DOD-11, A-DOD-12**.
- **Acceptance tests:** **A-AT-04, A-AT-05, A-AT-06, A-AT-13, A-AT-15**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


## Batch A3 — Receipt + Foundation Integration


### A3-01 — ReceiptDocument schema

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Representasikan seluruh canonical top-level fields dan schema-v1 block categories sebagai deterministic serializable IR tanpa browser/printer references. Bukti memenuhi **A-DOD-10, A-DOD-14**.
- **Acceptance tests:** **A-AT-14, A-AT-18**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A3-02 — ReceiptBuilder

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Bangun normalized invoice snapshot menjadi validated canonical ReceiptDocument tanpa mengenal iMin. Bukti memenuhi **A-DOD-10**.
- **Acceptance tests:** **A-AT-14**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A3-03 — Receipt layout abstraction

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Ubah logical receipt values menjadi ordered blocks berdasarkan paper profile tanpa printer calls. Bukti memenuhi **A-DOD-10**.
- **Acceptance tests:** **A-AT-14**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A3-04 — Text wrapper contract

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Implementasikan wrap/truncate deterministic tanpa memecah Unicode code point; jangan menentukan precise thermal character-width policy. Bukti memenuhi **A-DOD-10**.
- **Acceptance tests:** **A-AT-14**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A3-05 — Currency formatter

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Implementasikan deterministic formatting memakai explicit currency, locale, dan policy tanpa implicit browser locale. Bukti memenuhi **A-DOD-10, A-DOD-14**.
- **Acceptance tests:** **A-AT-14, A-AT-18**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A3-06 — Deterministic receipt hash

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Canonicalize dan hash ReceiptDocument sehingga input/schema identik sama dan perubahan material berbeda. Bukti memenuhi **A-DOD-14**.
- **Acceptance tests:** **A-AT-18**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A3-07 — Browser fallback driver and boundary

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Implementasikan saved original ERPNext browser handoff sebagai FALLBACK_BROWSER, hanya dengan approval dan zero content risk; jangan menyatakannya physical success. Bukti memenuhi **A-DOD-04, A-DOD-13**.
- **Acceptance tests:** **A-AT-05, A-AT-06, A-AT-16, A-AT-17**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


### A3-08 — Full Milestone A acceptance suite

- **Batch:** A3 — Receipt + Foundation Integration
- **Exit condition:** Jalankan dan hijaukan seluruh acceptance suite A-AT-01 sampai A-AT-25 tanpa hardware dependency. Bukti memenuhi **A-DOD-01 sampai A-DOD-16**.
- **Acceptance tests:** **A-AT-01 sampai A-AT-25**.
- **Larangan eksplisit A.25/A.26/A.27:** seluruh larangan berikut berlaku pada task ini tanpa pengecualian:
- **Milestone B/D:** jangan mengimplementasikan iMin V1 JavaScript API calls; iMin plugin initialization; actual receipt printing; actual `getPrinterStatus`; exact 58 mm item formatting; cutter implementation; QR; logo; physical retry; delay customer/internal receipt; model detection; USB vs SPI selection.
- **Milestone C:** jangan mengimplementasikan robust multi-tab coordination; browser local-lock implementation detail; cross-tab signaling; sleep/wake recovery; advanced retry; bridge re-init strategy; UNCERTAIN UX workflow.
- **Milestone D:** jangan mengimplementasikan D1/D1w/D4/M2/M2 Pro/S1 capability matrix; model-specific status normalization; ROM qualification; width-specific capability; cutter capabilities; transport differences.


## Final Checklist — Milestone A Handoff Gate

Milestone A siap untuk **AI coding agent Batch A1** karena seluruh poin berikut telah disetujui:

- [x] Seluruh A-OD-01 sampai A-OD-15 sudah diputuskan: **DECIDED — accepted default**.
- [x] Nama empat DocType diterima final.
- [x] State names diterima final.
- [x] Error-code prefix diterima final.
- [x] Identifier convention diterima final.
- [x] Idempotency semantics diterima final.
- [x] Reprint semantics diterima final.
- [x] Browser fallback semantics diterima final.
- [x] AI coding agent diinstruksikan tidak mengimplementasikan iMin SDK pada Milestone A.
- [x] Permission model untuk keempat custom DocType sudah didefinisikan, diterima final, dan mencakup role-level permission, field-level sensitivity, row-level Company/POS Profile restriction, audit immutability, serta REPRINT authority.
- [x] Permission model A.31 sudah **design-frozen**.

Seluruh keputusan di atas final untuk implementasi Milestone A. AI coding agent tidak boleh mengubahnya diam-diam. Jika implementasi menemukan konflik atau ambiguity, agent wajib berhenti dan melaporkannya sebagai architecture decision/change request.

Handoff berikutnya mengizinkan **implementasi A1-01 saja**. Design, scope, requirements, dan implementation direction A1-01 sudah disetujui; AI coding agent tidak perlu membuat atau menunggu persetujuan implementation plan tambahan. Agent wajib membaca dokumen terkait dan memeriksa pola Frappe v16 yang relevan, lalu langsung mengimplementasikan A1-01 beserta focused automated tests dan verifikasi yang diwajibkan `AGENTS.md`.

Handoff ini tidak mengizinkan A1-02 atau task lain, perubahan terhadap frozen specification, pekerjaan Milestone B/C/D, commit, atau push. Jika ditemukan konflik material atau ambiguity yang tidak dapat diselesaikan dari frozen specification dan pola Frappe v16, agent wajib berhenti dan melaporkannya tanpa menebak keputusan desain. Setelah A1-01 selesai dan diverifikasi, agent wajib berhenti dan menunggu instruksi user berikutnya.

## Recommended Design Freeze — A.30

Karena seluruh rekomendasi A.24 diterima tanpa perubahan, Milestone A ditandai:

**DESIGN FROZEN — READY FOR AI CODING AGENT BATCH A1**

Urutan implementasinya:

**A1 Persistence → A2 Client Foundation → A3 Receipt/Foundation Integration**

Baru setelah seluruh acceptance test Milestone A lulus:

**mulai Milestone B — Single-device Happy Path.**

## Catatan Penempatan

A.25–A.27 ditempatkan sebagai larangan pada setiap task karena instruksi task mewajibkan larangan eksplisit per task. A.29 beserta tambahan A.31 ditempatkan satu kali sebagai final checklist agar tidak menduplikasi gate lintas batch.
