import json

import frappe
from frappe.model.document import Document


class POSPrintAttempt(Document):
	def validate(self):
		# _check_* prefix — Frappe core Document reserves _validate_non_negative as a hook (A1-01 lesson)
		self._check_attempt_no_positive()
		self._check_duration_ms_non_negative()
		self._check_metadata_json_is_json()

	def _check_attempt_no_positive(self):
		if self.attempt_no is not None and self.attempt_no < 1:
			frappe.throw(
				f"{self.meta.get_label('attempt_no')} is a 1-based sequence.",
				frappe.ValidationError,
			)

	def _check_duration_ms_non_negative(self):
		if self.duration_ms is not None and self.duration_ms < 0:
			frappe.throw(
				f"{self.meta.get_label('duration_ms')} must be 0 or greater.",
				frappe.ValidationError,
			)

	def _check_metadata_json_is_json(self):
		if self.metadata_json:
			try:
				json.loads(self.metadata_json)
			except (TypeError, ValueError):
				frappe.throw(
					f"{self.meta.get_label('metadata_json')} must contain valid JSON.",
					frappe.ValidationError,
				)


def on_doctype_update():
	# Single-column indexes come from field-level search_index in the DocType JSON;
	# Frappe has no declarative composite index support, so composite indexes follow
	# the Frappe core pattern (see Comment/DynamicLink on_doctype_update).
	# IDX-ATT-UNIQUE-01 keeps (job, attempt_no) unique even though autoname is
	# attempt_id: it is the atomicity backstop for attempt numbering.
	frappe.db.add_unique("POS Print Attempt", ["job", "attempt_no"], "IDX_ATT_UNIQUE_01")
	frappe.db.add_index("POS Print Attempt", ["job", "started_at"], "IDX_ATT_01")
	frappe.db.add_index("POS Print Attempt", ["terminal", "started_at"], "IDX_ATT_02")
	frappe.db.add_index("POS Print Attempt", ["outcome", "started_at"], "IDX_ATT_03")
	frappe.db.add_index("POS Print Attempt", ["error_code", "started_at"], "IDX_ATT_04")
