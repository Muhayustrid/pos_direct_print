import frappe
from frappe.tests import IntegrationTestCase

DOCTYPE = "POS Print Settings"

FIELD_SPECS = {
	"enabled": ("Check", "0"),
	"operating_mode": ("Select", "OFF", "OFF\nPILOT\nON"),
	"default_driver": ("Data", "browser"),
	"terminal_required": ("Check", "1"),
	"allow_browser_fallback": ("Check", "1"),
	"browser_fallback_confirmation": ("Check", "1"),
	"reservation_ttl_seconds": ("Int", "120"),
	"local_lock_ttl_seconds": ("Int", "30"),
	"max_safe_auto_retries": ("Int", "1"),
	"safe_retry_delay_ms": ("Int", "1000"),
	"job_retention_days": ("Int", "180"),
	"attempt_retention_days": ("Int", "180"),
	"receipt_schema_version": ("Int", "1"),
	"debug_logging": ("Check", "0"),
	"settings_schema_version": ("Int", "1"),
}

VALID_BOUNDARIES = {
	"reservation_ttl_seconds": 1,
	"local_lock_ttl_seconds": 1,
	"max_safe_auto_retries": 0,
	"safe_retry_delay_ms": 0,
	"job_retention_days": 1,
	"attempt_retention_days": 1,
	"receipt_schema_version": 1,
}

INVALID_BOUNDARIES = {
	"reservation_ttl_seconds": 0,
	"local_lock_ttl_seconds": 0,
	"max_safe_auto_retries": -1,
	"safe_retry_delay_ms": -1,
	"job_retention_days": 0,
	"attempt_retention_days": 0,
	"receipt_schema_version": 0,
}


class TestPOSPrintSettings(IntegrationTestCase):
	def test_doctype_is_single_and_non_submittable(self):
		meta = frappe.get_meta(DOCTYPE)

		self.assertTrue(meta.issingle)
		self.assertFalse(meta.is_submittable)
		self.assertEqual(meta.module, "Pos Direct Print")

	def test_has_exactly_fifteen_required_fields_with_schema(self):
		meta = frappe.get_meta(DOCTYPE)

		fields = {field.fieldname: field for field in meta.fields}

		self.assertEqual(len(fields), len(FIELD_SPECS))
		self.assertCountEqual(fields.keys(), FIELD_SPECS.keys())

		for fieldname, spec in FIELD_SPECS.items():
			field = fields[fieldname]
			with self.subTest(field=fieldname):
				self.assertEqual(field.fieldtype, spec[0])
				self.assertEqual(field.reqd, 1)
				self.assertEqual(field.default, spec[1])
				if len(spec) > 2:
					self.assertEqual(field.options, spec[2])

	def test_defaults_created_on_fresh_site(self):
		settings = frappe.get_single(DOCTYPE)

		for fieldname, spec in FIELD_SPECS.items():
			with self.subTest(field=fieldname):
				self.assertEqual(settings.get(fieldname), _expected_default(spec))

	def test_only_system_manager_has_read_and_write(self):
		permissions = frappe.get_meta(DOCTYPE).permissions

		self.assertEqual(len(permissions), 1)
		perm = permissions[0]
		self.assertEqual(perm.role, "System Manager")
		self.assertEqual(perm.read, 1)
		self.assertEqual(perm.write, 1)
		self.assertEqual(perm.create, 0)
		self.assertEqual(perm.delete, 0)

	def test_valid_boundaries_are_accepted(self):
		for fieldname, value in VALID_BOUNDARIES.items():
			with self.subTest(field=fieldname, value=value):
				settings = frappe.get_single(DOCTYPE)
				settings.set(fieldname, value)
				settings.save(ignore_permissions=True)

	def test_invalid_boundaries_are_rejected(self):
		for fieldname, value in INVALID_BOUNDARIES.items():
			with self.subTest(field=fieldname, value=value):
				settings = frappe.get_single(DOCTYPE)
				settings.set(fieldname, value)
				with self.assertRaises(frappe.ValidationError):
					settings.save(ignore_permissions=True)

	def test_pos_print_operator_cannot_read_or_write(self):
		user = self._create_user("pdp.operator@example.test", "POS Print Operator")

		try:
			frappe.set_user(user.name)
			self.assertFalse(frappe.has_permission(DOCTYPE, "read", user=user.name))
			self.assertFalse(frappe.has_permission(DOCTYPE, "write", user=user.name))
		finally:
			frappe.set_user("Administrator")

	def test_pos_print_manager_cannot_read_or_write(self):
		user = self._create_user("pdp.manager@example.test", "POS Print Manager")

		try:
			frappe.set_user(user.name)
			self.assertFalse(frappe.has_permission(DOCTYPE, "read", user=user.name))
			self.assertFalse(frappe.has_permission(DOCTYPE, "write", user=user.name))
		finally:
			frappe.set_user("Administrator")

	def _create_user(self, email, role):
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
		user.reload()
		return user


def _expected_default(spec):
	# Int/Check: compare as integer; Select/Data: compare raw string default.
	if spec[0] in ("Int", "Check"):
		return int(spec[1])
	return spec[1]
