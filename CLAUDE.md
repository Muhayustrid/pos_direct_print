# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project State and Required Reading

`pos_direct_print` is a spec-driven Frappe app for direct thermal printing from ERPNext POS v16. The repository is currently a Frappe skeleton plus frozen Milestone A specifications; the direct-print subsystems, DocTypes, frontend assets, API endpoints, fixtures, and executable tests have not yet been implemented.

Before implementation work, read:

1. `AGENTS.md` for execution rules and current authorization.
2. `specs/pos-direct-print/constitution.md` for non-negotiable invariants.
3. `specs/pos-direct-print/plan.md` for architecture, state transitions, and idempotency.
4. The explicitly assigned task in `specs/pos-direct-print/tasks.md`, then its linked contracts and acceptance tests.

Only implement tasks explicitly authorized in `tasks.md`. The current handoff authorizes A1-01 only. Tasks may run sequentially within a Batch, but transitions between A1, A2, and A3 require explicit user review and approval. Do not modify Frappe core, ERPNext core, compiled assets, or files outside this app.

Milestone A builds contracts and foundations only. Actual iMin SDK calls, plugin initialization, physical printing/status checks, model detection, cutter/QR/logo support, transport selection, advanced retry, robust multi-tab coordination, and model-specific capability matrices belong to later milestones.

## Development Environment and Commands

Run all Bench/Frappe commands inside container `frappe_docker_devcontainer-frappe-1`. Bench root is `/workspace/development/frappe-bench`; development site is `development.localhost`.

Focused Python test module:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module <PYTHON_TEST_MODULE> \
     --failfast'
```

Full app test suite:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --test-category all'
```

Lint and format all tracked files:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench/apps/pos_direct_print && \
   pre-commit run --all-files'
```

Individual hooks can be run with `pre-commit run ruff --all-files`, `pre-commit run ruff-format --all-files`, `pre-commit run prettier --all-files`, or `pre-commit run eslint --all-files`. Pre-commit hooks may edit files; inspect the final diff.

After DocType, schema, or fixture changes only:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost migrate'
```

After frontend asset changes only:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench build --app pos_direct_print'
```

The repository currently contains no executable tests. A zero-test run does not prove success; confirm that expected tests were collected and executed. Do not run migrate or asset builds unless the task requires them.

## Architecture

Planned canonical flow:

```text
ERPNext POS v16
  -> integration/erpnext_v16_pos
  -> PrintManager
  -> JobCoordinator
  -> ReceiptBuilder
  -> BaseDriver
  -> concrete driver
```

`integration/erpnext_v16_pos` is the only module allowed to know ERPNext POS runtime structure. It will intercept `erpnext.PointOfSale.PastOrderSummary.prototype.print_receipt`, preserve the original method, construct a business-level `PrintRequest`, and call `PrintManager`. The original method is the single browser-fallback boundary. Bootstrap initialization must be idempotent, and shutdown must restore the original method.

`PrintManager` owns orchestration, not transport details: validate requests, resolve a terminal, reserve an idempotent Job, build a receipt, select a driver, create an Attempt, coordinate state transitions, normalize errors, and return a `PrintOutcome`. POS integration must not bypass it.

`core/print_api` is planned as thin Frappe RPC transport. Business lifecycle and atomicity belong in `JobCoordinator`, including idempotent reservation, unique attempt numbering, optimistic `expected_from_state` transitions, attempt completion, and reservation release. Mutation endpoints must enforce permissions server-side.

`ReceiptBuilder` converts a normalized invoice snapshot into serializable `ReceiptDocument`; it must not know iMin APIs. Drivers consume `ReceiptDocument` and return normalized `DriverPrintResult`. Browser fallback is a driver/handoff outcome, not proof of physical-print success.

## Persistence and Security Model

Milestone A defines four DocTypes:

- `POS Print Settings`: Single DocType for global mode, defaults, fallback/retry policy, retention, and schema version.
- `POS Print Terminal`: physical endpoint bound to Company and POS Profile; stores pairing, driver, health, and normalized capabilities.
- `POS Print Job`: one logical printing intent, including idempotency, reservation, receipt snapshot/hash, state, and fallback status.
- `POS Print Attempt`: one physical execution attempt; safe retry creates another Attempt under the same Job.

Core relations:

```text
POS Print Terminal 1 -- N POS Print Job 1 -- N POS Print Attempt
POS Invoice/Sales Invoice 1 -- N POS Print Job
Original Job 1 -- N Reprint Job through parent_job
```

Security scope is Company plus POS Profile. Canonical roles are `POS Print Operator`, `POS Print Manager`, and `System Manager`. Job and Attempt are system-managed audit records; list filtering and direct-document permission checks must share the same scope rules.

## Domain Invariants

Invoice completion and printing are separate transactions. Print failure must never roll back, cancel, resubmit, or alter the invoice/payment.

A Job is logical intent; an Attempt is physical execution. `UNCERTAIN` is final for retrying the same Job because output may already exist. A reprint creates a new Job with `job_type = REPRINT` and links it through `parent_job`.

Browser fallback is allowed only while physical content cannot have been printed. Browser handoff is not `SUCCEEDED`.

Reservation, state transitions, and attempt numbering must be atomic. Follow the state graph and retry matrix in `plan.md`; do not invent transitions or infer retry safety from raw driver errors.

## Code and Configuration Conventions

Python requires 3.14 and uses Ruff with a 110-character line limit, tab indentation, double quotes, and rule families `F`, `E`, `W`, `I`, `UP`, `B`, and `RUF`. JavaScript uses ES2022 modules and `eslint:recommended`; Prettier covers JavaScript, Vue, and SCSS. Frappe is managed by Bench and intentionally absent from package dependencies.

Keep functions focused, avoid premature abstractions, and place public or higher-order functions before low-level utilities. Comments should explain non-obvious constraints, not narrate code. Match Frappe v16 patterns already present in installed Frappe/ERPNext apps before introducing custom mechanisms.
