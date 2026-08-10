"""Safe-retry evaluation (plan.md section 7 retry matrix, A-DOD-07/A-DOD-08).

Evaluation only — no scheduler, queue, or delay timing (those belong to later
milestones). The rules encoded here are the Milestone A contract:

- Only FAILED_SAFE Jobs may auto-retry, and only when the last Attempt carries
  `retry_class = AUTO_SAFE`.
- Conservative content-risk rule: if the last Attempt has `content_started = 1`,
  the same Job can never be retried — a new REPRINT Job is the only safe path.
- The retry limit comes from POS Print Settings `max_safe_auto_retries`.

Executing an allowed retry re-reserves the Job through the same guarded
transition used by the original reservation, so concurrent evaluators cannot
both win.
"""

import frappe
from frappe import _

from pos_direct_print.core.reservation import reserve_safe_retry
from pos_direct_print.core.state_machine import content_risk_retry_class


def evaluate_auto_retry(job_name):
	"""Decide whether an automatic safe retry is allowed. Never mutates state.

	The decision always carries `retry_class` so callers can apply the
	mandated classification (A-DOD-07/A-DOD-08) even when retry is denied.
	"""
	job = frappe.get_doc("POS Print Job", job_name)

	last_attempt = frappe.db.get_value(
		"POS Print Attempt",
		{"job": job.name},
		["retry_class", "content_started", "content_completed"],
		order_by="attempt_no desc",
		as_dict=True,
	)
	content_retry_class = (
		content_risk_retry_class(last_attempt.content_started, last_attempt.content_completed)
		if last_attempt
		else None
	)
	if content_retry_class:
		# Conservative content-risk rule overrides every other check: output may
		# already exist, so only a new REPRINT Job can continue (A-DOD-08).
		return {
			"allowed": False,
			"reason": "PDP_JOB_CONFLICT",
			"retry_class": content_retry_class,
		}

	if job.status != "FAILED_SAFE":
		return {
			"allowed": False,
			"reason": "PDP_JOB_INVALID_TRANSITION",
			"retry_class": "NONE",
		}

	if not last_attempt or last_attempt.retry_class != "AUTO_SAFE":
		retry_class = last_attempt.retry_class if last_attempt else "NONE"
		return {
			"allowed": False,
			"reason": "PDP_JOB_INVALID_TRANSITION",
			"retry_class": retry_class,
		}

	# get_single_value reads tabSingles only and ignores field defaults before
	# the Single is ever saved; load the document so the schema default applies.
	max_retries = frappe.get_single("POS Print Settings").max_safe_auto_retries or 0
	if job.safe_retry_count >= max_retries:
		return {
			"allowed": False,
			"reason": "PDP_JOB_CONFLICT",
			"retry_class": "NONE",
		}

	return {"allowed": True, "reason": None, "retry_class": "AUTO_SAFE"}


def perform_auto_retry(job_name, reservation_owner):
	"""Evaluate and, when allowed, execute one safe-retry cycle: increment the
	retry counter and re-reserve via the guarded FAILED_SAFE -> RESERVED
	transition. Raises PDP_* errors when denied."""
	decision = evaluate_auto_retry(job_name)
	if not decision["allowed"]:
		frappe.throw(
			_("{0}: automatic safe retry is denied for Job {1}.").format(decision["reason"], job_name),
			exc=frappe.ValidationError,
		)

	max_retries = frappe.get_single("POS Print Settings").max_safe_auto_retries or 0
	return reserve_safe_retry(job_name, reservation_owner, max_retries)
