# Capability Registry Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.7 `core/capability_registry`

Milestone A provides generic registry only.

### `registerDriver`

Input:

DriverManifest.

Return:

registration result.

Duplicate driver key:

reject unless exact same registration instance is explicitly allowed by bootstrap policy.

### `getDriver`

Input:

driver_key.

Return:

driver factory/reference.

Error:

`PDP_DRIVER_NOT_FOUND`.

### `hasDriver`

Input:

driver_key.

Return:

boolean.

### `resolveCapabilities`

Input:

- driver;
- terminal;
- runtime capabilities.

Return:

DriverCapabilities.

---
