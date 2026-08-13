"""Rename the module `Pos Direct Print` to `Direct Print`.

The app now groups every print target under one module, so POS is a section
inside it rather than the module's identity. Non-POS direct print arrives later
under the same roof.

`Module Def.before_rename` refuses to rename a non-custom module, so the row is
replaced rather than renamed: insert the new name, repoint everything that
points at the old one, then drop the old row. `frappe.db.delete` is used instead
of `delete_doc` so the controller does not try to prune modules.txt or the
module folder — both already carry the new name in the app source.

Runs pre_model_sync: the DocType JSON files already declare
`module: Direct Print`, and importing them would fail on a missing Module Def.
"""

import frappe

OLD = "Pos Direct Print"
NEW = "Direct Print"

# Every DocType whose rows carry a module name. Workspace and Workspace Sidebar
# are included because a later sync writes the app's own sidebar under NEW.
MODULE_HOLDERS = (
	"DocType",
	"Report",
	"Page",
	"Dashboard",
	"Workspace",
	"Workspace Sidebar",
	"Print Format",
	"Web Form",
	"Notification",
	"Server Script",
	"Client Script",
)


def execute():
	if not frappe.db.exists("Module Def", OLD):
		return

	if not frappe.db.exists("Module Def", NEW):
		frappe.get_doc(
			{
				"doctype": "Module Def",
				"module_name": NEW,
				"app_name": frappe.db.get_value("Module Def", OLD, "app_name") or "pos_direct_print",
			}
		).insert(ignore_permissions=True)

	for doctype in MODULE_HOLDERS:
		if not frappe.db.table_exists(doctype):
			continue
		if not frappe.get_meta(doctype).has_field("module"):
			continue
		frappe.db.set_value(doctype, {"module": OLD}, "module", NEW, update_modified=False)

	frappe.db.delete("Module Def", {"name": OLD})
	frappe.clear_cache()
