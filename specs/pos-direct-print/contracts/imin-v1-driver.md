# iMin V1 Driver Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.14 `drivers/imin_v1_driver`

Milestone A **tidak mengimplementasikan SDK-specific behavior**.

Contract Milestone A hanya mengunci:

- `driver_key = imin_v1`;
- harus memenuhi seluruh BaseDriver contract;
- raw iMin status tidak boleh keluar dari driver;
- SDK-specific exceptions harus dinormalisasi;
- printer connection/bridge objects tidak boleh diberikan kepada PrintManager.

Exact V1 bridge calls, initialization strategy, model mappings, status conversion, paper width dan cutter behavior menjadi Milestone B/D.

---
