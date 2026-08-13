import uuid

import frappe
from frappe.exceptions import DuplicateEntryError
from frappe.tests import IntegrationTestCase

from pos_direct_print.core import terminal_scope

DOCTYPE = "POS Print Terminal"
TABLE_NAME = "tabPOS Print Terminal"

# fieldname -> (fieldtype, reqd, default, options)
FIELD_SPECS = {
	"terminal_tab": ("Tab Break", 0, None, None),
	"identity_section": ("Section Break", 0, None, None),
	"terminal_id": ("Data", 1, None, None),
	"terminal_label": ("Data", 1, None, None),
	"identity_column": ("Column Break", 0, None, None),
	"enabled": ("Check", 1, "1", None),
	"binding_section": ("Section Break", 0, None, None),
	"company": ("Link", 1, None, "Company"),
	"pos_profile": ("Link", 1, None, "POS Profile"),
	"extra_pos_profiles": ("Table", 0, None, "POS Print Terminal Profile"),
	"hardware_tab": ("Tab Break", 0, None, None),
	"hardware_section": ("Section Break", 0, None, None),
	"driver_key": ("Data", 1, "imin_v1", None),
	"transport": ("Select", 1, "SPI", "UNKNOWN\nUSB\nSPI\nBLUETOOTH"),
	"hardware_column": ("Column Break", 0, None, None),
	"paper_width_mm": ("Select", 1, "58", "UNKNOWN\n58\n80"),
	"cutter_capability": ("Select", 1, "UNKNOWN", "UNKNOWN\nSUPPORTED\nUNSUPPORTED"),
	"diagnostics_section": ("Section Break", 0, None, None),
	"device_model": ("Data", 0, None, None),
	"device_serial": ("Data", 0, None, None),
	"android_version": ("Data", 0, None, None),
	"diagnostics_column": ("Column Break", 0, None, None),
	"rom_build": ("Data", 0, None, None),
	"plugin_version": ("Data", 0, None, None),
	"browser_version": ("Data", 0, None, None),
	"webview_version": ("Data", 0, None, None),
	"qualification_tab": ("Tab Break", 0, None, None),
	"qualification_section": ("Section Break", 0, None, None),
	"qualification_status": ("Select", 1, "UNVERIFIED", "UNVERIFIED\nQUALIFIED\nBLOCKED"),
	"qualification_revision": ("Data", 0, None, None),
	"qualification_column": ("Column Break", 0, None, None),
	"capability_schema_version": ("Int", 1, "1", None),
	"capabilities_json": ("Long Text", 0, None, None),
	"notes": ("Small Text", 0, None, None),
	"runtime_tab": ("Tab Break", 0, None, None),
	"runtime_section": ("Section Break", 0, None, None),
	"last_seen_at": ("Datetime", 0, None, None),
	"last_health_state": ("Select", 1, "UNKNOWN", "UNKNOWN\nREADY\nDEGRADED\nOFFLINE"),
	"runtime_column": ("Column Break", 0, None, None),
	"paired_client_id": ("Data", 0, None, None),
	"pairing_status": ("Select", 1, "UNPAIRED", "UNPAIRED\nPAIRED\nREVOKED"),
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
		self.assertEqual(meta.module, "Direct Print")
		self.assertEqual(meta.autoname, "field:terminal_id")

	def test_field_schema_matches_spec(self):
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
		# SPI and 58 mm are the fleet reality, so a new terminal starts there
		# instead of forcing every operator to pick the same two values.
		self.assertEqual(terminal.transport, "SPI")
		self.assertEqual(terminal.paper_width_mm, "58")
		self.assertEqual(terminal.cutter_capability, "UNKNOWN")
		self.assertEqual(terminal.qualification_status, "UNVERIFIED")
		self.assertEqual(terminal.capability_schema_version, 1)
		self.assertEqual(terminal.last_health_state, "UNKNOWN")
		self.assertEqual(terminal.pairing_status, "UNPAIRED")
		self.assertEqual(terminal.extra_pos_profiles, [])

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

	def test_extra_profile_child_index_exists(self):
		rows = frappe.db.sql(
			"""
			SELECT COLUMN_NAME
			FROM information_schema.STATISTICS
			WHERE TABLE_SCHEMA = DATABASE()
				AND TABLE_NAME = "tabPOS Print Terminal Profile"
				AND INDEX_NAME = "IDX_TERMPROF_01"
			ORDER BY SEQ_IN_INDEX
			""",
			as_dict=True,
		)
		self.assertEqual([row.COLUMN_NAME for row in rows], ["pos_profile", "parent"])

	def test_extra_profile_grid_column_is_wide_enough_to_read(self):
		# Frappe's grid defaults a Link column to 2 of 12 units, which truncated the
		# POS Profile name to "Outlet ..." in the only column the table has. The
		# table shows one field, so that field gets the room.
		field = frappe.get_meta("POS Print Terminal Profile").get_field("pos_profile")
		self.assertEqual(field.columns, 8)
		self.assertEqual(field.in_list_view, 1)

	def test_extra_profiles_widen_what_the_terminal_serves(self):
		# One counter, two outlets, one printer: the second outlet is an extra row
		# rather than a second terminal.
		other = _second_pos_profile()
		terminal = _new_terminal("TERM-MULTI-01")
		terminal.append("extra_pos_profiles", {"pos_profile": other})
		terminal.save(ignore_permissions=True)

		self.assertEqual(terminal_scope.served_pos_profiles(terminal.name), [terminal.pos_profile, other])
		self.assertTrue(terminal_scope.serves_pos_profile(terminal.name, other))

	def test_extra_profile_is_optional_and_a_blank_row_is_dropped(self):
		# The table is an option, not a requirement. A row left blank — or emptied
		# to undo an extra outlet — must save, because a reqd child field would
		# trap the operator in a grid they cannot clear.
		terminal = _new_terminal("TERM-MULTI-05")
		terminal.append("extra_pos_profiles", {})
		terminal.save(ignore_permissions=True)

		self.assertEqual(terminal.extra_pos_profiles, [])
		self.assertEqual(terminal_scope.served_pos_profiles(terminal.name), [terminal.pos_profile])

	def test_emptying_an_extra_profile_row_removes_it(self):
		other = _second_pos_profile()
		terminal = _new_terminal("TERM-MULTI-06")
		terminal.append("extra_pos_profiles", {"pos_profile": other})
		terminal.save(ignore_permissions=True)
		self.assertTrue(terminal_scope.serves_pos_profile(terminal.name, other))

		terminal.extra_pos_profiles[0].pos_profile = None
		terminal.save(ignore_permissions=True)

		self.assertEqual(terminal.extra_pos_profiles, [])
		self.assertFalse(terminal_scope.serves_pos_profile(terminal.name, other))

	def test_blank_row_does_not_shift_the_remaining_row_indexes(self):
		other = _second_pos_profile()
		terminal = _new_terminal("TERM-MULTI-07")
		terminal.append("extra_pos_profiles", {})
		terminal.append("extra_pos_profiles", {"pos_profile": other})
		terminal.save(ignore_permissions=True)

		self.assertEqual([row.pos_profile for row in terminal.extra_pos_profiles], [other])
		self.assertEqual([row.idx for row in terminal.extra_pos_profiles], [1])

	def test_extra_profile_may_not_repeat_the_default(self):
		terminal = _new_terminal("TERM-MULTI-02")
		terminal.append("extra_pos_profiles", {"pos_profile": terminal.pos_profile})

		with self.assertRaises(frappe.ValidationError):
			terminal.save(ignore_permissions=True)

	def test_extra_profile_may_not_repeat_itself(self):
		other = _second_pos_profile()
		terminal = _new_terminal("TERM-MULTI-03")
		terminal.append("extra_pos_profiles", {"pos_profile": other})
		terminal.append("extra_pos_profiles", {"pos_profile": other})

		with self.assertRaises(frappe.ValidationError):
			terminal.save(ignore_permissions=True)

	def test_extra_profile_from_another_company_is_refused(self):
		# Company is the outer boundary of every scope check, so an extra row must
		# never be the way a print crosses it.
		foreign = frappe.db.get_value("POS Profile", {"company": ("!=", _company())}, "name")
		if not foreign:
			self.skipTest("site has no POS Profile outside the test Company")
		terminal = _new_terminal("TERM-MULTI-04")
		terminal.append("extra_pos_profiles", {"pos_profile": foreign})

		with self.assertRaises(frappe.ValidationError):
			terminal.save(ignore_permissions=True)

	def test_second_qualified_terminal_on_one_outlet_is_refused(self):
		# Terminal resolution asks for Company + POS Profile and takes the oldest
		# match, so a second QUALIFIED terminal on one outlet would lose that race
		# in silence and print Jobs recorded against the other device.
		outlet = _isolated_pos_profile()
		first = _qualified_terminal("TERM-ONE-01", outlet)

		second = _new_terminal("TERM-ONE-02")
		second.pos_profile = outlet
		second.qualification_status = "QUALIFIED"

		with self.assertRaises(frappe.ValidationError) as ctx:
			second.save(ignore_permissions=True)
		self.assertIn("already served by terminal", str(ctx.exception))
		self.assertIn(first.name, str(ctx.exception))

	def test_collision_through_an_extra_row_is_refused_too(self):
		# The extra table must not be the back door into the collision the default
		# binding is checked for.
		outlet = _isolated_pos_profile()
		_qualified_terminal("TERM-ONE-03", outlet)

		other = _qualified_terminal("TERM-ONE-04", _isolated_pos_profile())
		other.append("extra_pos_profiles", {"pos_profile": outlet})

		with self.assertRaises(frappe.ValidationError) as ctx:
			other.save(ignore_permissions=True)
		self.assertIn("already served by terminal", str(ctx.exception))

	def test_unverified_terminal_may_share_an_outlet(self):
		# Only an enabled QUALIFIED terminal can win the lookup, so an UNVERIFIED
		# one cannot steal a Job and is free to overlap — that is how a replacement
		# device is staged before it takes over.
		outlet = _isolated_pos_profile()
		_qualified_terminal("TERM-ONE-05", outlet)

		staged = _new_terminal("TERM-ONE-06")
		staged.pos_profile = outlet
		staged.save(ignore_permissions=True)

		self.assertEqual(staged.qualification_status, "UNVERIFIED")

	def test_disabled_terminal_may_share_an_outlet(self):
		# A retired terminal keeps its QUALIFIED history — enabled = 0 is how it is
		# taken out of service — so it must not block its own replacement.
		outlet = _isolated_pos_profile()
		retired = _new_terminal("TERM-ONE-07")
		retired.pos_profile = outlet
		retired.qualification_status = "QUALIFIED"
		retired.enabled = 0
		retired.save(ignore_permissions=True)

		replacement = _qualified_terminal("TERM-ONE-08", outlet)

		self.assertEqual(
			terminal_scope.terminal_names_serving(outlet, company=_company(), qualified=True),
			[replacement.name],
		)

	def test_resaving_the_only_terminal_for_an_outlet_is_allowed(self):
		# The check must skip the row being saved, otherwise a terminal could never
		# be edited again once it is QUALIFIED.
		terminal = _qualified_terminal("TERM-ONE-09", _isolated_pos_profile())

		terminal.terminal_label = "Renamed after qualification"
		terminal.save(ignore_permissions=True)

		self.assertEqual(terminal.terminal_label, "Renamed after qualification")

	def test_extra_profiles_do_not_widen_manager_doctype_reads(self):
		# Frappe applies the POS Profile User Permission to the terminal's own
		# pos_profile Link field, so an extra row cannot grant a Manager a read on
		# a terminal bound elsewhere. Terminal administration stays System Manager
		# work (A.31.5); printing scope lives in core.terminal_scope instead.
		default_outlet = _second_pos_profile()
		managed_outlet = _pos_profile()
		manager = self._create_user("pdp.manager.multi@example.test", "POS Print Manager")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": manager.name,
				"allow": "POS Profile",
				"for_value": managed_outlet,
			}
		).insert(ignore_permissions=True)

		shared = _new_terminal("TERM-SCOPE-01")
		shared.pos_profile = default_outlet
		shared.append("extra_pos_profiles", {"pos_profile": managed_outlet})
		shared.save(ignore_permissions=True)

		try:
			frappe.set_user(manager.name)
			frappe.clear_cache(user=manager.name)
			visible = {row.name for row in frappe.get_list(DOCTYPE, fields=["name"], limit=0)}
			self.assertNotIn(shared.name, visible)
			with self.assertRaises(frappe.PermissionError):
				frappe.get_doc(DOCTYPE, shared.name).check_permission("read")
		finally:
			frappe.set_user("Administrator")

		# The printing rule is the one that widened, and it did.
		self.assertTrue(terminal_scope.serves_pos_profile(shared.name, managed_outlet))

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


def _second_pos_profile():
	"""A different POS Profile in the same Company, created if the site lacks one."""
	default = _pos_profile()
	existing = frappe.db.get_value("POS Profile", {"company": _company(), "name": ("!=", default)}, "name")
	if existing:
		return existing
	profile = frappe.copy_doc(frappe.get_doc("POS Profile", default))
	profile.name = "PDP Terminal Second Outlet"
	profile.set("applicable_for_users", [])
	return profile.insert(ignore_permissions=True).name


def _isolated_pos_profile():
	"""A POS Profile no other terminal serves.

	The site's own profiles already carry QUALIFIED terminals, so a test about
	the one-terminal-per-outlet rule needs an outlet of its own to collide on.
	The group tables are cleared because ERPNext refuses a copy that repeats an
	Item Group, and this profile only ever has to exist, not sell anything.
	"""
	source = frappe.get_doc("POS Profile", _pos_profile())
	profile = frappe.copy_doc(source)
	profile.name = f"PDP Isolated Outlet {uuid.uuid4().hex[:8]}"
	profile.set("applicable_for_users", [])
	profile.set("item_groups", [])
	profile.set("customer_groups", [])
	return profile.insert(ignore_permissions=True).name


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


def _qualified_terminal(terminal_id, pos_profile):
	terminal = _new_terminal(terminal_id)
	terminal.pos_profile = pos_profile
	terminal.qualification_status = "QUALIFIED"
	return terminal.save(ignore_permissions=True)


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
