# Text Wrapper Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.11 `receipt/text_wrapper`

### `wrap`

Input:

- text;
- maximum logical width;
- WrapPolicy.

Return:

ordered array of strings.

### `truncate`

Input:

- text;
- max width;
- truncation policy.

Return:

string.

Must never split Unicode code point incorrectly.

Precise character-width policy for thermal font belongs to Milestone D.

---
