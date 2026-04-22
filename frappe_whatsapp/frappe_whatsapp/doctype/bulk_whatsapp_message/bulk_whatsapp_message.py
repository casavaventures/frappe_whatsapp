# Bulk WhatsApp Messaging for Frappe WhatsApp

import frappe
from frappe import _
import json
from frappe.utils import cint
from frappe.model.document import Document
from frappe.model.naming import make_autoname


# Bulk -> Child -> Webhook state machine
#
#  Bulk WhatsApp Message.status          WhatsApp Message (child).status
#  ---------------------------           --------------------------------
#  Draft                                    (not yet created)
#    | submit()
#    v
#  Queued                                Queued  (one row per recipient)
#    | workers run create_single_message()
#    |   -> child .insert() triggers before_insert()
#    |      -> notify() calls Meta Graph API
#    v
#  (children reach terminal status as workers finish)
#    child.insert() succeeded:             Success     (API accepted)
#    child.insert() raised:                Failed      (recorded via db_insert)
#    Meta webhook later flips child to:    sent -> delivered -> read
#
#  After each child is processed, maybe_complete() reads child counts from DB
#  (NOT an in-memory counter) and flips parent:
#    all children exist, none Failed    -> Completed
#    all children exist, some Failed    -> Partially Failed
#    fewer children than recipient_count -> stays Queued (worker died / retry needed)

class BulkWhatsAppMessage(Document):
    def autoname(self):
        self.name = make_autoname("BULK-WA-.YYYY.-.#####")
    
    def validate(self):
        self.sync_use_template()
        self.build_product_sections_json()
        self.validate_recipients()

    def sync_use_template(self):
        """Keep use_template in sync with message_mode for backwards compatibility."""
        if self.message_mode in ("Template", "Catalog Template"):
            self.use_template = 1
        elif self.message_mode:
            self.use_template = 0

    def build_product_sections_json(self):
        """Convert selected_products child table to product_sections JSON."""
        if not self.selected_products:
            return

        sections_map = {}
        for row in self.selected_products:
            title = row.section_title or "Products"
            if title not in sections_map:
                sections_map[title] = []
            sections_map[title].append({"product_retailer_id": row.retailer_id})

        sections = [
            {"title": title, "product_items": items}
            for title, items in sections_map.items()
        ]
        self.product_sections = json.dumps(sections)
    
    def validate_message(self):
        if not self.message_content:
            frappe.throw(_("Message content is required"))
    
    def validate_recipients(self):
        if not self.recipients and not self.recipient_list:
            frappe.throw(_("At least one recipient or a recipient list is required"))
        
        # If recipient list is provided, count recipients
        if self.recipient_type == 'Recipient List' and self.recipient_list:
            recipient_count = frappe.db.count("WhatsApp Recipient", {"parent": self.recipient_list})
            if recipient_count == 0:
                frappe.throw(_("Selected recipient list has no recipients"))
            self.recipient_count = recipient_count
        # If individual recipients are provided
        elif self.recipients:
            self.recipient_count = len(self.recipients)
    
    def on_submit(self):
        self.db_set("status", "Queued")
        self.queue_messages()
    
    def queue_messages(self):
        """Queue messages for sending"""
        if self.recipient_type == 'Recipient List' and self.recipient_list:
            # Fetch recipients from the recipient list
            recipients = frappe.get_all(
                "WhatsApp Recipient", 
                filters={"parent": self.recipient_list},
                fields=["mobile_number", "name", "recipient_name", "recipient_data"]
            )
            
            for recipient in recipients:
                frappe.enqueue_doc(
                    self.doctype, self.name,
                    "create_single_message",
                    "long", 4000,
                    recipient=recipient
                )
        else:
            # Use recipients from the current document
            for recipient in self.recipients:
                frappe.enqueue_doc(
                    self.doctype, self.name,
                    "create_single_message",
                    "long", 4000,
                    recipient=recipient
                )
    
    def create_single_message(self, recipient):
        """Create a single WhatsApp Message for one recipient."""
        wa_message = frappe.new_doc("WhatsApp Message")
        wa_message.to = recipient.get("mobile_number")
        wa_message.type = "Outgoing"
        wa_message.bulk_message_reference = self.name
        if self.whatsapp_account:
            wa_message.whatsapp_account = self.whatsapp_account

        if recipient.get("recipient_data"):
            try:
                wa_message.flags.custom_ref_doc = json.loads(recipient.get("recipient_data", "{}"))
            except Exception as e:
                frappe.log_error(f"Error parsing recipient data: {str(e)}", "WhatsApp Bulk Messaging")

        mode = self.message_mode or ("Template" if self.use_template else "Template")

        if mode == "Template":
            wa_message.message_type = "Template"
            wa_message.use_template = 1
            wa_message.template = self.template
            wa_message.content_type = "text"
            if recipient.get("recipient_data") and self.variable_type == "Unique":
                wa_message.body_param = recipient.get("recipient_data")
            elif self.template_variables and self.variable_type == "Common":
                wa_message.body_param = self.template_variables
            if self.attach:
                wa_message.attach = self.attach

        elif mode == "Product":
            wa_message.message_type = "Manual"
            wa_message.content_type = "product"
            wa_message.catalog = self.catalog
            wa_message.product_retailer_id = self.product_retailer_id
            wa_message.message = self.body_text or ""
            wa_message.footer = self.footer_text or ""

        elif mode == "Product List":
            wa_message.message_type = "Manual"
            wa_message.content_type = "product_list"
            wa_message.catalog = self.catalog
            wa_message.product_sections = self.product_sections
            wa_message.product_header = self.header_text or "Products"
            wa_message.message = self.body_text or ""
            wa_message.footer = self.footer_text or ""

        elif mode == "Catalog":
            wa_message.message_type = "Manual"
            wa_message.content_type = "catalog_message"
            wa_message.catalog = self.catalog
            wa_message.thumbnail_product_retailer_id = self.thumbnail_product_retailer_id or ""
            wa_message.message = self.body_text or ""

        elif mode == "Catalog Template":
            wa_message.message_type = "Template"
            wa_message.use_template = 1
            wa_message.template = self.template
            wa_message.content_type = "text"
            wa_message.product_sections = self.product_sections
            wa_message.thumbnail_product_retailer_id = self.thumbnail_product_retailer_id or ""
            if recipient.get("recipient_data") and self.variable_type == "Unique":
                wa_message.body_param = recipient.get("recipient_data")
            elif self.template_variables and self.variable_type == "Common":
                wa_message.body_param = self.template_variables
            if self.attach:
                wa_message.attach = self.attach

        wa_message.status = "Queued"
        try:
            wa_message.insert(ignore_permissions=True)
        except Exception as e:
            # before_insert hooks can call Meta's Graph API which may raise
            # (frappe.throw) on auth, rate-limit, or template errors. The row
            # never lands, so record a Failed stub so completion accounting is
            # correct and retry_failed() has a handle to requeue.
            frappe.db.rollback()
            frappe.log_error(
                title=f"Bulk WhatsApp send failed ({recipient.get('mobile_number')})",
                message=frappe.get_traceback(),
            )
            self._record_failed_child(recipient, str(e))

        self.maybe_complete()

    def _record_failed_child(self, recipient, error_msg):
        """Insert a Failed WhatsApp Message row without triggering send hooks."""
        failed = frappe.new_doc("WhatsApp Message")
        failed.to = recipient.get("mobile_number")
        failed.type = "Outgoing"
        failed.status = "Failed"
        failed.bulk_message_reference = self.name
        failed.whatsapp_account = self.whatsapp_account
        failed.message_type = "Template" if self.use_template else "Manual"
        failed.content_type = "text"
        failed.message = (error_msg or "")[:140]
        try:
            failed.flags.ignore_validate = True
            failed.db_insert()
        except Exception:
            frappe.log_error(
                title="Bulk WhatsApp: could not record failed child row",
                message=frappe.get_traceback(),
            )

    def maybe_complete(self):
        """Set bulk status from actual child counts in the DB.

        No in-memory counter. Parallel workers cannot race because each one
        reads the authoritative row count; the final worker to finish sees
        total == recipient_count and flips the status.
        """
        row = frappe.db.sql(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Failed' THEN 1 ELSE 0 END) AS failed
            FROM `tabWhatsApp Message`
            WHERE bulk_message_reference = %s
            """,
            self.name,
            as_dict=True,
        )[0]
        total = cint(row.get("total"))
        failed = cint(row.get("failed"))

        self.db_set("sent_count", total, update_modified=False)

        if total >= cint(self.recipient_count):
            self.db_set("status", "Partially Failed" if failed else "Completed")

    def retry_failed(self):
        """Retry failed messages"""
        failed_messages = frappe.get_all(
            "WhatsApp Message",
            filters={
                "bulk_message_reference": self.name,
                "status": "Failed"
            },
            fields=["name"]
        )
        
        count = 0
        for msg in failed_messages:
            message_doc = frappe.get_doc("WhatsApp Message", msg.name)
            message_doc.status = "Queued"
            message_doc.save(ignore_permissions=True)
            count += 1
        
        frappe.msgprint(_("{0} messages have been requeued for sending").format(count))
        
    def get_progress(self):
        """Get sending progress for this bulk message"""
        total = self.recipient_count
        sent = frappe.db.count("WhatsApp Message", {
            "bulk_message_reference": self.name,
            "status": ["in", ["sent","delivered", "Success", "read"]]
        })
        failed = frappe.db.count("WhatsApp Message", {
            "bulk_message_reference": self.name,
            "status": "Failed"
        })
        queued = frappe.db.count("WhatsApp Message", {
            "bulk_message_reference": self.name,
            "status": "Queued"
        })
        
        return {
            "total": total,
            "sent": sent,
            "failed": failed,
            "queued": queued,
            "percent": (sent / total * 100) if total else 0
        }
