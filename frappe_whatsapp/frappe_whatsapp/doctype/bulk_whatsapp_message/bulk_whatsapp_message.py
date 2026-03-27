# Bulk WhatsApp Messaging for Frappe WhatsApp
# bulk_whatsapp_messaging.py

import frappe
from frappe import _
import json
from frappe.utils import cint, get_datetime, now
from frappe.model.document import Document
from frappe.model.naming import make_autoname

# Add these files to your frappe_whatsapp app

# 1. First, create a new DocType for Bulk WhatsApp Messaging
# Save this as a Python file in your app's folder: 
# frappe_whatsapp/frappe_whatsapp/doctype/bulk_whatsapp_message/bulk_whatsapp_message.py

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
        except Exception:
            self.db_set("status", "Partially Failed")
        self.db_set("sent_count", cint(self.sent_count) + 1)
        if self.recipient_count == self.sent_count:
            self.db_set("status", "Completed")

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
