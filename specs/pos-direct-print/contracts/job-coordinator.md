# Job Coordinator Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.5 `core/job_coordinator`

Purpose:

server-backed job reservation and lifecycle coordination.

### `reserve`

Input:

PrintRequest + client concurrency context.

Return:

Reservation.

Errors:

- `PDP_JOB_CONFLICT`
- `PDP_JOB_RESERVATION_EXPIRED`
- `PDP_TERMINAL_DISABLED`

### `beginAttempt`

Input:

- job_id;
- reservation token;
- client context.

Return:

AttemptSnapshot.

### `transition`

Input:

- job_id;
- expected_from_state;
- target_state;
- reservation token;
- transition metadata.

Return:

updated PrintJobSnapshot.

Transition must be atomic.

If actual state does not equal expected state:

`PDP_JOB_CONFLICT`.

### `completeAttempt`

Input:

- attempt_id;
- outcome;
- content flags;
- printer states;
- error if any.

Return:

AttemptSnapshot.

### `release`

Input:

job_id + reservation token.

Return:

acknowledgement.

---
