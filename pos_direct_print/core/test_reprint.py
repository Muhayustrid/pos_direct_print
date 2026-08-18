import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.core.reprint import request_reprint
from pos_direct_print.tests.fixtures import test_company, test_outlet_a, test_outlet_b


class TestReprintAuthorization(IntegrationTestCase):
	"""A-AT-24 + A.31.19-A.31.21. REPRINT goes through request_reprint only; the
	standard DocType Create path stays denied for every role."""

	def setUp(self):
		self.outlet_a = test_outlet_a()
		self.outlet_b = test_outlet_b()

		self.operator = _user_with_role("reprint.op@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("reprint.mgr.a@example.test", "POS Print Manager")
		self.manager_b = _user_with_role("reprint.mgr.b@example.test", "POS Print Manager")
		self.system_manager = _user_with_role("reprint.sysmgr@example.test", "System Manager")

		_user_permission(self.manager_a, "POS Profile", self.outlet_a)
		_user_permission(self.manager_b, "POS Profile", self.outlet_b)

		self.completed_job = _job(
			requested_by=self.operator,
			pos_profile=self.outlet_a,
			status="SUCCEEDED",
			reservation_owner="client-x",
		)

	def test_case1_operator_reprint_denied(self):
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError):
				request_reprint(self.completed_job.name, "Torn receipt")

	def test_case2_scoped_manager_creates_new_reprint_job(self):
		with _user(self.manager_a):
			result = request_reprint(self.completed_job.name, "Paper jam on first copy")

		self.assertEqual(result["parent_job"], self.completed_job.name)
		reprint = frappe.get_doc("POS Print Job", result["job_id"])

		self.assertEqual(reprint.job_type, "REPRINT")
		self.assertEqual(reprint.parent_job, self.completed_job.name)
		self.assertEqual(reprint.requested_by, self.manager_a)
		self.assertEqual(reprint.reprint_reason, "Paper jam on first copy")
		self.assertEqual(reprint.status, "CREATED")

		# The parent job is never modified into a reprint.
		parent = frappe.get_doc("POS Print Job", self.completed_job.name)
		self.assertEqual(parent.job_type, "ORIGINAL")
		self.assertEqual(parent.status, "SUCCEEDED")

	def test_case3_missing_reason_denied(self):
		with _user(self.manager_a):
			with self.assertRaises(frappe.MandatoryError):
				request_reprint(self.completed_job.name, "")
			with self.assertRaises(frappe.MandatoryError):
				request_reprint(self.completed_job.name, "   ")

	def test_case4_wrong_outlet_manager_denied(self):
		# manager_b is authorized for Outlet B only.
		with _user(self.manager_b):
			with self.assertRaises(frappe.PermissionError):
				request_reprint(self.completed_job.name, "Customer asked again")

	def test_unscoped_manager_fail_closed(self):
		unscoped = _user_with_role("reprint.mgr.none@example.test", "POS Print Manager")
		with _user(unscoped):
			with self.assertRaises(frappe.PermissionError):
				request_reprint(self.completed_job.name, "Reason")

	def test_non_reprintable_state_denied(self):
		preflight_job = _job(
			requested_by=self.operator,
			pos_profile=self.outlet_a,
			status="PREFLIGHT",
			reservation_owner="client-y",
		)
		with _user(self.manager_a):
			with self.assertRaises(frappe.ValidationError):
				request_reprint(preflight_job.name, "Reason")

	def test_system_manager_can_reprint_with_reason(self):
		with _user(self.system_manager):
			result = request_reprint(self.completed_job.name, "Audit reissue")
		self.assertEqual(result["parent_job"], self.completed_job.name)

	def test_terminal_outside_scope_denied(self):
		other_terminal = _terminal(self.outlet_b)
		with _user(self.manager_a):
			with self.assertRaises(frappe.ValidationError):
				request_reprint(self.completed_job.name, "Reason", terminal=other_terminal)

	def test_terminal_serving_the_outlet_as_an_extra_is_accepted(self):
		# A shared counter whose default binding is Outlet B but which also serves
		# Outlet A may reprint an Outlet A receipt: it is the same physical printer
		# the outlet legitimately uses.
		shared = frappe.get_doc("POS Print Terminal", _terminal(self.outlet_b))
		shared.append("extra_pos_profiles", {"pos_profile": self.outlet_a})
		shared.save(ignore_permissions=True)

		with _user(self.manager_a):
			result = request_reprint(self.completed_job.name, "Shared counter", terminal=shared.name)

		reprint = frappe.get_doc("POS Print Job", result["job_id"])
		self.assertEqual(reprint.terminal, shared.name)
		# The reprint stays on the parent's outlet, never the terminal's default.
		self.assertEqual(reprint.pos_profile, self.outlet_a)

	def test_disabled_terminal_denied(self):
		disabled = _terminal(self.outlet_a)
		frappe.db.set_value("POS Print Terminal", disabled, "enabled", 0)
		with _user(self.manager_a):
			with self.assertRaises(frappe.ValidationError) as ctx:
				request_reprint(self.completed_job.name, "Reason", terminal=disabled)
		self.assertIn("PDP_TERMINAL_DISABLED", str(ctx.exception))


class _user:
	def __init__(self, user):
		self.user = user

	def __enter__(self):
		self.previous = frappe.session.user
		frappe.set_user(self.user)
		frappe.clear_cache(user=self.user)

	def __exit__(self, *exc):
		frappe.set_user(self.previous)


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
				"doctype": "POS Print Terminal",
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
			"doctype": "POS Print Job",
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
	return doc.insert(ignore_permissions=True)
