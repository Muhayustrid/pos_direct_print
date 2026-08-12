# Contract B-RUN: imin_v1 Runtime and SDK Adapter

**Status:** GENERIC DESIGN FROZEN — SDK asset pin owned by B1-01; hardware qualification values pending reference device

**Refinement of:** none. This is a new Milestone B contract.

**Depends on frozen Milestone A contracts:**

- `error-contract.md`
- `error-normalizer.md`

## B-RUN-01 Purpose

This contract defines the only module allowed to touch the raw iMin JavaScript Printer SDK.

The module is `drivers/imin_sdk_adapter.mjs`.

## B-RUN-02 SDK asset

One SDK V1 asset from `docs/iMinJSPrinterSDK/v1/` is pinned during B1-01. The current candidate is `v1/js-demo/html-demo/imin-printer.js`; B1 records an app-owned vendored path separately and never loads reference files from `docs/`.

The local `docs/iMinJSPrinterSDK/v2/` tree is byte-identical to V1.4.0 and is not evidence of an authoritative distinct V2 API. It must not be selected or vendored by Milestone B.

The pinned asset record must include:

- file path inside app assets;
- checksum;
- version string;
- exported constructor name;
- status API style, callback or Promise.

No other SDK variant may be loaded by Milestone B.

Assets under `docs/` are reference material only and never loaded by production code.

## B-RUN-03 Bridge availability

The adapter reports bridge availability as one controlled result:

- available, when the SDK constructor exists and `connect()` succeeds;
- unavailable, when WebSocket support is missing, the asset is missing, construction fails, or `connect()` fails or times out.

The adapter must not throw raw SDK errors across this boundary.

Unavailable results must carry a short canonical reason, not raw stack traces.

## B-RUN-04 Initialization

The adapter exposes one initialize operation with the reference connection type.

It must:

- call `initPrinter` exactly once per qualification sequence;
- return a controlled success or failure result;
- never resolve success from an unverified device side effect.

No fixed delay is added unless the reference-device qualification record requires it.

## B-RUN-05 Status query

The adapter exposes one status query operation.

It must:

- call `getPrinterStatus` with the reference connection type;
- return the raw value inside a controlled result envelope;
- coerce numeric-string ambiguity before returning, so callers receive one normalized numeric value;
- time-box the query using an injected timeout, with the default defined during B1 qualification.

The adapter must not decide `READY`. Raw mapping belongs to the driver.

## B-RUN-06 Dispatch operations

The adapter exposes dispatch operations for:

- page format;
- text width;
- alignment;
- text size;
- text style;
- one logical text line;
- final feed.

For the pinned UMD asset, the adapter strips trailing newline characters from the logical line and calls the no-type `printText(line)` overload. The SDK appends exactly one newline to the outbound command. Tests assert the outbound command payload, not merely the pre-SDK argument.

The underlying SDK dispatch methods are void/fire-and-forget. Each adapter operation converts synchronous return/throw behavior into a controlled dispatch result; that result proves dispatch acceptance only, not SDK or physical completion.

The adapter must not reorder operations.

The adapter must not retry dispatch.

## B-RUN-07 Cleanup

If the pinned asset exposes `close()`, the adapter may call it during dispose.

This is allowed only after B1 qualification proves the call does not corrupt printer state.

If `close()` is unproven, dispose only drops the SDK reference.

## B-RUN-08 Mock boundary

The adapter interface must be fully injectable.

Automated tests must replace the adapter with a fake that records every operation.

No automated test may open a real WebSocket.

## B-RUN-09 Error containment

Every SDK failure must become one of:

- a controlled adapter result carrying a canonical error code from the frozen taxonomy;
- a `PrintDomainError` built through the existing normalizer.

Raw SDK objects, WebSocket handles, and raw error objects must never leave the adapter.
