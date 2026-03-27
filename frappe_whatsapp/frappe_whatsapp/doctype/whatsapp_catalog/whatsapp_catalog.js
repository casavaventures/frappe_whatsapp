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
