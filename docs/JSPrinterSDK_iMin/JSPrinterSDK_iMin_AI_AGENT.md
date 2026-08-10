---
title: iMin JSPrinterSDK Agent Reference
purpose: Machine-oriented implementation reference for AI coding agents
audience: AI coding agents
source_of_truth: User-provided iMin JSPrinterSDK documentation
scope: iMin JavaScript printer integration
status: derived-reference
---

# iMin JSPrinterSDK — AI Agent Implementation Reference

## 0. AGENT DIRECTIVE

This file is written for AI coding agents.

Use it as an implementation constraint, not as tutorial material.

### Normative keywords

- `MUST`: required.
- `MUST NOT`: prohibited.
- `SHOULD`: recommended unless project context requires otherwise.
- `MAY`: optional.
- `UNKNOWN`: not established by source documentation.
- `AMBIGUOUS`: source documentation is internally inconsistent or incomplete.

---

# 1. SOURCE BOUNDARY

The supported API surface in this file is derived from the provided iMin JSPrinterSDK documentation.

Agent rules:

1. MUST NOT invent SDK methods.
2. MUST NOT invent parameter values.
3. MUST NOT invent printer status meanings.
4. MUST NOT invent device compatibility.
5. MUST NOT infer asynchronous completion semantics unless documented.
6. MUST isolate any undocumented behavior behind an adapter and mark it `UNVERIFIED`.
7. If implementation requires behavior not covered here, agent MUST mark it for runtime/device verification.

Primary SDK object shown by source:

```js
IminPrintInstance
```

---

# 2. GLOBAL IMPLEMENTATION RULES

## 2.1 SDK access

Agent MUST NOT assume `IminPrintInstance` exists in every environment.

Recommended runtime guard:

```js
function hasIminPrinterSdk() {
  return (
    typeof window !== "undefined" &&
    typeof window.IminPrintInstance !== "undefined"
  );
}
```

If project exposes the SDK through another object, use project runtime reality instead.

---

## 2.2 Architecture

Direct SDK calls SHOULD be isolated.

Recommended boundary:

```text
printer/
  imin_printer_adapter.js
  receipt_renderer.js
  print_service.js
```

Responsibilities:

```text
imin_printer_adapter.js
  -> only iMin SDK calls

receipt_renderer.js
  -> receipt formatting/layout

print_service.js
  -> workflow, retry, fallback, business orchestration
```

Agent SHOULD NOT scatter `IminPrintInstance.*` calls throughout UI code.

---

## 2.3 Capability assumptions

Agent MUST NOT assume all devices support:

```text
SPI
USB
Bluetooth
cutter
cash drawer
Double QR
same paper width
same printer status behavior
same firmware behavior
```

Device-specific behavior SHOULD be expressed as configuration/capability flags.

Example:

```js
const printerCapabilities = {
  cutter: false,
  cashDrawer: false,
  doubleQr: false,
  paperWidthMm: 58,
};
```

---

# 3. CONNECTION TYPES

Verified constants from source:

```js
IminPrintInstance.PrintConnectType.USB
IminPrintInstance.PrintConnectType.SPI
IminPrintInstance.PrintConnectType.Bluetooth
```

Meaning:

| Constant | Meaning |
|---|---|
| `USB` | USB |
| `SPI` | SPI |
| `Bluetooth` | Bluetooth |

Agent MUST NOT hardcode `SPI` for every device unless project/device configuration explicitly establishes it.

---

# 4. INITIALIZATION

## `initPrinter(connectType)`

Source example:

```js
IminPrintInstance.initPrinter(
  IminPrintInstance.PrintConnectType.SPI
);
```

Source behavior:

```text
Resets printer logic settings such as layout/bold/style.
Does NOT clear buffered data.
Unfinished print data may continue after reset.
```

Agent implications:

```text
MUST NOT treat initPrinter() as "clear print queue".
MUST NOT assume buffered content is discarded.
SHOULD explicitly restore required styles after init.
```

---

# 5. PRINTER STATUS

## `getPrinterStatus(connectType, callback)`

Source example:

```js
IminPrintInstance.getPrinterStatus(
  IminPrintInstance.PrintConnectType.SPI,
  function (status) {
    console.log("printer status:" + status.value);
  }
);
```

Known source status values:

| Value | Source description |
|---:|---|
| `-1` | printer not connected or powered on |
| `1` | printer not connected or powered on |
| `3` | print head open |
| `7` | no paper feed |
| `8` | paper running out |
| `99` | other errors |

## Status constraints

Source does NOT establish a ready/success status code.

Therefore:

```text
MUST NOT assume 0 = READY.
MUST NOT assume any undocumented value = READY.
MUST preserve unknown status values.
```

Recommended mapper:

```js
function mapIminPrinterStatus(value) {
  switch (value) {
    case -1:
      return { kind: "not_connected_or_powered", raw: value };

    case 1:
      return { kind: "not_connected_or_powered", raw: value };

    case 3:
      return { kind: "print_head_open", raw: value };

    case 7:
      return { kind: "no_paper_feed", raw: value };

    case 8:
      return { kind: "paper_running_out", raw: value };

    case 99:
      return { kind: "other_error", raw: value };

    default:
      return { kind: "unknown", raw: value };
  }
}
```

### Ambiguity

`-1` and `1` have the same description in source.

Classification:

```text
AMBIGUOUS
```

Agent MUST NOT invent a distinction.

---

# 6. PAPER FEED

## `printAndLineFeed()`

Source:

```js
IminPrintInstance.printAndLineFeed();
```

Meaning:

```text
feeds one line
```

---

## `printAndFeedPaper(value)`

Source:

```js
IminPrintInstance.printAndFeedPaper(100);
```

Source parameter:

```text
value: 0-255
```

Source also states:

```text
maximum paper distance: 1016 mm / 40 inch
```

Agent SHOULD preserve documented range validation.

---

# 7. CUTTER

## `partialCut()`

Source:

```js
IminPrintInstance.partialCut();
```

Constraint:

```text
requires device support
```

Agent rules:

```text
MUST gate behind capability check.
MUST NOT assume every iMin has cutter.
```

---

# 8. TEXT CONFIGURATION

## `setAlignment(alignment)`

```js
IminPrintInstance.setAlignment(1);
```

Values:

```text
0 = left
1 = center
2 = right
default = 0
```

---

## `setTextSize(size)`

```js
IminPrintInstance.setTextSize(26);
```

Source default:

```text
28
```

---

## `setTextTypeface(typeface)`

```js
IminPrintInstance.setTextTypeface(0);
```

Values:

```text
0 = DEFAULT
1 = MONOSPACE
2 = DEFAULT_BOLD
3 = SANS_SERIF
4 = SERIF
```

---

## `setTextStyle(style)`

```js
IminPrintInstance.setTextStyle(1);
```

Values:

```text
0 = NORMAL
1 = BOLD
2 = ITALIC
3 = BOLD_ITALIC
```

---

## `setTextLineSpacing(space)`

```js
IminPrintInstance.setTextLineSpacing(1.0);
```

Source default:

```text
1.0f
```

---

## `setTextWidth(width)`

```js
IminPrintInstance.setTextWidth(576);
```

Source statement:

```text
80mm effective print width = 576
```

Agent MUST NOT assume `576` applies to every printer/paper size.

---

# 9. TEXT PRINTING

## `printText(text)`

Source:

```js
IminPrintInstance.printText("test print content");
```

Source behavior:

```text
automatic wrap
```

---

## `printText(text, type)`

Source:

```js
IminPrintInstance.printText(
  "test print content",
  0
);
```

Source semantics:

```text
type = 0
  newline is required at the end for immediate printing
  otherwise content may remain buffered

type = 1
  word wrap
```

Important source rule:

```text
alignment/font size/bold/etc must be set BEFORE calling printText()
```

Agent rules:

```text
MUST set required style before printText().
MUST preserve newline semantics.
MUST NOT silently strip trailing "\n" when type = 0.
```

Recommended helper:

```js
function printImmediateText(imin, text) {
  const payload = text.endsWith("\n")
    ? text
    : `${text}\n`;

  imin.printText(payload, 0);
}
```

---

# 10. COLUMN PRINTING

## `printColumnsText(...)`

Source description:

```text
not support Arabic
```

Documented conceptual parameters:

```text
colTextArr
colWidthArr
colAlign
width
size
```

Source parameter meaning:

```text
colTextArr
  array of column strings

colWidthArr
  column widths measured in English characters
  Chinese character counts as two English characters
  each width > 0

colAlign
  0 = left
  1 = center
  2 = right

size
  font size array per column

width
  total printable width
  80mm = 576
```

Source example:

```js
IminPrintInstance.printColumnsText(
  ["1", "iMin", "iMin"],
  [1, 2, 1],
  [1, 0, 2],
  [26, 26, 26],
  576
);
```

## Critical ambiguity

The textual signature and the example disagree about the order of:

```text
width
size
```

Source example behaves as:

```text
texts
widths
alignments
sizes
totalWidth
```

Classification:

```text
AMBIGUOUS
```

Agent rule:

```text
MUST isolate this call in adapter.
MUST verify actual runtime signature before depending on it.
MUST NOT silently rewrite source behavior.
```

Recommended adapter boundary:

```js
function printColumns(imin, {
  texts,
  widths,
  alignments,
  sizes,
  totalWidth,
}) {
  // Signature must be verified against runtime SDK/demo.
  return imin.printColumnsText(
    texts,
    widths,
    alignments,
    sizes,
    totalWidth
  );
}
```

---

# 11. BARCODE CONFIGURATION

## `setBarCodeWidth(width)`

```js
IminPrintInstance.setBarCodeWidth(4);
```

Range:

```text
2 <= width <= 6
```

Source default:

```text
3
```

---

## `setBarCodeHeight(height)`

```js
IminPrintInstance.setBarCodeHeight(100);
```

Range:

```text
1 <= height <= 255
```

Source conversion:

```text
8 points = 1 mm
```

---

## `setBarCodeContentPrintPos(position)`

```js
IminPrintInstance.setBarCodeContentPrintPos(2);
```

Values:

```text
0 = do not print HRI
1 = above barcode
2 = below barcode
3 = above and below barcode
```

---

# 12. BARCODE PRINTING

## `printBarCode(barCodeType, barCodeContent)`

Source:

```js
IminPrintInstance.printBarCode(
  73,
  "{B0123456789"
);
```

Known barcode types:

| Code | Type | Length constraints |
|---:|---|---|
| `0` | UPC-A | 11 or 12 |
| `1` | UPC-E | 11 or 12 |
| `2` | JAN13 / EAN13 | 12 or 13 |
| `3` | JAN8 / EAN8 | 7 |
| `4` | CODE39 | >= 1 |
| `5` | ITF | >= 2 |
| `6` | CODABAR | >= 2 |
| `73` | CODE128 | >= 2 |

CODE128 source requirement:

```text
prefix content with {A, {B, or {C
```

Example:

```js
IminPrintInstance.printBarCode(
  73,
  "{B0123456789"
);
```

---

## `printBarCode(barCodeType, barCodeContent, alignmentMode)`

Source:

```js
IminPrintInstance.printBarCode(
  73,
  "{B0123456789",
  1
);
```

Alignment:

```text
0 = left
1 = center
2 = right
```

---

# 13. QR CONFIGURATION

## `setQrCodeSize(level)`

```js
IminPrintInstance.setQrCodeSize(2);
```

Range:

```text
1 <= level <= 16
```

Unit:

```text
dot
```

---

## `setQrCodeErrorCorrectionLev(level)`

```js
IminPrintInstance.setQrCodeErrorCorrectionLev(51);
```

Range:

```text
48 <= level <= 51
```

Source does NOT map these numeric values to named QR correction levels.

Agent:

```text
MUST NOT invent L/M/Q/H mapping.
```

---

## `setLeftMargin(marginValue)`

```js
IminPrintInstance.setLeftMargin(100);
```

Range:

```text
0-576
```

Applies to:

```text
barcode
QR code
```

---

# 14. QR PRINTING

## `printQrCode(qrStr)`

```js
IminPrintInstance.printQrCode(
  "https://www.imin.sg"
);
```

---

## `printQrCode(qrStr, alignmentMode)`

```js
IminPrintInstance.printQrCode(
  "https://www.imin.sg",
  1
);
```

Alignment:

```text
0 = left
1 = center
2 = right
```

---

# 15. PAPER FORMAT

## `setPageFormat(style)`

```js
IminPrintInstance.setPageFormat(1);
```

Values:

```text
0 = 80mm
1 = 58mm
```

---

# 16. BITMAP PRINTING

## `printSingleBitmap(bitmap)`

Source accepts:

```text
base64
URL
```

Examples:

```js
IminPrintInstance.printSingleBitmap(
  "data:image/ico;base64,..."
);
```

```js
IminPrintInstance.printSingleBitmap(
  "https://example.com/image.png"
);
```

Source does NOT establish:

```text
all supported image formats
network timeout behavior
maximum image dimensions
maximum image byte size
retry behavior
```

Classification:

```text
UNKNOWN
```

Agent SHOULD treat image failure as independently recoverable where business flow permits.

---

# 17. CASH DRAWER

## `openCashBox()`

```js
IminPrintInstance.openCashBox();
```

Agent:

```text
MUST gate behind device capability.
MUST NOT assume hardware exists.
```

---

# 18. DOUBLE QR

Source states these methods only support:

```text
M2-203
M2 Pro
M2 Max
D1
```

Agent MUST gate all Double QR calls by supported model/capability.

---

## `setDoubleQRSize(size)`

```js
IminPrintInstance.setDoubleQRSize(1);
```

Range:

```text
1 <= size <= 8
```

---

## `setDoubleQR1Level(level)`

Source parameter:

```text
0-3
```

Source example:

```js
IminPrintInstance.setDoubleQR1Level(16);
```

Classification:

```text
AMBIGUOUS
```

Agent MUST verify before implementation.

---

## `setDoubleQR2Level(level)`

Source parameter:

```text
0-3
```

Source example:

```js
IminPrintInstance.setDoubleQR2Level(16);
```

Classification:

```text
AMBIGUOUS
```

Agent MUST verify before implementation.

---

## `setDoubleQR1MarginLeft(marginValue)`

```js
IminPrintInstance.setDoubleQR1MarginLeft(26);
```

Range:

```text
0-576
```

---

## `setDoubleQR2MarginLeft(marginValue)`

```js
IminPrintInstance.setDoubleQR2MarginLeft(26);
```

Range:

```text
0-576
```

---

## `setDoubleQR1Version(version)`

```js
IminPrintInstance.setDoubleQR1Version(40);
```

Range:

```text
0-40
```

---

## `setDoubleQR2Version(version)`

```js
IminPrintInstance.setDoubleQR2Version(40);
```

Range:

```text
0-40
```

---

## `printDoubleQR(colTextArr)`

```js
IminPrintInstance.printDoubleQR([
  "www.iMin.sg",
  "www.google.com"
]);
```

Supported models remain restricted to:

```text
M2-203
M2 Pro
M2 Max
D1
```

---

# 19. COMPLETE VERIFIED METHOD INDEX

```text
initPrinter(connectType)

getPrinterStatus(connectType, callback)

printAndLineFeed()

printAndFeedPaper(value)

partialCut()

setAlignment(alignment)

setTextSize(size)

setTextTypeface(typeface)

setTextStyle(style)

setTextLineSpacing(space)

setTextWidth(width)

printText(text)

printText(text, type)

printColumnsText(...)

setBarCodeWidth(width)

setBarCodeHeight(height)

setBarCodeContentPrintPos(position)

printBarCode(barCodeType, barCodeContent)

printBarCode(barCodeType, barCodeContent, alignmentMode)

setQrCodeSize(level)

setQrCodeErrorCorrectionLev(level)

setLeftMargin(marginValue)

printQrCode(qrStr)

printQrCode(qrStr, alignmentMode)

setPageFormat(style)

printSingleBitmap(bitmap)

openCashBox()

setDoubleQRSize(size)

setDoubleQR1Level(level)

setDoubleQR2Level(level)

setDoubleQR1MarginLeft(marginValue)

setDoubleQR2MarginLeft(marginValue)

setDoubleQR1Version(version)

setDoubleQR2Version(version)

printDoubleQR(colTextArr)
```

If a requested method is absent from this list:

```text
DO NOT INVENT IT.
```

---

# 20. RECOMMENDED ADAPTER CONTRACT

The following is project architecture guidance, not an official SDK API.

```js
export class IminPrinterAdapter {
  constructor({
    sdk,
    connectType,
    capabilities = {},
  }) {
    this.sdk = sdk;
    this.connectType = connectType;
    this.capabilities = capabilities;
  }

  init() {
    this.sdk.initPrinter(this.connectType);
  }

  getStatus(callback) {
    this.sdk.getPrinterStatus(
      this.connectType,
      callback
    );
  }

  printText(text, type = 0) {
    let payload = text;

    if (
      type === 0 &&
      typeof payload === "string" &&
      !payload.endsWith("\n")
    ) {
      payload += "\n";
    }

    this.sdk.printText(payload, type);
  }

  feedLine() {
    this.sdk.printAndLineFeed();
  }

  feed(value) {
    this.sdk.printAndFeedPaper(value);
  }

  cut() {
    if (!this.capabilities.cutter) {
      throw new Error(
        "iMin cutter capability is not enabled"
      );
    }

    this.sdk.partialCut();
  }

  openCashDrawer() {
    if (!this.capabilities.cashDrawer) {
      throw new Error(
        "iMin cash drawer capability is not enabled"
      );
    }

    this.sdk.openCashBox();
  }
}
```

---

# 21. RECOMMENDED PRINT FLOW

Agent SHOULD implement printing approximately as:

```text
detect SDK
  ↓
resolve device configuration
  ↓
resolve connection type
  ↓
initPrinter()
  ↓
getPrinterStatus()
  ↓
validate known blocking status
  ↓
set page/layout/style
  ↓
print receipt content
  ↓
feed paper
  ↓
cut if supported
  ↓
surface errors to calling layer
```

Do not mix transaction persistence with printer SDK state unless project requirements explicitly demand it.

---

# 22. TWO-RECEIPT DELAY WORKFLOW

Business flow:

```text
customer receipt
  ↓
delay
  ↓
internal receipt
```

The JSPrinterSDK source provided here does NOT define a documented "wait until physical print complete" API.

Therefore:

```text
MUST NOT claim setTimeout() means receipt #1 physically finished.
MUST NOT invent printer acknowledgement callbacks.
```

Application-level delay MAY be implemented:

```js
function delay(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function printTwoReceipts({
  printCustomerReceipt,
  printInternalReceipt,
  delayMs,
}) {
  await printCustomerReceipt();

  await delay(delayMs);

  await printInternalReceipt();
}
```

Interpretation:

```text
This delays dispatch of the second application action.
It does NOT prove physical completion of the first print.
```

If strict physical completion is required:

```text
status = UNVERIFIED
action = verify SDK/device behavior
```

---

# 23. STYLE STATE RULE

Because printer style is stateful:

```text
Agent SHOULD explicitly set style before each logical receipt section.
Agent SHOULD NOT rely on implicit previous style state.
```

Example:

```js
imin.setAlignment(1);
imin.setTextStyle(1);
imin.setTextSize(28);
imin.printText("ROTI ROPI\n", 0);

imin.setAlignment(0);
imin.setTextStyle(0);
imin.setTextSize(24);
imin.printText("Item A\n", 0);
```

---

# 24. MINIMUM ERROR MODEL

Recommended application-level categories:

```text
SDK_UNAVAILABLE
PRINTER_NOT_CONNECTED
PRINT_HEAD_OPEN
NO_PAPER_FEED
PAPER_RUNNING_OUT
OTHER_PRINTER_ERROR
UNKNOWN_PRINTER_STATUS
UNSUPPORTED_CAPABILITY
PRINT_COMMAND_FAILED
```

This taxonomy is project-level, not official SDK terminology.

Unknown SDK values MUST retain raw status data.

---

# 25. REQUIRED AGENT BEHAVIOR FOR AMBIGUITIES

When source is ambiguous:

```text
1. Do not guess.
2. Preserve source data.
3. Isolate uncertain behavior.
4. Add code comment:
   "VERIFY AGAINST IMIN RUNTIME/DEMO".
5. Do not mark task complete if uncertainty blocks required behavior.
```

Known ambiguous areas:

```text
printer status -1 vs 1
printColumnsText argument order
setDoubleQR1Level range/example
setDoubleQR2Level range/example
ready/success status code
physical-print completion acknowledgement
```

---

# 26. PROHIBITED AGENT ASSUMPTIONS

Agent MUST NOT assume:

```text
0 means printer ready

SPI is always the correct connection

initPrinter clears queued/buffered print content

partialCut exists on every target device

openCashBox hardware exists

all iMin models support Double QR

all image URLs will load

all image formats are supported

printText without newline immediately prints in type 0

setTimeout means physical printer completion

printColumnsText argument order is definitively resolved

Double QR level 16 is valid

Arabic is supported by printColumnsText

remote image/network failure cannot affect printing
```

---

# 27. AGENT VALIDATION CHECKLIST

Before declaring implementation complete:

```text
[ ] IminPrintInstance availability tested
[ ] actual runtime exposure confirmed
[ ] connection type confirmed
[ ] initPrinter tested
[ ] getPrinterStatus tested
[ ] known error states mapped
[ ] unknown status preserved
[ ] type=0 newline behavior tested
[ ] text alignment tested
[ ] text style reset behavior tested
[ ] target paper format tested
[ ] image printing tested if used
[ ] barcode tested if used
[ ] QR tested if used
[ ] cutter capability confirmed if used
[ ] cash drawer capability confirmed if used
[ ] Double QR model support confirmed if used
[ ] two-receipt delay tested on physical device if used
[ ] SDK calls isolated in adapter/service
[ ] no undocumented iMin API introduced
```

---

# 28. TASK EXECUTION POLICY FOR AI AGENT

When asked to implement iMin printing:

```text
STEP 1
Read this entire file.

STEP 2
Inspect existing project printer abstraction.

STEP 3
Reuse existing architecture where possible.

STEP 4
Do not introduce undocumented SDK methods.

STEP 5
Centralize iMin SDK calls.

STEP 6
Preserve raw status values.

STEP 7
Mark ambiguous SDK behavior explicitly.

STEP 8
Implement capability gating.

STEP 9
Add runtime error handling.

STEP 10
Test behavior against physical iMin device before claiming hardware correctness.
```

---

# 29. COMPACT AGENT CONTEXT

Use the following as compressed context when full reference is too large:

```text
iMin JSPrinterSDK uses global IminPrintInstance.

Allowed connection constants:
- PrintConnectType.USB
- PrintConnectType.SPI
- PrintConnectType.Bluetooth

Core methods:
- initPrinter(connectType)
- getPrinterStatus(connectType, callback)
- printAndLineFeed()
- printAndFeedPaper(value)
- partialCut()
- setAlignment()
- setTextSize()
- setTextTypeface()
- setTextStyle()
- setTextLineSpacing()
- setTextWidth()
- printText()
- printColumnsText()
- barcode methods
- QR methods
- setPageFormat()
- printSingleBitmap()
- openCashBox()
- Double QR methods

Critical constraints:
- Do not invent SDK APIs.
- initPrinter does not clear buffer.
- printText(text, 0) may require trailing newline to print immediately.
- Style must be set before printText.
- No documented READY status exists in provided source.
- Status -1 and 1 have duplicate source descriptions.
- printColumnsText parameter order is ambiguous.
- Double QR level docs conflict with examples.
- Cutter/cash drawer/Double QR require capability checks.
- Double QR documented only for M2-203, M2 Pro, M2 Max, D1.
- setTimeout delay does not prove physical print completion.
- Unknown behavior must be marked UNVERIFIED.
```

---

# 30. SOURCE REFERENCE

Source documentation represented by this file:

```text
iMin JSPrinterSDK
https://oss-sg.imin.sg/docs/en/JSPrinterSDK.html
```

Source demo reference:

```text
https://oss-sg.imin.sg/docs/demo/iMinJSPrinterSDK.zip
```

End of agent reference.
