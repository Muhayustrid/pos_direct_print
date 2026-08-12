frappe.listview_settings["POS Print Terminal"] = {
	onload(listview) {
		if (!frappe.user.has_role("System Manager")) return;

		listview.page.add_actions_menu_item(__("Disable Terminals"), () => {
			const names = listview.get_checked_items(true);
			if (!names.length) {
				frappe.msgprint(__("Select at least one terminal."));
				return;
			}

			frappe.confirm(__("Disable {0} selected terminal(s)?", [names.length]), () => {
				frappe.call({
					method: "pos_direct_print.core.print_api.disable_terminals",
					args: { terminal_ids: names },
					freeze: true,
					callback() {
						listview.refresh();
					},
				});
			});
		});
	},
};
