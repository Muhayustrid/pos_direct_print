"""Atomic reservation and attempt numbering (A-DOD-06, A-DOD-07).

Concurrency guarantees come from the database, never from application-level
locks:

- Idempotent original Job creation: `idempotency_key` is UNIQUE; a racing
  duplicate insert is caught and answered with the existing Job.
- Reservation: one guarded UPDATE keyed on the expected current state
  (`expected_from_state`). The losing racer sees zero affected rows and gets
  PDP_JOB_CONFLICT instead of a second reservation.
- Attempt numbering: `attempt_no = max(attempt_no) + 1` plus the
  IDX_ATT_UNIQUE_01 unique constraint on (job, attempt_no). A losing racer
  retries with the next free number; the database is the final arbiter.

Transaction boundaries belong to the caller: every operation ends with the
caller's own commit/rollback decision.
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

from pos_direct_print.core.security import operator_pos_profile_is_applicable
from pos_direct_print.core.state_machine import check_transition

# Only states from which a reservation cycle may start (plan.md transition table).
RESERVABLE_FROM_STATES = ("CREATED", "FAILED_SAFE")


def assert_operator_pos_profile_applicable(user, pos_profile, company):
	roles = frappe.get_roles(user)
	if user == "Administrator" or "POS Print Operator" not in roles:
		return
	if operator_pos_profile_is_applicable(user, pos_profile, company):
		return
	frappe.throw(
		_("PDP_PERMISSION_DENIED: POS Profile is not available for this Operator."),
		exc=frappe.PermissionError,
	)


def create_original_job(
	idempotency_key,
	reference_doctype,
	reference_name,
	company,
	pos_profile,
	terminal,
	requested_by,
	source="POS_AUTO",
	driver_key="imin_v1",
):
	"""Idempotent ORIGINAL Job creation. Duplicate idempotency key answers with
	the existing Job instead of failing (A-DOD-06). Insert-first + catch is used
	instead of check-then-insert: a preceding existence check reads a stale
	REPEATABLE READ snapshot under racing connections."""
	assert_operator_pos_profile_applicable(requested_by, pos_profile, company)
	try:
		job = frappe.get_doc(
			{
				"doctype": "POS Print Job",
				"job_id": f"JOB-{frappe.generate_hash(length=24)}",
				"idempotency_key": idempotency_key,
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"company": company,
				"pos_profile": pos_profile,
				"terminal": terminal,
				"requested_by": requested_by,
				"source": source,
				"driver_key": driver_key,
			}
		).insert(ignore_permissions=True)
		job.flags.is_new_job = True
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		existing = frappe.db.get_value("POS Print Job", {"idempotency_key": idempotency_key}, "name")
		if not existing:
			raise
		job = frappe.get_doc("POS Print Job", existing)
		job.flags.is_new_job = False

	return job


def reserve_job(job_name, reservation_owner, expected_from_state="CREATED", reserved_until=None):
	"""Atomic reservation with optimistic state expectation.

	Returns the reserved Job. Raises PDP_JOB_CONFLICT when the stored state no
	longer matches `expected_from_state` or when a concurrent racer won the
	guarded UPDATE.
	"""
	if expected_from_state not in RESERVABLE_FROM_STATES:
		frappe.throw(
			_("PDP_JOB_INVALID_TRANSITION: reservation cannot start from {0}.").format(expected_from_state),
			exc=frappe.ValidationError,
		)

	job = frappe.get_doc("POS Print Job", job_name)
	if job.status != expected_from_state:
		_throw_conflict(job.name, expected_from_state, job.status)

	reserved_until = reserved_until or _default_reserved_until()
	affected = _guarded_update(
		"UPDATE `tabPOS Print Job`"
		" SET `status` = 'RESERVED', `reservation_owner` = %s, `reserved_at` = %s, `reserved_until` = %s"
		" WHERE `name` = %s AND `status` = %s",
		(reservation_owner, now_datetime(), reserved_until, job_name, expected_from_state),
		job_name,
		expected_from_state,
	)
	if not affected:
		current = frappe.db.get_value("POS Print Job", job.name, "status")
		_throw_conflict(job.name, expected_from_state, current)

	return frappe.get_doc("POS Print Job", job.name)


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


def release_reservation(job_name, expected_from_state, reservation_owner=None):
	"""Release an unfulfilled reservation through a valid transition.

	Original reservation (expected_from_state CREATED) releases to CANCELLED;
	a safe-retry reservation (expected_from_state FAILED_SAFE) returns to
	FAILED_SAFE. A mismatched expectation or lost guarded UPDATE raises
	PDP_JOB_CONFLICT.
	"""
	if expected_from_state == "CREATED":
		to_state = "CANCELLED"
	elif expected_from_state == "FAILED_SAFE":
		to_state = "FAILED_SAFE"
	else:
		frappe.throw(
			_("PDP_JOB_INVALID_TRANSITION: reservation cannot be released from {0}.").format(
				expected_from_state
			),
			exc=frappe.ValidationError,
		)

	check_transition("RESERVED", to_state)

	conditions = "`status` = 'RESERVED'"
	if reservation_owner:
		conditions += f" AND `reservation_owner` = {frappe.db.escape(reservation_owner)}"

	affected = _guarded_update(
		"UPDATE `tabPOS Print Job` SET `status` = %s WHERE `name` = %s AND {conditions}".format(
			conditions=conditions
		),
		(to_state, job_name),
		job_name,
		"RESERVED",
	)
	if not affected:
		current = frappe.db.get_value("POS Print Job", job_name, "status")
		_throw_conflict(job_name, "RESERVED", current)

	return frappe.get_doc("POS Print Job", job_name)


def start_attempt(job_name, terminal, driver_key, reservation_owner=None):
	"""Atomic attempt start: RESERVED -> PREFLIGHT guarded UPDATE plus a new
	Attempt with the next monotonic attempt_no (A-DOD-07)."""
	check_transition("RESERVED", "PREFLIGHT")

	conditions = "`status` = 'RESERVED'"
	if reservation_owner:
		conditions += f" AND `reservation_owner` = {frappe.db.escape(reservation_owner)}"

	affected = _guarded_update(
		"UPDATE `tabPOS Print Job` SET `status` = 'PREFLIGHT' WHERE `name` = %s AND {conditions}".format(
			conditions=conditions
		),
		(job_name,),
		job_name,
		"RESERVED",
	)
	if not affected:
		current = frappe.db.get_value("POS Print Job", job_name, "status")
		_throw_conflict(job_name, "RESERVED", current)

	attempt = _insert_next_attempt(job_name, terminal, driver_key)
	return frappe.get_doc("POS Print Job", job_name), attempt


def _insert_next_attempt(job_name, terminal, driver_key):
	# max(attempt_no) + 1 guarded by IDX_ATT_UNIQUE_01; on conflict, retry with
	# the next free number. The unique constraint is the final arbiter.
	for _retry in range(3):
		next_no = (
			frappe.db.sql(
				"SELECT COALESCE(MAX(`attempt_no`), 0) FROM `tabPOS Print Attempt` WHERE `job` = %s",
				job_name,
			)[0][0]
			+ 1
		)
		attempt = frappe.get_doc(
			{
				"doctype": "POS Print Attempt",
				"attempt_id": f"ATT-{frappe.generate_hash(length=24)}",
				"job": job_name,
				"attempt_no": next_no,
				"terminal": terminal,
				"driver_key": driver_key,
				"started_at": now_datetime(),
			}
		)
		try:
			return attempt.insert(ignore_permissions=True)
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			continue

	frappe.throw(
		_("PDP_JOB_CONFLICT: unable to allocate a unique attempt number for Job {0}.").format(job_name),
		exc=frappe.ValidationError,
	)


def _guarded_update(sql, values, job_name, expected_status):
	"""Execute a guarded UPDATE and return the affected-row count.

	`frappe.db.sql` fetches the result set, which is always empty for an UPDATE,
	so it cannot report rowcount; `execute_query` exposes the cursor return
	value, which is the affected-row count for UPDATE statements.

	MariaDB 11.8 raises error 1020 ("Record has changed since last read") when
	this transaction read the row and another transaction committed a change to
	it afterwards. That is exactly the losing-race outcome, so it is mapped to
	PDP_JOB_CONFLICT instead of leaking a driver error.
	"""
	# execute_query touches the cursor directly and does not run the lazy
	# connection path, so warm the connection first.
	frappe.db.sql("SELECT 1")
	try:
		return frappe.db.execute_query(sql, values)
	except Exception as exc:
		if not (getattr(exc, "args", None) and exc.args and exc.args[0] == 1020):
			raise
		# Restart the transaction so the conflict message reads fresh state.
		frappe.db.rollback()
		current = frappe.db.get_value("POS Print Job", job_name, "status")
		_throw_conflict(job_name, expected_status, current)


def _default_reserved_until():
	ttl_seconds = frappe.db.get_single_value("POS Print Settings", "reservation_ttl_seconds") or 120
	return add_to_date(now_datetime(), seconds=ttl_seconds)


def _throw_conflict(job_name, expected_status, actual_status):
	frappe.throw(
		_(
			"PDP_JOB_CONFLICT: Job {0} was expected in state {1} but is currently in state {2}. Another request won the race."
		).format(job_name, expected_status, actual_status),
		exc=frappe.ValidationError,
	)
