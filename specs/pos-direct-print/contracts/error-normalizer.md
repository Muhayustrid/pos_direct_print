# Error Normalizer Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.8 `core/error_normalizer`

### `normalize`

Input:

- raw error;
- lifecycle phase;
- context including content_started flag.

Return:

PrintDomainError.

### `classifyRetry`

Input:

PrintDomainError + attempt context.

Return:

retry class.

Absolute rule:

if `content_may_have_printed = true`:

return must never be `AUTO_SAFE` or `MANUAL_SAFE`.

Must be `REPRINT_ONLY` or `NONE`.

### `toUserError`

Input:

PrintDomainError.

Return:

safe user-facing structure containing:

- title/message key;
- allowed actions;
- no stack trace.

---
