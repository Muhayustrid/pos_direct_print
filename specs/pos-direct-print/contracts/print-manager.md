# Print Manager Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.3 `core/print_manager`

Purpose:

top-level orchestration.

POS integration may call PrintManager.

POS integration may not call printer driver directly.

### `requestPrint`

Input:

PrintRequest.

Return:

Promise-like asynchronous `PrintOutcome`.

Responsibilities conceptually:

1. validate request;
2. resolve terminal;
3. reserve job;
4. build ReceiptDocument;
5. select driver;
6. coordinate attempt;
7. drive state transitions;
8. normalize errors;
9. produce PrintOutcome.

Possible errors/outcomes:

all canonical domain errors.

### `retryJob`

Input:

- `job_id`
- retry initiator;
- retry reason.

Return:

PrintOutcome.

Precondition:

job state must allow retry.

Invalid use:

`UNCERTAIN` must throw/return `PDP_JOB_INVALID_TRANSITION`.

### `cancelJob`

Input:

- job_id;
- reason.

Return:

PrintJobSnapshot.

Only valid from cancellable states.

### `fallbackToBrowser`

Input:

- job_id;
- explicit user approval flag.

Return:

PrintOutcome.

Must reject if:

`content_may_have_printed = true`.

### `getJobStatus`

Input:

job_id.

Return:

PrintJobSnapshot.

---
