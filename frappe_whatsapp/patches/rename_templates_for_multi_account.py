"""Rename WhatsApp Templates docs to include whatsapp_account in the name.

Old format: {template_name}-{language_code}
New format: {actual_name}-{language_code}-{whatsapp_account}

Also updates WhatsApp Notification link references.
"""
import frappe


def execute():
    if not frappe.db.table_exists("tabWhatsApp Templates"):
        return

    templates = frappe.db.get_all(
        "WhatsApp Templates",
        fields=["name", "actual_name", "language_code", "whatsapp_account"],
    )

    for tmpl in templates:
        actual_name = tmpl.actual_name or tmpl.name.split("-")[0]
        language_code = tmpl.language_code or "en"
        whatsapp_account = tmpl.whatsapp_account or ""

        new_name = f"{actual_name}-{language_code}-{whatsapp_account}"

        if new_name == tmpl.name:
            continue

        # Update WhatsApp Notification references
        frappe.db.sql(
            "UPDATE `tabWhatsApp Notification` SET template = %s WHERE template = %s",
            (new_name, tmpl.name),
        )

        # Rename the document
        frappe.rename_doc(
            "WhatsApp Templates", tmpl.name, new_name, force=True, show_alert=False
        )

    frappe.db.commit()
