# Bootstrap Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.1 `bootstrap`

Purpose:

initialize subsystem once per Desk/browser lifecycle.

Functions:

### `initialize`

Input:

BootstrapContext containing:

- current user;
- current route;
- feature settings;
- app asset version.

Returns:

BootstrapResult:

- initialized;
- integration_installed;
- active_driver;
- warnings.

May raise:

- `PDP_CONFIG_INVALID`
- `PDP_INTERNAL_ERROR`

Must be idempotent.

Calling initialize twice must not install two POS overrides.

### `shutdown`

Input:

none.

Return:

void/result acknowledgement.

Responsibilities:

- restore override if necessary;
- release transient client resources.

---
