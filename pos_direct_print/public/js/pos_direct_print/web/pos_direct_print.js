/**
 * Classic script loader (B4-03) — no static ESM syntax.
 *
 * Loads the pinned iMin SDK, then dynamically imports the ESM bootstrap and
 * registers the `imin_v1` driver against the live ERPNext POS prototype.
 * Every failure is non-fatal: POS keeps its baseline browser print (A-DOD-04).
 *
 * The pinned SDK's UMD tail executes `if (inBrowser && window.Vue)
 * window.Vue.use(IminPrinter);`. Installing an iMin Vue plugin into the Desk
 * Vue app is out of scope, so `window.Vue` is hidden for the evaluation
 * window and restored in `onload` (which fires after script execution).
 */
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
				try {
					window.Vue = undefined;
				} catch (e) {
					// ponytail: non-writable window.Vue getter — logged; device gate
					// confirms real state (C-9)
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

	function wait_for_pos_prototype(retries) {
		// ponytail: bounded polling (500 ms x 30); swap for a frappe router/page
		// event if one proves reliable
		return new Promise(function (resolve, reject) {
			var left = retries;
			var timer = setInterval(function () {
				var proto =
					window.erpnext &&
					window.erpnext.PointOfSale &&
					window.erpnext.PointOfSale.PastOrderSummary &&
					window.erpnext.PointOfSale.PastOrderSummary.prototype;
				if (proto && typeof proto.print_receipt === "function") {
					clearInterval(timer);
					resolve(proto);
				} else if (--left <= 0) {
					clearInterval(timer);
					reject(new Error("PDP_POS_CONTEXT_UNAVAILABLE"));
				}
			}, 500);
		});
	}

	load_sdk_with_vue_guard()
		.then(function () {
			return import(BOOTSTRAP_URL);
		})
		.then(function (mod) {
			return wait_for_pos_prototype(30).then(function (proto) {
				return mod.bootSubsystem({
					pos_context: proto,
					active_driver_key: "imin_v1",
				});
			});
		})
		.catch(function (error) {
			// Non-fatal for ERPNext: POS keeps baseline browser print (A-DOD-04).
			console.warn("pos_direct_print: bootstrap skipped", error && error.message);
		});
})();
