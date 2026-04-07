frappe.listview_settings['WhatsApp Catalog'] = {

	onload: function(listview) {
		listview.page.add_inner_button(__("Setup Catalog"), function() {
			frappe.prompt(
				[
					{
						fieldname: 'catalog_id',
						fieldtype: 'Data',
						label: __('Catalog ID'),
						reqd: 1,
						description: __('Find this in Meta Commerce Manager → your catalog → Settings → Catalog ID')
					}
				],
				function(values) {
					frappe.call({
						method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_catalog.whatsapp_catalog.setup_catalog',
						args: { catalog_id: values.catalog_id },
						freeze: true,
						freeze_message: __("Linking catalog and syncing products to Meta..."),
						callback: function(r) {
							if (r.message) {
								const m = r.message;
								frappe.msgprint({
									title: __("Catalog Setup Complete"),
									message: __(
										"Catalog linked (ID: {0}).<br>Products synced: {1} of {2}. Errors: {3}",
										[m.catalog_id, m.synced || 0, m.total || 0, m.sync_errors || 0]
									),
									indicator: (m.sync_errors || 0) > 0 ? "orange" : "green"
								});
								listview.refresh();
							}
						}
					});
				},
				__("Link Meta Catalog"),
				__("Link & Sync")
			);
		});

		listview.page.add_inner_button(__("Sync from Meta"), function() {
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
						listview.refresh();
					}
				}
			});
		});

		// Only show "Sync Products to Meta" if a catalog record already exists
		frappe.db.count('WhatsApp Catalog').then(count => {
			if (count > 0) {
				listview.page.add_inner_button(__("Sync Products to Meta"), function() {
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
										} else {
											frappe.msgprint({ title: __("Error"), message: m.message, indicator: "red" });
										}
										listview.refresh();
									}
								}
							});
						}
					);
				});
			}
		});
	}
};
