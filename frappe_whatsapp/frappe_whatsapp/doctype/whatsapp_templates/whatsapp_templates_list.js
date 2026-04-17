frappe.listview_settings['WhatsApp Templates'] = {

	get_indicator: function(doc) {
		if (doc.status === 'APPROVED') {
			return [__('Approved'), 'green', 'status,=,APPROVED'];
		} else if (doc.status === 'PENDING') {
			return [__('Pending'), 'yellow', 'status,=,PENDING'];
		} else if (doc.status === 'REJECTED') {
			return [__('Rejected'), 'red', 'status,=,REJECTED'];
		} else if (doc.status === 'Deleted on Meta') {
			return [__('Deleted on Meta'), 'orange', 'status,=,Deleted on Meta'];
		}
	},

	onload: function(listview) {
		listview.page.add_inner_button(__("Sync from Meta"), function() {
			frappe.call({
				method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.fetch',
				freeze: true,
				freeze_message: __("Syncing templates from Meta..."),
				callback: function(r) {
					if (r.message) {
						frappe.msgprint({
							title: __("Sync Complete"),
							message: r.message,
							indicator: "green"
						});
						listview.refresh();
					}
				}
			});
		});
	}
};