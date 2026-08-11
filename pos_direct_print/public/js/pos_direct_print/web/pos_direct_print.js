/**
 * Classic script loader (B4-03) — no static ESM syntax.
 *
 * Loads the pinned iMin SDK, fetches live settings, then dynamically imports
 * the ESM bootstrap and registers the driver against the live ERPNext POS
 * prototype. Every failure is non-fatal: POS keeps baseline browser print.
 */
(function () {
	if (window.__pos_direct_print_booted) return;
	window.__pos_direct_print_booted = true;

	var SDK_URL = "/assets/pos_direct_print/js/lib/imin/1.4.0/imin-printer.js";
	var BOOTSTRAP_URL = "/assets/pos_direct_print/js/pos_direct_print/core/bootstrap.mjs";
	var SETTINGS_METHOD = "pos_direct_print.core.print_api.get_settings";

	function load_sdk_with_vue_guard() {
		return new Promise(function (resolve, reject) {
			var had_vue = "Vue" in window;
			var saved_vue = window.Vue;
			if (had_vue) {
				try {
					window.Vue = undefined;
				} catch (e) {
					console.warn(
						"pos_direct_print: could not hide window.Vue; SDK Vue plugin may install"
					);
				}
			}
			function restore() {
				if (had_vue) {
					try {
						window.Vue = saved_vue;
					} catch (e) {
						/* ignore */
					}
				}
			}
			var script = document.createElement("script");
			script.src = SDK_URL;
			script.async = false;
			script.onload = function () {
				restore();
				resolve();
			};
			script.onerror = function () {
				restore();
				reject(new Error("PDP_SDK_ASSET_LOAD_FAILED"));
			};
			document.head.appendChild(script);
		});
	}

	function get_pos_prototype() {
		var constructor =
			window.erpnext &&
			window.erpnext.PointOfSale &&
			window.erpnext.PointOfSale.PastOrderSummary;
		var prototype = constructor && constructor.prototype;
		return prototype && typeof prototype.print_receipt === "function"
			? prototype
			: null;
	}

	function get_settings() {
		return new Promise(function (resolve, reject) {
			if (!window.frappe || typeof window.frappe.call !== "function") {
				reject(new Error("PDP_SETTINGS_UNAVAILABLE"));
				return;
			}
			window.frappe.call({
				method: SETTINGS_METHOD,
				args: {},
				callback: function (response) {
					if (response && response.message) resolve(response.message);
					else reject(new Error("PDP_SETTINGS_UNAVAILABLE"));
				},
				error: function () {
					reject(new Error("PDP_SETTINGS_UNAVAILABLE"));
				},
			});
		});
	}

	function load_bootstrap() {
		if (typeof window.__pos_direct_print_import === "function") {
			return Promise.resolve(window.__pos_direct_print_import(BOOTSTRAP_URL));
		}
		return import(BOOTSTRAP_URL);
	}

	function arm_when_pos_is_ready(mod, settings) {
		var armed = false;
		var left = 30;
		var timer = setInterval(function () {
			var prototype = get_pos_prototype();
			if (!prototype || armed) {
				if (--left <= 0) clearInterval(timer);
				return;
			}
			armed = true;
			clearInterval(timer);
			mod.bootSubsystem({
				pos_context: prototype,
				settings: settings,
				active_driver_key: "imin_v1",
			});
		}, 500);
	}

	load_sdk_with_vue_guard()
		.then(function () {
			return Promise.all([load_bootstrap(), get_settings()]);
		})
		.then(function (values) {
			var settings = values[1];
			if (!settings.enabled) return;
			arm_when_pos_is_ready(values[0], settings);
		})
		.catch(function (error) {
			console.warn("pos_direct_print: bootstrap skipped", error && error.message);
		});
})();
