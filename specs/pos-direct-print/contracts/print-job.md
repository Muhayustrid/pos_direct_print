# Print Job Contract

> Restrukturisasi normatif dari `docs/milestone-a-source.md`; tidak menambah desain baru.

# A.12.4 `core/print_job`

Pure domain/state-machine component.

Must contain no printer SDK calls.

### `canTransition`

Input:

- current_state;
- target_state.

Return:

boolean.

### `assertTransition`

Input:

- current_state;
- target_state.

Return:

transition validity result.

Error:

`PDP_JOB_INVALID_TRANSITION`.

### `isTerminalState`

Input:

state.

Return:

boolean.

### `isRetryAllowed`

Input:

- job snapshot;
- latest attempt;
- domain error.

Return:

RetryDecision:

- allowed;
- retry_class;
- automatic;
- reason.

### `deriveContentRisk`

Input:

latest attempt.

Return:

boolean `content_may_have_printed`.

---
