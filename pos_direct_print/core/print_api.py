"""Thin Frappe RPC transport (A.12.6). No business rules live here — lifecycle
rules belong to the JobCoordinator primitives in core.reservation /
core.state_machine. Every endpoint enforces authorization server-side and
returns only sanitized projections (A-DOD-15), never raw documents.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from pos_direct_print.core import reprint as reprint_service
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
def disable_terminals(terminal_ids):
	"""Retire selected terminals without deleting audit references."""
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(
			_("PDP_PERMISSION_DENIED: System Manager role is required."),
			exc=frappe.PermissionError,
		)
	terminal_ids = frappe.parse_json(terminal_ids)
	if not isinstance(terminal_ids, list) or not terminal_ids:
		frappe.throw(
			_("PDP_CONFIG_INVALID: select at least one terminal."),
			exc=frappe.ValidationError,
		)
	for terminal_id in terminal_ids:
		if not frappe.db.exists("POS Print Terminal", terminal_id):
			frappe.throw(
				_("PDP_TERMINAL_NOT_FOUND: terminal {0} does not exist.").format(terminal_id),
				exc=frappe.ValidationError,
			)
	for terminal_id in terminal_ids:
		frappe.db.set_value("POS Print Terminal", terminal_id, "enabled", 0)
	return {"disabled": len(terminal_ids)}


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
	filters = {
		"company": company,
		"pos_profile": pos_profile,
		"enabled": 1,
		"qualification_status": "QUALIFIED",
	}
	name = frappe.db.get_value("POS Print Terminal", filters, "name", order_by="creation asc")
	if not name:
		enabled = frappe.db.get_value(
			"POS Print Terminal",
			{"company": company, "pos_profile": pos_profile, "enabled": 1},
			"name",
		)
		if enabled:
			frappe.throw(
				_("PDP_TERMINAL_NOT_QUALIFIED: no qualified terminal for {0} / {1}.").format(
					company, pos_profile
				),
				exc=frappe.ValidationError,
			)
		frappe.throw(
			_("PDP_TERMINAL_NOT_FOUND: no enabled terminal for {0} / {1}.").format(company, pos_profile),
			exc=frappe.ValidationError,
		)
	terminal = frappe.get_doc("POS Print Terminal", name)
	return {
		"terminal_id": terminal.terminal_id,
		"transport": terminal.transport,
		"driver_key": terminal.driver_key,
		"paper_width_mm": terminal.paper_width_mm,
		"qualification_status": terminal.qualification_status,
	}


@frappe.whitelist()
def invoice_print_state(reference_doctype, reference_name):
	"""Has this invoice already reached paper? Read-only, row-scoped.

	The POS button row needs this before the cashier clicks anything: an invoice
	reopened from Recent Orders must offer Reprint straight away, because a
	repeated ORIGINAL print is refused by idempotency and would only earn a
	conflict.

	Scope comes from the standard Job query conditions, so a Job outside your
	scope reads as not printed — there is no reprint you could perform on it
	anyway. Returns a bare flag: no Job id, no terminal, nothing to correlate.
	"""
	jobs = _reprintable_jobs(reference_doctype, reference_name)
	return {"printed": bool(jobs) and _reprint_terminal_still_matches(jobs[0])}


@frappe.whitelist()
def reprint_invoice(reference_doctype, reference_name, reason, terminal_id=None):
	"""Authorize a REPRINT for an invoice and hand back a live reservation.

	The POS client knows an invoice, not a Job id, so this endpoint owns the
	whole authorized entry: find the latest reprintable Job for that invoice
	(row-scoped), run the full REPRINT authorization chain in core.reprint, then
	start a reservation cycle with a server-minted owner. The client never names
	the parent Job and never learns a reservation owner outside the returned
	token.

	Returns the same reservation payload shape as reserve_print_job, plus the
	terminal and driver the reprint must use, so the client drives the identical
	attempt cycle.
	"""
	user = frappe.session.user
	parent = _latest_reprintable_job(reference_doctype, reference_name, user)
	created = reprint_service.request_reprint(parent.name, reason, terminal_id or parent.terminal)

	owner = f"REPRINT-{frappe.generate_hash(length=24)}"
	reserved = reservation_service.reserve_job(created["job_id"], owner)
	payload = _reservation_payload(reserved)
	payload["driver_key"] = reserved.driver_key
	payload["terminal_id"] = frappe.db.get_value("POS Print Terminal", reserved.terminal, "terminal_id")
	payload["parent_job_id"] = parent.name
	return payload


def _latest_reprintable_job(reference_doctype, reference_name, user):
	"""Newest Job for an invoice whose state permits a reprint, row-scoped.

	Scope comes from the same document permission check the rest of the
	transport uses, so a Manager outside the Job's Company/POS Profile is
	refused here rather than inside the reprint chain.
	"""
	names = _reprintable_jobs(reference_doctype, reference_name, scoped=False)
	if not names:
		frappe.throw(
			_("PDP_JOB_NOT_FOUND: no reprintable print job for {0} {1}.").format(
				reference_doctype, reference_name
			),
			exc=frappe.ValidationError,
		)
	return _scoped_job(names[0].name, user)


def _reprintable_jobs(reference_doctype, reference_name, scoped=True):
	"""Newest-first reprintable Jobs for an invoice, with the fields the button
	row needs to tell whether a reprint could actually run.

	`scoped` runs the query through frappe.get_list so the standard permission
	query conditions apply and out-of-scope rows drop out silently — note that
	frappe.get_all always ignores permissions, so the distinction is the call,
	not a flag. Pass False when the caller must instead refuse an out-of-scope
	Job out loud through _scoped_job.
	"""
	query = frappe.get_list if scoped else frappe.get_all
	return query(
		"POS Print Job",
		filters={
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
			"status": ("in", reprint_service.REPRINTABLE_STATUSES),
		},
		fields=["name", "terminal", "pos_profile"],
		order_by="creation desc",
		limit=1,
	)


def _reprint_terminal_still_matches(job):
	"""Would a reprint of this Job survive the terminal guard in core.reprint?

	A terminal can be reassigned to another POS Profile after a receipt printed.
	The reprint chain then refuses the Job, because reprinting an outlet's
	receipt on a terminal now serving a different outlet crosses that boundary.
	Report such a Job as not printed so the row keeps Print Receipt instead of
	offering a button whose only outcome is PDP_JOB_CONFLICT.
	"""
	terminal = frappe.db.get_value(
		"POS Print Terminal", job.terminal, ["pos_profile", "enabled"], as_dict=True
	)
	return bool(terminal and terminal.enabled and terminal.pos_profile == job.pos_profile)


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
