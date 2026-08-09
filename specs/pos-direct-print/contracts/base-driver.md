# Base Driver Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.13 `drivers/base_driver`

Abstract driver contract.

Every printer driver must implement it.

### `detect`

Input:

DriverContext.

Return:

DetectionResult:

- available;
- reason;
- metadata.

### `initialize`

Input:

DriverContext.

Return:

InitializationResult.

### `getCapabilities`

Input:

none/runtime context if required.

Return:

DriverCapabilities.

### `getStatus`

Return:

PrinterStatus.

### `print`

Input:

- ReceiptDocument;
- DriverJobContext.

Return:

DriverPrintResult.

### `feed`

Input:

normalized feed request.

Return:

DriverOperationResult.

### `cut`

Input:

cut request.

Return:

DriverOperationResult.

Unsupported cutter:

must result in capability-related controlled outcome, never uncontrolled exception.

### `dispose`

Input:

none.

Return:

cleanup acknowledgement.

---
