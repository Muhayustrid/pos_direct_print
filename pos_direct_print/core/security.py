"""Row-level security for the custom print DocTypes.

One rule source (`user_scopes` + `job_row_visible`) feeds BOTH the list-query
conditions (permission_query_conditions) and the document-level checks
(has_permission), per A.31.15: a row hidden from the list must also be denied
on direct document access, and vice versa.

Scope rules (A.31.10-A.31.14, A.31.24, A.31.25):

- Operator: own jobs only (`requested_by = user`), intersected with the
  companies the user may access AND the ERPNext POS Profile applicability
  rule: the Job's POS Profile must be enabled and either list the Operator in
  `tabPOS Profile User` or declare no applicable users at all. A Job with no
  applicable user rows is treated as available to every Operator, mirroring
  ERPNext v16 `get_pos_profile`.
- Manager: jobs in explicitly authorized POS Profiles (Frappe User Permission),
  intersected with company access. Absence of a POS Profile User Permission
  means ZERO outlet scope, never unrestricted (fail-closed, A.31.24).
- Attempts inherit their parent Job scope; Terminal reads follow the manager's
  POS Profile scope. A terminal that serves extra outlets is still scoped by its
  own `pos_profile` field: Frappe applies the POS Profile User Permission to
  that Link field directly, so no hook can widen what a Manager sees. Terminal
  administration is System Manager work (A.31.5), and printing scope is decided
  in core.terminal_scope, not here.
- System Manager / Administrator: unrestricted.
"""

import frappe

OPERATOR_ROLE = "POS Print Operator"
MANAGER_ROLE = "POS Print Manager"
SYSTEM_MANAGER_ROLE = "System Manager"

JOB_TABLE = "`tabPOS Print Job`"
ATTEMPT_TABLE = "`tabPOS Print Attempt`"
TERMINAL_TABLE = "`tabPOS Print Terminal`"


def user_scopes(user):
	"""Resolve the row-level scope for a user. Single rule source for both the
	query conditions and the document checks."""
	if user == "Administrator" or SYSTEM_MANAGER_ROLE in frappe.get_roles(user):
		return {"unrestricted": True}

	user_permissions = _user_permission_map(user)
	return {
		"unrestricted": False,
		"operator": OPERATOR_ROLE in frappe.get_roles(user),
		"manager": MANAGER_ROLE in frappe.get_roles(user),
		# Empty companies = no Frappe company restriction (company permission only
		# applies when User Permissions exist).
		"companies": sorted(set(user_permissions.get("Company", []))),
		# Empty profiles = zero outlet scope for a Manager (fail-closed).
		"profiles": sorted(set(user_permissions.get("POS Profile", []))),
	}


def job_row_visible(scopes, user, requested_by, company, pos_profile):
	"""True if the given Job row values are visible to the resolved scopes."""
	if scopes["unrestricted"]:
		return True

	company_ok = not scopes["companies"] or company in scopes["companies"]
	if not company_ok:
		return False

	if scopes["operator"] and requested_by == user:
		return operator_pos_profile_is_applicable(user, pos_profile, company)
	if scopes["manager"] and pos_profile and pos_profile in scopes["profiles"]:
		return True
	return False


def operator_pos_profile_condition(user, profile_expression, company_expression):
	"""Return the ERPNext v16 POS Profile applicability predicate for an Operator."""
	user = frappe.db.escape(user)
	return (
		"EXISTS ("
		"SELECT 1 FROM `tabPOS Profile` profile "
		f"WHERE profile.name = {profile_expression} "
		f"AND profile.company = {company_expression} "
		"AND profile.disabled = 0 "
		"AND ("
		"EXISTS ("
		"SELECT 1 FROM `tabPOS Profile User` applicable "
		"WHERE applicable.parent = profile.name "
		f"AND applicable.user = {user}"
		") "
		"OR NOT EXISTS ("
		"SELECT 1 FROM `tabPOS Profile User` configured "
		"WHERE configured.parent = profile.name"
		")"
		")"
		")"
	)


def operator_pos_profile_is_applicable(user, pos_profile, company):
	condition = operator_pos_profile_condition(
		user,
		frappe.db.escape(pos_profile),
		frappe.db.escape(company),
	)
	return bool(frappe.db.sql(f"SELECT 1 WHERE {condition}"))


# Query conditions -----------------------------------------------------------


def get_job_query_conditions(user):
	scopes = user_scopes(user)
	if scopes["unrestricted"]:
		return ""

	clauses = []
	if scopes["operator"]:
		clause = f"requested_by = {frappe.db.escape(user)}"
		if scopes["companies"]:
			clause += f" AND company IN {_sql_values(scopes['companies'])}"
		clause += " AND " + operator_pos_profile_condition(user, "pos_profile", "company")
		clauses.append(f"({clause})")
	if scopes["manager"] and scopes["profiles"]:
		clause = f"pos_profile IN {_sql_values(scopes['profiles'])}"
		if scopes["companies"]:
			clause += f" AND company IN {_sql_values(scopes['companies'])}"
		clauses.append(f"({clause})")

	if not clauses:
		return "1=0"
	return "(" + " OR ".join(clauses) + ")"


def get_attempt_query_conditions(user):
	scopes = user_scopes(user)
	if scopes["unrestricted"]:
		return ""
	# Attempts inherit the parent Job scope. Operators get no direct DocType access
	# to Attempts at all (A.31.16), so the query must return nothing for them.
	if not scopes["manager"] or not scopes["profiles"]:
		return "1=0"
	return f"job IN (SELECT name FROM {JOB_TABLE} WHERE {get_job_query_conditions(user)})"


def get_terminal_query_conditions(user):
	scopes = user_scopes(user)
	if scopes["unrestricted"]:
		return ""
	if scopes["manager"] and scopes["profiles"]:
		# Scope follows the terminal's own POS Profile field, not the extra
		# profiles it may also print for: Frappe applies the POS Profile User
		# Permission to that Link field itself, so a widened condition here could
		# not grant more than the built-in filter allows. Terminal administration
		# belongs to System Manager anyway (A.31.5).
		clause = f"pos_profile IN {_sql_values(scopes['profiles'])}"
		if scopes["companies"]:
			clause += f" AND company IN {_sql_values(scopes['companies'])}"
		return clause
	return "1=0"


# Document-level checks ------------------------------------------------------


def has_job_permission(doc, ptype="read", user=None, **kwargs):
	if ptype not in ("read", "select"):
		# Mutations are already denied by the role matrix; the hook only narrows reads.
		return True

	user = user or frappe.session.user
	scopes = user_scopes(user)
	if scopes["unrestricted"]:
		return True

	return job_row_visible(scopes, user, doc.requested_by, doc.company, doc.pos_profile)


def has_attempt_permission(doc, ptype="read", user=None, **kwargs):
	if ptype not in ("read", "select"):
		return True

	user = user or frappe.session.user
	scopes = user_scopes(user)
	if scopes["unrestricted"]:
		return True

	parent = frappe.db.get_value(
		"POS Print Job", doc.job, ["requested_by", "company", "pos_profile"], as_dict=True
	)
	if not parent:
		# Fail-closed: scope cannot be resolved.
		return False

	return job_row_visible(scopes, user, parent.requested_by, parent.company, parent.pos_profile)


def has_terminal_permission(doc, ptype="read", user=None, **kwargs):
	if ptype not in ("read", "select"):
		return True

	user = user or frappe.session.user
	scopes = user_scopes(user)
	if scopes["unrestricted"]:
		return True

	company_ok = not scopes["companies"] or doc.company in scopes["companies"]
	return (
		scopes["manager"] and company_ok and bool(doc.pos_profile) and doc.pos_profile in scopes["profiles"]
	)


def _user_permission_map(user):
	rows = frappe.get_all("User Permission", filters={"user": user}, fields=["allow", "for_value"])
	grouped = {}
	for row in rows:
		grouped.setdefault(row.allow, []).append(row.for_value)
	return grouped


def _sql_values(values):
	return "(" + ", ".join(frappe.db.escape(value) for value in values) + ")"
