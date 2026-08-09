# Currency Formatter Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.12 `receipt/currency_formatter`

### `format`

Input:

- numeric amount;
- currency;
- locale;
- format policy.

Return:

string.

Must be deterministic.

No dependency on browser locale defaults without explicit locale.

---
