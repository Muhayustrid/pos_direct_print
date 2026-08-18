"""Self-contained master data for the Direct Print test suites.

Every suite used to point at the operator's own records — Company
"PT. JUARA ROTI INDONESIA" and POS Profile "yusuf" — so the tests only passed on
the one machine that happened to hold that data, and failed everywhere else with
`DoesNotExistError` / `LinkValidationError` before a single assertion ran. These
helpers build the master data the suites need instead, on any site.

Nothing here commits: `IntegrationTestCase` rolls the whole transaction back in
`addClassCleanup(_rollback_db)`, which takes these rows with it.

The helpers are idempotent by name rather than cached in a module global for that
same reason — the rollback runs once per test *class*, so a row created by an
earlier class is already gone when the next one starts, while a cached name would
still look valid. Looking the name up each time costs one indexed read and is
always truthful.
"""

import uuid

import frappe

COMPANY_NAME = "_PDP Test Company"
COMPANY_ABBR = "_PDPT"
SECOND_COMPANY_NAME = "_PDP Test Company 2"
SECOND_COMPANY_ABBR = "_PDPT2"
OUTLET_A_NAME = "_PDP Outlet A"
OUTLET_B_NAME = "_PDP Outlet B"
FOREIGN_OUTLET_NAME = "_PDP Foreign Outlet"
CURRENCY = "IDR"
COUNTRY = "Indonesia"


def test_company() -> str:
	"""The Company every Direct Print fixture hangs off."""
	return ensure_company(COMPANY_NAME, COMPANY_ABBR)


def second_test_company() -> str:
	"""A Company the primary fixtures never touch, for cross-Company refusals."""
	return ensure_company(SECOND_COMPANY_NAME, SECOND_COMPANY_ABBR)


def test_outlet_a() -> str:
	"""The default outlet terminals and jobs bind to."""
	return ensure_pos_profile(OUTLET_A_NAME)


def test_outlet_b() -> str:
	"""A second outlet on the same Company, for multi-outlet scope tests."""
	return ensure_pos_profile(OUTLET_B_NAME)


def foreign_outlet() -> str:
	"""An outlet on a different Company, for cross-Company refusal tests."""
	return ensure_pos_profile(FOREIGN_OUTLET_NAME, company=second_test_company())


def ensure_company(company_name: str, abbr: str) -> str:
	"""Insert the named Company once per transaction, without its chart of accounts.

	`ignore_chart_of_accounts` is what makes this affordable: Company.on_update
	otherwise builds the full CoA, default warehouses, cost centres and tax
	templates, none of which any Direct Print test reads — these DocTypes link
	Company only as a scope label.
	"""
	if frappe.db.exists("Company", company_name):
		return company_name

	previous = frappe.local.flags.ignore_chart_of_accounts
	frappe.local.flags.ignore_chart_of_accounts = True
	try:
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": abbr,
				"default_currency": CURRENCY,
				"country": COUNTRY,
			}
		)
		company.insert(ignore_permissions=True)
	finally:
		frappe.local.flags.ignore_chart_of_accounts = previous
	return company.name


def ensure_warehouse(company: str) -> str:
	"""A leaf Warehouse on ``company``; POS Profile links one as mandatory."""
	warehouse_name = f"_PDP Store - {frappe.get_cached_value('Company', company, 'abbr')}"
	if frappe.db.exists("Warehouse", warehouse_name):
		return warehouse_name
	return (
		frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": "_PDP Store",
				"company": company,
				"is_group": 0,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


def ensure_pos_profile(profile_name: str, *, company: str | None = None, disabled: int = 0) -> str:
	"""Insert a POS Profile scoped to ``company``, bypassing ERPNext's validate.

	ERPNext's POSProfile.validate demands income/expense accounts, a cost centre
	and a Mode of Payment account — all of which live in the chart of accounts
	`ensure_company` deliberately skips. Direct Print reads only `company`,
	`disabled` and `applicable_for_users` from a profile, so the fixture inserts
	the fields those checks actually consult rather than standing up an accounting
	tree no assertion looks at. Same approach as `roti_ropi_pos.tests.helpers`.
	"""
	if frappe.db.exists("POS Profile", profile_name):
		return profile_name

	company = company or test_company()
	profile = frappe.get_doc(
		{
			"doctype": "POS Profile",
			"name": profile_name,
			"company": company,
			"warehouse": ensure_warehouse(company),
			"currency": frappe.get_cached_value("Company", company, "default_currency"),
			"disabled": disabled,
		}
	)
	profile.flags.ignore_validate = True
	profile.flags.ignore_links = True
	profile.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
	return profile.name


def isolated_pos_profile(*, company: str | None = None, disabled: int = 0, user: str = "") -> str:
	"""A uniquely named outlet, for tests that must own their own profile.

	The shared `test_outlet_a` accumulates terminals across a class; a test that
	asserts on "the terminal serving this outlet" needs an outlet nothing else has
	touched.
	"""
	company = company or test_company()
	name = ensure_pos_profile(f"_PDP Outlet {uuid.uuid4().hex[:8]}", company=company, disabled=disabled)
	if user:
		grant_profile_user(name, user)
	return name


def grant_profile_user(pos_profile: str, user: str) -> None:
	"""Make ``user`` applicable for ``pos_profile``, the way the POS form does.

	ERPNext treats a profile with no applicable-user rows as available to every
	user (`get_pos_profile`), and `core.security` mirrors that rule — so a test
	proving an Operator is scoped OUT of an outlet has to add a row for somebody,
	not rely on the empty table.
	"""
	profile = frappe.get_doc("POS Profile", pos_profile)
	if user in {row.user for row in profile.applicable_for_users}:
		return
	profile.append("applicable_for_users", {"user": user, "default": 0})
	# The flags set at insert time do not survive the re-fetch, and the fixture
	# profile is deliberately missing the accounting fields ERPNext marks mandatory
	# (payments, write-off account and cost centre) because they all live in the
	# chart of accounts `ensure_company` skips. Re-declare them for the save.
	profile.flags.ignore_validate = True
	profile.flags.ignore_links = True
	profile.flags.ignore_mandatory = True
	profile.save(ignore_permissions=True)
