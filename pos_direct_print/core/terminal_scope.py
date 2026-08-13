"""Which POS Profiles one physical terminal may print for.

A counter can serve more than one outlet without gaining a second printer.
`POS Print Terminal.pos_profile` stays the terminal's primary binding, and
`extra_pos_profiles` widens what it may print for. Every printing decision about
a terminal asks this module, so the answer cannot drift between the reprint
guard, the terminal lookup, and the reservation path.

This module governs PRINTING scope, not DocType read scope. Terminal reads stay
bound to the terminal's own `pos_profile` field, because Frappe applies the POS
Profile User Permission to that Link field directly (see core.security).
"""

import frappe

EXTRA_PROFILE_TABLE = "`tabPOS Print Terminal Profile`"


def served_pos_profiles(terminal):
	"""POS Profiles this terminal may print for: the default plus the extra rows.

	`terminal` accepts a document or a terminal name.
	"""
	doc = frappe.get_doc("POS Print Terminal", terminal) if isinstance(terminal, str) else terminal
	profiles = [doc.pos_profile] if doc.pos_profile else []
	profiles += [row.pos_profile for row in (doc.get("extra_pos_profiles") or []) if row.pos_profile]
	return profiles


def serves_pos_profile(terminal, pos_profile):
	return bool(pos_profile) and pos_profile in served_pos_profiles(terminal)


def terminal_names_serving(pos_profile, company=None, enabled=True, qualified=False):
	"""Terminal names that may print for a POS Profile, oldest first.

	Oldest first so a stable terminal wins when a counter has more than one.
	"""
	conditions = [
		"(term.pos_profile = %(pos_profile)s"
		f" OR EXISTS (SELECT 1 FROM {EXTRA_PROFILE_TABLE} extra"
		" WHERE extra.parent = term.name AND extra.pos_profile = %(pos_profile)s))"
	]
	values = {"pos_profile": pos_profile}
	if company:
		conditions.append("term.company = %(company)s")
		values["company"] = company
	if enabled:
		conditions.append("term.enabled = 1")
	if qualified:
		conditions.append("term.qualification_status = 'QUALIFIED'")

	return frappe.db.sql_list(
		"SELECT term.name FROM `tabPOS Print Terminal` term"
		f" WHERE {' AND '.join(conditions)}"
		" ORDER BY term.creation ASC",
		values,
	)
