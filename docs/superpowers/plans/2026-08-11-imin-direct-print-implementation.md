# ERPNext POS Direct Print (iMin L21D01) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Print one ERPNext POS v16 transaction physically on the iMin L21D01 reference device through the full canonical path (`POSIntegrationAdapter → PrintManager → JobCoordinator → ReceiptBuilder → imin_v1 → iMin SDK V1`), completing Milestone B1→B5 of `specs/pos-direct-print/milestone-b/`.

**Architecture:** Milestone A contracts are frozen and binding. The only sanctioned refinements are the approved `B-AC-01` snapshot binding (plan.md §9) and the single `_settleStatus` completion gate refinement (plan.md §10). One PrintManager lifecycle remediation aligns existing code to the frozen BaseDriver lifecycle (plan.md §1.6). Hardware unknowns (transport, READY value, feed, timing) are constructor/profile-injected values with gates — never code branches. The pinned SDK asset (`pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js`, 29162 bytes, SHA-256 `d874f3fa2dafa0a729ae0f8f28b4e76825542f64a95c075692ab203a3503fd9a`) is loaded byte-untouched behind a `window.Vue` hide/restore guard.

**Tech Stack:** Frappe v16 custom app (Python server, whitelisted RPC), vanilla ESM `.mjs` client modules, `node --test` JS suite, Frappe `IntegrationTestCase` Python suite, UMD iMin JS Printer SDK V1.4.0 over local WebSocket.

## Global Constraints

1. No modification of ERPNext or Frappe core files, compiled assets, or anything under `docs/` (constitution §1, A-DOD-01).
2. No new error codes. Only codes already in `pos_direct_print/public/js/pos_direct_print/core/errors.mjs` (plan.md §6).
3. No DocType, field, index, permission, or state-transition changes (plan.md §2). `receipt_snapshot`, `receipt_hash`, `receipt_schema_version`, and `transport` all already exist.
4. Milestone C and Milestone D scope is excluded: no multi-tab coordination, sleep/wake, mid-print recovery, sophisticated retry, multi-model, `imin_v2`, status matrix, universal profiles (plan.md §12–13).
5. Hardware values are injected (`connection_type`, `final_feed`, `address`, `timeout_ms`, `post_connect_delay_ms`). Placeholder profile values are calibration constants marked `GATED`, changed only by qualification evidence recorded in `research.md` §13.
6. The pinned SDK bytes never change. Verify before and after every task that touches assets:
   `shasum -a 256 pos_direct_print/public/js/lib/imin/1.4.0/imin-printer.js` → `d874f3fa2dafa0a729ae0f8f28b4e76825542f64a95c075692ab203a3503fd9a`.
7. Every task ends with both suites green. Baseline: 131 Python + 42 JavaScript tests; each task adds to that count. Zero-test runs do not count.
8. No terminal, transport, or feed value is hardcoded into selection logic. Selection follows the qualified `POS Print Terminal` record and injected config (research.md §13.8).
9. Commits need explicit user approval per `AGENTS.md`; commit steps below are drafted, not pre-authorized.

## Verification Commands

JavaScript suite (host, app root):

```bash
find pos_direct_print/public/js/pos_direct_print \
  -path '*__tests__/*.test.mjs' -print -exec node --test {} +
```

Focused Python module (devcontainer):

```bash
docker exec frappe_docker_devcontainer-frappe-1 bash -lc \
  'cd /workspace/development/frappe-bench && \
   bench --site development.localhost run-tests \
     --app pos_direct_print --module <MODULE> --failfast'
```

Full Python suite: same, with `--test-category all` instead of `--module`.

## Task Dependency Order

```text
Task 1 (B3 profiles/renderer) ──┐
Task 2 (hash vectors)           ├── independent, parallelizable
Task 3 (PrintManager remediation)
Task 4 (terminal lookup + POS context)
                                │
Task 5 (B-AC-01 binding) ───────┤── after Tasks 2 + 3
Task 6 (imin_v1 driver) ────────┤── after Tasks 1 + 3
Task 7 (asset loader + bootstrap)── after Task 6
Task 8 (failure boundary) ────────── after Tasks 3 + 6
Device gate (B1-04/B1-05 runbook) ── after Task 7, on physical device
```

---

## Task 1 — Parameterized paper profile + receipt line renderer (B3-01/02/03)

**Files:**
- Create `pos_direct_print/public/js/pos_direct_print/receipt/paper_profiles.mjs`
- Create `pos_direct_print/public/js/pos_direct_print/receipt/receipt_lines.mjs`
- Create `pos_direct_print/public/js/pos_direct_print/receipt/__tests__/paper_profiles.test.mjs`

**Interfaces:**

```js
// paper_profiles.mjs
export function makePaperProfile({
  key = "reference_58mm",
  width_mm = 58,          // B-RCP-05 width parameter
  logical_width = 32,     // usable character columns for wrapping
  page_format = 1,        // SDK setPageFormat: 1 = 58 mm (research.md §8)
  text_width_dots = 384,  // SDK setTextWidth; 58 mm demo evidence
  final_feed = 4,         // GATED: B1-05/B6 physical receipt UAT may change this value
} = {}) // -> Object.freeze({ key, width_mm, logical_width, page_format, text_width_dots, final_feed })
export const TEST_PROFILE = makePaperProfile({ key: "test" });
export const REFERENCE_PROFILE = makePaperProfile({});
export function resolvePaperProfile(key_or_profile)
// frozen profile object passthrough; known key -> profile; anything else -> REFERENCE_PROFILE

// receipt_lines.mjs
export function renderReceiptLines(receipt_document, profile)
// -> ordered array of { kind: "style"|"text"|"feed", text?, bold? }
```

Rendering rules (B-RCP-04/06): `TEXT` → `text` line keeping `bold`; a `style` marker is emitted before a text line only when `bold` changed from the previous line. `SEPARATOR` → `char.repeat(logical_width).slice(0, logical_width)`. `COLUMNS` → one flattened line `left + " ".repeat(Math.max(1, width - left.length - right.length)) + right`. `FEED` → one `feed` marker (driver issues ONE `printAndFeedPaper`). `SPACER`/`IMAGE`/`QR`/`CUT` → throw `makeError("PDP_RECEIPT_INVALID", { phase: "RECEIPT" })`. Lines never contain `\n` — the SDK adapter owns newline policy (B-RUN-06).

**Steps:**
- [ ] 1. RED: write `paper_profiles.test.mjs` asserting: profile freeze + defaults; `resolvePaperProfile(TEST_PROFILE)` identity; unknown key → `REFERENCE_PROFILE`; renderer output for a fixture document built with `ReceiptBuilder().build` — block order preserved, style marker precedes bold text, COLUMNS pads to exactly `logical_width`, no line contains `\n`, `FEED` block yields one trailing `feed` marker, IMAGE block throws `PDP_RECEIPT_INVALID`; same document twice → deep-equal output.
- [ ] 2. Run RED: `node --test pos_direct_print/public/js/pos_direct_print/receipt/__tests__/paper_profiles.test.mjs` → fails (modules missing).
- [ ] 3. GREEN: implement `paper_profiles.mjs` and `receipt_lines.mjs` per interfaces above.
- [ ] 4. Run GREEN: same command → all pass. Run full JS suite → baseline + new tests green.
- [ ] 5. Commit: `feat: add parameterized paper profiles and receipt line renderer`

---

## Task 2 — Cross-language receipt hash vectors (B4-02 prerequisite)

**Files:**
- Create `pos_direct_print/core/hash_vectors.json`
- Create `pos_direct_print/public/js/pos_direct_print/receipt/__tests__/hash_vectors.test.mjs`

**Interfaces:** `hash_vectors.json` is `{"vectors":[{"name":string,"receipt":object,"canonical":string,"hash":"pdpr1:…"}]}`. Vectors cover exactly: (a) minimal IDR receipt with integer amounts; (b) one non-integer amount `1.5`; (c) non-ASCII strings `"Té"` and `"Rp 1.500"`; (d) empty `blocks: []`; (e) nested `metadata` object; (f) boolean `true` and `null` values inside metadata.

**Steps:**
- [ ] 1. Write a throwaway node script that imports `canonicalize`/`hashReceipt` from `receipt_builder.mjs`, builds the six schema-v1 receipts, and emits `hash_vectors.json` (format: 2-space JSON). Run it, inspect output, delete the script.
- [ ] 2. RED: write `hash_vectors.test.mjs` — for every vector: `canonicalize(receipt) === canonical` and `hashReceipt(receipt) === hash`; mutating one material field changes the hash. Run → passes trivially (vectors generated from same code); the real gate is the Python task in Task 5 step 4, which fails until Python parity exists.
- [ ] 3. GREEN: JS test green. Commit: `test: freeze cross-language receipt hash vectors`

---

## Task 3 — PrintManager lifecycle remediation (plan.md §1.6 / R-GAP-05, separately authorized)

**Files:**
- Modify `pos_direct_print/public/js/pos_direct_print/core/print_manager.mjs`
- Modify `pos_direct_print/public/js/pos_direct_print/drivers/fake_driver.mjs` (one line: add `post_status_checked: true` to the success result metadata)
- Create `pos_direct_print/public/js/pos_direct_print/core/__tests__/print_manager.test.mjs`

**Interfaces (all private to PrintManager; no public signature changes):**

```js
// shared by requestPrint and retryJob: reserve/re-reserve stays in each caller,
// everything from receipt onward routes through this one cycle
async _attemptCycle(driver, receipt, request, state)
// state gains: { current: "PREFLIGHT"|"PRINTING", phase: "PREFLIGHT"|"PRINT"|"VERIFY" }

async _preflight(driver, state)
// detect -> initialize -> getStatus; throws canonical errors below, content stays unstarted

async _transitionTo(state, target_state)
// coordinator.transition + updates state.current

_settleStatus(result)
// FALLBACK_BROWSER on result.metadata.handoff
// SUCCEEDED only when accepted && content_completed && result.final_status.ready === true
//   && result.metadata.post_status_checked === true        (B-COMP-A gate)
// UNCERTAIN when content_started && !content_completed
// UNCERTAIN when accepted && content_completed but no approved post-status evidence
//   (DECIDED C-2: dispatch without approved post-status settles UNCERTAIN —
//    constitution §7 "unknown = may have printed"; FAILED_SAFE would understate risk)
// FAILED_SAFE otherwise
```

Preflight error mapping (existing codes only):

```js
detect unavailable      -> makeError("PDP_BRIDGE_UNAVAILABLE", { phase: "PREFLIGHT", metadata: { reason } })
initialize not ok       -> makeError("PDP_PRINTER_NOT_READY", { phase: "PREFLIGHT" })
status not ready:
  state "PAPER_OUT"     -> makeError("PDP_PRINTER_PAPER_OUT", { phase: "PREFLIGHT" })
  state "COVER_OPEN"    -> makeError("PDP_PRINTER_COVER_OPEN", { phase: "PREFLIGHT" })
  any other             -> makeError("PDP_PRINTER_NOT_READY", { phase: "PREFLIGHT" })
```

Settlement walk starts from the live state (`state.current`), walking the tail of the existing `SETTLE_PATHS` — `PRINTING→VERIFYING→SUCCEEDED` after dispatch, `PREFLIGHT→FAILED_SAFE` for preflight failures. No new transitions.

**Steps:**
- [ ] 1. RED: write `print_manager.test.mjs` using a recording stub driver + the `InMemoryApi` pattern from `integration/__tests__/foundation.test.mjs`. Cases: (1) happy-path call order is exactly `reserve → beginAttempt → detect → initialize → getStatus → transition(PREFLIGHT→PRINTING) → driver.print → completeAttempt → transition(PRINTING→VERIFYING) → transition(VERIFYING→SUCCEEDED)`; (2) detect unavailable → `FAILED_SAFE`, code `PDP_BRIDGE_UNAVAILABLE`, `print` never called; (3) getStatus `PAPER_OUT` → `FAILED_SAFE`, code `PDP_PRINTER_PAPER_OUT`; (4) dispatch complete but `post_status_checked` false/missing → outcome `UNCERTAIN`, never `SUCCEEDED` (B-AT-09); (5) dispatch complete, post-status ready:false → `UNCERTAIN`; (6) `retryJob` happy path re-runs the cycle and re-reserves `FAILED_SAFE→RESERVED`; (7) browser handoff result still settles `FALLBACK_BROWSER`. Run: `node --test pos_direct_print/public/js/pos_direct_print/core/__tests__/print_manager.test.mjs` → fails.
- [ ] 2. GREEN: refactor `print_manager.mjs`: extract `_attemptCycle`; add `_preflight`, `_transitionTo`, `_statusCodeFor`; insert lifecycle into the cycle before dispatch; gate `_settleStatus` per interface; make `_settle` walk from `state.current`; add `post_status_checked: true` to FakeDriver success metadata.
- [ ] 3. Run GREEN: new file passes. Then full JS suite — existing `foundation.test.mjs`, `fallback.test.mjs`, `error_normalizer.test.mjs`, `print_job.test.mjs` must stay green (FakeDriver change keeps them passing).
- [ ] 4. Commit: `fix: align PrintManager with frozen driver lifecycle and B-COMP Option A settlement`

---

## Task 4 — Terminal lookup API + POS context wiring (B4-01, C-6 resolved, C-3 resolved)

**C-3 rationale (transport exposure).** The driver needs the terminal's `connection_type` at runtime. Options inspected against the frozen contracts: (a) extend `TERMINAL_RUNTIME_FIELDS` in `projections.py` — rejected: plan.md §1.1 lists `core/projections.py` as reused without change, and A.31.7 freezes the terminal projection shape; (b) inject a constant at bootstrap — rejected: hardcodes a per-terminal value, violates Global Constraint 8. Chosen: the NEW row-scoped lookup added in this task (a sanctioned extension of `print_api.py`, the same precedent B-AC-01 uses) returns `terminal_id, transport, driver_key, paper_width_mm, qualification_status` — `transport` travels in the new lookup's own projection, not in the frozen one. Zero frozen-file edits.

**Files:**
- Modify `pos_direct_print/core/print_api.py` — add `resolve_terminal_for_profile(company, pos_profile)`
- Modify `pos_direct_print/public/js/pos_direct_print/core/print_api.mjs` — add operation
- Modify `pos_direct_print/public/js/pos_direct_print/integration/erpnext_v16_pos.mjs` — context wiring
- Modify `pos_direct_print/core/test_print_api.py` — lookup cases
- Modify `pos_direct_print/public/js/pos_direct_print/integration/__tests__/foundation.test.mjs` — context cases

**Interfaces:**

```python
# core/print_api.py
@frappe.whitelist()
def resolve_terminal_for_profile(company, pos_profile):
	"""Row-scoped read-only lookup: the enabled, QUALIFIED terminal for a
	Company + POS Profile. Returns the NEW terminal transport projection only.
	Mirrors _scoped_terminal authorization; fail-closed."""
	user = frappe.session.user
	scopes = user_scopes(user)
	if not scopes["unrestricted"]:
		if scopes["companies"] and company not in scopes["companies"]:
			frappe.throw(
				_("PDP_PERMISSION_DENIED: company is outside your authorized scope."),
				exc=frappe.PermissionError,
			)
		if scopes["manager"] and (not scopes["profiles"] or pos_profile not in scopes["profiles"]):
			frappe.throw(
				_("PDP_PERMISSION_DENIED: POS Profile is outside your authorized scope."),
				exc=frappe.PermissionError,
			)
		if not (scopes["manager"] or scopes["operator"]):
			frappe.throw(
				_("PDP_PERMISSION_DENIED: no print role grants terminal access."),
				exc=frappe.PermissionError,
			)
	name = frappe.db.get_value(
		"POS Print Terminal",
		{"company": company, "pos_profile": pos_profile, "enabled": 1},
		"name",
		order_by="creation asc",
	)
	if not name:
		frappe.throw(
			_("PDP_TERMINAL_NOT_FOUND: no enabled terminal for {0} / {1}.").format(company, pos_profile),
			exc=frappe.ValidationError,
		)
	terminal = frappe.get_doc("POS Print Terminal", name)
	if terminal.qualification_status != "QUALIFIED":
		frappe.throw(
			_("PDP_TERMINAL_NOT_QUALIFIED: terminal {0} is not qualified.").format(name),
			exc=frappe.ValidationError,
		)
	return {
		"terminal_id": terminal.terminal_id,
		"transport": terminal.transport,
		"driver_key": terminal.driver_key,
		"paper_width_mm": terminal.paper_width_mm,
		"qualification_status": terminal.qualification_status,
	}
```

```js
// print_api.mjs — add to OPERATIONS + client method
RESOLVE_TERMINAL_FOR_PROFILE: `${MODULE}.resolve_terminal_for_profile`,
resolveTerminalForProfile(company, pos_profile) { … }

// erpnext_v16_pos.mjs — constructor option + helpers
constructor(options = { …, resolve_terminal_context }) // injectable; default below
async resolve_context(summary) // -> { pos_direct_print_terminal_id,
                               //      pos_direct_print_idempotency_key, paired_client_id }
export function computeIdempotencyKey({ schema_version, reference_doctype, reference_name,
                                        terminal_id, job_type, purpose = "ORIGINAL_PRINT" })
// `pdpr1:` FNV over `${schema_version}|${reference_doctype}|${reference_name}|${terminal_id}|${job_type}|${purpose}`
// (plan.md §8 components, no timestamp; reuses receipt_builder canonicalize/hash lane)
```

Default `resolve_context`: read `summary.frm.doc.pos_profile` and company from the invoice snapshot; call `resolveTerminalForProfile`; cache the result per session keyed `company|pos_profile`; compute the idempotency key from `settings.receipt_schema_version` + invoice name + resolved terminal; read `paired_client_id` from `localStorage` (generate+persist once per browser). No hardcoded terminal anywhere.

The interception wrapper becomes:

```js
prototype.print_receipt = function intercepted_print_receipt(...args) {
  const settings = adapter._settings();
  if (!settings.enabled) return adapter.invokeOriginalPrint(original_method, this, args);
  return Promise.resolve()
    .then(() => adapter.resolve_context(this))
    .then((ctx) => Object.assign(this, ctx))
    .then(() => print_manager.requestPrint(
      adapter.buildPrintRequest(this, args, "POS_AUTO"),
      adapter._requestContext(this)))
    .then((outcome) => adapter._settleOutcome(outcome, original_method, this, args));
};
```

**Steps:**
- [ ] 1. RED: `test_print_api.py` cases — operator with applicable profile gets the transport projection; manager without POS Profile scope → `PermissionError`; user with no print role → `PermissionError`; no enabled terminal → `ValidationError PDP_TERMINAL_NOT_FOUND`; enabled but UNVERIFIED terminal → `ValidationError PDP_TERMINAL_NOT_QUALIFIED`; two terminals → oldest returned. Run focused module → fails.
- [ ] 2. GREEN: add `resolve_terminal_for_profile` to `print_api.py`. Run focused module → passes.
- [ ] 3. RED: JS cases in `foundation.test.mjs` — fake resolver supplies context → `buildPrintRequest` receives terminal/idem fields; `computeIdempotencyKey` stable for same inputs and differs across invoices; resolver failure surfaces canonical error without touching original print; disabled settings bypass resolver entirely (A-AT-06 regression). Run → fails.
- [ ] 4. GREEN: implement client operation + adapter wiring. Run full JS suite → green.
- [ ] 5. Commit: `feat: add row-scoped terminal lookup and POS print context wiring`

---

## Task 5 — B-AC-01 receipt snapshot binding (B4-02)

**Files:**
- Create `pos_direct_print/core/receipt_hash.py`
- Create `pos_direct_print/core/test_receipt_hash.py`
- Modify `pos_direct_print/core/reservation.py` — add `bind_receipt_snapshot`
- Modify `pos_direct_print/core/print_api.py` — add whitelisted `bind_receipt_snapshot`
- Modify `pos_direct_print/core/test_print_api.py` — binding cases
- Modify `pos_direct_print/public/js/pos_direct_print/core/print_api.mjs` — operation
- Modify `pos_direct_print/public/js/pos_direct_print/core/job_coordinator.mjs` — `bindReceiptSnapshot`
- Modify `pos_direct_print/public/js/pos_direct_print/core/print_manager.mjs` — binding step
- Modify `pos_direct_print/public/js/pos_direct_print/core/__tests__/print_manager.test.mjs` — binding cases

**Interfaces:**

```python
# core/receipt_hash.py
def canonicalize(value)      # JS-equivalent canonical JSON (rules below)
def hash_receipt(document)   # -> "pdpr1:<8 hex><8 hex>" FNV-1a over UTF-16 code units

# core/reservation.py
def bind_receipt_snapshot(job_name, reservation_owner, receipt_snapshot, receipt_hash):
	"""One guarded UPDATE: RESERVED state + matching non-empty reservation_owner +
	both binding fields empty. Zero affected rows -> if already bound with the SAME
	hash return the Job (DECIDED C-5 idempotency); else PDP_JOB_CONFLICT."""
	affected = _guarded_update(
		"UPDATE `tabPOS Print Job`"
		" SET `receipt_snapshot` = %s, `receipt_hash` = %s, `receipt_schema_version` = 1"
		" WHERE `name` = %s AND `status` = 'RESERVED'"
		" AND `reservation_owner` = %s AND `reservation_owner` <> ''"
		" AND (`receipt_snapshot` IS NULL OR `receipt_snapshot` = '')"
		" AND (`receipt_hash` IS NULL OR `receipt_hash` = '')",
		(receipt_snapshot, receipt_hash, job_name, reservation_owner),
		job_name,
		"RESERVED",
	)
	if affected:
		return frappe.get_doc("POS Print Job", job_name)
	stored = frappe.db.get_value(
		"POS Print Job", job_name, ["status", "reservation_owner", "receipt_hash"], as_dict=True
	)
	if (
		stored.status == "RESERVED"
		and stored.reservation_owner == reservation_owner
		and stored.receipt_hash == receipt_hash
	):
		return frappe.get_doc("POS Print Job", job_name)
	_throw_conflict(job_name, "RESERVED", stored.status)

# core/print_api.py
@frappe.whitelist()
def bind_receipt_snapshot(job_id, reservation_token, receipt_snapshot, receipt_hash):
	"""B-AC-01. Order: scope -> parse JSON -> schema v1 -> server-side hash
	recompute + equality -> guarded atomic bind. Returns job_status_projection
	only (snapshot/hash never leave through any projection — A.31.9 Level 1)."""
	user = frappe.session.user
	_scoped_job(job_id, user)
	try:
		document = json.loads(receipt_snapshot)
	except (TypeError, ValueError):
		frappe.throw(_("PDP_RECEIPT_INVALID: receipt snapshot is not valid JSON."), exc=frappe.ValidationError)
	if not isinstance(document, dict) or document.get("schema_version") != 1:
		frappe.throw(_("PDP_RECEIPT_INVALID: receipt snapshot must be schema version 1."), exc=frappe.ValidationError)
	if hash_receipt(document) != receipt_hash:
		frappe.throw(_("PDP_RECEIPT_INVALID: receipt hash does not match the snapshot."), exc=frappe.ValidationError)
	bound = reservation_service.bind_receipt_snapshot(job_id, reservation_token, receipt_snapshot, receipt_hash)
	return job_status_projection(bound)
```

`receipt_hash.py` parity rules with `receipt_builder.mjs`: object keys sorted with `sorted()` (Python codepoint order matches JS UTF-16 order for ASCII keys; all receipt keys are ASCII); `json.dumps(key, ensure_ascii=False)` for key quoting; `True`→`true`, `False`→`false` checked BEFORE `int`; `int` → `str(v)`; `float` → `str(int(v))` when integral else shortest `repr`; `None`→`null`; strings `json.dumps(..., ensure_ascii=False)`; hash loop reads UTF-16-LE code units (`canonical.encode("utf-16-le")`, two bytes per unit) exactly mirroring JS `charCodeAt`.

```js
// job_coordinator.mjs
async bindReceiptSnapshot({ job_id, reservation_token, receipt }) {
  return this.api.bindReceiptSnapshot({
    job_id, reservation_token,
    receipt_snapshot: canonicalize(receipt),   // import { canonicalize } from "../receipt/receipt_builder.mjs"
    receipt_hash: hashReceipt(receipt),
  });
}
```

PrintManager wiring — approved sequence `reserve → build → BIND → beginAttempt → preflight → print`:

```js
// requestPrint: after receipt built, before _selectDriver/beginAttempt
await this.coordinator.bindReceiptSnapshot({
  job_id: reservation.job_id,
  reservation_token: reservation.reservation_token,
  receipt,
});
// retryJob (DECIDED C-5): skip the bind when reusing the bound snapshot
const receipt = this.fetchReceipt ? await this.fetchReceipt(job_id) : /* rebuild */;
if (!this.fetchReceipt) {
  await this.coordinator.bindReceiptSnapshot({ job_id, reservation_token: state.reservation_token, receipt });
}
```

**Steps:**
- [ ] 1. RED: write `test_receipt_hash.py` loading `core/hash_vectors.json` (Task 2) — for every vector `canonicalize(receipt) == canonical` and `hash_receipt(receipt) == hash`; plus direct cases: `True` not treated as int; `1.5` float; empty doc skeleton. Run: `--module pos_direct_print.core.test_receipt_hash --failfast` → fails (module missing).
- [ ] 2. GREEN: implement `receipt_hash.py`. Run focused module → all vectors pass. This is the C-7 cross-language gate; do not proceed to the endpoint until green.
- [ ] 3. RED: `test_print_api.py` binding cases — (a) RESERVED + matching token persists snapshot/hash/schema version; (b) second identical bind idempotent success; (c) different hash while bound → `PDP_JOB_CONFLICT`; (d) wrong/empty token → rejected; (e) bind after `start_attempt` (PREFLIGHT) → rejected; (f) hash mismatch with client-provided value → `ValidationError`; (g) malformed JSON → `ValidationError`; (h) `retrieve_job` and `transition_job` responses contain no `receipt_snapshot`/`receipt_hash` keys. Run focused module → fails.
- [ ] 4. GREEN: add server endpoint + reservation helper. Run focused module → passes. Run full Python suite → green.
- [ ] 5. RED: JS cases in `print_manager.test.mjs` — bind called between reserve and beginAttempt with exact args; bind failure (stub coordinator throws `PDP_JOB_CONFLICT`) → outcome `FAILED_SAFE`, no attempt created; retry with `fetchReceipt` skips bind; retry without `fetchReceipt` binds. Run → fails.
- [ ] 6. GREEN: client operation + coordinator method + manager wiring. Run full JS suite → green.
- [ ] 7. Commit: `feat: bind receipt snapshot to reserved job (B-AC-01)`

---

## Task 6 — imin_v1 driver (B2-01/02/03/04/05/06)

**Files:**
- Create `pos_direct_print/public/js/pos_direct_print/drivers/imin_v1_driver.mjs`
- Create `pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_v1_driver.test.mjs`

**Interfaces:**

```js
import { BaseDriver } from "./base_driver.mjs";
import { IminSdkAdapter } from "./imin_sdk_adapter.mjs";
import { makeError, isPrintDomainError } from "../core/errors.mjs";
import { normalize } from "../core/error_normalizer.mjs";
import { resolvePaperProfile } from "../receipt/paper_profiles.mjs";
import { renderReceiptLines } from "../receipt/receipt_lines.mjs";

export const IMIN_V1_DRIVER_KEY = "imin_v1";

export class IminV1Driver extends BaseDriver {
  /**
   * @param {object} options every hardware unknown is injected here:
   * @param {IminSdkAdapter} [options.sdk_adapter]    test seam; default new IminSdkAdapter({ address, timeout_ms })
   * @param {"USB"|"SPI"|"Bluetooth"} [options.connection_type]  GATED: SPI candidate; confirmed by B1-04 app-origin qualification
   * @param {object} [options.paper_profile]          resolvePaperProfile() output; default REFERENCE_PROFILE
   * @param {string} [options.address]                default "127.0.0.1"
   * @param {number} [options.timeout_ms]             default 5000
   * @param {number} [options.post_connect_delay_ms]  default 0 — calibration knob; nonzero only when B1-05 records a required delay
   */
  constructor(options = {})

  async detect(context)     // adapter.detect() passthrough: { available, reason, error, metadata }
  async initialize(context) // adapter.initialize(connection_type) [+ gated delay] then getStatus must be READY; throws normalized error otherwise; never dispatches content
  getCapabilities()         // DriverCapabilities A.10.4 from profile (below)
  async getStatus()         // adapter.getStatus(connection_type) -> mapStatus -> PrinterStatus A.10.5; raw value only in metadata.raw_code
  async print(receipt_document, job_context) // B-DRV-07 sequence -> DriverPrintResult A.10.6
  async feed(request)       // adapter.feed(profile.final_feed) -> DriverPrintResult
  cut(request)              // this._unsupportedResult("cut") — controlled outcome, never throws (B-AT-18)
  dispose()                 // adapter.dispose(); later detect() may run again (B-AT-19)
}

export function mapStatus(raw_value)
// 0 -> READY (ready:true)  7 -> PAPER_OUT  3 -> COVER_OPEN  8 -> PAPER_LOW
// -1 | 1 -> DISCONNECTED   99 -> UNKNOWN_ERROR   else UNKNOWN_ERROR
```

`print()` sequence (B-DRV-07; content_started at first content dispatch, content_completed after final feed, `verification_supported` always false):

```js
async print(receipt_document, job_context) {
  const profile = resolvePaperProfile(receipt_document.paper_profile || this.paper_profile.key);
  const result = { accepted: false, content_started: false, content_completed: false,
                   verification_supported: false, final_status: null,
                   metadata: { driver_key: this.driver_key, post_status_checked: false } };
  try {
    const pre = await this.getStatus();
    if (pre.state === "PAPER_OUT") throw makeError("PDP_PRINTER_PAPER_OUT", { phase: "PREFLIGHT" });
    if (!pre.ready) throw makeError("PDP_PRINTER_NOT_READY", { phase: "PREFLIGHT" });

    this._require(this.adapter.setPageFormat(profile.page_format));
    this._require(this.adapter.setTextWidth(profile.text_width_dots));
    this._require(this.adapter.setAlignment(0)); // left default (B-RCP-06)
    this._require(this.adapter.setTextSize(1));
    this._require(this.adapter.setTextStyle(0));

    for (const line of renderReceiptLines(receipt_document, profile)) {
      if (line.kind === "feed") continue; // single final feed below
      if (line.kind === "style") { this._require(this.adapter.setTextStyle(line.bold ? 1 : 0)); continue; }
      const dispatched = this.adapter.printText(line.text);
      result.content_started = true;      // first content dispatch
      this._require(dispatched);          // mid-print failure -> UNCERTAIN via manager
    }
    this._require(this.adapter.feed(profile.final_feed));
    result.content_completed = true;

    const post = await this.getStatus();  // bounded: adapter timeout; failure forbids SUCCEEDED
    result.metadata.post_status_checked = true;
    result.final_status = post;
    result.accepted = true;
    return result;
  } catch (raw) {
    if (isPrintDomainError(raw)) throw raw;
    throw normalize(raw, result.content_started ? "PRINT" : "PREFLIGHT",
                    { content_started: result.content_started });
  }
}
// _require(dispatch): if (!dispatch.accepted) throw dispatch.error;
```

`getCapabilities()` (B-DRV-09):

```js
{ driver_key: "imin_v1", available: this._initialized,
  supports_status: true, supports_text: true, supports_columns: false,
  supports_image: false, supports_qr: false, supports_feed: true, supports_cut: false,
  paper_width_mm: profile.width_mm,
  transport: this.connection_type === "Bluetooth" ? "BLUETOOTH" : this.connection_type,
  metadata: {} }
```

**Steps:**
- [ ] 1. RED: write `imin_v1_driver.test.mjs` reusing the B1 fake-SDK pattern (`makeRuntime(script)` from `drivers/__tests__/imin_sdk_adapter.test.mjs`). Cases: (1) `mapStatus` table 0/3/7/8/-1/1/99/garbage, raw value only in `metadata.raw_code`; (2) `initialize` success → READY (B-AT-03); init throw → `PDP_PRINTER_NOT_READY`, no dispatch (B-AT-04); (3) command sequence with recorded `outbound_commands`: `setPageFormat, setTextWidth, setAlignment, setTextSize, setTextStyle` first, then style-before-text pairs, each `printText` outbound is `line + "\n"` with exactly one trailing newline even when the logical line already ends `\n`, final `printAndFeedPaper` last (B-AT-15); (4) paper out before dispatch → `content_started` false, `PDP_PRINTER_PAPER_OUT` (B-AT-06); (5) throw at line N>0 → `content_started` true, `content_completed` false; (6) post-status not READY → `post_status_checked: true`, `final_status.ready: false`; (7) `cut()` → controlled unsupported result (B-AT-18); (8) `dispose()` then `detect()` works again (B-AT-19); (9) containment: no property of any returned or thrown value identity-equals the fake SDK instance (B-AT-20). Run → fails.
- [ ] 2. GREEN: implement `imin_v1_driver.mjs` per interfaces. Run new file → passes.
- [ ] 3. Run full JS suite → green. Verify adapter file untouched (`git diff --stat` lists only the two new files).
- [ ] 4. Commit: `feat: add imin_v1 driver on the B1 SDK adapter`

---

## Task 7 — Asset bundle, safe SDK loader, bootstrap registration (B4-03)

**Files:**
- Modify `pos_direct_print/hooks.py` — one uncommented line
- Create `pos_direct_print/public/js/pos_direct_print/web/pos_direct_print.js` (classic script loader)
- Modify `pos_direct_print/public/js/pos_direct_print/core/bootstrap.mjs` — `imin_v1` registration
- Create `pos_direct_print/public/js/pos_direct_print/integration/__tests__/asset_loader.test.mjs`

**UMD `window.Vue` hazard, solved without touching pinned bytes:** the asset tail executes `if (inBrowser && window.Vue) window.Vue.use(IminPrinter);`. The loader hides `window.Vue` for the evaluation window and restores it in `onload` (which fires after script execution completes).

```js
// hooks.py — the ONLY hooks change
app_include_js = ["pos_direct_print/public/js/pos_direct_print/web/pos_direct_print.js"]
```

```js
// web/pos_direct_print.js — classic script, idempotent, no ESM syntax
(function () {
  if (window.__pos_direct_print_booted) return;
  window.__pos_direct_print_booted = true;

  var SDK_URL = "/assets/pos_direct_print/js/lib/imin/1.4.0/imin-printer.js";
  var BOOTSTRAP_URL = "/assets/pos_direct_print/js/pos_direct_print/core/bootstrap.mjs";

  function load_sdk_with_vue_guard() {
    return new Promise(function (resolve, reject) {
      var had_vue = "Vue" in window;
      var saved_vue = window.Vue;
      if (had_vue) {
        try { window.Vue = undefined; } catch (e) {
          // ponytail: non-writable window.Vue getter — logged; device gate confirms real state (C-9)
          console.warn("pos_direct_print: could not hide window.Vue; SDK Vue plugin may install");
        }
      }
      function restore() { if (had_vue) { try { window.Vue = saved_vue; } catch (e) {} } }
      var script = document.createElement("script");
      script.src = SDK_URL;
      script.async = false;
      script.onload = function () { restore(); resolve(); };
      script.onerror = function () { restore(); reject(new Error("PDP_SDK_ASSET_LOAD_FAILED")); };
      document.head.appendChild(script);
    });
  }

  function wait_for_pos_prototype(retries) {
    // ponytail: bounded polling (500 ms x 30); swap for a frappe router/page event if one proves reliable
    return new Promise(function (resolve, reject) {
      var left = retries;
      var timer = setInterval(function () {
        var proto = window.erpnext && window.erpnext.PointOfSale
          && window.erpnext.PointOfSale.PastOrderSummary
          && window.erpnext.PointOfSale.PastOrderSummary.prototype;
        if (proto && typeof proto.print_receipt === "function") {
          clearInterval(timer); resolve(proto);
        } else if (--left <= 0) {
          clearInterval(timer); reject(new Error("PDP_POS_CONTEXT_UNAVAILABLE"));
        }
      }, 500);
    });
  }

  load_sdk_with_vue_guard()
    .then(function () { return import(BOOTSTRAP_URL); })
    .then(function (mod) {
      return wait_for_pos_prototype(30).then(function (proto) {
        return mod.bootSubsystem({ pos_context: proto, active_driver_key: "imin_v1" });
      });
    })
    .catch(function (error) {
      // Non-fatal for ERPNext: POS keeps baseline browser print (A-DOD-04).
      console.warn("pos_direct_print: bootstrap skipped", error && error.message);
    });
})();
```

```js
// bootstrap.mjs — new exported helper used by the loader + tests; initialize() core unchanged
export function bootSubsystem(context) {
  const bootstrap = new SubsystemBootstrap();
  return bootstrap.initialize({
    ...context,
    settings: context.settings || { receipt_schema_version: 1 },
  });
}
// inside SubsystemBootstrap.initialize(), after registry creation:
const runtime = context.runtime || globalThis;
if (context.register_imin_v1 !== false && typeof runtime.IminPrinter === "function") {
  registry.registerDriver({
    driver_key: "imin_v1",
    factory: () => new IminV1Driver({
      connection_type: context.terminal_transport || "SPI", // injected from resolved terminal; GATED by B1-04
      paper_profile: resolvePaperProfile(context.paper_profile || "reference_58mm"),
      address: context.sdk_address,
      timeout_ms: context.sdk_timeout_ms,
    }),
    capabilities: { supports_status: true, supports_text: true, supports_feed: true,
                    supports_columns: false, supports_image: false, supports_qr: false,
                    supports_cut: false, paper_width_mm: 58,
                    transport: context.terminal_transport || "SPI" },
  });
}
```

**Steps:**
- [ ] 1. RED: write `asset_loader.test.mjs` with a fake `window`/`document` shim whose `createElement("script")` "loads" by evaluating the pinned asset source against the shim (`new Function("window","self", source)` with `this` bound per UMD). Cases: (a) fake `Vue` whose `use` throws → asset evaluation succeeds, `Vue.use` never called, `window.Vue` restored to the same identity; (b) no `Vue` → `window.IminPrinter` becomes a function; (c) `bootSubsystem` twice → second call returns the identical result object (idempotency A-DOD-03); (d) `IminPrinter` absent → registry has no `imin_v1`, `initialize` still succeeds with warning; (e) double loader boot flag → single SDK script appended. Run → fails.
- [ ] 2. GREEN: create loader, add `bootSubsystem` + registration block to `bootstrap.mjs`, uncomment `app_include_js` in `hooks.py`. Run new test → passes.
- [ ] 3. Run full JS suite → green. Run pinned-asset checksum (Global Constraint 6).
- [ ] 4. Build verification (one-time, C-8): `docker exec frappe_docker_devcontainer-frappe-1 bash -lc 'cd /workspace/development/frappe-bench && bench build --app pos_direct_print'` — confirm the dynamic `import()` URL survives the asset pipeline unrewritten (grep the built bundle for `bootstrap.mjs`).
- [ ] 5. Commit: `feat: load pinned iMin SDK with Vue guard and register imin_v1 driver`

---

## Task 8 — Pre-output failure boundary + fallback preservation (B5-01/02/03)

**Files:**
- Modify `pos_direct_print/public/js/pos_direct_print/drivers/__tests__/imin_v1_driver.test.mjs` — failure-mapping cases
- Modify `pos_direct_print/public/js/pos_direct_print/integration/__tests__/fallback.test.mjs` — end-to-end fallback cases

No production code is expected in this task — B5 is mapping verification on top of Tasks 3 and 6. If any of the four failures cannot be expressed with existing codes, STOP and record an unresolved contract question (plan.md §6) instead of adding a code.

**Mapping (existing codes only):**

| Failure | Source | Code | State |
| --- | --- | --- | --- |
| Bridge unavailable | adapter detect reason | `PDP_BRIDGE_UNAVAILABLE` | `FAILED_SAFE` |
| Initialization failure | driver initialize | `PDP_PRINTER_NOT_READY` | `FAILED_SAFE` |
| Printer not ready | driver getStatus (raw -1/1/3/8/99) | `PDP_PRINTER_NOT_READY` / `PDP_PRINTER_COVER_OPEN` | `FAILED_SAFE` |
| Paper out before content | driver getStatus raw 7 pre-dispatch | `PDP_PRINTER_PAPER_OUT` | `FAILED_SAFE` |

**Steps:**
- [ ] 1. RED: driver-test cases — each of the four failures returns/throws the canonical code with `content_started` false and no content dispatched (B-AT-02/04/06, B-DOD-11).
- [ ] 2. RED: `fallback.test.mjs` end-to-end cases with the imin driver scripted through a fake SDK — after each pre-output failure: `fallbackToBrowser(job_id, true)` → `FALLBACK_BROWSER`, never `SUCCEEDED` (B-AT-12); `fallbackToBrowser(job_id, false)` → `PDP_PERMISSION_DENIED`; a failure mid-dispatch instead settles `UNCERTAIN` and fallback is rejected (content risk).
- [ ] 3. RED: containment cases — `toUserError(outcome.error)` carries only message keys and actions; no raw SDK text or object appears in any outcome; raw status values appear only inside driver `metadata` (B-AT-14/20, B-DOD-16).
- [ ] 4. GREEN: fix any mapping gaps found (expected: none). Run full JS suite → green.
- [ ] 5. Commit: `test: verify pre-output failure mapping and browser fallback preservation`

---

## Device Gate — B1-04/B1-05 app-origin qualification (manual, on reference device)

No code in this gate. Run on `Domba Jantan` (iMin L21D01, Android 11, ROM 1.2.8.3.12_260603, Chrome 108.0.5359.61, iMinprinterplugin 1.2.15_2408141815, 58 mm) AFTER Tasks 1–8 are merged, and record every result in `research.md` §13:

1. Open ERPNext POS from the app origin; confirm the loader boots, `window.Vue` was hidden/restored, `window.IminPrinter` exists, no SDK load warnings.
2. `detect`: WebSocket present, `connect()` succeeds from app origin (`ws://127.0.0.1:8081/websocket`); record cold-start connection time.
3. `initialize` with `SPI`; if it fails, try `USB` — the working transport becomes the terminal's `transport` value (record; never derive from Android version).
4. `getStatus` raw value with paper loaded, cover closed → confirm `0` = READY.
5. Print one minimal text line; confirm exactly one trailing feed-line of physical output per line (B1-05 newline behavior, C-10).
6. If a post-connect delay proves required, set `post_connect_delay_ms`; otherwise leave `0` (research §5.3).
7. Update the qualified `POS Print Terminal` record (`transport`, `qualification_status = QUALIFIED`, `paper_width_mm = 58`) and `REFERENCE_PROFILE.final_feed` candidate values — config changes only, no code branches.

B6 physical UAT and B4-04 remain BLOCKED UNTIL PHYSICAL UAT per `tasks.md`; they are not part of this plan.

---

## Explicitly Excluded

Milestone C: multi-tab coordination, cross-tab locking, double-click protection, sleep/wake recovery, repeated bridge re-initialization, long-lived lifecycle recovery, sophisticated retry, mid-print failure recovery, paper-out during print, full UNCERTAIN user workflow, duplicate print recovery, soak tests.

Milestone D: multi-model capability matrices, generic multi-model support, runtime-generation detection, `imin_v2`, automatic model detection, ROM matrix, model-specific status normalization, universal USB/SPI handling, universal 58/80 mm profiles, cutter matrix, model quirks.

Also excluded: B4-04 physical end-to-end run, B6 UAT checklist, pairing workflows, reprint snapshot policy (deferred inside B-AC-01). No new error codes, no schema changes, no permission changes, no state transitions anywhere in this plan.

## Resolved Conflicts (decisions embedded in tasks above)

| # | Resolution |
| --- | --- |
| C-2 | DECIDED: content dispatched without approved post-status evidence settles `UNCERTAIN` (constitution §7); `SUCCEEDED` requires the B-COMP-A gate. Task 3. |
| C-5 | DECIDED: server idempotently accepts a bind whose stored hash equals the submitted hash under the same reservation owner; `retryJob` skips bind when reusing the bound snapshot. Task 5. |
| C-6 | DECIDED: one read-only row-scoped `resolve_terminal_for_profile(company, pos_profile)` endpoint; no hardcoded terminal. Task 4. |
| C-3 | RESOLVED: `transport` rides the new lookup's own projection; frozen `TERMINAL_RUNTIME_FIELDS` untouched (rationale in Task 4). |
| C-7 | Controlled by frozen `hash_vectors.json` executed by both language suites before the endpoint ships. Tasks 2 + 5. |
| C-8 | Classic loader + dynamic `import()`; one-time `bench build` grep verification. Task 7 step 4. |
| C-9 | Hide/restore `window.Vue` with warning fallback; device gate confirms real Desk state. Task 7 + Device Gate step 1. |
| C-10 | Fake-SDK outbound assertion now; physical single-newline evidence is Device Gate step 5. |
| C-11 | Kept as-is (B1-frozen); identical settle outcome makes the distinction moot for Milestone B. |
