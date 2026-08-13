import json

import frappe
from frappe.model.document import Document

from pos_direct_print.core import terminal_scope


class POSPrintTerminal(Document):
	def validate(self):
		# _check_* prefix — Frappe core Document reserves _validate_non_negative as a hook (A1-01 lesson)
		self._check_capability_schema_version()
		self._check_capabilities_json_is_json()
		self._check_extra_profiles()
		self._check_outlet_has_one_printing_terminal()

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

	def _check_extra_profiles(self):
		"""Extra outlets must be distinct, exclude the default, and share the Company.

		A duplicate row is only noise, but a row from another Company would let a
		print cross a Company boundary that every scope check treats as final.

		Blank rows are dropped instead of refused. The table is optional, so a row
		left empty — or emptied to undo it — means the operator wants no extra
		outlet, not a mandatory-field error they cannot clear from the grid.
		"""
		self._drop_blank_extra_profiles()

		seen = set()
		for row in self.get("extra_pos_profiles") or []:
			if row.pos_profile == self.pos_profile:
				frappe.throw(
					f"{row.pos_profile} is already the default POS Profile.",
					frappe.ValidationError,
				)
			if row.pos_profile in seen:
				frappe.throw(f"{row.pos_profile} is listed more than once.", frappe.ValidationError)
			seen.add(row.pos_profile)

			company = frappe.db.get_value("POS Profile", row.pos_profile, "company")
			if company != self.company:
				frappe.throw(
					f"{row.pos_profile} belongs to {company}, not {self.company}.",
					frappe.ValidationError,
				)

	def _drop_blank_extra_profiles(self):
		rows = [row for row in (self.get("extra_pos_profiles") or []) if row.pos_profile]
		if len(rows) == len(self.get("extra_pos_profiles") or []):
			return
		for index, row in enumerate(rows, start=1):
			row.idx = index
		self.set("extra_pos_profiles", rows)

	def _check_outlet_has_one_printing_terminal(self):
		"""One outlet may be served by one printing terminal, not two.

		A terminal may serve several outlets, but the reverse must stay single:
		terminal resolution asks only for Company + POS Profile, then takes the
		oldest match. A second enabled QUALIFIED terminal on the same outlet
		therefore loses that race in silence, and every Job it prints is recorded
		against the other terminal — wrong device in the audit trail, and a
		terminal_id in the idempotency key that does not match the printer.

		Only enabled QUALIFIED terminals collide. An UNVERIFIED or disabled
		terminal can never win the lookup, so it is free to overlap.
		"""
		if not self.enabled or self.qualification_status != "QUALIFIED":
			return

		for pos_profile in terminal_scope.served_pos_profiles(self):
			for other in terminal_scope.terminal_names_serving(
				pos_profile, company=self.company, qualified=True
			):
				if other == self.name:
					continue
				frappe.throw(
					f"{pos_profile} is already served by terminal {other}."
					" One outlet may have one printing terminal:"
					" disable that terminal, or move this one to another outlet.",
					frappe.ValidationError,
				)


def on_doctype_update():
	# Single-column indexes come from field-level search_index in the DocType JSON;
	# Frappe has no declarative composite index support, so composite indexes follow
	# the Frappe core pattern (see Comment/DynamicLink on_doctype_update).
	frappe.db.add_index("POS Print Terminal", ["company", "pos_profile", "enabled"], "IDX_TERM_01")
	frappe.db.add_index("POS Print Terminal", ["paired_client_id", "enabled"], "IDX_TERM_02")
	# Extra-profile lookups run per terminal resolution, so the child rows need an
	# index on the profile they grant.
	frappe.db.add_index("POS Print Terminal Profile", ["pos_profile", "parent"], "IDX_TERMPROF_01")
