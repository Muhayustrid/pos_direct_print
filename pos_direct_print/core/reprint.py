"""Trusted backend action for REPRINT authorization (A.31.19-A.31.21).

REPRINT never goes through standard DocType Create — every role has create=0
on POS Print Job. This action performs the full authorization chain itself,
server-side, then creates the new Job with ignore_permissions:

role check -> parent Job permission -> state/business rule -> mandatory reason
-> terminal scope -> new Job insert.
"""

import uuid

import frappe
from frappe import _

from pos_direct_print.core.security import (
	MANAGER_ROLE,
	SYSTEM_MANAGER_ROLE,
	user_scopes,
)

# Retry matrix (plan.md section 7): only states where output may already exist
# and reprint authority applies. CREATED/RESERVED/PREFLIGHT/BLOCKED/FAILED_SAFE
# resolve through retry or cancellation; PRINTING/VERIFYING are not final yet;
# CANCELLED is fail-closed ambiguous.
REPRINTABLE_STATUSES = ("UNCERTAIN", "FALLBACK_BROWSER", "SUCCEEDED")


@frappe.whitelist()
def request_reprint(parent_job, reason, terminal=None):
	user = frappe.session.user
	_check_reprint_role(user)

	reason = (reason or "").strip()
	if not reason:
		frappe.throw(
			_("PDP_PERMISSION_DENIED: reprint_reason is mandatory for every reprint."),
			exc=frappe.MandatoryError,
		)

	parent = _load_scoped_parent(parent_job, user)

	target_terminal = _resolve_scoped_terminal(terminal or parent.terminal, user, parent)

	job = frappe.get_doc(
		{
			"doctype": "POS Print Job",
			"job_id": f"JOB-{uuid.uuid4().hex}",
			"idempotency_key": f"reprint:{parent.name}:{uuid.uuid4().hex}",
			"reference_doctype": parent.reference_doctype,
			"reference_name": parent.reference_name,
			"company": parent.company,
			"pos_profile": parent.pos_profile,
			"terminal": target_terminal.name,
			"requested_by": user,
			"source": "REPRINT_UI",
			"job_type": "REPRINT",
			"parent_job": parent.name,
			"reprint_reason": reason,
			"driver_key": parent.driver_key,
			"status": "CREATED",
		}
	).insert(ignore_permissions=True)

	return {"job_id": job.name, "status": job.status, "parent_job": parent.name}


def _check_reprint_role(user):
	# Operator never gets reprint authority, not even for their own jobs (A.31.19).
	if user == "Administrator":
		return
	roles = frappe.get_roles(user)
	if MANAGER_ROLE not in roles and SYSTEM_MANAGER_ROLE not in roles:
		frappe.throw(
			_(
				"PDP_PERMISSION_DENIED: POS Print Manager or System Manager authority is required for reprint."
			),
			exc=frappe.PermissionError,
		)


def _load_scoped_parent(parent_job, user):
	parent = frappe.get_doc("POS Print Job", parent_job)

	if not frappe.has_permission("POS Print Job", "read", doc=parent, user=user):
		frappe.throw(
			_("PDP_PERMISSION_DENIED: parent Job is outside your authorized scope."),
			exc=frappe.PermissionError,
		)

	if parent.status not in REPRINTABLE_STATUSES:
		frappe.throw(
			_("PDP_JOB_CONFLICT: Job {0} in state {1} cannot be reprinted.").format(
				parent.name, parent.status
			),
			exc=frappe.ValidationError,
		)

	return parent


def _resolve_scoped_terminal(terminal, user, parent):
	target = frappe.get_doc("POS Print Terminal", terminal)

	if not target.enabled:
		frappe.throw(
			_("PDP_TERMINAL_DISABLED: terminal {0} is disabled.").format(target.name),
			exc=frappe.ValidationError,
		)

	if target.pos_profile != parent.pos_profile:
		frappe.throw(
			_("PDP_JOB_CONFLICT: terminal {0} does not belong to the parent Job POS Profile.").format(
				target.name
			),
			exc=frappe.ValidationError,
		)

	scopes = user_scopes(user)
	if not scopes["unrestricted"]:
		if scopes["companies"] and target.company not in scopes["companies"]:
			frappe.throw(
				_("PDP_PERMISSION_DENIED: terminal is outside your authorized companies."),
				exc=frappe.PermissionError,
			)
		if not scopes["profiles"] or target.pos_profile not in scopes["profiles"]:
			frappe.throw(
				_("PDP_PERMISSION_DENIED: terminal is outside your authorized POS Profile scope."),
				exc=frappe.PermissionError,
			)

	return target
