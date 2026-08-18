import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.core.state_machine import (
	ALL_STATES,
	TERMINAL_STATES,
	VALID_TRANSITIONS,
	apply_transition,
	check_transition,
	content_risk_retry_class,
)
from pos_direct_print.tests.fixtures import test_company, test_outlet_a


class TestValidTransitions(IntegrationTestCase):
	"""A-AT-07 — every transition marked valid in table A.16 is accepted."""

	def test_all_22_table_transitions_accepted(self):
		self.assertEqual(len(VALID_TRANSITIONS), 22)
		for from_state, to_state in sorted(VALID_TRANSITIONS):
			job = _job(status=from_state, reservation_owner="client-x")
			apply_transition(job, to_state)
			self.assertEqual(
				frappe.db.get_value("POS Print Job", job.name, "status"),
				to_state,
				f"{from_state} -> {to_state} rejected",
			)

	def test_terminal_states_have_no_outgoing_transitions(self):
		for state in TERMINAL_STATES:
			self.assertNotIn(state, {pair[0] for pair in VALID_TRANSITIONS})

	def test_full_happy_path_walk(self):
		job = _job(status="CREATED")
		for next_state in ("RESERVED", "PREFLIGHT", "PRINTING", "VERIFYING", "SUCCEEDED"):
			if next_state == "RESERVED":
				job.reservation_owner = "client-x"
			apply_transition(job, next_state)
		self.assertEqual(frappe.db.get_value("POS Print Job", job.name, "status"), "SUCCEEDED")


class TestInvalidTransitions(IntegrationTestCase):
	"""A-AT-08 + A-DOD-05 — transitions outside the table are rejected with
	PDP_JOB_INVALID_TRANSITION and the stored state never changes."""

	def test_uncertain_to_preflight_rejected(self):
		job = _job(status="UNCERTAIN", reservation_owner="client-x")

		with self.assertRaises(frappe.ValidationError) as ctx:
			apply_transition(job, "PREFLIGHT")
		self.assertIn("PDP_JOB_INVALID_TRANSITION", str(ctx.exception))

		self.assertEqual(frappe.db.get_value("POS Print Job", job.name, "status"), "UNCERTAIN")

	def test_every_unlisted_pair_rejected(self):
		unlisted = {
			(from_state, to_state)
			for from_state in ALL_STATES
			for to_state in ALL_STATES
			if (from_state, to_state) not in VALID_TRANSITIONS
		}
		# 11x11 grid minus the 22 valid rows.
		self.assertEqual(len(unlisted), 121 - 22)
		for from_state, to_state in sorted(unlisted):
			with self.assertRaises(frappe.ValidationError, msg=f"{from_state} -> {to_state} accepted"):
				check_transition(from_state, to_state)

	def test_direct_status_mutation_blocked(self):
		# A-DOD-05: no direct state mutation — even via save(), even by System Manager.
		job = _job(status="UNCERTAIN", reservation_owner="client-x")

		with _user("Administrator"):
			doc = frappe.get_doc("POS Print Job", job.name)
			doc.status = "PREFLIGHT"
			with self.assertRaises(frappe.ValidationError) as ctx:
				doc.save(ignore_permissions=True)
		self.assertIn("PDP_JOB_INVALID_TRANSITION", str(ctx.exception))
		self.assertEqual(frappe.db.get_value("POS Print Job", job.name, "status"), "UNCERTAIN")


class TestUncertainSafetyRule(IntegrationTestCase):
	"""A-AT-12 + A-DOD-08 — once content may have started and completion is
	unproven, the Job is REPRINT_ONLY: no auto retry, no same-job retry, no
	re-entry into PREFLIGHT/PRINTING."""

	def test_content_started_attempt_ends_job_uncertain_with_no_retry(self):
		job = _job(status="PRINTING", reservation_owner="client-x")
		attempt = _attempt(job.name, job.terminal, content_started=1, outcome="UNCERTAIN")

		self.assertEqual(content_risk_retry_class(attempt.content_started), "REPRINT_ONLY")

		apply_transition(job, "UNCERTAIN")
		self.assertEqual(job.status, "UNCERTAIN")

		# Manual same-job retry and auto retry both need a transition back into
		# the retry cycle; UNCERTAIN has none.
		for reentry in ("PREFLIGHT", "PRINTING", "RESERVED", "FAILED_SAFE", "BLOCKED"):
			with self.assertRaises(frappe.ValidationError):
				check_transition("UNCERTAIN", reentry)

	def test_content_completed_still_no_same_job_retry(self):
		# Conservative rule: completed output is printed output — reprint only.
		self.assertEqual(content_risk_retry_class(1, content_completed=True), "NONE")

	def test_no_content_started_leaves_retry_policy_open(self):
		# Output proven not started: retry_class is a policy decision, not a
		# content-risk mandate, so the rule returns no mandate.
		self.assertIsNone(content_risk_retry_class(0))
		self.assertIsNone(content_risk_retry_class(0, content_completed=False))


class _user:
	def __init__(self, user):
		self.user = user

	def __enter__(self):
		self.previous = frappe.session.user
		frappe.set_user(self.user)

	def __exit__(self, *exc):
		frappe.set_user(self.previous)


def _terminal():
	suffix = uuid.uuid4().hex[:8]
	return (
		frappe.get_doc(
			{
				"doctype": "POS Print Terminal",
				"terminal_id": f"TERM-{suffix}",
				"terminal_label": f"Terminal {suffix}",
				"company": test_company(),
				"pos_profile": test_outlet_a(),
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _job(status="CREATED", reservation_owner=None):
	suffix = uuid.uuid4().hex[:8]
	company = test_company()
	return frappe.get_doc(
		{
			"doctype": "POS Print Job",
			"job_id": f"JOB-{suffix}",
			"idempotency_key": f"idem-JOB-{suffix}",
			"reference_doctype": "Company",
			"reference_name": company,
			"company": company,
			"pos_profile": test_outlet_a(),
			"terminal": _terminal(),
			"requested_by": "Administrator",
			"source": "POS_AUTO",
			"driver_key": "imin_v1",
			"status": status,
			"reservation_owner": reservation_owner,
		}
	).insert(ignore_permissions=True)


def _attempt(job, terminal, **overrides):
	suffix = uuid.uuid4().hex[:8]
	doc = frappe.get_doc(
		{
			"doctype": "POS Print Attempt",
			"attempt_id": f"ATT-{suffix}",
			"job": job,
			"attempt_no": 1,
			"terminal": terminal,
			"driver_key": "imin_v1",
			"outcome": "STARTED",
			"started_at": "2026-08-10 10:00:00",
		}
	)
	doc.update(overrides)
	return doc.insert(ignore_permissions=True)
