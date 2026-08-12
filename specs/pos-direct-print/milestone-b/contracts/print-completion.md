# Contract B-COMP: Print Completion Semantics

**Status:** DECIDED — APPROVED: Option A (Conservative Dispatch Success), 2026-08-10.

**Refinement of:** interpretation of `DriverPrintResult` and settle rules.

**Depends on frozen Milestone A contracts:**

- `data-contracts.md`
- `print-manager.md`
- `constitution.md`

## B-COMP-01 Problem

iMin JavaScript Printer SDK V1 gives no physical print-completion proof.

Evidence gathered in `research.md` sections 7 and 10 shows:

- `printText` returns after the command is handed to the local service;
- `printAndFeedPaper` returns after dispatch;
- no job id, completion callback, or hardware acknowledgment exists;
- buffered content may remain after a call returns;
- `initPrinter` explicitly does not clear buffered data.

Therefore "function returned" must never be treated as "paper printed".

## B-COMP-02 Evidence that dispatch completed

This evidence is required and sufficient to enter `VERIFYING`:

1. preflight status was `READY`;
2. every receipt line was dispatched in order;
3. every outbound SDK command carried exactly one trailing newline;
4. the final feed was dispatched;
5. no synchronous SDK error occurred;
6. no connection-loss signal occurred before final dispatch.

This evidence proves command dispatch only. It is recorded in the Attempt.

## B-COMP-03 What `SUCCEEDED` requires

Milestone A settle rule uses `accepted && content_completed` to reach `SUCCEEDED`.

In Milestone B, `content_completed` has one meaning: all commands dispatched.

Because dispatch is not physical completion, one of the options below must be approved.

No implementation may pick an option silently.

## B-COMP-A: Conservative dispatch success — APPROVED

`SUCCEEDED` is allowed when B-COMP-02 holds and a post-dispatch status query returns `READY`.

Constraints:

- the status query happens after final feed;
- the status query is bounded in time;
- a failed or absent post-status query does not allow `SUCCEEDED`;
- the returned `DriverPrintResult` records `verification_supported = false`; the existing Attempt/Job schema has no dedicated `verification_supported` field, so any persisted evidence belongs in existing metadata or status fields without schema change.

Recorded limitation: `SUCCEEDED` under Option A is the best-available SDK-confirmed operational completion. It is NOT physical-completion proof, because iMin JS Printer SDK V1 provides no physical acknowledgment.

Failure rule: if any error occurs after `content_started = true` and the physical result cannot be established, the existing Milestone A conservative policy applies. The Job settles `UNCERTAIN` and same-job retry is forbidden; only REPRINT continues.

Residual risk: paper may still be moving when the Job is marked succeeded.

## B-COMP-B: No automatic success — REJECTED

Rejected 2026-08-10. It cannot prove the Milestone B happy path and either amends the frozen transition table or converts every successful print into `UNCERTAIN`.

## B-COMP-C: External completion evidence — REJECTED

Rejected 2026-08-10. No approved evidence source exists and the gating workflow belongs to later milestones.

## B-COMP-04 Invariants

Regardless of option:

- `content_completed` never means physical completion;
- `verification_supported` stays false for SDK-only evidence;
- `UNCERTAIN` remains final for retrying the same Job once content started;
- browser fallback is never marked physical success;
- no new state transition is invented without Milestone A approval.

## B-COMP-05 Approval gate

Approved option: **Option A (Conservative Dispatch Success)**

Decision: DECIDED — APPROVED

Approval date: 2026-08-10

Remaining gate: implementation still waits for the reference-device blockers in `research.md` section 13.
