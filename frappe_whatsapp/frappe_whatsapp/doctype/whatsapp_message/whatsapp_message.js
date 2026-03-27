// Copyright (c) 2022, Shridhar Patil and contributors
// For license information, please see license.txt

frappe.ui.form.on('WhatsApp Message', {
	onload: function(frm) {
		frappe.db.get_value('WhatsApp Account', frm.doc.whatsapp_account, 'allow_auto_read_receipt').then(value => {
			if (value && frm.doc.type === "Incoming" && frm.doc.status !== "marked as read" && frm.doc.message_id) {
				send_read_receipt(frm);
			}
		});
	},
	refresh: function(frm) {
		if (frm.doc.type == 'Incoming'){
			frm.add_custom_button(__("Reply"), function(){
				frappe.new_doc("WhatsApp Message", {"to": frm.doc.from});
			});
		}
		add_mark_as_read(frm);
		add_product_picker_buttons(frm);
		load_wa_catalog_products(frm);
	},
	content_type: function(frm) {
		add_product_picker_buttons(frm);
	},
	catalog: function(frm) {
		load_wa_catalog_products(frm);
	}
});

frappe.ui.form.on('WhatsApp Message Product', {
	retailer_id: function(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (!row.retailer_id || !frm._catalog_products) return;
		let product = frm._catalog_products.find(p => p.retailer_id === row.retailer_id);
		if (product) {
			frappe.model.set_value(cdt, cdn, 'product_name', product.product_name);
			frappe.model.set_value(cdt, cdn, 'price', product.price);
			frappe.model.set_value(cdt, cdn, 'currency', product.currency);
		}
	}
});

function load_wa_catalog_products(frm) {
	if (!frm.doc.catalog) {
		frm._catalog_products = [];
		return;
	}

	frappe.call({
		method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_catalog.whatsapp_catalog.get_catalog_products',
		args: { catalog: frm.doc.catalog },
		callback: function(r) {
			frm._catalog_products = r.message || [];
			let options = frm._catalog_products.map(p => p.retailer_id);
			if (frm.fields_dict.selected_products) {
				frm.fields_dict.selected_products.grid.update_docfield_property(
					'retailer_id', 'options', options
				);
			}
			frm.set_df_property('product_retailer_id', 'options', options);
			frm.set_df_property('thumbnail_product_retailer_id', 'options', options);
		}
	});
}

function add_product_picker_buttons(frm) {
	try { frm.remove_custom_button(__('Pick Product')); } catch(e) {}
	try { frm.remove_custom_button(__('Add Products from Catalog')); } catch(e) {}

	let ct = frm.doc.content_type;

	if (ct === 'product') {
		frm.add_custom_button(__('Pick Product'), function() {
			if (!frappe.whatsapp) { frappe.msgprint(__('Product picker not loaded. Please refresh.')); return; }
			frappe.whatsapp.pick_product({
				catalog: frm.doc.catalog,
				callback: function(product) {
					frm.set_value('product_retailer_id', product.retailer_id);
				}
			});
		});
	}

	if (ct === 'product_list') {
		frm.add_custom_button(__('Add Products from Catalog'), function() {
			if (!frm.doc.catalog) {
				frappe.msgprint(__('Please select a Catalog first'));
				return;
			}
			if (!frappe.whatsapp) { frappe.msgprint(__('Product picker not loaded. Please refresh.')); return; }
			frappe.whatsapp.pick_products({
				catalog: frm.doc.catalog,
				callback: function(products) {
					frappe.prompt({
						fieldname: 'section_title',
						fieldtype: 'Data',
						label: __('Section Title'),
						default: 'Products',
						reqd: 1
					}, function(values) {
						for (let p of products) {
							let row = frm.add_child('selected_products');
							row.section_title = values.section_title;
							row.retailer_id = p.retailer_id;
							row.product_name = p.product_name;
							row.price = p.price;
							row.currency = p.currency;
						}
						frm.refresh_field('selected_products');
					}, __('Section Title for Selected Products'), __('Add'));
				}
			});
		});
	}

	if (ct === 'catalog_message') {
		frm.add_custom_button(__('Pick Product'), function() {
			if (!frappe.whatsapp) { frappe.msgprint(__('Product picker not loaded. Please refresh.')); return; }
			frappe.whatsapp.pick_product({
				catalog: frm.doc.catalog,
				callback: function(product) {
					frm.set_value('thumbnail_product_retailer_id', product.retailer_id);
				}
			});
		});
	}
}

function add_mark_as_read(frm){
	if(frm.doc.type === "Outgoing" || frm.doc.status == "marked as read" || !frm.doc.message_id)
		return;
	frappe.db.get_value('WhatsApp Account', frm.doc.whatsapp_account, 'allow_auto_read_receipt').then(value => {
		if (value) return;
		frm.add_custom_button(__('Mark as read'), function(){
			send_read_receipt(frm);
		});
	});
}

function send_read_receipt(frm) {
	frappe.call({
		doc: frm.doc,
		method: "send_read_receipt",
		callback: function(r) {
			if (r && r.message) frappe.msgprint(__('Marked as read'));
		}
	});
}
