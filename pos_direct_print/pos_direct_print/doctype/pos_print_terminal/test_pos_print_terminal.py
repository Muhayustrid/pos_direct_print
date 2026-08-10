import frappe
from frappe.exceptions import DuplicateEntryError
from frappe.tests import IntegrationTestCase

DOCTYPE = "POS Print Terminal"
TABLE_NAME = "tabPOS Print Terminal"

# fieldname -> (fieldtype, reqd, default, options)
FIELD_SPECS = {
	"terminal_id": ("Data", 1, None, None),
	"terminal_label": ("Data", 1, None, None),
	"enabled": ("Check", 1, "1", None),
	"company": ("Link", 1, None, "Company"),
	"pos_profile": ("Link", 1, None, "POS Profile"),
	"driver_key": ("Data", 1, "imin_v1", None),
	"device_model": ("Data", 0, None, None),
	"device_serial": ("Data", 0, None, None),
	"android_version": ("Data", 0, None, None),
	"rom_build": ("Data", 0, None, None),
	"plugin_version": ("Data", 0, None, None),
	"browser_version": ("Data", 0, None, None),
	"webview_version": ("Data", 0, None, None),
	"transport": ("Select", 1, "UNKNOWN", "UNKNOWN\nUSB\nSPI\nBLUETOOTH"),
	"paper_width_mm": ("Select", 1, "UNKNOWN", "UNKNOWN\n58\n80"),
	"cutter_capability": ("Select", 1, "UNKNOWN", "UNKNOWN\nSUPPORTED\nUNSUPPORTED"),
	"qualification_status": ("Select", 1, "UNVERIFIED", "UNVERIFIED\nQUALIFIED\nBLOCKED"),
	"qualification_revision": ("Data", 0, None, None),
	"capability_schema_version": ("Int", 1, "1", None),
	"capabilities_json": ("Long Text", 0, None, None),
	"last_seen_at": ("Datetime", 0, None, None),
	"last_health_state": ("Select", 1, "UNKNOWN", "UNKNOWN\nREADY\nDEGRADED\nOFFLINE"),
	"paired_client_id": ("Data", 0, None, None),
	"pairing_status": ("Select", 1, "UNPAIRED", "UNPAIRED\nPAIRED\nREVOKED"),
	"notes": ("Small Text", 0, None, None),
}

SEARCH_INDEXED_FIELDS = {
	"terminal_id",
	"terminal_label",
	"enabled",
	"company",
	"pos_profile",
	"driver_key",
	"device_model",
	"device_serial",
	"qualification_status",
	"last_seen_at",
	"last_health_state",
	"paired_client_id",
	"pairing_status",
}


class TestPOSPrintTerminal(IntegrationTestCase):
	def test_doctype_metadata_is_regular_and_non_submittable(self):
		meta = frappe.get_meta(DOCTYPE)

		self.assertFalse(meta.issingle)
		self.assertFalse(meta.is_submittable)
		self.assertEqual(meta.module, "Pos Direct Print")
		self.assertEqual(meta.autoname, "field:terminal_id")

	def test_has_exactly_twenty_five_fields_with_schema(self):
		meta = frappe.get_meta(DOCTYPE)

		fields = {field.fieldname: field for field in meta.fields}

		self.assertEqual(len(fields), len(FIELD_SPECS))
		self.assertCountEqual(fields.keys(), FIELD_SPECS.keys())

		for fieldname, (fieldtype, reqd, default, options) in FIELD_SPECS.items():
			field = fields[fieldname]
			with self.subTest(field=fieldname):
				self.assertEqual(field.fieldtype, fieldtype)
				self.assertEqual(field.reqd, reqd)
				self.assertEqual(field.default, default)
				if options is not None:
					self.assertEqual(field.options, options)

	def test_defaults_applied_on_new_terminal(self):
		terminal = _new_terminal("TERM-DEF-01")

		self.assertEqual(terminal.enabled, 1)
		self.assertEqual(terminal.driver_key, "imin_v1")
		self.assertEqual(terminal.transport, "UNKNOWN")
		self.assertEqual(terminal.paper_width_mm, "UNKNOWN")
		self.assertEqual(terminal.cutter_capability, "UNKNOWN")
		self.assertEqual(terminal.qualification_status, "UNVERIFIED")
		self.assertEqual(terminal.capability_schema_version, 1)
		self.assertEqual(terminal.last_health_state, "UNKNOWN")
		self.assertEqual(terminal.pairing_status, "UNPAIRED")

	def test_single_column_indexes_exist(self):
		for fieldname in SEARCH_INDEXED_FIELDS:
			with self.subTest(field=fieldname):
				self.assertTrue(_has_leading_index(fieldname))

	def test_composite_indexes_exist(self):
		rows = frappe.db.sql(
			"""
			SELECT INDEX_NAME, COLUMN_NAME
			FROM information_schema.STATISTICS
			WHERE TABLE_SCHEMA = DATABASE()
				AND TABLE_NAME = %s
				AND INDEX_NAME IN ("IDX_TERM_01", "IDX_TERM_02")
			ORDER BY INDEX_NAME, SEQ_IN_INDEX
			""",
			(TABLE_NAME,),
			as_dict=True,
		)

		index_columns = {}
		for row in rows:
			index_columns.setdefault(row.INDEX_NAME, []).append(row.COLUMN_NAME)

		self.assertEqual(index_columns.get("IDX_TERM_01"), ["company", "pos_profile", "enabled"])
		self.assertEqual(index_columns.get("IDX_TERM_02"), ["paired_client_id", "enabled"])

	def test_terminal_id_unique_constraint(self):
		# A-AT-02: unique constraint on terminal_id.
		_new_terminal("TERM-UNIQ-01")

		duplicate = frappe.get_doc(
			{
				"doctype": DOCTYPE,
				"terminal_id": "TERM-UNIQ-01",
				"terminal_label": "Duplicate",
				"company": _company(),
				"pos_profile": _pos_profile(),
			}
		)

		with self.assertRaises(DuplicateEntryError):
			duplicate.insert(ignore_permissions=True)

	def test_device_serial_not_unique(self):
		first = _new_terminal("TERM-SER-01")
		first.device_serial = "SN-SHARED"
		first.save(ignore_permissions=True)

		second = _new_terminal("TERM-SER-02")
		second.device_serial = "SN-SHARED"
		second.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value(DOCTYPE, second.name, "device_serial"), "SN-SHARED")

	def test_paired_client_id_not_unique(self):
		first = _new_terminal("TERM-PAIR-01")
		first.paired_client_id = "client-shared"
		first.save(ignore_permissions=True)

		second = _new_terminal("TERM-PAIR-02")
		second.paired_client_id = "client-shared"
		second.save(ignore_permissions=True)

		self.assertEqual(frappe.db.get_value(DOCTYPE, second.name, "paired_client_id"), "client-shared")

	def test_permission_matrix(self):
		# A.31.5. Delete is withheld from every role: retired terminals are disabled
		# via enabled = 0 so historical Job/Attempt references stay valid.
		# Operator gets no direct DocType access at all (runtime projection only).
		# Level 0 rows only; permlevel 1 rows are asserted in core.test_projections.
		perms = {perm.role: perm for perm in frappe.get_meta(DOCTYPE).permissions if not perm.permlevel}

		self.assertCountEqual(perms.keys(), ["System Manager", "POS Print Manager"])

		system_manager = perms["System Manager"]
		self.assertEqual(system_manager.read, 1)
		self.assertEqual(system_manager.create, 1)
		self.assertEqual(system_manager.write, 1)
		self.assertEqual(system_manager.delete, 0)

		manager = perms["POS Print Manager"]
		self.assertEqual(manager.read, 1)
		self.assertEqual(manager.create, 0)
		self.assertEqual(manager.write, 0)
		self.assertEqual(manager.delete, 0)

	def test_no_delete_permission_for_any_role(self):
		for perm in frappe.get_meta(DOCTYPE).permissions:
			with self.subTest(role=perm.role):
				self.assertEqual(perm.delete, 0)

	def test_pos_print_operator_cannot_modify_terminal(self):
		# A-AT-19. Operator has no Terminal permission row at all, so every write is
		# denied. The doc is re-fetched inside the operator session: a document
		# inserted with ignore_permissions=True keeps that flag on the object, which
		# would make a later save() skip permission checks entirely.
		terminal_name = _new_terminal("TERM-OPR-01").name

		user = self._create_user("pdp.operator.terminal@example.test", "POS Print Operator")

		try:
			frappe.set_user(user.name)
			for fieldname, value in (
				("qualification_status", "QUALIFIED"),
				("driver_key", "other_driver"),
				("capabilities_json", '{"width_mm": 58}'),
				("device_serial", "SN-OPR-01"),
				("rom_build", "ROM-OPR-01"),
			):
				with self.subTest(field=fieldname):
					with self.assertRaises(frappe.PermissionError):
						terminal = frappe.get_doc(DOCTYPE, terminal_name)
						terminal.set(fieldname, value)
						terminal.save()

			self.assertEqual(
				frappe.db.get_value(DOCTYPE, terminal_name, "qualification_status"), "UNVERIFIED"
			)
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


def _company():
	return "PT. JUARA ROTI INDONESIA"


def _pos_profile():
	return frappe.db.get_value("POS Profile", {"company": _company()}, "name") or frappe.db.get_value(
		"POS Profile", {}, "name"
	)


def _new_terminal(terminal_id):
	return frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"terminal_id": terminal_id,
			"terminal_label": f"Terminal {terminal_id}",
			"company": _company(),
			"pos_profile": _pos_profile(),
		}
	).insert(ignore_permissions=True)


def _has_leading_index(fieldname):
	return bool(
		frappe.db.sql(
			"""
			SELECT 1
			FROM information_schema.STATISTICS
			WHERE TABLE_SCHEMA = DATABASE()
				AND TABLE_NAME = %s
				AND COLUMN_NAME = %s
				AND SEQ_IN_INDEX = 1
			LIMIT 1
			""",
			(TABLE_NAME, fieldname),
		)
	)
