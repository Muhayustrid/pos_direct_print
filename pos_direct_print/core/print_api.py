"""Thin Frappe RPC transport (A.12.6). No business rules live here — lifecycle
rules belong to the JobCoordinator primitives in core.reservation /
core.state_machine. Every endpoint enforces authorization server-side and
returns only sanitized projections (A-DOD-15), never raw documents.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from pos_direct_print.core import reservation as reservation_service
from pos_direct_print.core.projections import (
	job_status_projection,
	outcome_projection,
	runtime_settings_projection,
	terminal_runtime_projection,
)
from pos_direct_print.core.receipt_hash import hash_receipt
from pos_direct_print.core.retry import evaluate_auto_retry
from pos_direct_print.core.security import operator_pos_profile_is_applicable, user_scopes
from pos_direct_print.core.state_machine import check_transition, content_risk_retry_class


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
def resolve_terminal_for_profile(company, pos_profile):
	"""Row-scoped read-only lookup: the enabled, QUALIFIED terminal for a
	Company + POS Profile. Returns the NEW terminal transport projection only.
	Mirrors _scoped_terminal authorization; fail-closed."""
	user = frappe.session.user
	scopes = user_scopes(user)
	if not scopes["unrestricted"]:
		if scopes["companies"] and company not in scopes["companies"]:
			frappe.throw(
				_("PDP_PERMISSION_DENIED: company is outside your authorized scope."),
				exc=frappe.PermissionError,
			)
		manager_allowed = scopes["manager"] and pos_profile in scopes["profiles"]
		operator_allowed = scopes["operator"] and operator_pos_profile_is_applicable(
			user, pos_profile, company
		)
		if not (manager_allowed or operator_allowed):
			frappe.throw(
				_("PDP_PERMISSION_DENIED: POS Profile is outside your authorized scope."),
				exc=frappe.PermissionError,
			)
	name = frappe.db.get_value(
		"POS Print Terminal",
		{"company": company, "pos_profile": pos_profile, "enabled": 1},
		"name",
		order_by="creation asc",
	)
	if not name:
		frappe.throw(
			_("PDP_TERMINAL_NOT_FOUND: no enabled terminal for {0} / {1}.").format(company, pos_profile),
			exc=frappe.ValidationError,
		)
	terminal = frappe.get_doc("POS Print Terminal", name)
	if terminal.qualification_status != "QUALIFIED":
		frappe.throw(
			_("PDP_TERMINAL_NOT_QUALIFIED: terminal {0} is not qualified.").format(name),
			exc=frappe.ValidationError,
		)
	return {
		"terminal_id": terminal.terminal_id,
		"transport": terminal.transport,
		"driver_key": terminal.driver_key,
		"paper_width_mm": terminal.paper_width_mm,
		"qualification_status": terminal.qualification_status,
	}


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
def re_reserve_job(job_id, initiator):
	"""Server-side safe-retry re-reservation (B-AC-01 retry cycle).

	A FAILED_SAFE Job keeps the reservation owner from its first cycle, and
	that owner is never visible through projections (A.31.9 Level 1), so a
	retry cannot present the original owner to a guarded transition. This
	endpoint runs the retry decision and then starts a NEW reservation cycle
	atomically: FAILED_SAFE -> RESERVED with a fresh server-minted owner
	distinct from the retry initiator. The initiator is audit metadata only
	and is never minted as a reservation token.

	Returns the same reservation payload shape as reserve_print_job, so the
	client treats the retry exactly like a fresh reservation. The new owner
	never leaves the server except inside the returned reservation_token.
	"""
	user = frappe.session.user
	job = _scoped_job(job_id, user)
	decision = evaluate_auto_retry(job.name)
	if not decision["allowed"]:
		frappe.throw(
			_("{0}: safe retry is denied for Job {1}.").format(decision["reason"], job.name),
			exc=frappe.ValidationError,
		)
	max_retries = frappe.get_single("POS Print Settings").max_safe_auto_retries or 0
	owner = f"RETRY-{frappe.generate_hash(length=24)}"
	reserved = reservation_service.reserve_safe_retry(job.name, owner, max_retries)
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
def bind_receipt_snapshot(job_id, reservation_token, receipt_snapshot, receipt_hash):
	"""B-AC-01. Order: scope -> parse JSON -> schema v1 -> server-side hash
	recompute + equality -> guarded atomic bind. Returns job_status_projection
	only (snapshot/hash never leave through any projection — A.31.9 Level 1)."""
	user = frappe.session.user
	_scoped_job(job_id, user)
	try:
		document = json.loads(receipt_snapshot)
	except (TypeError, ValueError):
		frappe.throw(
			_("PDP_RECEIPT_INVALID: receipt snapshot is not valid JSON."),
			exc=frappe.ValidationError,
		)
	if not isinstance(document, dict) or document.get("schema_version") != 1:
		frappe.throw(
			_("PDP_RECEIPT_INVALID: receipt snapshot must be schema version 1."),
			exc=frappe.ValidationError,
		)
	try:
		computed_hash = hash_receipt(document)
	except (TypeError, UnicodeEncodeError):
		frappe.throw(
			_("PDP_RECEIPT_INVALID: receipt snapshot contains unsupported values."),
			exc=frappe.ValidationError,
		)
	if computed_hash != receipt_hash:
		frappe.throw(
			_("PDP_RECEIPT_INVALID: receipt hash does not match the snapshot."),
			exc=frappe.ValidationError,
		)
	bound = reservation_service.bind_receipt_snapshot(
		job_id, reservation_token, receipt_snapshot, receipt_hash
	)
	return job_status_projection(bound)


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

	content_started = int(bool(cint(content_started)))
	content_completed = int(bool(cint(content_completed)))
	attempt.db_set(
		{
			"outcome": outcome,
			"content_started": content_started,
			"content_completed": content_completed,
			"retry_class": _attempt_retry_class(error_code, content_started, content_completed),
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
def fallback_to_browser(job_id, approved):
	"""Approve browser handoff without exposing the reservation owner."""
	if not cint(approved):
		frappe.throw(
			_("PDP_PERMISSION_DENIED: explicit browser fallback approval is required."),
			exc=frappe.PermissionError,
		)
	job = _scoped_job(job_id, frappe.session.user)
	if job.content_may_have_printed:
		frappe.throw(
			_("PDP_JOB_CONFLICT: physical content may already have printed."),
			exc=frappe.ValidationError,
		)
	return job_status_projection(_transition_action(job, "FALLBACK_BROWSER"))


@frappe.whitelist()
def cancel_job(job_id, reason=None):
	"""Cancel a scoped Job through a server-owned guarded transition."""
	job = _scoped_job(job_id, frappe.session.user)
	return job_status_projection(_transition_action(job, "CANCELLED"))


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


def _attempt_retry_class(error_code, content_started, content_completed):
	content_class = content_risk_retry_class(content_started, content_completed)
	if content_class:
		return content_class
	if error_code and error_code.startswith(
		("PDP_TERMINAL_", "PDP_DRIVER_", "PDP_BRIDGE_", "PDP_PRINTER_", "PDP_PRINT_")
	):
		return "AUTO_SAFE"
	if error_code == "PDP_SERVER_UNAVAILABLE":
		return "AUTO_SAFE"
	return "NONE"


def _transition_action(job, target_state):
	check_transition(job.status, target_state)
	affected = frappe.db.execute_query(
		"UPDATE `tabPOS Print Job` SET `status` = %s WHERE `name` = %s AND `status` = %s",
		[target_state, job.name, job.status],
	)
	if not affected:
		current = frappe.db.get_value("POS Print Job", job.name, "status")
		frappe.throw(
			_("PDP_JOB_CONFLICT: Job {0} expected {1} but is {2}.").format(job.name, job.status, current),
			exc=frappe.ValidationError,
		)
	return frappe.get_doc("POS Print Job", job.name)


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
	manager_allowed = scopes["manager"] and terminal.pos_profile in scopes["profiles"]
	operator_allowed = scopes["operator"] and operator_pos_profile_is_applicable(
		user, terminal.pos_profile, terminal.company
	)
	if manager_allowed or operator_allowed:
		return terminal

	frappe.throw(
		_("PDP_PERMISSION_DENIED: terminal is outside your authorized POS Profile scope."),
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
