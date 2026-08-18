import uuid

import frappe
from frappe.tests import IntegrationTestCase

import pos_direct_print
from pos_direct_print.core.retry import evaluate_auto_retry, perform_auto_retry
from pos_direct_print.tests.fixtures import test_company, test_outlet_a


class TestAppIsolation(IntegrationTestCase):
	"""A-AT-01 / A-DOD-01 — every customization lives inside the custom app.

	Milestone A only wires permission hooks; nothing may override or patch
	Frappe/ERPNext core behavior."""

	def test_hooks_never_override_or_patch_core(self):
		hooks = pos_direct_print.hooks
		for forbidden in (
			"override_whitelisted_methods",
			"override_doctype_class",
			"extend_doctype_class",
			"doc_events",
			"doctype_js",
			"fixtures",
			"scheduler_events",
			"override_doctype_dashboards",
		):
			self.assertFalse(getattr(hooks, forbidden, None), f"{forbidden} must stay unused in Milestone A")

	def test_hooks_only_declare_permission_rule_sources(self):
		hooks = pos_direct_print.hooks
		self.assertEqual(
			set(hooks.permission_query_conditions),
			{"POS Print Job", "POS Print Attempt", "POS Print Terminal"},
		)
		self.assertEqual(
			set(hooks.has_permission),
			{"POS Print Job", "POS Print Attempt", "POS Print Terminal"},
		)


class TestDeskEntryPoint(IntegrationTestCase):
	"""The module is reachable: one sidebar plus the Desktop Icon that names it.

	`Workspace Sidebar` decides what the left nav holds. `Desktop Icon` is what
	puts the module in the icon rail and in awesomebar results — the awesomebar
	reads `boot.desktop_icons` only. A sidebar without its icon is invisible to
	search, which is exactly how this app shipped before."""

	def test_desktop_icon_points_at_the_sidebar(self):
		icon = frappe.get_doc("Desktop Icon", "Direct Print")

		self.assertEqual(icon.link_type, "Workspace Sidebar")
		self.assertEqual(icon.link_to, "Direct Print")
		self.assertEqual(icon.app, "pos_direct_print")
		self.assertFalse(icon.hidden)
		self.assertTrue(frappe.db.exists("Workspace Sidebar", icon.link_to))

	def test_icon_parent_exists_or_the_icon_is_dropped_in_silence(self):
		# get_desktop_icons keeps a child icon only while its parent survives the
		# same permission pass, and drops it without a message otherwise. The
		# parent is ERPNext, which `required_apps` makes a hard install dependency.
		self.assertEqual(frappe.db.get_value("Desktop Icon", "Direct Print", "parent_icon"), "ERPNext")
		self.assertTrue(frappe.db.exists("Desktop Icon", "ERPNext"))
		self.assertEqual(pos_direct_print.hooks.required_apps, ["erpnext"])

	def test_sidebar_groups_the_pos_doctypes_under_one_section(self):
		sidebar = frappe.get_doc("Workspace Sidebar", "Direct Print")
		labels = [item.label for item in sidebar.items]

		self.assertEqual(
			labels,
			[
				"POS Direct Print",
				"POS Print Terminal",
				"POS Print Job",
				"POS Print Attempt",
				"POS Print Settings",
			],
		)
		section, *links = sidebar.items
		self.assertEqual(section.type, "Section Break")
		self.assertTrue(section.collapsible)
		self.assertTrue(all(link.child for link in links))


class TestDuplicateJobId(IntegrationTestCase):
	"""A-AT-03 / A-DOD-02 — duplicate job_id is rejected at persistence."""

	def test_duplicate_job_id_rejected(self):
		first = _job()
		# job_id is the autoname field, so a duplicate is a primary-key collision.
		with self.assertRaises(frappe.DuplicateEntryError):
			_job(job_id=first.job_id)

		count = frappe.db.count("POS Print Job", {"job_id": first.job_id})
		self.assertEqual(count, 1)


class TestSafeRetryEvaluation(IntegrationTestCase):
	"""A-AT-11 / A-DOD-07 / A-DOD-08 — a pre-output failure with AUTO_SAFE and
	headroom may retry on the same Job; content risk and the limit deny it."""

	def setUp(self):
		self.job = _job(status="FAILED_SAFE", reservation_owner="client-x")
		self.max_retries = frappe.get_single("POS Print Settings").max_safe_auto_retries or 1

	def test_auto_safe_retry_allowed_and_executed(self):
		_attempt(
			self.job.name,
			self.job.terminal,
			retry_class="AUTO_SAFE",
			content_started=0,
			outcome="FAILED_SAFE",
		)

		decision = evaluate_auto_retry(self.job.name)
		self.assertTrue(decision["allowed"], decision)
		self.assertEqual(decision["retry_class"], "AUTO_SAFE")

		retried = perform_auto_retry(self.job.name, "client-x")
		self.assertEqual(retried.status, "RESERVED")
		self.assertEqual(retried.safe_retry_count, 1)

	def test_uncertain_job_returns_reprint_only(self):
		job = _job(status="UNCERTAIN", reservation_owner="client-x")
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
		job = _job(status="SUCCEEDED", reservation_owner="client-x")
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

	def test_retry_denied_when_content_started(self):
		# Conservative content-risk rule overrides AUTO_SAFE.
		_attempt(
			self.job.name, self.job.terminal, retry_class="AUTO_SAFE", content_started=1, outcome="UNCERTAIN"
		)
		decision = evaluate_auto_retry(self.job.name)
		self.assertFalse(decision["allowed"])
		self.assertEqual(decision["reason"], "PDP_JOB_CONFLICT")

	def test_retry_denied_at_limit(self):
		_attempt(
			self.job.name,
			self.job.terminal,
			retry_class="AUTO_SAFE",
			content_started=0,
			outcome="FAILED_SAFE",
		)
		self.job.db_set("safe_retry_count", self.max_retries)

		decision = evaluate_auto_retry(self.job.name)
		self.assertFalse(decision["allowed"])
		self.assertEqual(decision["retry_class"], "NONE")
		with self.assertRaises(frappe.ValidationError):
			perform_auto_retry(self.job.name, "client-x")

	def test_retry_denied_outside_failed_safe(self):
		job = _job(status="CREATED")
		decision = evaluate_auto_retry(job.name)
		self.assertFalse(decision["allowed"])
		self.assertEqual(decision["reason"], "PDP_JOB_INVALID_TRANSITION")

	def test_retry_denied_without_auto_safe_attempt(self):
		_attempt(
			self.job.name,
			self.job.terminal,
			retry_class="MANUAL_SAFE",
			content_started=0,
			outcome="FAILED_SAFE",
		)
		decision = evaluate_auto_retry(self.job.name)
		self.assertFalse(decision["allowed"])


def _job(status="CREATED", job_id=None, reservation_owner=None):
	suffix = uuid.uuid4().hex[:8]
	company = test_company()
	return frappe.get_doc(
		{
			"doctype": "POS Print Job",
			"job_id": job_id or f"JOB-{suffix}",
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
