// Copyright (c) 2022, Shridhar Patil and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Templates', {
	refresh: function(frm) {
		frm.set_query('language', function() {
			return { filters: { enabled: 1 } };
		});

		if (!frm.is_new() && frm.doc.actual_name) {
			frm.add_custom_button(__('Delete from Meta'), function() {
				frappe.confirm(
					__('This will permanently delete the template <b>{0}</b> from Meta (WhatsApp Business). This cannot be undone. Continue?', [frm.doc.actual_name]),
					function() {
						frappe.call({
							method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.delete_from_meta',
							args: { template_name: frm.doc.name },
							freeze: true,
							freeze_message: __('Deleting from Meta...'),
							callback: function(r) {
								if (r.message && r.message.status === 'success') {
									frappe.show_alert({ message: r.message.message, indicator: 'green' });
									frappe.set_route('List', 'WhatsApp Templates');
								}
							}
						});
					}
				);
			}, __('Actions'));
		}
	},

	validate: function(frm) {
		// MPM and Catalog buttons require a header
		if (frm.doc.buttons && frm.doc.buttons.length) {
			for (let btn of frm.doc.buttons) {
				if ((btn.button_type === 'MPM' || btn.button_type === 'Catalog') && !frm.doc.header_type) {
					frappe.throw(__('A header is required for templates with a {0} button. Please set a Header Type.', [btn.button_type]));
				}
			}
		}
	}
});

frappe.ui.form.on('WhatsApp Button', {
	button_type: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		// Auto-set fixed button labels for MPM and Catalog (Meta enforces these)
		if (row.button_type === 'MPM') {
			frappe.model.set_value(cdt, cdn, 'button_label', 'View items');
		} else if (row.button_type === 'Catalog') {
			frappe.model.set_value(cdt, cdn, 'button_label', 'View catalog');
		} else if (row.button_type === 'Copy Code') {
			frappe.model.set_value(cdt, cdn, 'button_label', 'Copy offer code');
		}
	}
});
