import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.core.print_api import (
	complete_attempt,
	get_settings,
	release_reservation,
	reserve_print_job,
	resolve_terminal,
	retrieve_job,
	start_attempt,
	transition_job,
)

COMPANY = "PT. JUARA ROTI INDONESIA"
OUTLET_A = "yusuf"
OUTLET_B = "POS Training"


class TestPrintApiTransport(IntegrationTestCase):
	"""A2-05 / A-DOD-15/16 — thin RPC: authorization server-side, sanitized
	projections out, canonical PDP errors on denial."""

	def setUp(self):
		self.operator = _user_with_role("api.op@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("api.mgr.a@example.test", "POS Print Manager")
		_pos_profile_grant_user(OUTLET_A, self.operator)
		_user_permission(self.manager_a, "POS Profile", OUTLET_A)

		self.terminal = _terminal(OUTLET_A)
		self.terminal_b = _terminal(OUTLET_B)

	def test_get_settings_exposes_runtime_fields_only(self):
		with _user(self.operator):
			settings = get_settings()
		self.assertIn("operating_mode", settings)
		self.assertNotIn("job_retention_days", settings)

	def test_resolve_terminal_returns_runtime_projection(self):
		with _user("Administrator"):
			projection = resolve_terminal(self.terminal)
		self.assertEqual(projection["terminal_id"], self.terminal)
		# A-AT-19: device-admin fields never cross the RPC boundary.
		self.assertNotIn("device_serial", projection)
		self.assertNotIn("firmware_version", projection)

	def test_resolve_disabled_terminal_rejected(self):
		frappe.db.set_value("POS Print Terminal", self.terminal, "enabled", 0)
		with _user("Administrator"):
			with self.assertRaises(frappe.ValidationError) as ctx:
				resolve_terminal(self.terminal)
		self.assertIn("PDP_TERMINAL_DISABLED", str(ctx.exception))

	def test_reserve_print_job_idempotent_single_logical_job(self):
		key = f"api-idem-{uuid.uuid4().hex[:8]}"
		with _user(self.operator):
			first = reserve_print_job(
				reference_doctype="Company",
				reference_name=COMPANY,
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=key,
			)
			second = reserve_print_job(
				reference_doctype="Company",
				reference_name=COMPANY,
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=key,
			)
		self.assertEqual(first["job_id"], second["job_id"])
		self.assertEqual(first["status"], "RESERVED")
		self.assertTrue(first["is_new_job"])
		self.assertFalse(second["is_new_job"], "idempotent hit must not claim a new Job")

		rows = frappe.db.get_all("POS Print Job", filters={"idempotency_key": key})
		self.assertEqual(len(rows), 1)

	def test_reserve_rejects_impersonation(self):
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError) as ctx:
				reserve_print_job(
					reference_doctype="Company",
					reference_name=COMPANY,
					terminal_id=self.terminal,
					requested_by="someone-else@example.test",
					idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
				)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_reserve_non_original_rejected(self):
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError):
				reserve_print_job(
					reference_doctype="Company",
					reference_name=COMPANY,
					terminal_id=self.terminal,
					requested_by=self.operator,
					idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
					job_type="REPRINT",
				)

	def test_manager_out_of_scope_terminal_rejected(self):
		with _user(self.manager_a):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal(self.terminal_b)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_attempt_lifecycle_through_transport(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=COMPANY,
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			started = start_attempt(
				job_id=reservation["job_id"],
				reservation_token=reservation["reservation_token"],
			)
			self.assertEqual(started["job"]["status"], "PREFLIGHT")
			self.assertEqual(started["attempt"]["attempt_no"], 1)

			outcome = complete_attempt(
				attempt_id=started["attempt"]["attempt_id"],
				outcome="SUCCEEDED",
				content_started=1,
				content_completed=1,
			)
			# Thin transport completes the Attempt; the Job only moves through
			# validated transitions requested by the coordinator.
			self.assertEqual(outcome["status"], "PREFLIGHT")

			released = retrieve_job(reservation["job_id"])
			self.assertEqual(released["status"], "PREFLIGHT")

	def test_transition_job_rejects_invalid_transition(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=COMPANY,
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			with self.assertRaises(frappe.ValidationError) as ctx:
				transition_job(
					job_id=reservation["job_id"],
					expected_from_state="RESERVED",
					target_state="SUCCEEDED",
					reservation_token=reservation["reservation_token"],
				)
		self.assertIn("PDP_JOB_INVALID_TRANSITION", str(ctx.exception))

	def test_transition_job_conflict_on_stale_expectation(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=COMPANY,
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			transition_job(
				job_id=reservation["job_id"],
				expected_from_state="RESERVED",
				target_state="PREFLIGHT",
				reservation_token=reservation["reservation_token"],
			)
			with self.assertRaises(frappe.ValidationError) as ctx:
				transition_job(
					job_id=reservation["job_id"],
					expected_from_state="RESERVED",
					target_state="CANCELLED",
					reservation_token=reservation["reservation_token"],
				)
		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))

	def test_release_reservation_cancels(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=COMPANY,
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			released = release_reservation(
				job_id=reservation["job_id"],
				reservation_token=reservation["reservation_token"],
				expected_from_state="CREATED",
			)
			self.assertEqual(released["status"], "CANCELLED")

	def test_retrieve_job_out_of_scope_denied(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=COMPANY,
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
		other_operator = _user_with_role("api.op2@example.test", "POS Print Operator")
		with _user(other_operator):
			with self.assertRaises(frappe.PermissionError):
				retrieve_job(reservation["job_id"])


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


def _pos_profile_grant_user(pos_profile, user):
	profile = frappe.get_doc("POS Profile", pos_profile)
	if user not in {row.user for row in profile.applicable_for_users}:
		profile.append("applicable_for_users", {"user": user, "default": 0})
		profile.save(ignore_permissions=True)


def _terminal(pos_profile):
	suffix = uuid.uuid4().hex[:8]
	return (
		frappe.get_doc(
			{
				"doctype": "POS Print Terminal",
				"terminal_id": f"TERM-{suffix}",
				"terminal_label": f"Terminal {suffix}",
				"company": COMPANY,
				"pos_profile": pos_profile,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)
