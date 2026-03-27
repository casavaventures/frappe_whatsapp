frappe.ui.form.on('Bulk WhatsApp Message', {
    refresh: function(frm) {
        if(frm.doc.docstatus === 1 && frm.doc.status != 'Draft') {
            frm.add_custom_button(__('Check Progress'), function() {
                frappe.call({
                    method: 'frappe_whatsapp.utils.bulk_messaging.get_progress',
                    args: { name: frm.doc.name },
                    callback: function(r) {
                        if(r.message) {
                            let progress = r.message;
                            frappe.msgprint({
                                title: __('Message Progress'),
                                indicator: 'blue',
                                message: `
                                    <div class="progress" style="height: 20px;">
                                        <div class="progress-bar bg-success" style="width: ${progress.percent}%;">
                                            ${Math.round(progress.percent)}%
                                        </div>
                                    </div>
                                    <div class="mt-2">
                                        <span class="badge badge-success">Sent: ${progress.sent}</span>
                                        <span class="badge badge-danger ml-2">Failed: ${progress.failed}</span>
                                        <span class="badge badge-warning ml-2">Queued: ${progress.queued}</span>
                                        <span class="badge badge-info ml-2">Total: ${progress.total}</span>
                                    </div>`
                            });
                        }
                    }
                });
            });

            frm.add_custom_button(__('Retry Failed Messages'), function() {
                frappe.call({
                    method: 'frappe_whatsapp.utils.bulk_messaging.retry_failed',
                    args: { name: frm.doc.name },
                    callback: function(r) { if(r.message) frm.reload_doc(); }
                });
            }).addClass('btn-danger');
        }

        add_bulk_product_buttons(frm);
        load_catalog_products(frm);
    },
    message_mode: function(frm) {
        add_bulk_product_buttons(frm);
    },
    catalog: function(frm) {
        load_catalog_products(frm);
    },
    validate: function(frm) {
        if(frm.doc.recipient_type == 'Individual' && (!frm.doc.recipients || frm.doc.recipients.length === 0)) {
            frappe.throw(__('Please add at least one recipient'));
            return false;
        }
        if(frm.doc.recipient_type == 'Recipient List' && !frm.doc.recipient_list) {
            frappe.throw(__('Please select a recipient list'));
            return false;
        }

        let mode = frm.doc.message_mode;
        if(['Template', 'Catalog Template'].includes(mode) && !frm.doc.template) {
            frappe.throw(__('Please select a template'));
            return false;
        }
        if(['Product', 'Product List', 'Catalog', 'Catalog Template'].includes(mode) && !frm.doc.catalog) {
            frappe.throw(__('Please select a catalog'));
            return false;
        }
        if(mode === 'Product' && !frm.doc.product_retailer_id) {
            frappe.throw(__('Please enter a Product Retailer ID'));
            return false;
        }
        if(['Product List', 'Catalog Template'].includes(mode) && (!frm.doc.selected_products || !frm.doc.selected_products.length)) {
            frappe.throw(__('Please add products to the Selected Products table'));
            return false;
        }
        return true;
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

function load_catalog_products(frm) {
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

            // Set dropdown options on child table retailer_id
            if (frm.fields_dict.selected_products) {
                frm.fields_dict.selected_products.grid.update_docfield_property(
                    'retailer_id', 'options', options
                );
            }

            // Set dropdown options on standalone retailer fields
            frm.set_df_property('product_retailer_id', 'options', options);
            frm.set_df_property('thumbnail_product_retailer_id', 'options', options);
        }
    });
}

function add_bulk_product_buttons(frm) {
    if (frm.doc.docstatus !== 0) return;

    try { frm.remove_custom_button(__('Pick Product')); } catch(e) {}
    try { frm.remove_custom_button(__('Pick Thumbnail')); } catch(e) {}
    try { frm.remove_custom_button(__('Add Products from Catalog')); } catch(e) {}

    let mode = frm.doc.message_mode;

    if (mode === 'Product') {
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

    if (['Product List', 'Catalog Template'].includes(mode)) {
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

    if (['Catalog', 'Catalog Template'].includes(mode)) {
        frm.add_custom_button(__('Pick Thumbnail'), function() {
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
