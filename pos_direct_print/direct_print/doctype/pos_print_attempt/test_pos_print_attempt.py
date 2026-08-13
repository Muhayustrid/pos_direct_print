import uuid

import frappe
from frappe.exceptions import DuplicateEntryError, UniqueValidationError
from frappe.tests import IntegrationTestCase

DOCTYPE = "POS Print Attempt"
TABLE_NAME = "tabPOS Print Attempt"

# fieldname -> (fieldtype, reqd, default, options)
FIELD_SPECS = {
	"attempt_id": ("Data", 1, None, None),
	"job": ("Link", 1, None, "POS Print Job"),
	"attempt_no": ("Int", 1, None, None),
	"terminal": ("Link", 1, None, "POS Print Terminal"),
	"driver_key": ("Data", 1, None, None),
	"outcome": (
		"Select",
		1,
		"STARTED",
		"STARTED\nBLOCKED\nFAILED_SAFE\nUNCERTAIN\nSUCCEEDED\nFALLBACK_BROWSER\nCANCELLED",
	),
	"phase_reached": (
		"Select",
		1,
		"RESERVATION",
		"RESERVATION\nRECEIPT\nPREFLIGHT\nPRINT\nVERIFY\nFALLBACK",
	),
	"content_started": ("Check", 1, "0", None),
	"content_completed": ("Check", 1, "0", None),
	"normalized_status_before": ("Data", 0, None, None),
	"normalized_status_after": ("Data", 0, None, None),
	"raw_status_before": ("Small Text", 0, None, None),
	"raw_status_after": ("Small Text", 0, None, None),
	"error_code": ("Data", 0, None, None),
	"error_detail": ("Long Text", 0, None, None),
	"retry_class": ("Select", 1, "NONE", "NONE\nAUTO_SAFE\nMANUAL_SAFE\nREPRINT_ONLY"),
	"client_session_id": ("Data", 0, None, None),
	"browser_tab_id": ("Data", 0, None, None),
	"paired_client_id": ("Data", 0, None, None),
	"driver_version": ("Data", 0, None, None),
	"asset_version": ("Data", 0, None, None),
	"started_at": ("Datetime", 1, None, None),
	"finished_at": ("Datetime", 0, None, None),
	"duration_ms": ("Int", 0, None, None),
	"metadata_json": ("Long Text", 0, None, None),
}

SEARCH_INDEXED_FIELDS = {
	"attempt_id",
	"job",
	"attempt_no",
	"terminal",
	"driver_key",
	"outcome",
	"phase_reached",
	"content_started",
	"normalized_status_before",
	"normalized_status_after",
	"error_code",
	"retry_class",
	"client_session_id",
	"browser_tab_id",
	"paired_client_id",
	"started_at",
	"finished_at",
}

EXPECTED_COMPOSITE_INDEXES = {
	"IDX_ATT_01": ["job", "started_at"],
	"IDX_ATT_02": ["terminal", "started_at"],
	"IDX_ATT_03": ["outcome", "started_at"],
	"IDX_ATT_04": ["error_code", "started_at"],
}


class TestPOSPrintAttempt(IntegrationTestCase):
	def test_doctype_metadata_is_regular_and_non_submittable(self):
		meta = frappe.get_meta(DOCTYPE)

		self.assertFalse(meta.issingle)
		self.assertFalse(meta.is_submittable)
		self.assertEqual(meta.module, "Direct Print")
		self.assertEqual(meta.autoname, "field:attempt_id")

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

	def test_defaults_applied_on_new_attempt(self):
		attempt = _new_attempt("ATT-DEF-01")

		self.assertEqual(attempt.outcome, "STARTED")
		self.assertEqual(attempt.phase_reached, "RESERVATION")
		self.assertEqual(attempt.retry_class, "NONE")
		self.assertEqual(attempt.content_started, 0)
		self.assertEqual(attempt.content_completed, 0)
		self.assertEqual(attempt.name, "ATT-DEF-01")

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
				AND INDEX_NAME IN ("IDX_ATT_UNIQUE_01", "IDX_ATT_01", "IDX_ATT_02", "IDX_ATT_03", "IDX_ATT_04")
			ORDER BY INDEX_NAME, SEQ_IN_INDEX
			""",
			(TABLE_NAME,),
			as_dict=True,
		)

		index_columns = {}
		for row in rows:
			index_columns.setdefault(row.INDEX_NAME, []).append(row.COLUMN_NAME)

		self.assertEqual(index_columns.get("IDX_ATT_UNIQUE_01"), ["job", "attempt_no"])

		for index_name, columns in EXPECTED_COMPOSITE_INDEXES.items():
			with self.subTest(index=index_name):
				self.assertEqual(index_columns.get(index_name), columns)

	def test_attempt_id_unique_constraint(self):
		# A-AT-02: unique constraint on attempt_id.
		_new_attempt("ATT-UNIQ-01")

		with self.assertRaises(DuplicateEntryError):
			_new_attempt("ATT-UNIQ-01")

	def test_job_attempt_no_unique_constraint(self):
		job = _job()
		_new_attempt("ATT-PAIR-01", job=job, attempt_no=1)

		with self.assertRaises(UniqueValidationError):
			_new_attempt("ATT-PAIR-02", job=job, attempt_no=1)

		second = _new_attempt("ATT-PAIR-03", job=job, attempt_no=2)
		self.assertEqual(second.attempt_no, 2)

	def test_attempt_no_must_be_positive(self):
		attempt = _attempt_doc("ATT-NO-01", attempt_no=0)
		with self.assertRaises(frappe.ValidationError):
			attempt.insert(ignore_permissions=True)

	def test_duration_ms_lower_bound_rejected(self):
		attempt = _attempt_doc("ATT-DUR-01", duration_ms=-1)
		with self.assertRaises(frappe.ValidationError):
			attempt.insert(ignore_permissions=True)

	def test_invalid_select_values_rejected(self):
		for fieldname, value in (
			("outcome", "NOPE"),
			("phase_reached", "NOWHERE"),
			("retry_class", "ALWAYS"),
		):
			with self.subTest(field=fieldname):
				attempt = _attempt_doc(f"ATT-ENUM-{fieldname}", **{fieldname: value})
				with self.assertRaises(frappe.ValidationError):
					attempt.insert(ignore_permissions=True)

	def test_permission_matrix(self):
		# A.31.16. Attempt is a system-managed immutable audit record: read only for
		# System Manager and scoped Manager, create/write/delete denied to every role
		# including System Manager. Attempts may only be created by the
		# JobCoordinator/backend service. Operator gets no direct DocType access.
		# Level 0 rows only; permlevel 1 rows are asserted in core.test_projections.
		perms = {perm.role: perm for perm in frappe.get_meta(DOCTYPE).permissions if not perm.permlevel}

		self.assertCountEqual(perms.keys(), ["System Manager", "POS Print Manager"])

		for role, perm in perms.items():
			with self.subTest(role=role):
				self.assertEqual(perm.read, 1)
				self.assertEqual(perm.create, 0)
				self.assertEqual(perm.write, 0)
				self.assertEqual(perm.delete, 0)

	def test_attempt_audit_immutability(self):
		# A-AT-23. Create/Write/Delete denied for Operator, Manager, and System
		# Manager alike. Docs are re-fetched inside each session: a document inserted
		# with ignore_permissions=True keeps that flag on the object, which would make
		# a later save() skip permission checks entirely.
		attempt_name = _new_attempt("ATT-IMMUT-01").name

		operator = self._create_user("pdp.operator.attempt@example.test", "POS Print Operator")
		manager = self._create_user("pdp.manager.attempt@example.test", "POS Print Manager")
		system_manager = self._create_user("pdp.sysmanager.attempt@example.test", "System Manager")

		try:
			for user in (operator, manager, system_manager):
				with self.subTest(user=user.email):
					frappe.set_user(user.name)
					with self.assertRaises(frappe.PermissionError):
						attempt = frappe.get_doc(DOCTYPE, attempt_name)
						attempt.set("error_code", "TAMPERED")
						attempt.save()
					with self.assertRaises(frappe.PermissionError):
						frappe.delete_doc(DOCTYPE, attempt_name)
		finally:
			frappe.set_user("Administrator")

		self.assertIsNone(frappe.db.get_value(DOCTYPE, attempt_name, "error_code"))

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


def _terminal():
	suffix = uuid.uuid4().hex[:8]
	terminal = frappe.get_doc(
		{
			"doctype": "POS Print Terminal",
			"terminal_id": f"TERM-{suffix}",
			"terminal_label": f"Terminal {suffix}",
			"company": _company(),
			"pos_profile": _pos_profile(),
		}
	).insert(ignore_permissions=True)
	return terminal.name


def _job():
	suffix = uuid.uuid4().hex[:8]
	job = frappe.get_doc(
		{
			"doctype": "POS Print Job",
			"job_id": f"JOB-{suffix}",
			"idempotency_key": f"idem-JOB-{suffix}",
			"reference_doctype": "Company",
			"reference_name": _company(),
			"company": _company(),
			"pos_profile": _pos_profile(),
			"terminal": _terminal(),
			"requested_by": "Administrator",
			"source": "POS_AUTO",
			"driver_key": "imin_v1",
		}
	).insert(ignore_permissions=True)
	return job.name


def _attempt_doc(attempt_id, **overrides):
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"attempt_id": attempt_id,
			"job": _job(),
			"attempt_no": 1,
			"terminal": _terminal(),
			"driver_key": "imin_v1",
			"started_at": "2026-08-10 10:00:00",
		}
	)
	doc.update(overrides)
	return doc


def _new_attempt(attempt_id, **overrides):
	return _attempt_doc(attempt_id, **overrides).insert(ignore_permissions=True)


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
