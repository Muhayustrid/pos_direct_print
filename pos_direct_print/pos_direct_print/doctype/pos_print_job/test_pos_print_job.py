import uuid

import frappe
from frappe.exceptions import DuplicateEntryError
from frappe.tests import IntegrationTestCase

DOCTYPE = "POS Print Job"
TABLE_NAME = "tabPOS Print Job"

# fieldname -> (fieldtype, reqd, default, options)
FIELD_SPECS = {
	"job_id": ("Data", 1, None, None),
	"idempotency_key": ("Data", 1, None, None),
	"reference_doctype": ("Link", 1, None, "DocType"),
	"reference_name": ("Dynamic Link", 1, None, "reference_doctype"),
	"company": ("Link", 1, None, "Company"),
	"pos_profile": ("Link", 0, None, "POS Profile"),
	"terminal": ("Link", 1, None, "POS Print Terminal"),
	"requested_by": ("Link", 1, None, "User"),
	"source": ("Select", 1, None, "POS_AUTO\nPOS_MANUAL\nREPRINT_UI\nTEST_UI\nAPI"),
	"job_type": ("Select", 1, "ORIGINAL", "ORIGINAL\nREPRINT\nTEST"),
	"parent_job": ("Link", 0, None, "POS Print Job"),
	"reprint_reason": ("Small Text", 0, None, None),
	"driver_key": ("Data", 1, None, None),
	"status": (
		"Select",
		1,
		"CREATED",
		"CREATED\nRESERVED\nPREFLIGHT\nBLOCKED\nPRINTING\nVERIFYING\nFAILED_SAFE\nUNCERTAIN\nSUCCEEDED\nFALLBACK_BROWSER\nCANCELLED",
	),
	"status_reason_code": ("Data", 0, None, None),
	"reservation_owner": ("Data", 0, None, None),
	"reserved_at": ("Datetime", 0, None, None),
	"reserved_until": ("Datetime", 0, None, None),
	"attempt_count": ("Int", 1, "0", None),
	"safe_retry_count": ("Int", 1, "0", None),
	"content_may_have_printed": ("Check", 1, "0", None),
	"receipt_schema_version": ("Int", 1, "1", None),
	"receipt_hash": ("Data", 0, None, None),
	"receipt_snapshot": ("Long Text", 0, None, None),
	"started_at": ("Datetime", 0, None, None),
	"finished_at": ("Datetime", 0, None, None),
	"last_error_code": ("Data", 0, None, None),
	"last_error_phase": (
		"Select",
		0,
		None,
		"VALIDATION\nRESERVATION\nRECEIPT\nPREFLIGHT\nPRINT\nVERIFY\nFALLBACK",
	),
	"last_error_detail": ("Long Text", 0, None, None),
	"fallback_used": ("Check", 1, "0", None),
	"browser_fallback_at": ("Datetime", 0, None, None),
	"metadata_json": ("Long Text", 0, None, None),
}

SEARCH_INDEXED_FIELDS = {
	"job_id",
	"idempotency_key",
	"reference_doctype",
	"reference_name",
	"company",
	"pos_profile",
	"terminal",
	"requested_by",
	"source",
	"job_type",
	"parent_job",
	"driver_key",
	"status",
	"status_reason_code",
	"reservation_owner",
	"reserved_at",
	"reserved_until",
	"content_may_have_printed",
	"receipt_hash",
	"started_at",
	"finished_at",
	"last_error_code",
	"last_error_phase",
	"fallback_used",
}

EXPECTED_COMPOSITE_INDEXES = {
	"IDX_JOB_01": ["reference_doctype", "reference_name", "job_type"],
	"IDX_JOB_02": ["terminal", "status"],
	"IDX_JOB_03": ["terminal", "creation"],
	"IDX_JOB_04": ["reference_doctype", "reference_name", "creation"],
	"IDX_JOB_05": ["status", "reserved_until"],
}


class TestPOSPrintJob(IntegrationTestCase):
	def test_doctype_metadata_is_regular_and_non_submittable(self):
		meta = frappe.get_meta(DOCTYPE)

		self.assertFalse(meta.issingle)
		self.assertFalse(meta.is_submittable)
		self.assertEqual(meta.module, "Pos Direct Print")
		self.assertEqual(meta.autoname, "field:job_id")

	def test_has_exactly_thirty_two_fields_with_schema(self):
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

	def test_defaults_applied_on_new_job(self):
		job = _new_job("JOB-DEF-01")

		self.assertEqual(job.status, "CREATED")
		self.assertEqual(job.job_type, "ORIGINAL")
		self.assertEqual(job.attempt_count, 0)
		self.assertEqual(job.safe_retry_count, 0)
		self.assertEqual(job.content_may_have_printed, 0)
		self.assertEqual(job.receipt_schema_version, 1)
		self.assertEqual(job.fallback_used, 0)
		self.assertEqual(job.name, "JOB-DEF-01")

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
				AND INDEX_NAME IN ("IDX_JOB_01", "IDX_JOB_02", "IDX_JOB_03", "IDX_JOB_04", "IDX_JOB_05")
			ORDER BY INDEX_NAME, SEQ_IN_INDEX
			""",
			(TABLE_NAME,),
			as_dict=True,
		)

		index_columns = {}
		for row in rows:
			index_columns.setdefault(row.INDEX_NAME, []).append(row.COLUMN_NAME)

		for index_name, columns in EXPECTED_COMPOSITE_INDEXES.items():
			with self.subTest(index=index_name):
				self.assertEqual(index_columns.get(index_name), columns)

	def test_job_id_unique_constraint(self):
		# A-AT-02: unique constraint on job_id.
		_new_job("JOB-UNIQ-01")

		with self.assertRaises(DuplicateEntryError):
			_new_job("JOB-UNIQ-01")

	def test_idempotency_key_unique_constraint(self):
		# A-AT-02: unique constraint on idempotency_key.
		first = _new_job("JOB-IDEM-01")

		# name-level duplicates raise DuplicateEntryError; other unique fields are
		# wrapped by Frappe as UniqueValidationError.
		with self.assertRaises(frappe.UniqueValidationError):
			_new_job("JOB-IDEM-02", idempotency_key=first.idempotency_key)

	def test_reprint_requires_parent_job_and_reason(self):
		parent = _new_job("JOB-REPRINT-PARENT")

		without_parent = _job_doc("JOB-REPRINT-01", job_type="REPRINT")
		with self.assertRaises(frappe.ValidationError):
			without_parent.insert(ignore_permissions=True)

		without_reason = _job_doc("JOB-REPRINT-02", job_type="REPRINT", parent_job=parent.name)
		with self.assertRaises(frappe.ValidationError):
			without_reason.insert(ignore_permissions=True)

		reprint = _new_job(
			"JOB-REPRINT-03", job_type="REPRINT", parent_job=parent.name, reprint_reason="Paper jam"
		)
		self.assertEqual(reprint.parent_job, parent.name)

	def test_reservation_owner_required_from_reserved(self):
		without_owner = _job_doc("JOB-RESV-01", status="RESERVED")
		with self.assertRaises(frappe.ValidationError):
			without_owner.insert(ignore_permissions=True)

		with_owner = _new_job("JOB-RESV-02", status="RESERVED", reservation_owner="client-1")
		self.assertEqual(with_owner.reservation_owner, "client-1")

	def test_receipt_hash_requires_snapshot(self):
		without_snapshot = _job_doc("JOB-HASH-01", receipt_hash="abc123")
		with self.assertRaises(frappe.ValidationError):
			without_snapshot.insert(ignore_permissions=True)

		with_snapshot = _new_job("JOB-HASH-02", receipt_hash="abc123", receipt_snapshot='{"items": []}')
		self.assertEqual(with_snapshot.receipt_snapshot, '{"items": []}')

	def test_counter_lower_bound_rejected(self):
		job = _job_doc("JOB-COUNT-01", attempt_count=-1)
		with self.assertRaises(frappe.ValidationError):
			job.insert(ignore_permissions=True)

	def test_receipt_schema_version_minimum_rejected(self):
		job = _job_doc("JOB-SCHEMA-01", receipt_schema_version=0)
		with self.assertRaises(frappe.ValidationError):
			job.insert(ignore_permissions=True)

	def test_parent_job_cannot_be_self(self):
		job = _job_doc("JOB-SELF-01", job_type="REPRINT", parent_job="JOB-SELF-01", reprint_reason="x")
		with self.assertRaises(frappe.ValidationError):
			job.insert(ignore_permissions=True)

	def test_invalid_select_values_rejected(self):
		for fieldname, value in (
			("source", "NOPE"),
			("job_type", "WRONG"),
			("status", "BOGUS"),
			("last_error_phase", "NOWHERE"),
		):
			with self.subTest(field=fieldname):
				job = _job_doc(f"JOB-ENUM-{fieldname}", **{fieldname: value})
				with self.assertRaises(frappe.ValidationError):
					job.insert(ignore_permissions=True)

	def test_no_role_can_create_reprint_job_through_doctype_api(self):
		# A-AT-24 at the matrix boundary: no interactive role may create a Job — and
		# therefore no REPRINT Job — through the standard DocType API. Which caller
		# may request a REPRINT, and the scope check on the parent Job, is the
		# authorization boundary built in A1-08.
		parent_name = _new_job("JOB-REPRINT-AUTH-PARENT").name

		users = [
			self._create_user("pdp.operator.reprint@example.test", "POS Print Operator"),
			self._create_user("pdp.manager.reprint@example.test", "POS Print Manager"),
			self._create_user("pdp.sysmanager.reprint@example.test", "System Manager"),
		]

		try:
			for user in users:
				with self.subTest(user=user.email):
					frappe.set_user(user.name)
					reprint = _job_doc(
						f"JOB-REPRINT-AUTH-{user.name}",
						job_type="REPRINT",
						parent_job=parent_name,
						reprint_reason="Torn receipt",
					)
					with self.assertRaises(frappe.PermissionError):
						reprint.insert()
		finally:
			frappe.set_user("Administrator")

		# Parent job is never mutated into a reprint.
		self.assertEqual(frappe.db.get_value(DOCTYPE, parent_name, "job_type"), "ORIGINAL")

	def test_permission_matrix(self):
		# A.31.8 + A.31.22. Job is a system-managed audit record: read for all three
		# roles, create/write/delete denied to every role including System Manager.
		# Row-level scoping of those reads is enforced in A1-07, not here.
		# Level 0 rows only; permlevel 1 rows are asserted in core.test_projections.
		perms = {perm.role: perm for perm in frappe.get_meta(DOCTYPE).permissions if not perm.permlevel}

		self.assertCountEqual(perms.keys(), ["System Manager", "POS Print Manager", "POS Print Operator"])

		for role, perm in perms.items():
			with self.subTest(role=role):
				self.assertEqual(perm.read, 1)
				self.assertEqual(perm.create, 0)
				self.assertEqual(perm.write, 0)
				self.assertEqual(perm.delete, 0)

	def test_job_manual_mutation_denied_for_every_role(self):
		# A.31.22 audit immutability. Docs are re-fetched inside each session: a
		# document inserted with ignore_permissions=True keeps that flag on the
		# object, which would make a later save() skip permission checks entirely.
		job_name = _new_job("JOB-IMMUT-01").name

		users = [
			self._create_user("pdp.operator.job@example.test", "POS Print Operator"),
			self._create_user("pdp.manager.job@example.test", "POS Print Manager"),
			self._create_user("pdp.sysmanager.job@example.test", "System Manager"),
		]

		try:
			for user in users:
				with self.subTest(user=user.email):
					frappe.set_user(user.name)
					with self.assertRaises(frappe.PermissionError):
						job = frappe.get_doc(DOCTYPE, job_name)
						job.set("status_reason_code", "TAMPERED")
						job.save()
					with self.assertRaises(frappe.PermissionError):
						frappe.delete_doc(DOCTYPE, job_name)
		finally:
			frappe.set_user("Administrator")

		self.assertIsNone(frappe.db.get_value(DOCTYPE, job_name, "status_reason_code"))

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


def _job_doc(job_id, **overrides):
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"job_id": job_id,
			"idempotency_key": f"idem-{job_id}",
			# Company doubles as the reference target in tests so the Dynamic Link
			# resolves without creating a POS Invoice.
			"reference_doctype": "Company",
			"reference_name": _company(),
			"company": _company(),
			"pos_profile": _pos_profile(),
			"terminal": _terminal(),
			"requested_by": "Administrator",
			"source": "POS_AUTO",
			"driver_key": "imin_v1",
		}
	)
	doc.update(overrides)
	return doc


def _new_job(job_id, **overrides):
	return _job_doc(job_id, **overrides).insert(ignore_permissions=True)


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
