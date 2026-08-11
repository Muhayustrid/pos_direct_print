import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.core.print_api import (
	complete_attempt,
	get_settings,
	release_reservation,
	reserve_print_job,
	resolve_terminal,
	resolve_terminal_for_profile,
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


class TestResolveTerminalForProfile(IntegrationTestCase):
	"""B4-01 — row-scoped terminal lookup for the POS context (C-3 resolved:
	transport travels in this lookup's own projection, not the frozen one)."""

	def setUp(self):
		self.operator = _user_with_role("profile.op@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("profile.mgr.a@example.test", "POS Print Manager")
		self.manager_none = _user_with_role("profile.mgr.none@example.test", "POS Print Manager")
		self.no_role = _user_with_role("profile.norole@example.test", "Sales User")
		# Dedicated profile per test: the site's shared OUTLET_A carries legacy
		# UNVERIFIED terminals that would win the creation-asc lookup.
		self.profile = _pos_profile("PDP Resolve Profile", self.operator)
		_user_permission(self.manager_a, "POS Profile", self.profile)

	def test_operator_with_applicable_profile_gets_transport_projection(self):
		terminal = _terminal(
			self.profile,
			qualification_status="QUALIFIED",
			transport="USB",
			paper_width_mm="58",
			driver_key="imin_v1",
		)
		with _user(self.operator):
			projection = resolve_terminal_for_profile(COMPANY, self.profile)
		self.assertEqual(projection["terminal_id"], terminal)
		self.assertEqual(projection["transport"], "USB")
		self.assertEqual(projection["driver_key"], "imin_v1")
		self.assertEqual(projection["paper_width_mm"], "58")
		self.assertEqual(projection["qualification_status"], "QUALIFIED")
		# Device-admin fields never cross this RPC boundary either.
		self.assertNotIn("device_serial", projection)
		self.assertNotIn("pairing_status", projection)

	def test_manager_without_pos_profile_scope_rejected(self):
		_terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		with _user(self.manager_none):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal_for_profile(COMPANY, self.profile)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_manager_with_scope_gets_lookup(self):
		terminal = _terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		with _user(self.manager_a):
			projection = resolve_terminal_for_profile(COMPANY, self.profile)
		self.assertEqual(projection["terminal_id"], terminal)

	def test_user_with_no_print_role_rejected(self):
		_terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		with _user(self.no_role):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal_for_profile(COMPANY, self.profile)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_no_enabled_terminal_raises_not_found(self):
		_terminal(self.profile, qualification_status="QUALIFIED", enabled=0)
		with _user(self.operator):
			with self.assertRaises(frappe.ValidationError) as ctx:
				resolve_terminal_for_profile(COMPANY, self.profile)
		self.assertIn("PDP_TERMINAL_NOT_FOUND", str(ctx.exception))

	def test_enabled_unverified_terminal_raises_not_qualified(self):
		_terminal(self.profile, qualification_status="UNVERIFIED", enabled=1)
		with _user(self.operator):
			with self.assertRaises(frappe.ValidationError) as ctx:
				resolve_terminal_for_profile(COMPANY, self.profile)
		self.assertIn("PDP_TERMINAL_NOT_QUALIFIED", str(ctx.exception))

	def test_two_enabled_terminals_returns_oldest(self):
		older = _terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		_terminal(self.profile, qualification_status="QUALIFIED", transport="SPI")
		frappe.db.set_value("POS Print Terminal", older, "creation", "2020-01-01 08:00:00")
		with _user(self.operator):
			projection = resolve_terminal_for_profile(COMPANY, self.profile)
		self.assertEqual(projection["terminal_id"], older)

	def test_out_of_company_scope_rejected(self):
		# Company User Permission narrows scope to COMPANY, so a lookup for a
		# different company is denied even though a terminal exists there.
		other_company = "_Test Company"
		_terminal(self.profile, qualification_status="QUALIFIED", company=other_company)
		_user_permission(self.operator, "Company", COMPANY)
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal_for_profile(other_company, self.profile)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))


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


def _pos_profile(name, user=None, *, company=COMPANY, disabled=0):
	"""Fresh POS Profile copied from the site template, so lookups scoped to it
	never collide with legacy terminals on the shared OUTLET_A profile."""
	source = frappe.get_doc("POS Profile", OUTLET_A)
	profile = frappe.copy_doc(source)
	profile.name = f"{name}-{uuid.uuid4().hex[:8]}"
	profile.company = company
	profile.disabled = disabled
	profile.set("applicable_for_users", [])
	if user:
		profile.append("applicable_for_users", {"user": user, "default": 0})
	return profile.insert(ignore_permissions=True).name


def _terminal(pos_profile, **overrides):
	suffix = uuid.uuid4().hex[:8]
	fields = {
		"doctype": "POS Print Terminal",
		"terminal_id": f"TERM-{suffix}",
		"terminal_label": f"Terminal {suffix}",
		"company": COMPANY,
		"pos_profile": pos_profile,
	}
	fields.update(overrides)
	return frappe.get_doc(fields).insert(ignore_permissions=True).name
