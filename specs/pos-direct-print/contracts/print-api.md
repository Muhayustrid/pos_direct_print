# Print API Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.6 `core/print_api`

Purpose:

thin Frappe RPC transport.

No business rules.

### Required operations

- get settings;
- resolve terminal;
- reserve print job;
- start attempt;
- transition job;
- complete attempt;
- release reservation;
- retrieve job.

All RPC failures must be normalized before reaching POS UI.

---
