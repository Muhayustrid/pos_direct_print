import frappe
from frappe.model.document import Document


class POSPrintSettings(Document):
	def validate(self):
		# ponytail: _check_* prefix — Frappe core Document reserves _validate_non_negative as a hook
		self._check_positive("reservation_ttl_seconds", minimum=1)
		self._check_positive("local_lock_ttl_seconds", minimum=1)
		self._check_non_negative("max_safe_auto_retries")
		self._check_non_negative("safe_retry_delay_ms")
		self._check_minimum("job_retention_days", minimum=1)
		self._check_minimum("attempt_retention_days", minimum=1)
		self._check_minimum("receipt_schema_version", minimum=1)

	def _check_positive(self, fieldname, minimum):
		if self.get(fieldname) is not None and self.get(fieldname) <= minimum - 1:
			frappe.throw(
				f"{self.meta.get_label(fieldname)} must be greater than 0.",
				frappe.ValidationError,
			)

	def _check_non_negative(self, fieldname):
		if self.get(fieldname) is not None and self.get(fieldname) < 0:
			frappe.throw(
				f"{self.meta.get_label(fieldname)} must be 0 or greater.",
				frappe.ValidationError,
			)

	def _check_minimum(self, fieldname, minimum):
		if self.get(fieldname) is not None and self.get(fieldname) < minimum:
			frappe.throw(
				f"{self.meta.get_label(fieldname)} must be {minimum} or greater.",
				frappe.ValidationError,
			)
