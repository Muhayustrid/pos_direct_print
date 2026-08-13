import json

import frappe
from frappe.model.document import Document

from pos_direct_print.core.state_machine import check_transition

# Canonical state order from plan.md; reservation ownership is mandatory from RESERVED onward.
STATE_ORDER = [
	"CREATED",
	"RESERVED",
	"PREFLIGHT",
	"BLOCKED",
	"PRINTING",
	"VERIFYING",
	"FAILED_SAFE",
	"UNCERTAIN",
	"SUCCEEDED",
	"FALLBACK_BROWSER",
	"CANCELLED",
]

RESERVED_INDEX = STATE_ORDER.index("RESERVED")


class POSPrintJob(Document):
	def validate(self):
		# _check_* prefix — Frappe core Document reserves _validate_non_negative as a hook (A1-01 lesson)
		self._check_state_transition()
		self._check_reprint_required_fields()
		self._check_reservation_owner_from_reserved()
		self._check_receipt_hash_has_snapshot()
		self._check_non_negative_counters()
		self._check_receipt_schema_version()
		self._check_parent_job_is_not_self()
		self._check_json_fields_are_json()

	def _check_state_transition(self):
		# A-DOD-05: a status change must satisfy the transition table no matter how
		# the change arrives (whitelisted action, coordinator, or direct save).
		if self.is_new():
			return
		stored_status = frappe.db.get_value("POS Print Job", self.name, "status")
		if stored_status != self.status:
			check_transition(stored_status, self.status)

	def _check_reprint_required_fields(self):
		if self.job_type == "REPRINT":
			if not self.parent_job:
				frappe.throw(
					f"{self.meta.get_label('parent_job')} is required when Job Type is REPRINT.",
					frappe.ValidationError,
				)
			if not self.reprint_reason:
				frappe.throw(
					f"{self.meta.get_label('reprint_reason')} is required when Job Type is REPRINT.",
					frappe.ValidationError,
				)

	def _check_reservation_owner_from_reserved(self):
		if (
			self.status in STATE_ORDER
			and STATE_ORDER.index(self.status) >= RESERVED_INDEX
			and not self.reservation_owner
		):
			frappe.throw(
				f"{self.meta.get_label('reservation_owner')} is required once the job reaches {self.status}.",
				frappe.ValidationError,
			)

	def _check_receipt_hash_has_snapshot(self):
		if self.receipt_hash and not self.receipt_snapshot:
			frappe.throw(
				f"{self.meta.get_label('receipt_snapshot')} is required when Receipt Hash is set.",
				frappe.ValidationError,
			)

	def _check_non_negative_counters(self):
		for fieldname in ("attempt_count", "safe_retry_count"):
			if self.get(fieldname) is not None and self.get(fieldname) < 0:
				frappe.throw(
					f"{self.meta.get_label(fieldname)} must be 0 or greater.",
					frappe.ValidationError,
				)

	def _check_receipt_schema_version(self):
		if self.receipt_schema_version is not None and self.receipt_schema_version < 1:
			frappe.throw(
				f"{self.meta.get_label('receipt_schema_version')} must be 1 or greater.",
				frappe.ValidationError,
			)

	def _check_parent_job_is_not_self(self):
		if self.parent_job and self.parent_job == self.name:
			frappe.throw(
				f"{self.meta.get_label('parent_job')} cannot reference the job itself.",
				frappe.ValidationError,
			)

	def _check_json_fields_are_json(self):
		for fieldname in ("metadata_json",):
			value = self.get(fieldname)
			if not value:
				continue
			try:
				json.loads(value)
			except (TypeError, ValueError):
				frappe.throw(
					f"{self.meta.get_label(fieldname)} must contain valid JSON.",
					frappe.ValidationError,
				)


def on_doctype_update():
	# Single-column indexes come from field-level search_index in the DocType JSON;
	# Frappe has no declarative composite index support, so composite indexes follow
	# the Frappe core pattern (see Comment/DynamicLink on_doctype_update).
	frappe.db.add_index("POS Print Job", ["reference_doctype", "reference_name", "job_type"], "IDX_JOB_01")
	frappe.db.add_index("POS Print Job", ["terminal", "status"], "IDX_JOB_02")
	frappe.db.add_index("POS Print Job", ["terminal", "creation"], "IDX_JOB_03")
	frappe.db.add_index("POS Print Job", ["reference_doctype", "reference_name", "creation"], "IDX_JOB_04")
	frappe.db.add_index("POS Print Job", ["status", "reserved_until"], "IDX_JOB_05")
