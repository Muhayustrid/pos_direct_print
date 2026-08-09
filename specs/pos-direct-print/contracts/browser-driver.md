# Browser Driver Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.15 `drivers/browser_driver`

Canonical key:

`browser`

BrowserDriver berbeda dengan physical driver.

Its output indicates:

**browser print handoff**, bukan confirmed physical success.

### `print`

Input:

browser fallback context.

Return outcome equivalent to:

- fallback handoff accepted;
- physical completion unknown.

BrowserDriver harus memakai saved original ERPNext `print_receipt` path.

---
