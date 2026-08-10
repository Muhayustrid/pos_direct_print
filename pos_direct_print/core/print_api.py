"""Thin Frappe RPC transport (A.12.6). No business rules live here — lifecycle
rules belong to the JobCoordinator primitives in core.reservation /
core.state_machine. Every endpoint enforces authorization server-side and
returns only sanitized projections (A-DOD-15), never raw documents.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from pos_direct_print.core import reservation as reservation_service
from pos_direct_print.core.projections import (
	job_status_projection,
	outcome_projection,
	runtime_settings_projection,
	terminal_runtime_projection,
)
from pos_direct_print.core.security import user_scopes
from pos_direct_print.core.state_machine import check_transition


@frappe.whitelist()
def get_settings():
	return runtime_settings_projection()


@frappe.whitelist()
def resolve_terminal(terminal_id):
	terminal = _scoped_terminal(terminal_id, frappe.session.user)
	if not terminal.enabled:
		frappe.throw(
			_("PDP_TERMINAL_DISABLED: terminal {0} is disabled.").format(terminal.name),
			exc=frappe.ValidationError,
		)
	return terminal_runtime_projection(terminal)


@frappe.whitelist()
def reserve_print_job(
	reference_doctype,
	reference_name,
	terminal_id,
	requested_by,
	idempotency_key,
	source="POS_AUTO",
	job_type="ORIGINAL",
	driver_key="imin_v1",
	reservation_owner=None,
):
	user = frappe.session.user
	if job_type != "ORIGINAL":
		# Reprints go through core.reprint.request_reprint; this endpoint only
		# reserves new original intent.
		frappe.throw(
			_("PDP_PERMISSION_DENIED: only ORIGINAL jobs may be reserved here."),
			exc=frappe.PermissionError,
		)
	if requested_by != user:
		frappe.throw(
			_("PDP_PERMISSION_DENIED: requested_by must be the calling user."),
			exc=frappe.PermissionError,
		)

	terminal = _scoped_terminal(terminal_id, user)
	if not terminal.enabled:
		frappe.throw(
			_("PDP_TERMINAL_DISABLED: terminal {0} is disabled.").format(terminal.name),
			exc=frappe.ValidationError,
		)

	job = reservation_service.create_original_job(
		idempotency_key=idempotency_key,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		company=terminal.company,
		pos_profile=terminal.pos_profile,
		terminal=terminal.name,
		requested_by=requested_by,
		source=source,
		driver_key=driver_key,
	)
	is_new = bool(job.flags.get("is_new_job"))
	_scoped_job(job.name, user)

	# Idempotency: a repeated call returns the already-reserved Job instead of
	# racing against its own prior reservation.
	if job.status == "RESERVED":
		return _reservation_payload(job)

	# reserve_job re-fetches the document, which drops request-scoped flags —
	# carry is_new across the re-fetch so the payload stays truthful.
	reserved = reservation_service.reserve_job(job.name, reservation_owner or requested_by)
	reserved.flags.is_new_job = is_new
	return _reservation_payload(reserved)


@frappe.whitelist()
def start_attempt(job_id, reservation_token, terminal_id=None):
	user = frappe.session.user
	_scoped_job(job_id, user)

	terminal = _scoped_terminal(terminal_id, user) if terminal_id else None
	job = frappe.get_doc("POS Print Job", job_id)
	terminal_name = terminal.name if terminal else job.terminal
	driver_key = terminal.driver_key if terminal else job.driver_key

	updated_job, attempt = reservation_service.start_attempt(
		job_id, terminal_name, driver_key, reservation_owner=reservation_token
	)
	job.db_set("attempt_count", (updated_job.attempt_count or 0) + 1)

	return {
		"job": job_status_projection(updated_job),
		"attempt": {
			"attempt_id": attempt.attempt_id,
			"attempt_no": attempt.attempt_no,
			"outcome": attempt.outcome,
			"phase_reached": attempt.phase_reached,
		},
	}


@frappe.whitelist()
def transition_job(job_id, expected_from_state, target_state, reservation_token=None):
	user = frappe.session.user
	_scoped_job(job_id, user)
	check_transition(expected_from_state, target_state)

	conditions = ["`name` = %s", "`status` = %s"]
	values = [job_id, expected_from_state]
	if reservation_token:
		conditions.append("`reservation_owner` = %s")
		values.append(reservation_token)

	affected = frappe.db.execute_query(
		"UPDATE `tabPOS Print Job` SET `status` = %s WHERE {conditions}".format(
			conditions=" AND ".join(conditions)
		),
		[target_state, *values],
	)
	if not affected:
		current = frappe.db.get_value("POS Print Job", job_id, "status")
		frappe.throw(
			_("PDP_JOB_CONFLICT: Job {0} expected {1} but is {2}.").format(
				job_id, expected_from_state, current
			),
			exc=frappe.ValidationError,
		)

	return job_status_projection(frappe.get_doc("POS Print Job", job_id))


@frappe.whitelist()
def complete_attempt(
	attempt_id,
	outcome,
	content_started=0,
	content_completed=0,
	error_code=None,
	error_detail=None,
):
	user = frappe.session.user
	attempt = frappe.get_doc("POS Print Attempt", attempt_id)
	_scoped_job(attempt.job, user)

	attempt.db_set(
		{
			"outcome": outcome,
			"content_started": int(bool(content_started)),
			"content_completed": int(bool(content_completed)),
			"error_code": error_code,
			"error_detail": error_detail,
			"finished_at": now_datetime(),
		}
	)

	job = frappe.get_doc("POS Print Job", attempt.job)
	if content_started:
		job.db_set("content_may_have_printed", 1)

	return outcome_projection(job)


@frappe.whitelist()
def release_reservation(job_id, reservation_token, expected_from_state="CREATED"):
	user = frappe.session.user
	_scoped_job(job_id, user)
	released = reservation_service.release_reservation(
		job_id, expected_from_state=expected_from_state, reservation_owner=reservation_token
	)
	return job_status_projection(released)


@frappe.whitelist()
def retrieve_job(job_id):
	job = _scoped_job(job_id, frappe.session.user)
	return job_status_projection(job)


def _scoped_terminal(terminal_id, user):
	"""Row-scope terminal check for RPC callers. The Terminal DocType read
	matrix has no Operator row (A.31), so the matrix check cannot serve
	operator-driven reservation; scope rules apply instead: company
	intersection, plus POS Profile scope for Managers, fail-closed otherwise."""
	if not terminal_id:
		frappe.throw(
			_("PDP_TERMINAL_NOT_FOUND: no terminal provided."),
			exc=frappe.ValidationError,
		)
	if not frappe.db.exists("POS Print Terminal", terminal_id):
		frappe.throw(
			_("PDP_TERMINAL_NOT_FOUND: terminal {0} does not exist.").format(terminal_id),
			exc=frappe.ValidationError,
		)
	terminal = frappe.get_doc("POS Print Terminal", terminal_id)

	scopes = user_scopes(user)
	if scopes["unrestricted"]:
		return terminal
	if scopes["companies"] and terminal.company not in scopes["companies"]:
		frappe.throw(
			_("PDP_PERMISSION_DENIED: terminal is outside your authorized companies."),
			exc=frappe.PermissionError,
		)
	if scopes["manager"]:
		if not scopes["profiles"] or terminal.pos_profile not in scopes["profiles"]:
			frappe.throw(
				_("PDP_PERMISSION_DENIED: terminal is outside your authorized POS Profile scope."),
				exc=frappe.PermissionError,
			)
		return terminal
	if scopes["operator"]:
		return terminal

	# No print role at all — fail closed.
	frappe.throw(
		_("PDP_PERMISSION_DENIED: no print role grants terminal access."),
		exc=frappe.PermissionError,
	)


def _scoped_job(job_id, user):
	if not frappe.db.exists("POS Print Job", job_id):
		frappe.throw(
			_("PDP_JOB_NOT_FOUND: Job {0} does not exist.").format(job_id),
			exc=frappe.ValidationError,
		)
	job = frappe.get_doc("POS Print Job", job_id)
	if not frappe.has_permission("POS Print Job", "read", doc=job, user=user):
		frappe.throw(
			_("PDP_PERMISSION_DENIED: Job is outside your authorized scope."),
			exc=frappe.PermissionError,
		)
	return job


def _reservation_payload(job):
	return {
		"job_id": job.name,
		"reservation_token": job.reservation_owner,
		"reserved_until": job.reserved_until,
		"status": job.status,
		"is_new_job": bool(job.flags.get("is_new_job")),
	}
