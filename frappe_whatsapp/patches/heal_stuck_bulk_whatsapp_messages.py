"""Heal Bulk WhatsApp Message records stuck in 'Queued' because of the race
condition in the old create_single_message() increment logic.

For every Bulk WhatsApp Message currently in 'Queued' or 'In Progress', recount
its child WhatsApp Message rows and flip status based on the actual counts.
Records where children are still genuinely being processed keep 'Queued'.
"""

import frappe
from frappe.utils import cint


def execute():
    stuck = frappe.get_all(
        "Bulk WhatsApp Message",
        filters={"status": ["in", ("Queued", "In Progress")], "docstatus": 1},
        fields=["name", "recipient_count"],
    )

    healed = 0
    for bulk in stuck:
        row = frappe.db.sql(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS failed
            FROM `tabWhatsApp Message`
            WHERE bulk_message_reference = %s
            """,
            bulk.name,
            as_dict=True,
        )[0]

        total = cint(row.get("total"))
        failed = cint(row.get("failed"))
        recipient_count = cint(bulk.recipient_count)

        frappe.db.set_value(
            "Bulk WhatsApp Message",
            bulk.name,
            "sent_count",
            total,
            update_modified=False,
        )

        if recipient_count and total >= recipient_count:
            new_status = "Partially Failed" if failed else "Completed"
            frappe.db.set_value(
                "Bulk WhatsApp Message",
                bulk.name,
                "status",
                new_status,
                update_modified=False,
            )
            healed += 1

    if healed:
        print(f"heal_stuck_bulk_whatsapp_messages: healed {healed} stuck bulks")
    frappe.db.commit()
