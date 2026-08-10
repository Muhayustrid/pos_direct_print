"""Print Job state machine validator (plan.md section 6, table A.16).

The transition table is the single source of truth. Every transition that is not
listed is rejected with PDP_JOB_INVALID_TRANSITION. State changes reach the
database only through `apply_transition` or through the controller guard in
POSPrintJob, and both read this same table (A-DOD-05: no direct state mutation
without state validation).
"""

import frappe
from frappe import _

ALL_STATES = (
	"CREATED",
	"RESERVED",
	"PREFLIGHT",
	"BLOCKED",
	"PRINTING",
	"VERIFYING",
	"FAILED_SAFE",
	"UNCERTAIN",
	"SUCCEEDED",
	"FALLBACK_BROWSER",
	"CANCELLED",
)

# plan.md section 6 — complete state transition table. Anything absent is invalid.
VALID_TRANSITIONS = frozenset(
	{
		("CREATED", "RESERVED"),
		("CREATED", "CANCELLED"),
		("CREATED", "FAILED_SAFE"),
		("RESERVED", "PREFLIGHT"),
		("RESERVED", "FAILED_SAFE"),
		("RESERVED", "CANCELLED"),
		("PREFLIGHT", "PRINTING"),
		("PREFLIGHT", "BLOCKED"),
		("PREFLIGHT", "FAILED_SAFE"),
		("PREFLIGHT", "FALLBACK_BROWSER"),
		("PREFLIGHT", "CANCELLED"),
		("BLOCKED", "PREFLIGHT"),
		("BLOCKED", "FALLBACK_BROWSER"),
		("BLOCKED", "CANCELLED"),
		("BLOCKED", "FAILED_SAFE"),
		("FAILED_SAFE", "RESERVED"),
		("FAILED_SAFE", "FALLBACK_BROWSER"),
		("FAILED_SAFE", "CANCELLED"),
		("PRINTING", "VERIFYING"),
		("PRINTING", "UNCERTAIN"),
		("VERIFYING", "SUCCEEDED"),
		("VERIFYING", "UNCERTAIN"),
	}
)

# plan.md section 5. UNCERTAIN is final even though output is unproven, because
# output may already exist (conservative content-risk rule).
TERMINAL_STATES = frozenset({"UNCERTAIN", "SUCCEEDED", "FALLBACK_BROWSER", "CANCELLED"})


def check_transition(from_state, to_state):
	"""Raise PDP_JOB_INVALID_TRANSITION unless the pair is in the table."""
	if (from_state, to_state) not in VALID_TRANSITIONS:
		frappe.throw(
			_("PDP_JOB_INVALID_TRANSITION: {0} -> {1} is not a valid Job state transition.").format(
				from_state, to_state
			),
			exc=frappe.ValidationError,
		)


def apply_transition(job, to_state):
	"""Validated state change. Jobs are system-managed audit records, so the
	mutation bypasses the role matrix exactly like the whitelisted actions do;
	the state machine itself is the authorization for the change."""
	check_transition(job.status, to_state)
	job.status = to_state
	job.save(ignore_permissions=True)
	return job


def content_risk_retry_class(content_started, content_completed=False):
	"""Conservative content-risk rule (A-DOD-08): once any physical content
	command may have started, the same Job can never be retried — only a new
	REPRINT Job is safe. Returns the mandated Attempt retry_class, or None when
	no output risk exists and the retry policy decides instead."""
	if not content_started:
		return None
	return "NONE" if content_completed else "REPRINT_ONLY"
