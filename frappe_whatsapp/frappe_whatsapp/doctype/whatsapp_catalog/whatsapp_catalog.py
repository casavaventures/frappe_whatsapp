"""WhatsApp Catalog - sync product catalogs from Meta."""

# Copyright (c) 2026, Frappe Technologies and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.integrations.utils import make_request

from frappe_whatsapp.utils import get_whatsapp_account


class WhatsAppCatalog(Document):
    pass


@frappe.whitelist()
def setup_catalog(catalog_id, catalog_name=None):
    """
    Link an existing Meta catalog to the WhatsApp Account, fetch its details,
    and push all published Frappe products to it.

    catalog_id  — the numeric ID from Meta Commerce Manager
    catalog_name — optional display name (ignored if catalog already has a name on Meta)
    """
    account = get_whatsapp_account(account_type='outgoing')
    if not account:
        frappe.throw("Please configure a default outgoing WhatsApp Account first.")

    # Save catalog_id on the WhatsApp Account so fetch() can find it
    frappe.db.set_value("WhatsApp Account", account.name, "catalog_id", str(catalog_id).strip())
    frappe.db.commit()

    # Pull catalog metadata and products from Meta into Frappe
    fetch_result = fetch()

    return {
        "catalog_id": catalog_id,
        "fetch": fetch_result,
    }


@frappe.whitelist()
def fetch():
    """Fetch catalogs and their products from Meta."""
    account = get_whatsapp_account(account_type='outgoing')
    if not account:
        frappe.throw("Please configure a default outgoing WhatsApp Account first.")

    if account.status != 'Active':
        frappe.throw(f"Default outgoing WhatsApp Account {account.name} is not Active.")

    token = account.get_password("token")
    url = account.url
    version = account.version
    business_id = account.business_id
    phone_id = account.phone_id

    headers = {
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
    }

    # Step 1: Determine catalog ID
    catalog_id_from_account = account.get("catalog_id")

    if not catalog_id_from_account:
        # Try WABA-level product_catalogs edge as fallback
        try:
            catalog_response = make_request(
                "GET",
                f"{url}/{version}/{business_id}/product_catalogs",
                headers=headers,
            )
            data = catalog_response.get("data", [])
            if data:
                catalog_id_from_account = data[0]["id"]
        except Exception:
            pass

    if not catalog_id_from_account:
        frappe.throw(
            "No Catalog ID configured. Please set the Catalog ID in your WhatsApp Account "
            "settings. You can find it in Meta Commerce Manager > Your Catalog > Settings."
        )

    catalog_id = catalog_id_from_account

    # Step 2: Fetch products for this catalog
    try:
        products = _fetch_all_products(url, version, catalog_id, headers)
    except Exception as e:
        error_msg = str(e)
        if "missing permissions" in error_msg.lower() or "does not exist" in error_msg.lower():
            frappe.throw(
                "Your WhatsApp API token does not have permission to access catalog data. "
                "Please add the <b>catalog_management</b> permission to your System User token "
                "in Meta Business Manager:<br><br>"
                "1. Go to <b>Meta Business Suite > Settings > Business Settings</b><br>"
                "2. Navigate to <b>Users > System Users</b><br>"
                "3. Select your System User and click <b>Generate New Token</b><br>"
                "4. Select your App and add <b>catalog_management</b> along with existing permissions<br>"
                "5. Copy the new token and update it in your WhatsApp Account settings",
                title="Missing catalog_management Permission",
            )
        raise

    # Step 3: Fetch catalog name
    catalog_name = catalog_id
    try:
        cat_info = make_request(
            "GET",
            f"{url}/{version}/{catalog_id}?fields=name",
            headers=headers,
        )
        catalog_name = cat_info.get("name", catalog_id)
    except Exception:
        pass

    # Step 4: Fetch commerce settings for visibility/cart flags
    commerce_settings = _fetch_commerce_settings(url, version, phone_id, headers)

    # Step 5: Upsert catalog document
    if frappe.db.exists("WhatsApp Catalog", {"catalog_id": catalog_id}):
        doc = frappe.get_doc("WhatsApp Catalog", {"catalog_id": catalog_id})
    else:
        doc = frappe.new_doc("WhatsApp Catalog")
        doc.catalog_id = catalog_id

    doc.catalog_name = catalog_name
    doc.whatsapp_account = account.name
    doc.product_count = len(products)

    if commerce_settings:
        doc.is_catalog_visible = 1 if commerce_settings.get("is_catalog_visible") else 0
        doc.is_cart_enabled = 1 if commerce_settings.get("is_cart_enabled") else 0

    # Set product items
    doc.set("items", [])
    for product in products:
        price_str = _format_price(product.get("price"))
        sale_price_str = _format_price(product.get("sale_price"))

        # additional_image_urls can be a list from Meta
        extra_images = product.get("additional_image_urls", [])
        if isinstance(extra_images, list):
            extra_images = ", ".join(extra_images)

        doc.append("items", {
            "product_id": product.get("id", ""),
            "retailer_id": product.get("retailer_id", ""),
            "product_name": product.get("name", ""),
            "description": product.get("description", ""),
            "short_description": product.get("short_description", ""),
            "price": price_str,
            "currency": product.get("currency", ""),
            "sale_price": sale_price_str,
            "sale_price_start_date": product.get("sale_price_start_date", ""),
            "sale_price_end_date": product.get("sale_price_end_date", ""),
            "availability": product.get("availability", ""),
            "condition": product.get("condition", ""),
            "visibility": product.get("visibility", ""),
            "review_status": product.get("review_status", ""),
            "brand": product.get("brand", ""),
            "category": product.get("category", ""),
            "product_type": product.get("product_type", ""),
            "gtin": product.get("gtin", ""),
            "color": product.get("color", ""),
            "size": product.get("size", ""),
            "gender": product.get("gender", ""),
            "age_group": product.get("age_group", ""),
            "material": product.get("material", ""),
            "pattern": product.get("pattern", ""),
            "inventory": product.get("inventory") or 0,
            "url": product.get("url", ""),
            "image_url": product.get("image_url", ""),
            "additional_image_urls": extra_images or "",
        })

    _upsert_doc_without_hooks(doc, "WhatsApp Catalog Item", "items")

    # Clean up catalogs that are no longer linked to this account
    _cleanup_stale_catalogs(account.name, [catalog_id])

    return f"Successfully synced catalog with {len(products)} product(s) from Meta."


def _format_price(price_raw):
    """Format price from Meta (cents) to decimal string."""
    if price_raw is None:
        return ""
    try:
        price_val = int(price_raw) / 100
        return f"{price_val:.2f}"
    except (ValueError, TypeError):
        return str(price_raw)


def _fetch_commerce_settings(url, version, phone_id, headers):
    """Fetch commerce settings for a WhatsApp phone number.

    Returns dict with keys like: id (catalog_id), name, is_catalog_visible,
    is_cart_enabled, etc. Returns empty dict if unavailable.
    """
    try:
        response = make_request(
            "GET",
            f"{url}/{version}/{phone_id}/whatsapp_commerce_settings",
            headers=headers,
        )
        # Response can be {"data": [{...}]} or {"data": {...}} depending on version
        data = response.get("data", {})
        if isinstance(data, list):
            return data[0] if data else {}
        return data
    except Exception:
        # Commerce settings may not be available; continue without them
        return {}


def _fetch_all_products(url, version, catalog_id, headers):
    """Fetch all products from a catalog, handling pagination."""
    products = []
    fields = (
        "id,retailer_id,name,description,short_description,price,currency,"
        "sale_price,sale_price_start_date,sale_price_end_date,"
        "availability,condition,visibility,review_status,"
        "brand,category,product_type,gtin,"
        "color,size,gender,age_group,material,pattern,"
        "inventory,url,image_url,additional_image_urls"
    )
    endpoint = f"{url}/{version}/{catalog_id}/products?fields={fields}&limit=100"

    while endpoint:
        response = make_request("GET", endpoint, headers=headers)
        products.extend(response.get("data", []))

        # Handle pagination
        paging = response.get("paging", {})
        endpoint = paging.get("next")

    return products


def _cleanup_stale_catalogs(account_name, active_catalog_ids):
    """Remove catalogs that are no longer linked to the account on Meta."""
    if active_catalog_ids:
        stale = frappe.get_all(
            "WhatsApp Catalog",
            filters={
                "whatsapp_account": account_name,
                "catalog_id": ["not in", active_catalog_ids],
            },
            pluck="name",
        )
    else:
        stale = frappe.get_all(
            "WhatsApp Catalog",
            filters={"whatsapp_account": account_name},
            pluck="name",
        )

    for name in stale:
        frappe.db.delete("WhatsApp Catalog Item", {"parent": name, "parenttype": "WhatsApp Catalog"})
        frappe.db.delete("WhatsApp Catalog", name)

    if stale:
        frappe.db.commit()


@frappe.whitelist()
def get_catalog_products(catalog):
    """Get products from a WhatsApp Catalog for the picker UI."""
    doc = frappe.get_doc("WhatsApp Catalog", catalog)
    return [{
        "retailer_id": item.retailer_id,
        "product_id": item.product_id,
        "product_name": item.product_name,
        "price": item.price,
        "currency": item.currency,
        "availability": item.availability,
        "image_url": item.image_url,
    } for item in doc.items]


def _upsert_doc_without_hooks(doc, child_dt, child_field):
    """Insert or update a parent document and its children without hooks."""
    if frappe.db.exists(doc.doctype, doc.name):
        doc.db_update()
        frappe.db.delete(child_dt, {"parent": doc.name, "parenttype": doc.doctype})
    else:
        doc.db_insert()
    for d in doc.get(child_field):
        d.parent = doc.name
        d.parenttype = doc.doctype
        d.parentfield = child_field
        d.db_insert()
    frappe.db.commit()
