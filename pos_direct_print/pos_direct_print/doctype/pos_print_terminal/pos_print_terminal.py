import json

import frappe
from frappe.model.document import Document


class POSPrintTerminal(Document):
	def validate(self):
		# _check_* prefix — Frappe core Document reserves _validate_non_negative as a hook (A1-01 lesson)
		self._check_capability_schema_version()
		self._check_capabilities_json_is_json()

	def _check_capability_schema_version(self):
		if self.capability_schema_version is not None and self.capability_schema_version < 1:
			frappe.throw(
				f"{self.meta.get_label('capability_schema_version')} must be 1 or greater.",
				frappe.ValidationError,
			)

	def _check_capabilities_json_is_json(self):
		if self.capabilities_json:
			try:
				json.loads(self.capabilities_json)
			except (TypeError, ValueError):
				frappe.throw(
					f"{self.meta.get_label('capabilities_json')} must contain valid JSON.",
					frappe.ValidationError,
				)


def on_doctype_update():
	# Single-column indexes come from field-level search_index in the DocType JSON;
	# Frappe has no declarative composite index support, so composite indexes follow
	# the Frappe core pattern (see Comment/DynamicLink on_doctype_update).
	frappe.db.add_index("POS Print Terminal", ["company", "pos_profile", "enabled"], "IDX_TERM_01")
	frappe.db.add_index("POS Print Terminal", ["paired_client_id", "enabled"], "IDX_TERM_02")
