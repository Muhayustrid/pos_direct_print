/**
 * Thin Print API transport (A.12.6, client side). No business rules — the
 * client only shapes RPC calls and normalizes every failure into a canonical
 * PrintDomainError before it can reach the POS UI (A-DOD-11).
 */

import { classifyRetry, normalize } from "./error_normalizer.mjs";
import { makeError } from "./errors.mjs";

export const MODULE = "pos_direct_print.core.print_api";

export const OPERATIONS = Object.freeze({
  GET_SETTINGS: `${MODULE}.get_settings`,
  RESOLVE_TERMINAL: `${MODULE}.resolve_terminal`,
  RESOLVE_TERMINAL_FOR_PROFILE: `${MODULE}.resolve_terminal_for_profile`,
  RESERVE_PRINT_JOB: `${MODULE}.reserve_print_job`,
  START_ATTEMPT: `${MODULE}.start_attempt`,
  TRANSITION_JOB: `${MODULE}.transition_job`,
  COMPLETE_ATTEMPT: `${MODULE}.complete_attempt`,
  RELEASE_RESERVATION: `${MODULE}.release_reservation`,
  RETRIEVE_JOB: `${MODULE}.retrieve_job`,
});

// Lifecycle phase stamped onto errors raised by each operation.
const OPERATION_PHASES = Object.freeze({
  [OPERATIONS.GET_SETTINGS]: "RESERVATION",
  [OPERATIONS.RESOLVE_TERMINAL]: "RESERVATION",
  [OPERATIONS.RESOLVE_TERMINAL_FOR_PROFILE]: "RESERVATION",
  [OPERATIONS.RESERVE_PRINT_JOB]: "RESERVATION",
  [OPERATIONS.START_ATTEMPT]: "PREFLIGHT",
  [OPERATIONS.TRANSITION_JOB]: "PRINT",
  [OPERATIONS.COMPLETE_ATTEMPT]: "VERIFY",
  [OPERATIONS.RELEASE_RESERVATION]: "RESERVATION",
  [OPERATIONS.RETRIEVE_JOB]: "RESERVATION",
});

export class PrintApi {
  /**
   * @param {object} options
   * @param {Function} options.call injectable transport; defaults to the Desk
   *   frappe.call bridge. Tests inject a stub so no network/browser is needed.
   */
  constructor(options = {}) {
    this.call = options.call || defaultFrappeCall;
  }

  getSettings() {
    return this._invoke(OPERATIONS.GET_SETTINGS, {});
  }

  resolveTerminal(terminal_id) {
    return this._invoke(OPERATIONS.RESOLVE_TERMINAL, { terminal_id });
  }

  resolveTerminalForProfile(company, pos_profile) {
    return this._invoke(OPERATIONS.RESOLVE_TERMINAL_FOR_PROFILE, {
      company,
      pos_profile,
    });
  }

  reservePrintJob(payload) {
    return this._invoke(OPERATIONS.RESERVE_PRINT_JOB, payload);
  }

  startAttempt({ job_id, reservation_token, terminal_id }) {
    return this._invoke(OPERATIONS.START_ATTEMPT, {
      job_id,
      reservation_token,
      terminal_id,
    });
  }

  transitionJob({
    job_id,
    expected_from_state,
    target_state,
    reservation_token,
  }) {
    return this._invoke(OPERATIONS.TRANSITION_JOB, {
      job_id,
      expected_from_state,
      target_state,
      reservation_token,
    });
  }

  completeAttempt(payload) {
    return this._invoke(OPERATIONS.COMPLETE_ATTEMPT, payload);
  }

  releaseReservation({ job_id, reservation_token, expected_from_state }) {
    return this._invoke(OPERATIONS.RELEASE_RESERVATION, {
      job_id,
      reservation_token,
      expected_from_state,
    });
  }

  retrieveJob(job_id) {
    return this._invoke(OPERATIONS.RETRIEVE_JOB, { job_id });
  }

  async _invoke(method, args) {
    try {
      return await this.call(method, args);
    } catch (raw) {
      const phase = OPERATION_PHASES[method] || "RESERVATION";
      const domainError = normalize(_rpcError(raw), phase, {
        content_started: false,
      });
      domainError.retry_class = classifyRetry(domainError, {
        content_started: false,
      });
      throw domainError;
    }
  }
}

/**
 * Desk bridge. frappe.call resolves asynchronously via callbacks; both the
 * error callback and an empty 200-with-exc body become rejects.
 */
async function defaultFrappeCall(method, args) {
  if (typeof frappe === "undefined" || typeof frappe.call !== "function") {
    throw makeError("PDP_SERVER_UNAVAILABLE", {
      metadata: { reason: "frappe.call bridge unavailable" },
    });
  }

  return new Promise((resolve, reject) => {
    frappe.call({
      method,
      args,
      freeze: true,
      callback: (response) => resolve(response && response.message),
      error: (response) => reject(response),
    });
  });
}

/**
 * Frappe error payloads carry `_server_messages` (JSON array) and `exc`;
 * unwrap them into a single raw message for the normalizer.
 */
function _rpcError(raw) {
  if (raw && typeof raw === "object" && raw._server_messages) {
    try {
      const messages = JSON.parse(raw._server_messages);
      if (Array.isArray(messages) && messages.length) {
        return new Error(messages.join("\n"));
      }
    } catch {
      // fall through to the generic handling
    }
  }
  if (raw && typeof raw === "object" && raw.message) {
    return new Error(raw.message);
  }
  return raw;
}
