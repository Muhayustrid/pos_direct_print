"""Sanitized projections for client-facing payloads.

Every projection is an explicit allowlist, never a denylist: a field added to a
DocType later stays invisible to clients until it is listed here on purpose.
Permission Level 1 fields (device fingerprints, receipt snapshots, reservation
internals, raw driver diagnostics) must never appear in these lists.
"""

import frappe

# A.31.4 — client needs policy, not internal configuration.
RUNTIME_SETTINGS_FIELDS = (
	"enabled",
	"operating_mode",
	"allow_browser_fallback",
	"browser_fallback_confirmation",
	"max_safe_auto_retries",
	"safe_retry_delay_ms",
	"receipt_schema_version",
)

# A.31.7 — TerminalRuntimeProjection. No serial, ROM, browser/WebView version,
# raw capability JSON, pairing internals, or administrative notes.
TERMINAL_RUNTIME_FIELDS = (
	"terminal_id",
	"terminal_label",
	"enabled",
	"driver_key",
	"qualification_status",
	"last_health_state",
	"paper_width_mm",
)

# Operational Level 0 Job fields the POS runtime may display.
JOB_STATUS_FIELDS = (
	"job_id",
	"status",
	"status_reason_code",
	"job_type",
	"attempt_count",
	"safe_retry_count",
	"content_may_have_printed",
	"fallback_used",
	"started_at",
	"finished_at",
	"last_error_code",
	"last_error_phase",
)

# Outcome returned to the caller after a print request settles.
OUTCOME_FIELDS = (
	"job_id",
	"status",
	"status_reason_code",
	"content_may_have_printed",
	"fallback_used",
	"last_error_code",
	"last_error_phase",
)


def runtime_settings_projection():
	"""Return the sanitized POS Print Settings payload for clients."""
	settings = frappe.get_cached_doc("POS Print Settings")
	return _project(settings, RUNTIME_SETTINGS_FIELDS)


def terminal_runtime_projection(terminal):
	"""Return the sanitized terminal payload for clients.

	`terminal` accepts a document or a terminal name.
	"""
	return _project(_resolve("POS Print Terminal", terminal), TERMINAL_RUNTIME_FIELDS)


def job_status_projection(job):
	"""Return the sanitized job status payload for clients."""
	return _project(_resolve("POS Print Job", job), JOB_STATUS_FIELDS)


def outcome_projection(job):
	"""Return the sanitized print outcome payload for clients."""
	return _project(_resolve("POS Print Job", job), OUTCOME_FIELDS)


def _resolve(doctype, doc_or_name):
	if isinstance(doc_or_name, str):
		return frappe.get_doc(doctype, doc_or_name)
	return doc_or_name


def _project(doc, fields):
	return {fieldname: doc.get(fieldname) for fieldname in fields}
