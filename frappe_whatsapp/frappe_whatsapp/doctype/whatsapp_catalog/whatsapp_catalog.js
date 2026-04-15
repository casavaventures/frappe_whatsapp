// Copyright (c) 2026, Frappe Technologies and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Catalog', {
	refresh: function(frm) {
		// Hide standard Save button — catalog is read-only mirror of Meta
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
	}
});
