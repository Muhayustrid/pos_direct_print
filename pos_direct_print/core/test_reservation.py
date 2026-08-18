import threading
import uuid

import frappe
from frappe.tests import IntegrationTestCase

from pos_direct_print.core.reservation import (
	_insert_next_attempt,
	create_original_job,
	release_reservation,
	reserve_job,
	reserve_safe_retry,
	start_attempt,
)
from pos_direct_print.core.retry import perform_auto_retry
from pos_direct_print.tests.fixtures import (
	isolated_pos_profile,
	second_test_company,
	test_company,
	test_outlet_a,
)


class TestReservationContract(IntegrationTestCase):
	def test_reserve_sets_reservation_fields(self):
		job = _job()
		reserved = reserve_job(job.name, "client-A")

		self.assertEqual(reserved.status, "RESERVED")
		self.assertEqual(reserved.reservation_owner, "client-A")
		self.assertTrue(reserved.reserved_at)
		self.assertTrue(reserved.reserved_until)

	def test_reserve_requires_expected_from_state(self):
		job = _job()
		reserve_job(job.name, "client-A")

		with self.assertRaises(frappe.ValidationError) as ctx:
			reserve_job(job.name, "client-B", expected_from_state="CREATED")
		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))

	def test_reserve_rejects_non_reservable_expectation(self):
		job = _job()
		with self.assertRaises(frappe.ValidationError):
			reserve_job(job.name, "client-A", expected_from_state="PREFLIGHT")

	def test_release_original_reservation_cancels(self):
		job = _job()
		reserve_job(job.name, "client-A")
		released = release_reservation(job.name, expected_from_state="CREATED")
		self.assertEqual(released.status, "CANCELLED")

	def test_release_safe_retry_reservation_returns_to_failed_safe(self):
		job = _job(status="FAILED_SAFE", reservation_owner="client-A")
		reserve_job(job.name, "client-A", expected_from_state="FAILED_SAFE")
		released = release_reservation(job.name, expected_from_state="FAILED_SAFE")
		self.assertEqual(released.status, "FAILED_SAFE")

	def test_start_attempt_requires_reserved(self):
		job = _job()
		with self.assertRaises(frappe.ValidationError) as ctx:
			start_attempt(job.name, job.terminal, job.driver_key)
		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))


class TestOriginalJobCreationScope(IntegrationTestCase):
	"""Original Job creation rejects Operators whose POS Profile is not
	applicable (A.31.10-A.31.14). Each test isolates one failed condition."""

	def test_original_job_rejects_operator_outside_pos_profile(self):
		operator = _user_with_role("pdp.creation.operator@example.test", "POS Print Operator")
		other = _user_with_role("pdp.creation.other@example.test", "POS Print Operator")
		profile = _pos_profile(other)
		company = test_company()

		with self.assertRaises(frappe.PermissionError) as ctx:
			create_original_job(
				idempotency_key=f"idem-{uuid.uuid4().hex}",
				reference_doctype="Company",
				reference_name=company,
				company=company,
				pos_profile=profile,
				terminal=_terminal(pos_profile=profile),
				requested_by=operator,
			)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_original_job_accepts_operator_inside_pos_profile(self):
		operator = _user_with_role("pdp.creation.inside@example.test", "POS Print Operator")
		profile = _pos_profile(operator)
		company = test_company()

		job = create_original_job(
			idempotency_key=f"idem-{uuid.uuid4().hex}",
			reference_doctype="Company",
			reference_name=company,
			company=company,
			pos_profile=profile,
			terminal=_terminal(pos_profile=profile),
			requested_by=operator,
		)
		self.assertEqual(job.pos_profile, profile)
		self.assertEqual(job.requested_by, operator)

	def test_original_job_rejects_disabled_pos_profile(self):
		operator = _user_with_role("pdp.creation.disabled@example.test", "POS Print Operator")
		# Operator is applicable, only the disabled flag fails the predicate.
		profile = _pos_profile(operator, disabled=1)
		company = test_company()

		with self.assertRaises(frappe.PermissionError) as ctx:
			create_original_job(
				idempotency_key=f"idem-{uuid.uuid4().hex}",
				reference_doctype="Company",
				reference_name=company,
				company=company,
				pos_profile=profile,
				terminal=_terminal(pos_profile=profile),
				requested_by=operator,
			)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_original_job_rejects_company_mismatch(self):
		operator = _user_with_role("pdp.creation.company@example.test", "POS Print Operator")
		# The profile lives in the second fixture Company and the Operator is
		# applicable there; only the Job company differs, so the predicate's company
		# match is the single failing condition.
		other_company = second_test_company()
		profile = _pos_profile(operator, company=other_company)
		company = test_company()

		with self.assertRaises(frappe.PermissionError) as ctx:
			create_original_job(
				idempotency_key=f"idem-{uuid.uuid4().hex}",
				reference_doctype="Company",
				reference_name=company,
				company=company,
				pos_profile=profile,
				terminal=_terminal(pos_profile=profile, company=other_company),
				requested_by=operator,
			)
		self.assertIn("PDP_PERMISSION_DENIED", str(ctx.exception))

	def test_original_job_skips_validation_for_non_operator(self):
		# Non-Operator callers (e.g. Manager/System Manager paths) are unaffected.
		company = test_company()
		job = create_original_job(
			idempotency_key=f"idem-{uuid.uuid4().hex}",
			reference_doctype="Company",
			reference_name=company,
			company=company,
			pos_profile=test_outlet_a(),
			terminal=_terminal(),
			requested_by="Administrator",
		)
		self.assertEqual(job.requested_by, "Administrator")


class TestConcurrentReservation(IntegrationTestCase):
	"""A-AT-09 / A-DOD-06 — duplicate idempotency key and racing reservations
	must never produce two logical original Jobs or two owners."""

	def test_concurrent_idempotent_creation_single_original_job(self):
		key = f"idem-race-{uuid.uuid4().hex}"
		company = test_company()
		pos_profile = test_outlet_a()
		terminal = _terminal()
		frappe.db.commit()  # workers run on their own connections

		outcomes = _thread_map(
			lambda i: create_original_job(
				idempotency_key=key,
				reference_doctype="Company",
				reference_name=company,
				company=company,
				pos_profile=pos_profile,
				terminal=terminal,
				requested_by="Administrator",
			).name,
			count=2,
		)

		names = {result for kind, result in outcomes if kind == "ok"}
		self.assertEqual(len(names), 1, f"racing creations diverged: {outcomes}")

		rows = frappe.db.get_all(
			"POS Print Job", filters={"idempotency_key": key}, fields=["name", "job_type"]
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0].job_type, "ORIGINAL")

	def test_concurrent_reservation_single_winner(self):
		job = _job()
		frappe.db.commit()

		outcomes = _thread_map(lambda i: reserve_job(job.name, f"client-{i}").reservation_owner, count=2)

		winners = [result for kind, result in outcomes if kind == "ok"]
		losers = [result for kind, result in outcomes if kind == "error"]
		self.assertEqual(len(winners), 1, f"expected exactly one reservation winner: {outcomes}")
		self.assertEqual(len(losers), 1)
		self.assertIn("PDP_JOB_CONFLICT", str(losers[0]))

		owner = frappe.db.get_value("POS Print Job", job.name, "reservation_owner")
		self.assertEqual(owner, winners[0])

	def test_safe_retry_conflict_does_not_increment_counter(self):
		job = _job(status="FAILED_SAFE", reservation_owner="client-A")
		job.db_set("safe_retry_count", 0)
		job.db_set("status", "RESERVED")

		with self.assertRaises(frappe.ValidationError) as ctx:
			reserve_safe_retry(job.name, "client-B", max_retries=1)

		self.assertIn("PDP_JOB_CONFLICT", str(ctx.exception))
		job.reload()
		self.assertEqual(job.status, "RESERVED")
		self.assertEqual(job.safe_retry_count, 0)

	def test_concurrent_safe_retry_has_one_winner_and_one_increment(self):
		job = _job(status="FAILED_SAFE", reservation_owner="client-A")
		_attempt(
			job.name,
			job.terminal,
			retry_class="AUTO_SAFE",
			content_started=0,
			outcome="FAILED_SAFE",
		)
		frappe.db.commit()

		outcomes = _thread_map(lambda i: perform_auto_retry(job.name, f"client-{i}").status, count=2)

		winners = [value for kind, value in outcomes if kind == "ok"]
		losers = [value for kind, value in outcomes if kind == "error"]
		self.assertEqual(winners, ["RESERVED"])
		self.assertEqual(len(losers), 1)
		self.assertIn("PDP_JOB_CONFLICT", str(losers[0]))

		status, count = frappe.db.get_value("POS Print Job", job.name, ["status", "safe_retry_count"])
		self.assertEqual(status, "RESERVED")
		self.assertEqual(count, 1)


class TestAtomicAttemptNumbering(IntegrationTestCase):
	"""A-AT-10 / A-DOD-07 — attempt numbers are unique and monotonic; two
	concurrent attempt starts never produce two (job, 2) rows."""

	def test_attempt_numbers_monotonic(self):
		job = _job()
		attempts = [_insert_next_attempt(job.name, job.terminal, job.driver_key) for _ in range(3)]
		self.assertEqual([a.attempt_no for a in attempts], [1, 2, 3])

	def test_duplicate_attempt_number_rejected_by_unique_constraint(self):
		job = _job()
		_insert_next_attempt(job.name, job.terminal, job.driver_key)
		with self.assertRaises(frappe.UniqueValidationError):
			frappe.get_doc(
				{
					"doctype": "POS Print Attempt",
					"attempt_id": f"ATT-{uuid.uuid4().hex[:8]}",
					"job": job.name,
					"attempt_no": 1,
					"terminal": job.terminal,
					"driver_key": job.driver_key,
					"started_at": "2026-08-10 10:00:00",
				}
			).insert(ignore_permissions=True)

	def test_concurrent_attempt_start_never_duplicates_number(self):
		job = _job()
		reserve_job(job.name, "client-A")
		_insert_next_attempt(job.name, job.terminal, job.driver_key)  # Attempt 1
		frappe.db.commit()

		outcomes = _thread_map(
			lambda i: start_attempt(job.name, job.terminal, job.driver_key, reservation_owner="client-A")[
				1
			].attempt_no,
			count=2,
		)

		winners = [result for kind, result in outcomes if kind == "ok"]
		losers = [result for kind, result in outcomes if kind == "error"]
		self.assertEqual(winners, [2], f"exactly one attempt 2 expected: {outcomes}")
		self.assertEqual(len(losers), 1)
		self.assertIn("PDP_JOB_CONFLICT", str(losers[0]))

		count = frappe.db.count("POS Print Attempt", {"job": job.name, "attempt_no": 2})
		self.assertEqual(count, 1)


def _thread_map(fn, count):
	"""Run fn(i) on `count` real threads, each with its own Frappe context and
	database connection. Returns [(kind, result-or-exception), ...]."""
	site = frappe.local.site
	sites_path = frappe.local.sites_path
	outcomes = [None] * count

	def worker(index):
		try:
			frappe.init(site=site, sites_path=sites_path)
			frappe.connect()
			outcomes[index] = ("ok", fn(index))
			frappe.db.commit()
		except Exception as exc:
			outcomes[index] = ("error", exc)
			if frappe.db:
				frappe.db.rollback()
		finally:
			frappe.destroy()

	threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
	for thread in threads:
		thread.start()
	for thread in threads:
		thread.join()

	# End the main thread's open snapshot so rows committed by workers are visible.
	frappe.db.rollback()
	return outcomes


def _attempt(job, terminal, **overrides):
	suffix = uuid.uuid4().hex[:8]
	doc = frappe.get_doc(
		{
			"doctype": "POS Print Attempt",
			"attempt_id": f"ATT-{suffix}",
			"job": job,
			"attempt_no": 1,
			"terminal": terminal,
			"driver_key": "imin_v1",
			"outcome": "STARTED",
			"started_at": "2026-08-10 10:00:00",
		}
	)
	doc.update(overrides)
	return doc.insert(ignore_permissions=True)


def _terminal(pos_profile=None, company=None):
	suffix = uuid.uuid4().hex[:8]
	return (
		frappe.get_doc(
			{
				"doctype": "POS Print Terminal",
				"terminal_id": f"TERM-{suffix}",
				"terminal_label": f"Terminal {suffix}",
				"company": company or test_company(),
				"pos_profile": pos_profile or test_outlet_a(),
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def _user_with_role(email, role):
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
	return user.name


def _pos_profile(user=None, *, company=None, disabled=0):
	"""An outlet of this test's own, optionally restricted to one Operator.

	Each creation-scope test needs exactly one condition of the applicability
	predicate to fail, so every profile is uniquely named and freshly built rather
	than copied from whatever outlet the site happens to hold.
	"""
	return isolated_pos_profile(company=company, disabled=disabled, user=user or "")


def _job(status="CREATED", reservation_owner=None):
	suffix = uuid.uuid4().hex[:8]
	company = test_company()
	return frappe.get_doc(
		{
			"doctype": "POS Print Job",
			"job_id": f"JOB-{suffix}",
			"idempotency_key": f"idem-JOB-{suffix}",
			"reference_doctype": "Company",
			"reference_name": company,
			"company": company,
			"pos_profile": test_outlet_a(),
			"terminal": _terminal(),
			"requested_by": "Administrator",
			"source": "POS_AUTO",
			"driver_key": "imin_v1",
			"status": status,
			"reservation_owner": reservation_owner,
		}
	).insert(ignore_permissions=True)
