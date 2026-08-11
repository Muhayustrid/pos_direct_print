/**
 * Job Coordinator (A.12.5, client side).
 *
 * Server-backed reservation and lifecycle coordination. All persistence
 * happens through the thin Print API transport — the coordinator owns the
 * optimistic `expected_from_state` semantics and surfaces conflicts as
 * canonical domain errors. The reservation token travels with each call while
 * the reservation is active and is never persisted client-side in plaintext.
 */

import { makeError } from "./errors.mjs";
import { assertTransition } from "./print_job.mjs";
import { canonicalize, hashReceipt } from "../receipt/receipt_builder.mjs";

export class JobCoordinator {
  /**
   * @param {import("./print_api.mjs").PrintApi} api authorized transport.
   */
  constructor(api) {
    this.api = api;
  }

  /**
   * Idempotent reservation of the logical print intent.
   * @param {object} request PrintRequest (A.10.1).
   * @param {object} concurrencyContext { reservation_owner, idempotency_key }
   * @returns {Promise<Reservation>} A.10.2 shape; `is_new_job` reflects whether
   *   this call created the Job or joined an existing one.
   */
  async reserve(request, concurrencyContext) {
    if (!request.terminal_id) {
      throw makeError("PDP_TERMINAL_NOT_FOUND", { phase: "RESERVATION" });
    }

    const payload = {
      reference_doctype: request.reference_doctype,
      reference_name: request.reference_name,
      terminal_id: request.terminal_id,
      requested_by: request.requested_by,
      idempotency_key: concurrencyContext.idempotency_key,
      source: request.source,
      job_type: request.job_type,
      driver_key: request.driver_key,
      reservation_owner: concurrencyContext.reservation_owner,
    };

    const result = await this.api.reservePrintJob(payload);
    return {
      job_id: result.job_id,
      reservation_token: result.reservation_token,
      reserved_until: result.reserved_until,
      // Truthful only when the transport says so: an idempotency hit joins an
      // existing Job and must never report a fresh logical Job.
      is_new_job: Boolean(result.is_new_job),
      status: result.status,
    };
  }

  async beginAttempt({ job_id, reservation_token, terminal_id = null }) {
    return this.api.startAttempt({ job_id, reservation_token, terminal_id });
  }

  async bindReceiptSnapshot({ job_id, reservation_token, receipt }) {
    return this.api.bindReceiptSnapshot({
      job_id,
      reservation_token,
      receipt_snapshot: canonicalize(receipt),
      receipt_hash: hashReceipt(receipt),
    });
  }

  /**
   * Atomic optimistic transition. The client pre-validates the pair against
   * the transition table, then lets the server's guarded UPDATE decide the
   * race; a stale expectation surfaces as PDP_JOB_CONFLICT.
   */
  async transition({
    job_id,
    expected_from_state,
    target_state,
    reservation_token,
  }) {
    assertTransition(expected_from_state, target_state);
    return this.api.transitionJob({
      job_id,
      expected_from_state,
      target_state,
      reservation_token,
    });
  }

  async completeAttempt({
    attempt_id,
    outcome,
    content_started = false,
    content_completed = false,
    error = null,
  }) {
    return this.api.completeAttempt({
      attempt_id,
      outcome,
      content_started: content_started ? 1 : 0,
      content_completed: content_completed ? 1 : 0,
      error_code: error ? error.code : null,
      error_detail: error ? error.technical_message : null,
    });
  }

  /**
   * Release an unfulfilled reservation. Original reservations release to
   * CANCELLED; a safe-retry reservation returns to FAILED_SAFE.
   */
  async release({
    job_id,
    reservation_token,
    expected_from_state = "CREATED",
  }) {
    return this.api.releaseReservation({
      job_id,
      reservation_token,
      expected_from_state,
    });
  }
}
