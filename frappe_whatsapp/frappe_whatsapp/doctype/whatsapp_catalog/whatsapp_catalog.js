// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Catalog', {
	refresh: function(frm) {
		// Hide standard Save button — use Push to Meta for data consistency
		frm.disable_save();

		frm.add_custom_button(__("Sync from Meta"), function() {
			frappe.call({
				method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_catalog.whatsapp_catalog.fetch',
				freeze: true,
				freeze_message: __("Syncing catalogs from Meta..."),
				callback: function(r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Sync Complete"),
							message: r.message,
							indicator: "green"
						});
						frm.reload_doc();
					}
				}
			});
		});

		if (frm.doc.catalog_id) {
			frm.add_custom_button(__("Sync Products to Meta"), function() {
				frappe.confirm(
					__("This will push all published products to the Meta catalog with updated images, prices, and URLs. Continue?"),
					function() {
						frappe.call({
							method: 'shopbridge.api.v1.whatsapp_shop.bulk_sync_catalog',
							freeze: true,
							freeze_message: __("Syncing products to Meta catalog..."),
							callback: function(r) {
								if (r.message) {
									const m = r.message;
									if (m.status === "ok") {
										frappe.msgprint({
											title: __("Sync Complete"),
											message: __("Synced {0} of {1} products. Errors: {2}", [m.synced, m.total, m.errors]),
											indicator: m.errors ? "orange" : "green"
										});
										frm.reload_doc();
									} else {
										frappe.msgprint({ title: __("Error"), message: m.message, indicator: "red" });
									}
								}
							}
						});
					}
				);
			}).addClass('btn-primary');
		}

		if (frm.doc.catalog_id && frm.doc.items && frm.doc.items.length) {
			frm.add_custom_button(__("Push to Meta"), function() {
				frappe.confirm(
					__("This will update all modified products on Meta. Continue?"),
					function() {
						// Save locally first, then push to Meta
						frm.call('save').then(() => {
							frappe.call({
								method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_catalog.whatsapp_catalog.push_to_meta',
								args: { catalog_name: frm.doc.name },
								freeze: true,
								freeze_message: __("Pushing updates to Meta..."),
								callback: function(r) {
									if (r.message) {
										frappe.msgprint({
											title: __("Push Complete"),
											message: r.message,
											indicator: "green"
										});
										frm.reload_doc();
									}
								}
							});
						});
					}
				);
			}).addClass('btn-primary');
		}
	}
});
