import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.core.projections import (
	JOB_STATUS_FIELDS,
	OUTCOME_FIELDS,
	RUNTIME_SETTINGS_FIELDS,
	TERMINAL_RUNTIME_FIELDS,
	job_status_projection,
	outcome_projection,
	runtime_settings_projection,
	terminal_runtime_projection,
)
from pos_direct_print.tests.fixtures import test_company, test_outlet_a

# Level 1 fields per A.31.6 / A.31.9 / A.31.17. No projection may expose these.
TERMINAL_LEVEL1_FIELDS = {
	"driver_key",
	"device_model",
	"device_serial",
	"android_version",
	"rom_build",
	"plugin_version",
	"browser_version",
	"webview_version",
	"transport",
	"paper_width_mm",
	"cutter_capability",
	"qualification_revision",
	"capability_schema_version",
	"capabilities_json",
	"paired_client_id",
	"pairing_status",
	"notes",
}

JOB_LEVEL1_FIELDS = {
	"idempotency_key",
	"reservation_owner",
	"reserved_at",
	"reserved_until",
	"receipt_schema_version",
	"receipt_hash",
	"receipt_snapshot",
	"last_error_detail",
	"metadata_json",
}

ATTEMPT_LEVEL1_FIELDS = {
	"raw_status_before",
	"raw_status_after",
	"error_detail",
	"client_session_id",
	"browser_tab_id",
	"paired_client_id",
	"driver_version",
	"asset_version",
	"metadata_json",
}


class TestFieldSensitivity(IntegrationTestCase):
	def test_terminal_level1_fields_have_permlevel_1(self):
		_assert_permlevels("POS Print Terminal", TERMINAL_LEVEL1_FIELDS)

	def test_job_level1_fields_have_permlevel_1(self):
		_assert_permlevels("POS Print Job", JOB_LEVEL1_FIELDS)

	def test_attempt_level1_fields_have_permlevel_1(self):
		_assert_permlevels("POS Print Attempt", ATTEMPT_LEVEL1_FIELDS)

	def test_terminal_level1_readable_only_by_system_manager(self):
		# A.31.6: device administration fields are System Manager only.
		roles = _permlevel1_roles("POS Print Terminal")
		self.assertEqual(roles, {"System Manager"})

	def test_job_level1_readable_by_system_manager_and_manager(self):
		# A.31.9: sensitive audit data readable by System Manager + scoped Manager,
		# never by Operator.
		roles = _permlevel1_roles("POS Print Job")
		self.assertEqual(roles, {"System Manager", "POS Print Manager"})
		self.assertNotIn("POS Print Operator", roles)

	def test_attempt_level1_readable_only_by_system_manager(self):
		# A.31.17: raw diagnostics are System Manager only, not even Manager.
		roles = _permlevel1_roles("POS Print Attempt")
		self.assertEqual(roles, {"System Manager"})

	def test_effective_permlevel_access_per_role(self):
		# A-AT-21 at the framework level: assert what Frappe actually grants, not just
		# what the matrix declares. Operator sees Job Level 0 only and has no Terminal
		# or Attempt access; Manager sees Job Level 1 but no raw Attempt diagnostics
		# and no Terminal device fingerprint.
		expected = {
			"POS Print Operator": {
				"POS Print Job": [0],
				"POS Print Attempt": [],
				"POS Print Terminal": [],
			},
			"POS Print Manager": {
				"POS Print Job": [0, 1],
				"POS Print Attempt": [0],
				"POS Print Terminal": [0],
			},
		}

		for role, per_doctype in expected.items():
			user = _user_with_role(role)
			try:
				frappe.set_user(user)
				frappe.clear_cache(user=user)
				for doctype, levels in per_doctype.items():
					with self.subTest(role=role, doctype=doctype):
						granted = sorted(frappe.get_meta(doctype).get_permlevel_access("read", user=user))
						self.assertEqual(granted, levels)
			finally:
				frappe.set_user("Administrator")

	def test_operator_cannot_read_receipt_snapshot_field(self):
		# A-AT-21: the sensitive field is filtered out of the fields the Operator may
		# read, so a direct document fetch cannot surface receipt content.
		user = _user_with_role("POS Print Operator")
		try:
			frappe.set_user(user)
			frappe.clear_cache(user=user)
			readable = set(
				frappe.get_meta("POS Print Job").get_permitted_fieldnames(permission_type="read", user=user)
			)
		finally:
			frappe.set_user("Administrator")

		self.assertNotIn("receipt_snapshot", readable)
		self.assertNotIn("idempotency_key", readable)
		self.assertIn("status", readable)

	def test_no_role_can_write_job_or_attempt_level1(self):
		for doctype in ("POS Print Job", "POS Print Attempt"):
			for perm in frappe.get_meta(doctype).permissions:
				with self.subTest(doctype=doctype, role=perm.role):
					self.assertEqual(perm.write, 0)


class TestSanitizedProjections(IntegrationTestCase):
	def test_runtime_settings_projection_exposes_only_allowlist(self):
		payload = runtime_settings_projection()

		self.assertCountEqual(payload.keys(), RUNTIME_SETTINGS_FIELDS)
		# Internal retention/lock configuration is not client business.
		for leaked in ("job_retention_days", "attempt_retention_days", "local_lock_ttl_seconds"):
			self.assertNotIn(leaked, payload)

	def test_terminal_runtime_projection_hides_device_fingerprint(self):
		# A.31.7 forbids serial, ROM, browser/WebView version, raw capability JSON,
		# pairing internals, and notes.
		terminal = _terminal()
		terminal.db_set(
			{
				"device_serial": "SN-SECRET",
				"rom_build": "ROM-SECRET",
				"capabilities_json": '{"secret": true}',
				"notes": "internal note",
			},
			update_modified=False,
		)

		payload = terminal_runtime_projection(terminal.name)

		self.assertCountEqual(payload.keys(), TERMINAL_RUNTIME_FIELDS)
		for forbidden in (
			"device_serial",
			"rom_build",
			"browser_version",
			"webview_version",
			"capabilities_json",
			"paired_client_id",
			"pairing_status",
			"notes",
		):
			with self.subTest(field=forbidden):
				self.assertNotIn(forbidden, payload)

	def test_job_status_projection_hides_receipt_snapshot(self):
		# A-AT-21: receipt_snapshot, idempotency_key, metadata_json, and
		# last_error_detail must never reach a client payload.
		job = _job(
			receipt_hash="hash-1",
			receipt_snapshot='{"items": [{"item": "Roti", "price": 15000}]}',
			metadata_json='{"internal": true}',
			last_error_detail="stack trace",
		)

		payload = job_status_projection(job.name)

		self.assertCountEqual(payload.keys(), JOB_STATUS_FIELDS)
		for forbidden in JOB_LEVEL1_FIELDS:
			with self.subTest(field=forbidden):
				self.assertNotIn(forbidden, payload)

	def test_outcome_projection_hides_sensitive_fields(self):
		job = _job(receipt_hash="hash-2", receipt_snapshot='{"items": []}')

		payload = outcome_projection(job.name)

		self.assertCountEqual(payload.keys(), OUTCOME_FIELDS)
		for forbidden in JOB_LEVEL1_FIELDS:
			with self.subTest(field=forbidden):
				self.assertNotIn(forbidden, payload)

	def test_job_projection_allowlists_contain_no_level1_field(self):
		# Guard against a future Level 1 field being added to an allowlist by accident.
		# Terminal is excluded on purpose: A.31.7 explicitly permits driver_key and
		# paper_width_mm in the runtime projection even though both are Level 1 on the
		# DocType, because PrintManager needs them to select a driver and layout.
		self.assertFalse(set(JOB_STATUS_FIELDS) & JOB_LEVEL1_FIELDS)
		self.assertFalse(set(OUTCOME_FIELDS) & JOB_LEVEL1_FIELDS)

	def test_attempt_level1_fields_are_in_no_projection(self):
		projected = set(TERMINAL_RUNTIME_FIELDS) | set(JOB_STATUS_FIELDS) | set(OUTCOME_FIELDS)
		self.assertFalse(projected & (ATTEMPT_LEVEL1_FIELDS - {"paired_client_id"}))


def _user_with_role(role):
	email = f"pdp.{frappe.scrub(role)}@example.test"
	if frappe.db.exists("User", email):
		frappe.delete_doc("User", email, force=True)
	user = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": frappe.scrub(role),
			"send_welcome_email": 0,
		}
	).insert(ignore_permissions=True)
	user.add_roles(role)
	return user.name


def _assert_permlevels(doctype, level1_fields):
	fields = {field.fieldname: field for field in frappe.get_meta(doctype).fields}
	for fieldname, field in fields.items():
		expected = 1 if fieldname in level1_fields else 0
		assert (field.permlevel or 0) == expected, (
			f"{doctype}.{fieldname} permlevel {field.permlevel} != {expected}"
		)


def _permlevel1_roles(doctype):
	return {perm.role for perm in frappe.get_meta(doctype).permissions if perm.permlevel == 1 and perm.read}


def _company():
	return test_company()


def _pos_profile():
	return test_outlet_a()


def _terminal():
	suffix = uuid.uuid4().hex[:8]
	return frappe.get_doc(
		{
			"doctype": "POS Print Terminal",
			"terminal_id": f"TERM-{suffix}",
			"terminal_label": f"Terminal {suffix}",
			"company": _company(),
			"pos_profile": _pos_profile(),
		}
	).insert(ignore_permissions=True)


def _job(**overrides):
	suffix = uuid.uuid4().hex[:8]
	doc = frappe.get_doc(
		{
			"doctype": "POS Print Job",
			"job_id": f"JOB-{suffix}",
			"idempotency_key": f"idem-JOB-{suffix}",
			"reference_doctype": "Company",
			"reference_name": _company(),
			"company": _company(),
			"pos_profile": _pos_profile(),
			"terminal": _terminal().name,
			"requested_by": "Administrator",
			"source": "POS_AUTO",
			"driver_key": "imin_v1",
		}
	)
	doc.update(overrides)
	return doc.insert(ignore_permissions=True)
