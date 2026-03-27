frappe.whatsapp = frappe.whatsapp || {};

/**
 * Pick a single product from a WhatsApp Catalog.
 * @param {Object} opts - { catalog: string, callback: function(product) }
 */
frappe.whatsapp.pick_product = function(opts) {
	let catalog = opts.catalog;
	let callback = opts.callback;
	let products = [];

	let d = new frappe.ui.Dialog({
		title: __('Select Product'),
		size: 'large',
		fields: [
			{
				fieldname: 'catalog',
				fieldtype: 'Link',
				label: __('Catalog'),
				options: 'WhatsApp Catalog',
				default: catalog,
				reqd: 1,
				onchange: function() {
					_load_products(d, products, false);
				}
			},
			{
				fieldname: 'search',
				fieldtype: 'Data',
				label: __('Search'),
				onchange: function() {
					_render_products(d, products, false);
				}
			},
			{
				fieldname: 'products_html',
				fieldtype: 'HTML',
			}
		],
		primary_action_label: __('Select'),
		primary_action: function() {
			let selected_id = d.$wrapper.find('input[name="product_select"]:checked').val();
			if (!selected_id) {
				frappe.msgprint(__('Please select a product'));
				return;
			}
			let product = products.find(p => p.retailer_id === selected_id);
			d.hide();
			callback(product);
		}
	});

	d.show();
	if (catalog) {
		_load_products(d, products, false);
	}
};

/**
 * Pick multiple products from a WhatsApp Catalog.
 * @param {Object} opts - { catalog: string, callback: function(products[]) }
 */
frappe.whatsapp.pick_products = function(opts) {
	let catalog = opts.catalog;
	let callback = opts.callback;
	let products = [];

	let d = new frappe.ui.Dialog({
		title: __('Select Products'),
		size: 'large',
		fields: [
			{
				fieldname: 'catalog',
				fieldtype: 'Link',
				label: __('Catalog'),
				options: 'WhatsApp Catalog',
				default: catalog,
				reqd: 1,
				onchange: function() {
					_load_products(d, products, true);
				}
			},
			{
				fieldname: 'search',
				fieldtype: 'Data',
				label: __('Search'),
				onchange: function() {
					_render_products(d, products, true);
				}
			},
			{
				fieldname: 'products_html',
				fieldtype: 'HTML',
			}
		],
		primary_action_label: __('Add Products'),
		primary_action: function() {
			let checked = [];
			d.$wrapper.find('input[name="product_select"]:checked').each(function() {
				let id = $(this).val();
				let p = products.find(item => item.retailer_id === id);
				if (p) checked.push(p);
			});
			if (!checked.length) {
				frappe.msgprint(__('Please select at least one product'));
				return;
			}
			d.hide();
			callback(checked);
		}
	});

	d.show();
	if (catalog) {
		_load_products(d, products, true);
	}
};

/**
 * Build product sections for Multi-Product / MPM Template messages.
 * @param {Object} opts - { catalog: string, current_sections: array|string, callback: function(sections) }
 */
frappe.whatsapp.build_sections = function(opts) {
	let catalog = opts.catalog;
	let callback = opts.callback;
	let sections = [];

	if (opts.current_sections) {
		try {
			sections = typeof opts.current_sections === 'string'
				? JSON.parse(opts.current_sections) : opts.current_sections;
		} catch(e) {
			sections = [];
		}
	}

	if (!sections.length) {
		sections.push({ title: 'Products', product_items: [] });
	}

	let d = new frappe.ui.Dialog({
		title: __('Build Product Sections'),
		size: 'extra-large',
		fields: [
			{
				fieldname: 'catalog',
				fieldtype: 'Link',
				label: __('Catalog'),
				options: 'WhatsApp Catalog',
				default: catalog,
				read_only: catalog ? 1 : 0,
				reqd: 1,
			},
			{
				fieldname: 'sections_html',
				fieldtype: 'HTML',
			}
		],
		primary_action_label: __('Save Sections'),
		primary_action: function() {
			// Validate
			let valid = sections.every(s => s.title && s.product_items.length > 0);
			if (!valid) {
				frappe.msgprint(__('Each section must have a title and at least one product'));
				return;
			}
			let total = sections.reduce((sum, s) => sum + s.product_items.length, 0);
			if (total > 30) {
				frappe.msgprint(__('Maximum 30 products allowed across all sections'));
				return;
			}
			if (sections.length > 10) {
				frappe.msgprint(__('Maximum 10 sections allowed'));
				return;
			}
			d.hide();
			callback(sections);
		}
	});

	function render() {
		let html = sections.map((section, si) => {
			let items_html = section.product_items.map((item, ii) => `
				<div style="display: flex; align-items: center; padding: 4px 8px; background: var(--bg-light-gray); border-radius: 4px; margin: 2px 0;">
					<span style="flex: 1;">${frappe.utils.escape_html(item.product_retailer_id)}</span>
					<button class="btn btn-xs btn-default remove-product" data-section="${si}" data-item="${ii}">
						${frappe.utils.icon('close', 'xs')}
					</button>
				</div>
			`).join('');

			return `
				<div class="section-block" style="border: 1px solid var(--border-color); border-radius: 8px; padding: 12px; margin-bottom: 12px;">
					<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
						<input type="text" class="form-control section-title" data-section="${si}"
							value="${frappe.utils.escape_html(section.title)}" placeholder="${__('Section Title')}">
						${sections.length > 1 ? `<button class="btn btn-xs btn-danger remove-section" data-section="${si}">${__('Remove')}</button>` : ''}
					</div>
					<div class="section-products">${items_html || '<div style="color: var(--text-muted); padding: 4px 8px;">No products</div>'}</div>
					<button class="btn btn-xs btn-default add-products-to-section" data-section="${si}" style="margin-top: 8px;">
						+ ${__('Add Products')}
					</button>
				</div>
			`;
		}).join('');

		html += `<button class="btn btn-sm btn-default add-section" style="margin-top: 4px;">+ ${__('Add Section')}</button>`;

		let total = sections.reduce((sum, s) => sum + s.product_items.length, 0);
		html += `<div style="margin-top: 8px; color: var(--text-muted); font-size: 12px;">${total} product(s) in ${sections.length} section(s) (max 30 products, 10 sections)</div>`;

		d.fields_dict.sections_html.$wrapper.html(html);

		// Event handlers
		d.fields_dict.sections_html.$wrapper.find('.section-title').off('change').on('change', function() {
			sections[$(this).data('section')].title = $(this).val();
		});

		d.fields_dict.sections_html.$wrapper.find('.remove-section').off('click').on('click', function() {
			sections.splice($(this).data('section'), 1);
			render();
		});

		d.fields_dict.sections_html.$wrapper.find('.remove-product').off('click').on('click', function() {
			sections[$(this).data('section')].product_items.splice($(this).data('item'), 1);
			render();
		});

		d.fields_dict.sections_html.$wrapper.find('.add-products-to-section').off('click').on('click', function() {
			let si = $(this).data('section');
			frappe.whatsapp.pick_products({
				catalog: d.get_value('catalog'),
				callback: function(selected) {
					for (let p of selected) {
						// Avoid duplicates within section
						if (!sections[si].product_items.find(x => x.product_retailer_id === p.retailer_id)) {
							sections[si].product_items.push({ product_retailer_id: p.retailer_id });
						}
					}
					render();
				}
			});
		});

		d.fields_dict.sections_html.$wrapper.find('.add-section').off('click').on('click', function() {
			if (sections.length >= 10) {
				frappe.msgprint(__('Maximum 10 sections allowed'));
				return;
			}
			sections.push({ title: '', product_items: [] });
			render();
		});
	}

	d.show();
	render();
};

// Internal helpers

function _load_products(dialog, products_arr, multi) {
	let catalog = dialog.get_value('catalog');
	if (!catalog) return;

	dialog.fields_dict.products_html.$wrapper.html(
		`<div style="padding: 20px; text-align: center;">${__('Loading...')}</div>`
	);

	frappe.call({
		method: 'frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_catalog.whatsapp_catalog.get_catalog_products',
		args: { catalog },
		callback: function(r) {
			products_arr.length = 0;
			(r.message || []).forEach(p => products_arr.push(p));
			_render_products(dialog, products_arr, multi);
		}
	});
}

function _render_products(dialog, products_arr, multi) {
	let search = (dialog.get_value('search') || '').toLowerCase();
	let filtered = products_arr.filter(p => {
		if (!search) return true;
		return (p.product_name || '').toLowerCase().includes(search)
			|| (p.retailer_id || '').toLowerCase().includes(search);
	});

	let input_type = multi ? 'checkbox' : 'radio';
	let html = filtered.map(p => `
		<div style="padding: 8px 12px; border-bottom: 1px solid var(--border-color); display: flex; align-items: center; gap: 10px;">
			<input type="${input_type}" name="product_select" value="${frappe.utils.escape_html(p.retailer_id)}">
			<div style="flex: 1;">
				<div style="font-weight: 500;">${frappe.utils.escape_html(p.product_name || p.retailer_id)}</div>
				<div style="font-size: 12px; color: var(--text-muted);">
					${frappe.utils.escape_html(p.retailer_id)}
					${p.price ? ' &middot; ' + frappe.utils.escape_html(p.currency || '') + ' ' + frappe.utils.escape_html(p.price) : ''}
					${p.availability ? ' &middot; ' + frappe.utils.escape_html(p.availability) : ''}
				</div>
			</div>
		</div>
	`).join('');

	if (!filtered.length) {
		html = `<div style="padding: 20px; text-align: center; color: var(--text-muted);">${__('No products found')}</div>`;
	}

	dialog.fields_dict.products_html.$wrapper.html(
		`<div style="max-height: 400px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius);">${html}</div>
		 <div style="margin-top: 4px; font-size: 12px; color: var(--text-muted);">${filtered.length} of ${products_arr.length} product(s)</div>`
	);
}
