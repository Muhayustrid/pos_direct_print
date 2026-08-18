import json
import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.core.print_api import (
	bind_receipt_snapshot,
	cancel_job,
	complete_attempt,
	disable_terminals,
	fallback_to_browser,
	get_settings,
	invoice_print_state,
	re_reserve_job,
	release_reservation,
	reprint_invoice,
	reserve_print_job,
	resolve_terminal,
	resolve_terminal_for_profile,
	retrieve_job,
	start_attempt,
	transition_job,
)
from pos_direct_print.core.receipt_hash import hash_receipt
from pos_direct_print.tests.fixtures import (
	grant_profile_user,
	isolated_pos_profile,
	second_test_company,
	test_company,
	test_outlet_a,
	test_outlet_b,
)

# The endpoint treats reference_doctype/reference_name as an opaque pair, so the
# reprint tests point them at the test's own Terminal instead of a real POS
# Invoice: the Dynamic Link resolves, and each test gets a reference nobody else
# shares. Reusing Company here would let jobs from other test classes surface as
# reprintable parents.
REPRINT_REFERENCE_DOCTYPE = "POS Print Terminal"


def _receipt():
	return {
		"schema_version": 1,
		"reference_doctype": "POS Invoice",
		"reference_name": "POS-INV-BIND-1",
		"locale": "id-ID",
		"currency": "IDR",
		"paper_profile": "58mm",
		"blocks": [{"type": "TEXT", "text": "TOTAL 1000"}],
		"metadata": {},
	}


class TestPrintApiTransport(IntegrationTestCase):
	"""A2-05 / A-DOD-15/16 — thin RPC: authorization server-side, sanitized
	projections out, canonical PDP errors on denial."""

	def setUp(self):
		self.outlet_a = test_outlet_a()
		self.outlet_b = test_outlet_b()
		self.operator = _user_with_role("api.op@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("api.mgr.a@example.test", "POS Print Manager")
		grant_profile_user(self.outlet_a, self.operator)
		_user_permission(self.manager_a, "POS Profile", self.outlet_a)

		self.terminal = _terminal(self.outlet_a)
		self.terminal_b = _terminal(self.outlet_b)

	def test_get_settings_exposes_runtime_fields_only(self):
		with _user(self.operator):
			settings = get_settings()
		self.assertIn("operating_mode", settings)
		self.assertNotIn("job_retention_days", settings)

	def test_system_manager_can_bulk_disable_terminals(self):
		with _user("Administrator"):
			result = disable_terminals([self.terminal, self.terminal_b])
		self.assertEqual(result, {"disabled": 2})
		self.assertEqual(frappe.db.get_value("POS Print Terminal", self.terminal, "enabled"), 0)
		self.assertEqual(frappe.db.get_value("POS Print Terminal", self.terminal_b, "enabled"), 0)

	def test_operator_cannot_bulk_disable_terminals(self):
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError):
				disable_terminals([self.terminal])
		self.assertEqual(frappe.db.get_value("POS Print Terminal", self.terminal, "enabled"), 1)

	def test_resolve_terminal_returns_runtime_projection(self):
		with _user("Administrator"):
			projection = resolve_terminal(self.terminal)
		self.assertEqual(projection["terminal_id"], self.terminal)
		# A-AT-19: device-admin fields never cross the RPC boundary.
		self.assertNotIn("device_serial", projection)
		self.assertNotIn("firmware_version", projection)

	def test_resolve_disabled_terminal_rejected(self):
		frappe.db.set_value("POS Print Terminal", self.terminal, "enabled", 0)
		with _user("Administrator"):
			with self.assertRaises(frappe.ValidationError) as ctx:
				resolve_terminal(self.terminal)
		self.assertIn("PDP_TERMINAL_DISABLED", str(ctx.exception))

	def test_reserve_print_job_idempotent_single_logical_job(self):
		key = f"api-idem-{uuid.uuid4().hex[:8]}"
		with _user(self.operator):
			first = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=key,
			)
			second = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=key,
			)
		self.assertEqual(first["job_id"], second["job_id"])
		self.assertEqual(first["status"], "RESERVED")
		self.assertTrue(first["is_new_job"])
		self.assertFalse(second["is_new_job"], "idempotent hit must not claim a new Job")

		rows = frappe.db.get_all("POS Print Job", filters={"idempotency_key": key})
		self.assertEqual(len(rows), 1)

	def test_reserve_rejects_impersonation(self):
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError) as ctx:
				reserve_print_job(
					reference_doctype="Company",
					reference_name=test_company(),
					terminal_id=self.terminal,
					requested_by="someone-else@example.test",
					idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
				)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_reserve_non_original_rejected(self):
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError):
				reserve_print_job(
					reference_doctype="Company",
					reference_name=test_company(),
					terminal_id=self.terminal,
					requested_by=self.operator,
					idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
					job_type="REPRINT",
				)

	def test_manager_out_of_scope_terminal_rejected(self):
		with _user(self.manager_a):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal(self.terminal_b)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_operator_outside_applicable_terminal_rejected(self):
		other = _user_with_role("api.other@example.test", "POS Print Operator")
		with _user(other):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal(self.terminal)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_attempt_lifecycle_through_transport(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			started = start_attempt(
				job_id=reservation["job_id"],
				reservation_token=reservation["reservation_token"],
			)
			self.assertEqual(started["job"]["status"], "PREFLIGHT")
			self.assertEqual(started["attempt"]["attempt_no"], 1)

			outcome = complete_attempt(
				attempt_id=started["attempt"]["attempt_id"],
				outcome="SUCCEEDED",
				content_started=1,
				content_completed=1,
			)
			# Thin transport completes the Attempt; the Job only moves through
			# validated transitions requested by the coordinator.
			self.assertEqual(outcome["status"], "PREFLIGHT")

			released = retrieve_job(reservation["job_id"])
			self.assertEqual(released["status"], "PREFLIGHT")

	def test_complete_attempt_derives_retry_class_server_side(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			started = start_attempt(
				job_id=reservation["job_id"], reservation_token=reservation["reservation_token"]
			)
			complete_attempt(
				attempt_id=started["attempt"]["attempt_id"],
				outcome="FAILED_SAFE",
				error_code="PDP_BRIDGE_UNAVAILABLE",
			)
		self.assertEqual(
			frappe.db.get_value("POS Print Attempt", started["attempt"]["attempt_id"], "retry_class"),
			"AUTO_SAFE",
		)

	def test_complete_attempt_content_risk_overrides_error_category(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			started = start_attempt(
				job_id=reservation["job_id"], reservation_token=reservation["reservation_token"]
			)
			complete_attempt(
				attempt_id=started["attempt"]["attempt_id"],
				outcome="UNCERTAIN",
				content_started=1,
				error_code="PDP_PRINTER_NOT_READY",
			)
		self.assertEqual(
			frappe.db.get_value("POS Print Attempt", started["attempt"]["attempt_id"], "retry_class"),
			"REPRINT_ONLY",
		)

	def test_server_lifecycle_actions_do_not_require_exposed_owner(self):
		with _user(self.operator):
			fallback_reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			transition_job(
				job_id=fallback_reservation["job_id"],
				expected_from_state="RESERVED",
				target_state="FAILED_SAFE",
				reservation_token=fallback_reservation["reservation_token"],
			)
			fallback = fallback_to_browser(fallback_reservation["job_id"], approved=1)
			self.assertEqual(fallback["status"], "FALLBACK_BROWSER")

			cancel_reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			cancelled = cancel_job(cancel_reservation["job_id"], reason="operator cancel")
			self.assertEqual(cancelled["status"], "CANCELLED")

	def test_fallback_requires_approval_and_rejects_content_risk(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			with self.assertRaises(frappe.PermissionError):
				fallback_to_browser(reservation["job_id"], approved=0)
			frappe.db.set_value("POS Print Job", reservation["job_id"], "content_may_have_printed", 1)
			with self.assertRaises(frappe.ValidationError):
				fallback_to_browser(reservation["job_id"], approved=1)

	def test_transition_job_rejects_invalid_transition(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			with self.assertRaises(frappe.ValidationError) as ctx:
				transition_job(
					job_id=reservation["job_id"],
					expected_from_state="RESERVED",
					target_state="SUCCEEDED",
					reservation_token=reservation["reservation_token"],
				)
		self.assertIn("PDP_JOB_INVALID_TRANSITION", str(ctx.exception))

	def test_transition_job_conflict_on_stale_expectation(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			transition_job(
				job_id=reservation["job_id"],
				expected_from_state="RESERVED",
				target_state="PREFLIGHT",
				reservation_token=reservation["reservation_token"],
			)
			with self.assertRaises(frappe.ValidationError) as ctx:
				transition_job(
					job_id=reservation["job_id"],
					expected_from_state="RESERVED",
					target_state="CANCELLED",
					reservation_token=reservation["reservation_token"],
				)
		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))

	def test_release_reservation_cancels(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
			released = release_reservation(
				job_id=reservation["job_id"],
				reservation_token=reservation["reservation_token"],
				expected_from_state="CREATED",
			)
			self.assertEqual(released["status"], "CANCELLED")

	def test_retrieve_job_out_of_scope_denied(self):
		with _user(self.operator):
			reservation = reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"api-idem-{uuid.uuid4().hex[:8]}",
			)
		other_operator = _user_with_role("api.op2@example.test", "POS Print Operator")
		with _user(other_operator):
			with self.assertRaises(frappe.PermissionError):
				retrieve_job(reservation["job_id"])


class TestBindReceiptSnapshot(IntegrationTestCase):
	def setUp(self):
		self.operator = _user_with_role("bind.op@example.test", "POS Print Operator")
		self.outlet_a = test_outlet_a()
		grant_profile_user(self.outlet_a, self.operator)
		self.terminal = _terminal(self.outlet_a)
		self.snapshot = _receipt()

	def _reserve(self):
		with _user(self.operator):
			return reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"bind-idem-{uuid.uuid4().hex[:8]}",
			)

	def _bind_kwargs(self, snapshot=None):
		snapshot = snapshot or self.snapshot
		return {
			"job_id": self.reservation["job_id"],
			"reservation_token": self.reservation["reservation_token"],
			"receipt_snapshot": json.dumps(snapshot),
			"receipt_hash": hash_receipt(snapshot),
		}

	def test_bind_persists_snapshot_hash_and_schema_version(self):
		self.reservation = self._reserve()
		with _user(self.operator):
			projection = bind_receipt_snapshot(**self._bind_kwargs())
		self.assertEqual(projection["status"], "RESERVED")
		stored = frappe.get_doc("POS Print Job", self.reservation["job_id"])
		self.assertEqual(stored.receipt_snapshot, json.dumps(self.snapshot))
		self.assertEqual(stored.receipt_hash, hash_receipt(self.snapshot))
		self.assertEqual(stored.receipt_schema_version, 1)

	def test_second_identical_bind_is_idempotent(self):
		self.reservation = self._reserve()
		with _user(self.operator):
			bind_receipt_snapshot(**self._bind_kwargs())
			projection = bind_receipt_snapshot(**self._bind_kwargs())
		self.assertEqual(projection["status"], "RESERVED")

	def test_different_hash_while_bound_raises_conflict(self):
		self.reservation = self._reserve()
		other = {**self.snapshot, "reference_name": "POS-INV-BIND-2"}
		with _user(self.operator):
			bind_receipt_snapshot(**self._bind_kwargs())
			with self.assertRaises(frappe.ValidationError) as ctx:
				bind_receipt_snapshot(**self._bind_kwargs(other))
		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))

	def test_wrong_or_empty_token_rejected(self):
		self.reservation = self._reserve()
		kwargs = self._bind_kwargs()
		with _user(self.operator):
			for token in ("wrong", ""):
				with self.subTest(token=token):
					with self.assertRaises(frappe.ValidationError):
						bind_receipt_snapshot(**{**kwargs, "reservation_token": token})

	def test_bind_after_start_attempt_rejected(self):
		self.reservation = self._reserve()
		with _user(self.operator):
			start_attempt(
				job_id=self.reservation["job_id"],
				reservation_token=self.reservation["reservation_token"],
			)
			with self.assertRaises(frappe.ValidationError) as ctx:
				bind_receipt_snapshot(**self._bind_kwargs())
		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))

	def test_hash_mismatch_with_client_value_raises_validation_error(self):
		self.reservation = self._reserve()
		with _user(self.operator):
			with self.assertRaises(frappe.ValidationError) as ctx:
				bind_receipt_snapshot(**{**self._bind_kwargs(), "receipt_hash": "pdpr1:0000000000000000"})
		self.assertIn("PDP_RECEIPT_INVALID", str(ctx.exception))

	def test_malformed_json_raises_validation_error(self):
		self.reservation = self._reserve()
		with _user(self.operator):
			with self.assertRaises(frappe.ValidationError) as ctx:
				bind_receipt_snapshot(**{**self._bind_kwargs(), "receipt_snapshot": "{not json"})
		self.assertIn("PDP_RECEIPT_INVALID", str(ctx.exception))

	def test_projections_never_contain_snapshot_or_hash(self):
		self.reservation = self._reserve()
		with _user(self.operator):
			bind_receipt_snapshot(**self._bind_kwargs())
			retrieved = retrieve_job(self.reservation["job_id"])
			transitioned = transition_job(
				job_id=self.reservation["job_id"],
				expected_from_state="RESERVED",
				target_state="CANCELLED",
				reservation_token=self.reservation["reservation_token"],
			)
		for projection in (retrieved, transitioned):
			self.assertNotIn("receipt_snapshot", projection)
			self.assertNotIn("receipt_hash", projection)

	def test_lone_surrogate_snapshot_raises_receipt_invalid(self):
		"""Fix round 1: canonicalize escapes a lone surrogate (json.dumps
		ensure_ascii=False succeeds), so the UnicodeEncodeError must come from
		hash_receipt's utf-16-le encode and be wrapped into PDP_RECEIPT_INVALID.
		The hash value is a placeholder: the server must reject the snapshot
		before it can compare hashes."""
		self.reservation = self._reserve()
		snapshot = {**self.snapshot, "reference_name": "POS-INV-" + chr(0xD800)}
		kwargs = {
			"job_id": self.reservation["job_id"],
			"reservation_token": self.reservation["reservation_token"],
			"receipt_snapshot": json.dumps(snapshot),
			"receipt_hash": "pdpr1:0000000000000000",
		}
		with _user(self.operator):
			with self.assertRaises(frappe.ValidationError) as ctx:
				bind_receipt_snapshot(**kwargs)
		self.assertIn("PDP_RECEIPT_INVALID", str(ctx.exception))


class TestReReserveJob(IntegrationTestCase):
	"""Fix round 1 — server-side safe-retry re-reservation. The FAILED_SAFE Job
	keeps its original reservation_owner, which is hidden from projections, so a
	retry can never present it. re_reserve_job mints a NEW server-side owner for
	the retry cycle; the initiator is audit metadata and never a token."""

	def setUp(self):
		self.operator = _user_with_role("rereserve.op@example.test", "POS Print Operator")
		self.outlet_a = test_outlet_a()
		grant_profile_user(self.outlet_a, self.operator)
		self.terminal = _terminal(self.outlet_a)

	def _reserve(self):
		with _user(self.operator):
			return reserve_print_job(
				reference_doctype="Company",
				reference_name=test_company(),
				terminal_id=self.terminal,
				requested_by=self.operator,
				idempotency_key=f"rereserve-idem-{uuid.uuid4().hex[:8]}",
			)

	def _drive_to_failed_safe(self, reservation):
		with _user(self.operator):
			started = start_attempt(
				job_id=reservation["job_id"],
				reservation_token=reservation["reservation_token"],
			)
			complete_attempt(
				attempt_id=started["attempt"]["attempt_id"],
				outcome="FAILED_SAFE",
				error_code="PDP_BRIDGE_UNAVAILABLE",
			)
			transition_job(
				job_id=reservation["job_id"],
				expected_from_state="PREFLIGHT",
				target_state="FAILED_SAFE",
				reservation_token=reservation["reservation_token"],
			)
		frappe.db.commit()

	def test_rereserve_mints_fresh_owner_distinct_from_initiator(self):
		reservation = self._reserve()
		self._drive_to_failed_safe(reservation)

		with _user(self.operator):
			payload = re_reserve_job(reservation["job_id"], initiator=self.operator)

		self.assertEqual(payload["job_id"], reservation["job_id"])
		self.assertEqual(payload["status"], "RESERVED")
		self.assertNotEqual(payload["reservation_token"], reservation["reservation_token"])
		self.assertNotEqual(payload["reservation_token"], self.operator)
		self.assertTrue(payload["reservation_token"].startswith("RETRY-"))

		job = frappe.get_doc("POS Print Job", reservation["job_id"])
		self.assertEqual(job.reservation_owner, payload["reservation_token"])
		self.assertEqual(job.safe_retry_count, 1)

	def test_original_owner_no_longer_matches_after_rereserve(self):
		reservation = self._reserve()
		self._drive_to_failed_safe(reservation)
		old_token = reservation["reservation_token"]

		with _user(self.operator):
			payload = re_reserve_job(reservation["job_id"], initiator=self.operator)

		# The old token must fail every guarded mutation now.
		with self.assertRaises(frappe.ValidationError):
			start_attempt(
				job_id=reservation["job_id"],
				reservation_token=old_token,
			)
		with _user(self.operator):
			# The fresh token starts the retry attempt instead.
			started = start_attempt(
				job_id=reservation["job_id"],
				reservation_token=payload["reservation_token"],
			)
		self.assertEqual(started["job"]["status"], "PREFLIGHT")

	def test_rereserve_denied_when_not_failed_safe(self):
		reservation = self._reserve()
		with self.assertRaises(frappe.ValidationError) as ctx:
			with _user(self.operator):
				re_reserve_job(reservation["job_id"], initiator=self.operator)
		self.assertIn("PDP_JOB_INVALID_TRANSITION", str(ctx.exception))

	def test_rereserve_respects_retry_limit(self):
		reservation = self._reserve()
		self._drive_to_failed_safe(reservation)
		max_retries = frappe.get_single("POS Print Settings").max_safe_auto_retries or 0
		frappe.db.set_value("POS Print Job", reservation["job_id"], "safe_retry_count", max_retries)

		with self.assertRaises(frappe.ValidationError) as ctx:
			with _user(self.operator):
				re_reserve_job(reservation["job_id"], initiator=self.operator)
		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))

	def test_rereserve_out_of_scope_denied(self):
		reservation = self._reserve()
		self._drive_to_failed_safe(reservation)
		other = _user_with_role("rereserve.op2@example.test", "POS Print Operator")
		with self.assertRaises(frappe.PermissionError):
			with _user(other):
				re_reserve_job(reservation["job_id"], initiator=other)


class TestResolveTerminalForProfile(IntegrationTestCase):
	"""B4-01 — row-scoped terminal lookup for the POS context (C-3 resolved:
	transport travels in this lookup's own projection, not the frozen one)."""

	def setUp(self):
		self.operator = _user_with_role("profile.op@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("profile.mgr.a@example.test", "POS Print Manager")
		self.manager_none = _user_with_role("profile.mgr.none@example.test", "POS Print Manager")
		self.no_role = _user_with_role("profile.norole@example.test", "Sales User")
		# Dedicated profile per test: the shared fixture outlet accumulates
		# UNVERIFIED terminals across a class, and those would win the creation-asc
		# lookup this class is about.
		self.profile = _pos_profile(self.operator)
		_user_permission(self.manager_a, "POS Profile", self.profile)

	def test_operator_with_applicable_profile_gets_transport_projection(self):
		terminal = _terminal(
			self.profile,
			qualification_status="QUALIFIED",
			transport="USB",
			paper_width_mm="58",
			driver_key="imin_v1",
		)
		with _user(self.operator):
			projection = resolve_terminal_for_profile(test_company(), self.profile)
		self.assertEqual(projection["terminal_id"], terminal)
		self.assertEqual(projection["transport"], "USB")
		self.assertEqual(projection["driver_key"], "imin_v1")
		self.assertEqual(projection["paper_width_mm"], "58")
		self.assertEqual(projection["qualification_status"], "QUALIFIED")
		# Device-admin fields never cross this RPC boundary either.
		self.assertNotIn("device_serial", projection)
		self.assertNotIn("pairing_status", projection)

	def test_operator_outside_applicable_profile_rejected(self):
		other = _user_with_role("profile.other@example.test", "POS Print Operator")
		_terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		with _user(other):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal_for_profile(test_company(), self.profile)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_manager_without_pos_profile_scope_rejected(self):
		_terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		with _user(self.manager_none):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal_for_profile(test_company(), self.profile)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_manager_with_scope_gets_lookup(self):
		terminal = _terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		with _user(self.manager_a):
			projection = resolve_terminal_for_profile(test_company(), self.profile)
		self.assertEqual(projection["terminal_id"], terminal)

	def test_user_with_no_print_role_rejected(self):
		_terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		with _user(self.no_role):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal_for_profile(test_company(), self.profile)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_no_enabled_terminal_raises_not_found(self):
		_terminal(self.profile, qualification_status="QUALIFIED", enabled=0)
		with _user(self.operator):
			with self.assertRaises(frappe.ValidationError) as ctx:
				resolve_terminal_for_profile(test_company(), self.profile)
		self.assertIn("PDP_TERMINAL_NOT_FOUND", str(ctx.exception))

	def test_enabled_unverified_terminal_raises_not_qualified(self):
		_terminal(self.profile, qualification_status="UNVERIFIED", enabled=1)
		with _user(self.operator):
			with self.assertRaises(frappe.ValidationError) as ctx:
				resolve_terminal_for_profile(test_company(), self.profile)
		self.assertIn("PDP_TERMINAL_NOT_QUALIFIED", str(ctx.exception))

	def test_qualified_terminal_wins_over_older_unverified_terminal(self):
		_terminal(self.profile, qualification_status="UNVERIFIED", transport="UNKNOWN")
		qualified = _terminal(self.profile, qualification_status="QUALIFIED", transport="SPI")
		with _user(self.operator):
			projection = resolve_terminal_for_profile(test_company(), self.profile)
		self.assertEqual(projection["terminal_id"], qualified)

	def test_two_enabled_terminals_returns_oldest(self):
		# Validation now refuses a second QUALIFIED terminal on one outlet, but
		# rows that predate that rule are already in the database. The tie-break
		# still has to be deterministic for them, so the collision is created
		# behind validation on purpose.
		older = _terminal(self.profile, qualification_status="QUALIFIED", transport="USB")
		_colliding_terminal(self.profile, transport="SPI")
		frappe.db.set_value("POS Print Terminal", older, "creation", "2020-01-01 08:00:00")
		with _user(self.operator):
			projection = resolve_terminal_for_profile(test_company(), self.profile)
		self.assertEqual(projection["terminal_id"], older)

	def test_second_qualified_terminal_on_one_outlet_is_refused(self):
		# The rule that keeps the lookup above deterministic, stated at the source.
		_terminal(self.profile, qualification_status="QUALIFIED")
		with self.assertRaises(frappe.ValidationError) as ctx:
			_terminal(self.profile, qualification_status="QUALIFIED")
		self.assertIn("already served by terminal", str(ctx.exception))

	def test_out_of_company_scope_rejected(self):
		# A Company User Permission narrows scope to the fixture Company, so a lookup
		# for a different one is denied even though a terminal exists there. The other
		# Company is a fixture rather than ERPNext's `_Test Company`, which only
		# exists on sites where ERPNext's own test records have been generated.
		other_company = second_test_company()
		_terminal(self.profile, qualification_status="QUALIFIED", company=other_company)
		_user_permission(self.operator, "Company", test_company())
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError) as ctx:
				resolve_terminal_for_profile(other_company, self.profile)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_terminal_serving_an_extra_profile_is_found(self):
		# One counter, two outlets, one printer: the lookup for the extra outlet
		# must land on the same terminal rather than report none.
		extra = _pos_profile(self.operator)
		_user_permission(self.manager_a, "POS Profile", extra)
		terminal = _terminal(self.profile, qualification_status="QUALIFIED", transport="SPI")
		_add_extra_profile(terminal, extra)

		with _user(self.manager_a):
			projection = resolve_terminal_for_profile(test_company(), extra)
		self.assertEqual(projection["terminal_id"], terminal)

	def test_extra_profile_on_an_unqualified_terminal_is_not_qualified(self):
		# The extra binding widens what a terminal serves; it never bypasses
		# qualification.
		extra = _pos_profile(self.operator)
		_user_permission(self.manager_a, "POS Profile", extra)
		terminal = _terminal(self.profile, qualification_status="UNVERIFIED")
		_add_extra_profile(terminal, extra)

		with _user(self.manager_a):
			with self.assertRaises(frappe.ValidationError) as ctx:
				resolve_terminal_for_profile(test_company(), extra)
		self.assertIn("PDP_TERMINAL_NOT_QUALIFIED", str(ctx.exception))


class TestReprintInvoice(IntegrationTestCase):
	"""reprint_invoice — the POS entry to an authorized second physical copy.

	It resolves the parent Job from the invoice (row-scoped), runs the full
	core.reprint authorization chain, and returns a live reservation on the NEW
	Job. A repeated ORIGINAL print stays refused by idempotency; this endpoint is
	the only sanctioned way to a second copy.
	"""

	def setUp(self):
		self.operator = _user_with_role("reprintapi.op@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("reprintapi.mgr.a@example.test", "POS Print Manager")
		self.manager_b = _user_with_role("reprintapi.mgr.b@example.test", "POS Print Manager")
		self.profile = _pos_profile(self.operator)
		self.other_profile = _pos_profile(self.operator)
		_user_permission(self.manager_a, "POS Profile", self.profile)
		_user_permission(self.manager_b, "POS Profile", self.other_profile)
		self.terminal = _terminal(self.profile, qualification_status="QUALIFIED")
		# Stands in for the printed invoice: unique per test, and a real record so
		# the Job's Dynamic Link resolves.
		self.invoice = self.terminal

	def _parent(self, status="SUCCEEDED"):
		return _reprint_job(
			requested_by=self.operator,
			pos_profile=self.profile,
			terminal=self.terminal,
			reference_name=self.invoice,
			status=status,
		)

	def test_manager_gets_a_reserved_reprint_job_for_the_invoice(self):
		parent = self._parent()
		with _user(self.manager_a):
			payload = reprint_invoice(REPRINT_REFERENCE_DOCTYPE, self.invoice, "Kertas tersangkut")

		self.assertEqual(payload["parent_job_id"], parent.name)
		self.assertEqual(payload["status"], "RESERVED")
		self.assertTrue(payload["reservation_token"])
		self.assertEqual(
			payload["terminal_id"], frappe.db.get_value("POS Print Terminal", self.terminal, "terminal_id")
		)

		reprint = frappe.get_doc("POS Print Job", payload["job_id"])
		self.assertEqual(reprint.job_type, "REPRINT")
		self.assertEqual(reprint.parent_job, parent.name)
		self.assertEqual(reprint.reprint_reason, "Kertas tersangkut")
		self.assertEqual(reprint.requested_by, self.manager_a)
		self.assertNotEqual(reprint.name, parent.name)

		# The parent is never mutated into a reprint.
		self.assertEqual(frappe.get_doc("POS Print Job", parent.name).job_type, "ORIGINAL")

	def test_reservation_token_is_server_minted_not_the_caller(self):
		self._parent()
		with _user(self.manager_a):
			payload = reprint_invoice(REPRINT_REFERENCE_DOCTYPE, self.invoice, "Audit reissue")
		self.assertNotEqual(payload["reservation_token"], self.manager_a)
		self.assertTrue(payload["reservation_token"].startswith("REPRINT-"))

	def test_operator_denied(self):
		self._parent()
		with _user(self.operator):
			with self.assertRaises(frappe.PermissionError):
				reprint_invoice(REPRINT_REFERENCE_DOCTYPE, self.invoice, "Customer asked again")

	def test_missing_reason_denied(self):
		self._parent()
		with _user(self.manager_a):
			with self.assertRaises(frappe.MandatoryError):
				reprint_invoice(REPRINT_REFERENCE_DOCTYPE, self.invoice, "   ")

	def test_manager_outside_scope_denied(self):
		self._parent()
		with _user(self.manager_b):
			with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
				reprint_invoice(REPRINT_REFERENCE_DOCTYPE, self.invoice, "Reason")

	def test_invoice_never_printed_is_not_found(self):
		with _user(self.manager_a):
			with self.assertRaises(frappe.ValidationError) as ctx:
				reprint_invoice(REPRINT_REFERENCE_DOCTYPE, "POS-INV-NEVER", "Reason")
		self.assertIn("PDP_JOB_NOT_FOUND", str(ctx.exception))

	def test_non_reprintable_parent_state_is_not_found(self):
		# PREFLIGHT is not a reprintable state, so the invoice has no eligible
		# parent at all — the lookup refuses before the reprint chain runs.
		self._parent(status="PREFLIGHT")
		with _user(self.manager_a):
			with self.assertRaises(frappe.ValidationError) as ctx:
				reprint_invoice(REPRINT_REFERENCE_DOCTYPE, self.invoice, "Reason")
		self.assertIn("PDP_JOB_NOT_FOUND", str(ctx.exception))

	def test_newest_reprintable_job_becomes_the_parent(self):
		self._parent()
		newest = self._parent()
		with _user(self.manager_a):
			payload = reprint_invoice(REPRINT_REFERENCE_DOCTYPE, self.invoice, "Reason")
		self.assertEqual(payload["parent_job_id"], newest.name)


class TestInvoicePrintState(IntegrationTestCase):
	"""invoice_print_state — the read-only flag the POS button row runs on.

	A reopened order must offer Reprint before the cashier clicks anything, so
	the row asks whether this invoice already reached paper. Row-scoped through
	the standard Job query conditions, and deliberately bare: a flag only, no
	Job id or terminal to correlate.
	"""

	def setUp(self):
		self.operator = _user_with_role("printstate.op@example.test", "POS Print Operator")
		self.manager_a = _user_with_role("printstate.mgr.a@example.test", "POS Print Manager")
		self.manager_b = _user_with_role("printstate.mgr.b@example.test", "POS Print Manager")
		self.profile = _pos_profile(self.operator)
		self.other_profile = _pos_profile(self.operator)
		_user_permission(self.manager_a, "POS Profile", self.profile)
		_user_permission(self.manager_b, "POS Profile", self.other_profile)
		self.terminal = _terminal(self.profile, qualification_status="QUALIFIED")
		self.invoice = self.terminal

	def _job(self, status):
		return _reprint_job(
			requested_by=self.operator,
			pos_profile=self.profile,
			terminal=self.terminal,
			reference_name=self.invoice,
			status=status,
		)

	def test_settled_print_reads_as_printed(self):
		self._job("SUCCEEDED")
		with _user(self.manager_a):
			self.assertEqual(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice), {"printed": True})

	def test_uncertain_and_fallback_also_read_as_printed(self):
		# Both mean paper may already carry the receipt, so another copy is a
		# reprint — exactly what the button row must offer.
		for status in ("UNCERTAIN", "FALLBACK_BROWSER"):
			with self.subTest(status=status):
				# A terminal name doubles as the reference target here (see
				# _reprint_job), so this row is a reference, not a printing
				# terminal — it stays UNVERIFIED to leave the outlet's one
				# QUALIFIED slot to self.terminal.
				invoice = _terminal(self.profile)
				_reprint_job(
					requested_by=self.operator,
					pos_profile=self.profile,
					terminal=self.terminal,
					reference_name=invoice,
					status=status,
				)
				with _user(self.manager_a):
					self.assertTrue(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, invoice)["printed"])

	def test_failed_safe_reads_as_not_printed(self):
		# Nothing reached paper, so Print Receipt must keep the slot.
		self._job("FAILED_SAFE")
		with _user(self.manager_a):
			self.assertEqual(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice), {"printed": False})

	def test_invoice_never_printed_reads_as_not_printed(self):
		with _user(self.manager_a):
			self.assertEqual(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice), {"printed": False})

	def test_out_of_scope_job_reads_as_not_printed(self):
		# Row scoping hides the Job, and that is the honest answer for this user:
		# there is no reprint they could perform on it anyway.
		self._job("SUCCEEDED")
		with _user(self.manager_b):
			self.assertEqual(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice), {"printed": False})

	def test_projection_exposes_nothing_but_the_flag(self):
		self._job("SUCCEEDED")
		with _user(self.manager_a):
			payload = invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice)
		self.assertEqual(list(payload), ["printed"])

	def test_reassigned_terminal_reads_as_not_printed(self):
		# The terminal that printed this receipt no longer serves the outlet, so
		# core.reprint would refuse with PDP_JOB_CONFLICT. Reporting the invoice as
		# printed would render a button whose only outcome is failure.
		self._job("SUCCEEDED")
		frappe.db.set_value("POS Print Terminal", self.terminal, "pos_profile", self.other_profile)
		with _user(self.manager_a):
			self.assertEqual(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice), {"printed": False})

	def test_terminal_still_serving_the_outlet_as_an_extra_reads_as_printed(self):
		# The default binding moved on, but the terminal still serves the Job's
		# outlet through an extra row — so the reprint would succeed and the
		# button belongs in the row.
		self._job("SUCCEEDED")
		terminal = frappe.get_doc("POS Print Terminal", self.terminal)
		original_profile = terminal.pos_profile
		terminal.pos_profile = self.other_profile
		terminal.append("extra_pos_profiles", {"pos_profile": original_profile})
		terminal.save(ignore_permissions=True)
		with _user(self.manager_a):
			self.assertEqual(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice), {"printed": True})

	def test_disabled_terminal_reads_as_not_printed(self):
		self._job("SUCCEEDED")
		frappe.db.set_value("POS Print Terminal", self.terminal, "enabled", 0)
		with _user(self.manager_a):
			self.assertEqual(invoice_print_state(REPRINT_REFERENCE_DOCTYPE, self.invoice), {"printed": False})


def _reprint_job(requested_by, pos_profile, terminal, reference_name, **overrides):
	suffix = uuid.uuid4().hex[:8]
	doc = frappe.get_doc(
		{
			"doctype": "POS Print Job",
			"job_id": f"JOB-{suffix}",
			"idempotency_key": f"idem-JOB-{suffix}",
			# Company doubles as the reference target here so the Dynamic Link
			# resolves without creating a real POS Invoice, matching the
			# convention in the Job DocType tests.
			"reference_doctype": REPRINT_REFERENCE_DOCTYPE,
			"reference_name": reference_name,
			"company": test_company(),
			"pos_profile": pos_profile,
			"terminal": terminal,
			"requested_by": requested_by,
			"source": "POS_AUTO",
			"driver_key": "imin_v1",
			"reservation_owner": "client-x",
		}
	)
	doc.update(overrides)
	return doc.insert(ignore_permissions=True)


class _user:
	def __init__(self, user):
		self.user = user

	def __enter__(self):
		self.previous = frappe.session.user
		frappe.set_user(self.user)
		frappe.clear_cache(user=self.user)

	def __exit__(self, *exc):
		frappe.set_user(self.previous)


def _user_with_role(email, role):
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	if role not in {row.role for row in user.roles}:
		user.add_roles(role)
	return user.name


def _user_permission(user, allow, for_value):
	if frappe.db.exists(
		"User Permission",
		{"user": user, "allow": allow, "for_value": for_value},
	):
		return
	frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": allow,
			"for_value": for_value,
		}
	).insert(ignore_permissions=True)


def _pos_profile(user=None, *, company=None, disabled=0):
	"""An outlet of this test's own, so a lookup scoped to it never collides with
	terminals another test put on the shared fixture outlet."""
	return isolated_pos_profile(company=company, disabled=disabled, user=user or "")


def _terminal(pos_profile, **overrides):
	suffix = uuid.uuid4().hex[:8]
	fields = {
		"doctype": "POS Print Terminal",
		"terminal_id": f"TERM-{suffix}",
		"terminal_label": f"Terminal {suffix}",
		"company": test_company(),
		"pos_profile": pos_profile,
	}
	fields.update(overrides)
	return frappe.get_doc(fields).insert(ignore_permissions=True).name


def _add_extra_profile(terminal, pos_profile):
	"""Widen a terminal to serve one more outlet, the way the form does."""
	doc = frappe.get_doc("POS Print Terminal", terminal)
	doc.append("extra_pos_profiles", {"pos_profile": pos_profile})
	doc.save(ignore_permissions=True)
	return doc


def _colliding_terminal(pos_profile, **overrides):
	"""A second QUALIFIED terminal on an outlet that already has one.

	Validation refuses this, so the row is inserted UNVERIFIED and promoted with
	db_set — mirroring rows that predate the rule. Only for tests that must prove
	the resolution tie-break stays deterministic on legacy data.
	"""
	name = _terminal(pos_profile, **overrides)
	frappe.db.set_value("POS Print Terminal", name, "qualification_status", "QUALIFIED")
	return name
