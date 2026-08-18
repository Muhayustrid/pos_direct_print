import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.tests.fixtures import (
	grant_profile_user,
	isolated_pos_profile,
	second_test_company,
	test_company,
	test_outlet_a,
	test_outlet_b,
)

JOB = "POS Print Job"
ATTEMPT = "POS Print Attempt"
TERMINAL = "POS Print Terminal"


class TestRowLevelScope(IntegrationTestCase):
	"""Row-level security per A.31.10-A.31.14 / A.31.24 / A.31.25.

	List queries and direct document access must agree, because both read from the
	same rule source in core.security.
	"""

	def setUp(self):
		self.company = test_company()
		self.outlet_a = test_outlet_a()
		self.outlet_b = test_outlet_b()

		self.operator_a = _user_with_role("op.a@example.test", "POS Print Operator")
		self.operator_b = _user_with_role("op.b@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("mgr.a@example.test", "POS Print Manager")
		self.unscoped_manager = _user_with_role("mgr.none@example.test", "POS Print Manager")
		self.system_manager = _user_with_role("sysmgr@example.test", "System Manager")

		_user_permission(self.manager_a, "POS Profile", self.outlet_a)
		grant_profile_user(self.outlet_a, self.operator_a)
		grant_profile_user(self.outlet_a, self.operator_b)
		grant_profile_user(self.outlet_b, self.operator_b)

		self.job_own_a = _job(requested_by=self.operator_a, pos_profile=self.outlet_a)
		self.job_own_b = _job(requested_by=self.operator_b, pos_profile=self.outlet_a)
		self.job_outlet_b = _job(requested_by=self.operator_b, pos_profile=self.outlet_b)

		self.profile_operator_a = isolated_pos_profile(user=self.operator_a)
		self.profile_operator_b = isolated_pos_profile(user=self.operator_b)
		self.profile_global = isolated_pos_profile()

		self.job_profile_a = _job(requested_by=self.operator_a, pos_profile=self.profile_operator_a)
		self.job_wrong_profile = _job(requested_by=self.operator_a, pos_profile=self.profile_operator_b)
		self.job_global_profile = _job(requested_by=self.operator_a, pos_profile=self.profile_global)

	def test_operator_sees_only_own_jobs(self):
		# A-AT-20: list query.
		visible = _list_as(self.operator_a, JOB)
		self.assertIn(self.job_own_a, visible)
		self.assertNotIn(self.job_own_b, visible)
		self.assertNotIn(self.job_outlet_b, visible)

	def test_operator_direct_access_to_other_job_denied(self):
		# A-AT-20: direct document access must fail identically to the list.
		with _user(self.operator_a):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(JOB, self.job_own_b).check_permission("read")
			frappe.get_doc(JOB, self.job_own_a).check_permission("read")

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

	def test_manager_scoped_to_authorized_pos_profile(self):
		# A-AT-22: Manager with explicit User Permission on Outlet A reads Outlet A
		# jobs and is denied Outlet B jobs, on list and direct access alike.
		visible = _list_as(self.manager_a, JOB)
		self.assertIn(self.job_own_a, visible)
		self.assertIn(self.job_own_b, visible)
		self.assertNotIn(self.job_outlet_b, visible)

		with _user(self.manager_a):
			frappe.get_doc(JOB, self.job_own_a).check_permission("read")
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(JOB, self.job_outlet_b).check_permission("read")

	def test_manager_without_user_permission_sees_zero_jobs(self):
		# A-AT-25 fail-closed: missing scope is never interpreted as unrestricted.
		visible = _list_as(self.unscoped_manager, JOB)
		self.assertEqual(visible, set())

		with _user(self.unscoped_manager):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(JOB, self.job_own_a).check_permission("read")

	def test_operator_has_no_attempt_access_even_own(self):
		# A.31.16: Operator gets no direct DocType access to Attempts, own or not.
		# Operational outcome data reaches them through projections, not the DocType.
		attempt_own = _attempt(self.job_own_a, _terminal(self.outlet_a))

		with _user(self.operator_a):
			# No Read permission row exists for Operator on Attempt, so even the list
			# query is refused, not merely filtered.
			with self.assertRaises(frappe.PermissionError):
				frappe.get_list(ATTEMPT)
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(ATTEMPT, attempt_own).check_permission("read")

	def test_manager_attempt_scope_follows_job_scope(self):
		attempt_a = _attempt(self.job_own_a, _terminal(self.outlet_a))
		attempt_b = _attempt(self.job_outlet_b, _terminal(self.outlet_b))

		visible = _list_as(self.manager_a, ATTEMPT)
		self.assertIn(attempt_a, visible)
		self.assertNotIn(attempt_b, visible)

	def test_manager_terminal_scope_follows_pos_profile(self):
		terminal_a = _terminal(self.outlet_a)
		terminal_b = _terminal(self.outlet_b)

		visible = _list_as(self.manager_a, TERMINAL)
		self.assertIn(terminal_a, visible)
		self.assertNotIn(terminal_b, visible)

	def test_cross_company_intersection_denies_access(self):
		# A.31.25: scope = Frappe company permission AND role AND POS Profile scope.
		# A Manager authorized for Outlet A but restricted by User Permission to a
		# Company that outlet does not belong to sees none of its jobs. The other
		# Company is a fixture rather than ERPNext's `_Test Company`, which only
		# exists on sites where ERPNext's own test records have been generated.
		_user_permission(self.manager_a, "Company", second_test_company())

		self.assertEqual(_list_as(self.manager_a, JOB), set())
		with _user(self.manager_a):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(JOB, self.job_own_a).check_permission("read")

	def test_system_manager_reads_all_jobs(self):
		visible = _list_as(self.system_manager, JOB)
		self.assertIn(self.job_own_a, visible)
		self.assertIn(self.job_own_b, visible)
		self.assertIn(self.job_outlet_b, visible)

	def test_administrator_reads_all_jobs(self):
		with _user("Administrator"):
			visible = {row.name for row in frappe.get_list(JOB, fields=["name"])}
		self.assertIn(self.job_own_a, visible)
		self.assertIn(self.job_outlet_b, visible)


class _user:
	"""Context manager switching the session user and always restoring."""

	def __init__(self, user):
		self.user = user

	def __enter__(self):
		self.previous = frappe.session.user
		frappe.set_user(self.user)
		frappe.clear_cache(user=self.user)

	def __exit__(self, *exc):
		frappe.set_user(self.previous)


def _list_as(user, doctype):
	with _user(user):
		return {row.name for row in frappe.get_list(doctype, fields=["name"])}


def _user_with_role(email, role):
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": email.split("@")[0],
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)
	user.add_roles(role)
	return user.name


def _user_permission(user, allow, for_value):
	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": allow,
			"for_value": for_value,
		}
	).insert(ignore_permissions=True)


def _terminal(pos_profile):
	suffix = uuid.uuid4().hex[:8]
	return (
		frappe.get_doc(
			{
				"doctype": TERMINAL,
				"terminal_id": f"TERM-{suffix}",
				"terminal_label": f"Terminal {suffix}",
				"company": test_company(),
				"pos_profile": pos_profile,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _job(requested_by, pos_profile, **overrides):
	suffix = uuid.uuid4().hex[:8]
	company = test_company()
	doc = frappe.get_doc(
		{
			"doctype": JOB,
			"job_id": f"JOB-{suffix}",
			"idempotency_key": f"idem-JOB-{suffix}",
			"reference_doctype": "Company",
			"reference_name": company,
			"company": company,
			"pos_profile": pos_profile,
			"terminal": _terminal(pos_profile),
			"requested_by": requested_by,
			"source": "POS_AUTO",
			"driver_key": "imin_v1",
		}
	)
	doc.update(overrides)
	return doc.insert(ignore_permissions=True).name


def _attempt(job, terminal, **overrides):
	suffix = uuid.uuid4().hex[:8]
	doc = frappe.get_doc(
		{
			"doctype": ATTEMPT,
			"attempt_id": f"ATT-{suffix}",
			"job": job,
			"attempt_no": 1,
			"terminal": terminal,
			"driver_key": "imin_v1",
			"started_at": "2026-08-10 10:00:00",
		}
	)
	doc.update(overrides)
	return doc.insert(ignore_permissions=True).name
