# Milestone A Audit Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menutup temuan audit permission, retry classification, retry atomicity, dan status remediation tanpa mengubah ERPNext atau Frappe.

**Architecture:** Custom app memakai satu pembuat SQL predicate untuk POS Profile applicability. List permission, direct permission, dan Job creation memakai predicate yang sama. Safe retry memakai satu guarded database update untuk reservation dan counter.

**Tech Stack:** Python 3.14, Frappe v16, MariaDB, `frappe.tests.IntegrationTestCase`, thread dengan koneksi Frappe terpisah, Node.js native test runner.

## Global Constraints

- Ubah file hanya dalam `apps/pos_direct_print/`.
- Jangan mengubah file dalam app `erpnext` atau `frappe`.
- Jangan menjalankan `bench migrate` atau `bench build`.
- Jangan menambah dependency.
- Jangan mengimplementasikan API iMin, plugin printer, physical printing, atau pekerjaan Milestone B, C, dan D.
- Gunakan tab, double quote, dan line length maksimum 110 untuk Python.
- Jalankan command Bench dalam container `frappe_docker_devcontainer-frappe-1`.
- Gunakan site `development.localhost` pada setiap command Bench.
- Jangan commit atau push tanpa instruksi user terpisah.
- Pertahankan perubahan working tree yang sudah ada.
- Laporkan perubahan eksternal ERPNext dan Frappe. Jangan membersihkan perubahan tersebut.

## File Map

| File | Tanggung jawab setelah remediation |
|---|---|
| `pos_direct_print/core/security.py` | Satu sumber SQL predicate untuk Company dan POS Profile applicability. |
| `pos_direct_print/core/reservation.py` | Original Job creation validation dan guarded safe-retry reservation. |
| `pos_direct_print/core/retry.py` | Pure retry decision dengan `retry_class` konsisten. |
| `pos_direct_print/core/test_row_scope.py` | List dan direct permission regression tests. |
| `pos_direct_print/core/test_reservation.py` | Creation validation dan concurrent safe-retry tests. |
| `pos_direct_print/core/test_suite_coverage.py` | Production retry classification tests. |
| `specs/pos-direct-print/tasks.md` | Handoff remediation baru. Riwayat lama tetap utuh. |
| `specs/pos-direct-print/progress.json` | Record remediation dan verification evidence. |

---

### Task 1: Enforce Operator POS Profile Applicability

**Files:**
- Modify: `pos_direct_print/core/security.py:1-174`
- Modify: `pos_direct_print/core/reservation.py:29-68`
- Test: `pos_direct_print/core/test_row_scope.py:15-205`
- Test: `pos_direct_print/core/test_reservation.py`

**Interfaces:**
- Produces: `operator_pos_profile_condition(user: str, profile_expression: str, company_expression: str) -> str`
- Produces: `operator_pos_profile_is_applicable(user: str, pos_profile: str, company: str) -> bool`
- Produces: `assert_operator_pos_profile_applicable(user: str, pos_profile: str, company: str) -> None`
- Consumes: ERPNext tables `tabPOS Profile` and `tabPOS Profile User` through read-only SQL.

- [ ] **Step 1: Add failing row-scope fixtures and tests**

Extend `TestRowLevelScope.setUp()` with three dedicated profiles:

```python
self.profile_operator_a = _pos_profile("PDP Scope A", self.operator_a)
self.profile_operator_b = _pos_profile("PDP Scope B", self.operator_b)
self.profile_global = _pos_profile("PDP Scope Global")

self.job_profile_a = _job(requested_by=self.operator_a, pos_profile=self.profile_operator_a)
self.job_wrong_profile = _job(requested_by=self.operator_a, pos_profile=self.profile_operator_b)
self.job_global_profile = _job(requested_by=self.operator_a, pos_profile=self.profile_global)
```

Add tests with exact list and direct assertions:

```python
def test_operator_scope_requires_pos_profile_applicability(self):
	visible = _list_as(self.operator_a, JOB)
	self.assertIn(self.job_profile_a, visible)
	self.assertIn(self.job_global_profile, visible)
	self.assertNotIn(self.job_wrong_profile, visible)

	with _user(self.operator_a):
		frappe.get_doc(JOB, self.job_profile_a).check_permission("read")
		frappe.get_doc(JOB, self.job_global_profile).check_permission("read")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(JOB, self.job_wrong_profile).check_permission("read")
```

Create `_pos_profile()` as a test helper. Copy an existing valid POS Profile document. Give it a unique name and Company. Clear `applicable_for_users`, then append one row only when `user` is not `None`.

```python
def _pos_profile(name, user=None, *, company=COMPANY, disabled=0):
	source = frappe.get_doc("POS Profile", OUTLET_A)
	profile = frappe.copy_doc(source)
	profile.name = f"{name}-{uuid.uuid4().hex[:8]}"
	profile.company = company
	profile.disabled = disabled
	profile.set("applicable_for_users", [])
	if user:
		profile.append("applicable_for_users", {"user": user, "default": 0})
	return profile.insert(ignore_permissions=True).name
```

- [ ] **Step 2: Run focused row-scope test and verify failure**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_row_scope \
     --failfast'
```

Expected: the wrong-profile Job remains visible before the production fix.

- [ ] **Step 3: Add one SQL predicate source in `security.py`**

Replace the Operator scope assumption in the module docstring. State the explicit applicability rule.

Add this public helper before query-condition functions:

```python
def operator_pos_profile_condition(user, profile_expression, company_expression):
	"""Return the ERPNext v16 POS Profile applicability predicate for an Operator."""
	user = frappe.db.escape(user)
	return (
		"EXISTS ("
		"SELECT 1 FROM `tabPOS Profile` profile "
		f"WHERE profile.name = {profile_expression} "
		f"AND profile.company = {company_expression} "
		"AND profile.disabled = 0 "
		"AND ("
			"EXISTS ("
				"SELECT 1 FROM `tabPOS Profile User` applicable "
				"WHERE applicable.parent = profile.name "
				f"AND applicable.user = {user}"
			") "
			"OR NOT EXISTS ("
				"SELECT 1 FROM `tabPOS Profile User` configured "
				"WHERE configured.parent = profile.name"
			")"
		")"
		")"
	)
```

Use the same predicate for a direct check:

```python
def operator_pos_profile_is_applicable(user, pos_profile, company):
	condition = operator_pos_profile_condition(
		user,
		frappe.db.escape(pos_profile),
		frappe.db.escape(company),
	)
	return bool(frappe.db.sql(f"SELECT 1 WHERE {condition}"))
```

The helper interpolates only server-owned SQL expressions or escaped values. Do not pass client-controlled raw expressions.

- [ ] **Step 4: Apply the predicate to list and direct Job permission**

Change the Operator query clause in `get_job_query_conditions()`:

```python
if scopes["operator"]:
	clause = f"requested_by = {frappe.db.escape(user)}"
	if scopes["companies"]:
		clause += f" AND company IN {_sql_values(scopes['companies'])}"
	clause += " AND " + operator_pos_profile_condition(user, "pos_profile", "company")
	clauses.append(f"({clause})")
```

Change `job_row_visible()`:

```python
if scopes["operator"] and requested_by == user:
	return operator_pos_profile_is_applicable(user, pos_profile, company)
```

Do not alter Manager behavior.

- [ ] **Step 5: Add creation validator and failing creation tests**

Import the applicability helper into `reservation.py`:

```python
from pos_direct_print.core.security import operator_pos_profile_is_applicable
```

Add:

```python
def assert_operator_pos_profile_applicable(user, pos_profile, company):
	roles = frappe.get_roles(user)
	if "POS Print Operator" not in roles:
		return
	if operator_pos_profile_is_applicable(user, pos_profile, company):
		return
	frappe.throw(
		_("PDP_PERMISSION_DENIED: POS Profile is not available for this Operator."),
		exc=frappe.PermissionError,
	)
```

Call it at the start of `create_original_job()` before constructing the document:

```python
assert_operator_pos_profile_applicable(requested_by, pos_profile, company)
```

Add creation tests to `test_reservation.py`:

```python
def test_original_job_rejects_operator_outside_pos_profile(self):
	operator = _user_with_role("pdp.creation.operator@example.test", "POS Print Operator")
	other = _user_with_role("pdp.creation.other@example.test", "POS Print Operator")
	profile = _pos_profile("PDP Creation Restricted", other)

	with self.assertRaises(frappe.PermissionError) as ctx:
		create_original_job(
			idempotency_key=f"idem-{uuid.uuid4().hex}",
			reference_doctype="Company",
			reference_name=COMPANY,
			company=COMPANY,
			pos_profile=profile,
			terminal=_terminal(pos_profile=profile),
			requested_by=operator,
		)
	self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))
```

Add equivalent tests for disabled profile and Company mismatch. Use a profile applicable to the Operator so each test isolates one failed condition.

- [ ] **Step 6: Run focused permission and reservation tests**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_row_scope \
     --failfast && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_reservation \
     --failfast'
```

Expected: all tests pass. No ERPNext file changes occur.

---

### Task 2: Wire Retry Classification Into Production

**Files:**
- Modify: `pos_direct_print/core/retry.py:1-72`
- Reuse: `pos_direct_print/core/state_machine.py:81-88`
- Test: `pos_direct_print/core/test_suite_coverage.py:58-121`

**Interfaces:**
- Consumes: `content_risk_retry_class(content_started, content_completed=False) -> str | None`
- Produces: `evaluate_auto_retry(job_name: str) -> dict[str, bool | str | None]`
- Result always contains `allowed`, `reason`, and `retry_class`.

- [ ] **Step 1: Add failing production-path classification tests**

Add these tests to `TestSafeRetryEvaluation`:

```python
def test_uncertain_job_returns_reprint_only(self):
	job = _job(status="UNCERTAIN")
	_attempt(
		job.name,
		job.terminal,
		retry_class="AUTO_SAFE",
		content_started=1,
		outcome="UNCERTAIN",
	)

	decision = evaluate_auto_retry(job.name)
	self.assertFalse(decision["allowed"])
	self.assertEqual(decision["retry_class"], "REPRINT_ONLY")


def test_completed_content_returns_none(self):
	job = _job(status="SUCCEEDED")
	_attempt(
		job.name,
		job.terminal,
		retry_class="AUTO_SAFE",
		content_started=1,
		content_completed=1,
		outcome="SUCCEEDED",
	)

	decision = evaluate_auto_retry(job.name)
	self.assertFalse(decision["allowed"])
	self.assertEqual(decision["retry_class"], "NONE")
```

Update the existing allowed test:

```python
self.assertEqual(decision["retry_class"], "AUTO_SAFE")
```

- [ ] **Step 2: Run focused suite and verify failure**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_suite_coverage \
     --failfast'
```

Expected: failure because old decisions omit `retry_class`.

- [ ] **Step 3: Return a consistent decision shape**

Import the existing helper:

```python
from pos_direct_print.core.state_machine import check_transition, content_risk_retry_class
```

Read `content_completed` with the latest Attempt:

```python
["retry_class", "content_started", "content_completed"]
```

Apply content risk before the Job-state check:

```python
content_retry_class = (
	content_risk_retry_class(last_attempt.content_started, last_attempt.content_completed)
	if last_attempt
	else None
)
if content_retry_class:
	return {
		"allowed": False,
		"reason": "PDP_JOB_CONFLICT",
		"retry_class": content_retry_class,
	}
```

Return all denied decisions with explicit `retry_class`:

```python
return {
	"allowed": False,
	"reason": "PDP_JOB_INVALID_TRANSITION",
	"retry_class": "NONE",
}
```

When the latest Attempt exists but is not `AUTO_SAFE`, preserve only a safe canonical class:

```python
retry_class = last_attempt.retry_class if last_attempt else "NONE"
return {
	"allowed": False,
	"reason": "PDP_JOB_INVALID_TRANSITION",
	"retry_class": retry_class,
}
```

Return the allowed decision:

```python
return {"allowed": True, "reason": None, "retry_class": "AUTO_SAFE"}
```

- [ ] **Step 4: Run focused state-machine and retry tests**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_state_machine \
     --failfast && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_suite_coverage \
     --failfast'
```

Expected: all classification tests pass. `content_risk_retry_class()` now has a production caller.

---

### Task 3: Make Safe Retry Reservation Atomic

**Files:**
- Modify: `pos_direct_print/core/reservation.py:71-240`
- Modify: `pos_direct_print/core/retry.py:55-72`
- Test: `pos_direct_print/core/test_reservation.py`
- Test: `pos_direct_print/core/test_suite_coverage.py:58-121`

**Interfaces:**
- Produces: `reserve_safe_retry(job_name: str, reservation_owner: str, max_retries: int, reserved_until=None) -> Document`
- Consumes: `_guarded_update(sql, values, job_name, expected_status) -> int`
- `perform_auto_retry()` calls only `evaluate_auto_retry()` and `reserve_safe_retry()`.

- [ ] **Step 1: Add failing conflict and atomicity tests**

Add a sequential conflict test:

```python
def test_safe_retry_conflict_does_not_increment_counter(self):
	job = _job(status="FAILED_SAFE", reservation_owner="client-A")
	job.db_set("safe_retry_count", 0)
	job.db_set("status", "RESERVED")

	with self.assertRaises(frappe.ValidationError) as ctx:
		reserve_safe_retry(job.name, "client-B", max_retries=1)

	self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))
	job.reload()
	self.assertEqual(job.status, "RESERVED")
	self.assertEqual(job.safe_retry_count, 0)
```

Add a threaded test. Create one `FAILED_SAFE` Job and one latest `AUTO_SAFE` Attempt. Commit before starting workers.

```python
def test_concurrent_safe_retry_has_one_winner_and_one_increment(self):
	job = _job(status="FAILED_SAFE", reservation_owner="client-A")
	_attempt(job.name, job.terminal, retry_class="AUTO_SAFE", content_started=0, outcome="FAILED_SAFE")
	frappe.db.commit()

	outcomes = _thread_map(lambda i: perform_auto_retry(job.name, f"client-{i}").status, count=2)

	winners = [value for kind, value in outcomes if kind == "ok"]
	losers = [value for kind, value in outcomes if kind == "error"]
	self.assertEqual(winners, ["RESERVED"])
	self.assertEqual(len(losers), 1)
	self.assertIn("PDP_JOB_CONFLICT", str(losers[0]))

	status, count = frappe.db.get_value(
		"POS Print Job", job.name, ["status", "safe_retry_count"]
	)
	self.assertEqual(status, "RESERVED")
	self.assertEqual(count, 1)
```

Reuse `_thread_map()` from the same module. Do not add another concurrency helper.

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_reservation \
     --failfast'
```

Expected: failure because `reserve_safe_retry()` does not exist.

- [ ] **Step 3: Add atomic `reserve_safe_retry()`**

Place this public function after `reserve_job()`:

```python
def reserve_safe_retry(job_name, reservation_owner, max_retries, reserved_until=None):
	"""Atomically increment the safe-retry counter and reserve a FAILED_SAFE Job."""
	check_transition("FAILED_SAFE", "RESERVED")
	reserved_until = reserved_until or _default_reserved_until()
	reserved_at = now_datetime()
	passed_limit = int(max_retries or 0)

	affected = _guarded_update(
		"UPDATE `tabPOS Print Job` "
		"SET `status` = 'RESERVED', "
		"`safe_retry_count` = `safe_retry_count` + 1, "
		"`reservation_owner` = %s, `reserved_at` = %s, `reserved_until` = %s "
		"WHERE `name` = %s AND `status` = 'FAILED_SAFE' "
		"AND `safe_retry_count` < %s",
		(reservation_owner, reserved_at, reserved_until, job_name, passed_limit),
		job_name,
		"FAILED_SAFE",
	)
	if not affected:
		current = frappe.db.get_value("POS Print Job", job_name, "status")
		_throw_conflict(job_name, "FAILED_SAFE", current)

	return frappe.get_doc("POS Print Job", job_name)
```

Keep `reserve_job()` unchanged for original reservation. Do not overload it with retry counter behavior.

- [ ] **Step 4: Replace the split update in `perform_auto_retry()`**

Import:

```python
from pos_direct_print.core.reservation import reserve_safe_retry
```

Replace `get_doc()`, increment, save, and `reserve_job()` with:

```python
max_retries = frappe.get_single("POS Print Settings").max_safe_auto_retries or 0
return reserve_safe_retry(job_name, reservation_owner, max_retries)
```

Remove the unused `reserve_job` import. Keep `check_transition()` only if another function uses it. Otherwise remove it.

- [ ] **Step 5: Run focused retry and concurrency suites**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_reservation \
     --failfast && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_suite_coverage \
     --failfast'
```

Expected: one concurrent winner, one conflict, final counter `1`.

---

### Task 4: Record Remediation Authorization and Evidence

**Files:**
- Modify: `specs/pos-direct-print/tasks.md:342-382`
- Modify: `specs/pos-direct-print/progress.json:1-39`

**Interfaces:**
- Produces: a historical handoff entry that authorizes this remediation only.
- Produces: `audit_remediation` object in `progress.json`.
- Consumes: exact test counts and command results from Task 5.

- [ ] **Step 1: Add the remediation handoff to `tasks.md`**

Append this section after the existing historical handoff. Do not edit lines that describe the old A1-01 authorization.

```markdown
## Handoff Remediasi Audit — 10 Agustus 2026

User mengizinkan perubahan lintas task hanya untuk menutup temuan audit berikut:

1. Operator POS Profile applicability pada list, direct access, dan original Job creation.
2. Production retry classification untuk `UNCERTAIN` dan content risk.
3. Atomic safe-retry counter dan reservation.
4. Focused regression tests dan full Milestone A verification.
5. Pencatatan hasil remediation pada `progress.json`.

Handoff ini tidak mengizinkan pekerjaan Milestone B, C, atau D. Handoff ini tidak mengubah riwayat checkpoint A1, A2, atau A3. Agent dilarang mengubah ERPNext dan Frappe.
```

- [ ] **Step 2: Add an in-progress remediation record to `progress.json`**

Add a top-level object after `current_batch_checkpoint_pending`:

```json
"audit_remediation": {
  "authorized_at": "2026-08-10",
  "status": "in_progress",
  "scope": [
    "operator_pos_profile_applicability",
    "uncertain_retry_classification",
    "atomic_safe_retry",
    "verification_evidence"
  ],
  "verification": {},
  "external_worktree_notes": [
    "ERPNext tracked changes existed before remediation and were not modified by this work."
  ]
}
```

Keep every existing A1, A2, and A3 task status unchanged.

- [ ] **Step 3: Validate JSON and documentation diff**

Run:

```bash
python3 -m json.tool specs/pos-direct-print/progress.json >/dev/null
git diff --check -- specs/pos-direct-print/tasks.md specs/pos-direct-print/progress.json
```

Expected: both commands exit 0.

---

### Task 5: Run Full Verification and Finalize Evidence

**Files:**
- Modify: `specs/pos-direct-print/progress.json`
- Verify only: all changed production and test files
- Verify external only: app repositories `erpnext` and `frappe`

**Interfaces:**
- Consumes: all production changes from Tasks 1-3.
- Produces: final test counts and status in `audit_remediation.verification`.

- [ ] **Step 1: Run all focused Python modules**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_row_scope \
     --failfast && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_reservation \
     --failfast && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_suite_coverage \
     --failfast && \
   bench --site development.localhost run-tests \
     --app pos_direct_print \
     --module pos_direct_print.core.test_state_machine \
     --failfast'
```

Expected: every module reports `OK`.

- [ ] **Step 2: Run the complete Python suite**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests --app pos_direct_print'
```

Expected: all collected tests pass. Record the exact count. Report every warning, skip, or error.

- [ ] **Step 3: Run all JavaScript tests**

Run:

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench/apps/pos_direct_print && \
   node --test $(find pos_direct_print/public/js -name "*.test.mjs" -type f | sort)'
```

Expected: 42 tests pass, zero fail, zero skipped, unless test inventory changed for a documented reason.

- [ ] **Step 4: Run the prohibited-feature grep**

Run:

```bash
grep -RniE -C 2 \
  'imin|escpos|getPrinterStatus|iMinprinterplugin|cutPaper|printQrCode|bluetooth' \
  pos_direct_print public 2>/dev/null || true
```

Expected: no new SDK, plugin, status, cutter, QR, ESC/POS, or Bluetooth implementation. Existing schema identifiers and negative comments remain acceptable.

- [ ] **Step 5: Capture app and external repository status separately**

Run:

```bash
git status --short --untracked-files=all
git -C ../erpnext status --short --untracked-files=all
git -C ../frappe status --short --untracked-files=all
```

Expected:

- The remediation changes only files under `pos_direct_print`.
- Existing ERPNext changes remain present and untouched.
- No new Frappe source change appears.

Do not restore, stage, or edit any ERPNext or Frappe file.

- [ ] **Step 6: Write exact verification evidence**

Set `audit_remediation.status` to `completed` only when every required test passes.

Populate the record with exact values:

```json
"verification": {
  "focused_python": "passed",
  "full_python": {
    "status": "passed",
    "tests": 0,
    "skipped": 0
  },
  "javascript": {
    "status": "passed",
    "tests": 42,
    "skipped": 0
  },
  "milestone_bcd_grep": "no_real_implementation",
  "app_scope": "pos_direct_print_only",
  "erpnext_frappe_modified_by_remediation": false
}
```

Replace Python `tests: 0` with the actual full-suite count. Do not claim completion if any test fails.

- [ ] **Step 7: Validate final files**

Run:

```bash
python3 -m json.tool specs/pos-direct-print/progress.json >/dev/null
git diff --check
git diff --name-only
```

Expected: JSON valid, no whitespace error, and no ERPNext/Frappe path in the app diff.

## Plan Completion Gate

Implementation is complete only when:

- Operator POS Profile list and direct permission use the same predicate.
- Original Job creation rejects an inapplicable Operator profile.
- `evaluate_auto_retry()` returns `retry_class` on every path.
- An actual `UNCERTAIN` Job returns `REPRINT_ONLY` or `NONE` based on content completion.
- Safe retry counter and reservation update in one SQL statement.
- Concurrent safe retry has one winner and one counter increment.
- Focused and full suites pass.
- `tasks.md` records only remediation authorization.
- Existing 29 task statuses remain historically unchanged.
- No ERPNext or Frappe file is changed by remediation.
