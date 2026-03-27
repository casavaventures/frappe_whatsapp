# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt
import json
import frappe
from frappe import _, throw
from frappe.model.document import Document
from frappe.integrations.utils import make_post_request

from frappe_whatsapp.utils import get_whatsapp_account, format_number

class WhatsAppMessage(Document):
    def validate(self):
        self.set_whatsapp_account()

    def on_update(self):
        self.update_profile_name()

    def update_profile_name(self):
        number = self.get("from")
        if not number:
            return
        from_number = format_number(number)

        if (
            self.has_value_changed("profile_name")
            and self.profile_name
            and from_number
            and frappe.db.exists("WhatsApp Profiles", {"number": from_number})
        ):
            profile_id = frappe.get_value("WhatsApp Profiles", {"number": from_number}, "name")
            frappe.db.set_value("WhatsApp Profiles", profile_id, "profile_name", self.profile_name)

    def create_whatsapp_profile(self):
        number = format_number(self.get("from") or self.to)
        if not frappe.db.exists("WhatsApp Profiles", {"number": number}):
            frappe.get_doc({
                "doctype": "WhatsApp Profiles",
                "profile_name": self.profile_name,
                "number": number,
                "whatsapp_account": self.whatsapp_account
            }).insert(ignore_permissions=True)

    def set_whatsapp_account(self):
        """Set whatsapp account to default if missing"""
        if not self.whatsapp_account:
            account_type = 'outgoing' if self.type == 'Outgoing' else 'incoming'
            default_whatsapp_account = get_whatsapp_account(account_type=account_type)
            if not default_whatsapp_account:
                throw(_("Please set a default outgoing WhatsApp Account or Select available WhatsApp Account"))
            else:
                self.whatsapp_account = default_whatsapp_account.name

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

    """Send whats app messages."""
    def before_insert(self):
        """Send message."""
        self.build_product_sections_json()
        self.set_whatsapp_account()
        if self.type == "Outgoing" and self.message_type != "Template":
            if self.attach and not self.attach.startswith("http"):
                link = frappe.utils.get_url() + "/" + self.attach
            else:
                link = self.attach

            data = {
                "messaging_product": "whatsapp",
                "to": format_number(self.to),
                "type": self.content_type,
            }
            if self.is_reply and self.reply_to_message_id:
                data["context"] = {"message_id": self.reply_to_message_id}
            if self.content_type in ["document", "image", "video"]:
                data[self.content_type.lower()] = {
                    "link": link,
                    "caption": self.message,
                }
            elif self.content_type == "reaction":
                data["reaction"] = {
                    "message_id": self.reply_to_message_id,
                    "emoji": self.message,
                }
            elif self.content_type == "text":
                data["text"] = {"preview_url": True, "body": self.message}

            elif self.content_type == "audio":
                data["audio"] = {"link": link}

            elif self.content_type == "interactive":
                # Interactive message (buttons or list)
                data["type"] = "interactive"
                buttons_data = json.loads(self.buttons) if isinstance(self.buttons, str) else self.buttons

                if isinstance(buttons_data, list) and len(buttons_data) > 3:
                    # Use list message for more than 3 options (max 10)
                    data["interactive"] = {
                        "type": "list",
                        "body": {"text": self.message},
                        "action": {
                            "button": "Select Option",
                            "sections": [{
                                "title": "Options",
                                "rows": [
                                    {"id": btn["id"], "title": btn["title"], "description": btn.get("description", "")}
                                    for btn in buttons_data[:10]
                                ]
                            }]
                        }
                    }
                else:
                    # Use button message for 3 or fewer options
                    data["interactive"] = {
                        "type": "button",
                        "body": {"text": self.message},
                        "action": {
                            "buttons": [
                                {
                                    "type": "reply",
                                    "reply": {"id": btn["id"], "title": btn["title"]}
                                }
                                for btn in buttons_data[:3]
                            ]
                        }
                    }

            elif self.content_type == "product":
                catalog_id = self._get_catalog_id()
                data["type"] = "interactive"
                interactive = {
                    "type": "product",
                    "body": {"text": self.message or ""},
                    "action": {
                        "catalog_id": catalog_id,
                        "product_retailer_id": self.product_retailer_id,
                    }
                }
                if self.footer:
                    interactive["footer"] = {"text": self.footer}
                data["interactive"] = interactive

            elif self.content_type == "product_list":
                catalog_id = self._get_catalog_id()
                sections = json.loads(self.product_sections) if isinstance(self.product_sections, str) else self.product_sections
                data["type"] = "interactive"
                interactive = {
                    "type": "product_list",
                    "header": {"type": "text", "text": self.product_header or "Products"},
                    "body": {"text": self.message or ""},
                    "action": {
                        "catalog_id": catalog_id,
                        "sections": sections,
                    }
                }
                if self.footer:
                    interactive["footer"] = {"text": self.footer}
                data["interactive"] = interactive

            elif self.content_type == "catalog_message":
                catalog_id = self._get_catalog_id()
                data["type"] = "interactive"
                params = {}
                if self.thumbnail_product_retailer_id:
                    params["thumbnail_product_retailer_id"] = self.thumbnail_product_retailer_id
                data["interactive"] = {
                    "type": "catalog_message",
                    "body": {"text": self.message or ""},
                    "action": {
                        "name": "catalog_message",
                        "parameters": params,
                    }
                }

            elif self.content_type == "flow":
                # WhatsApp Flow message
                if not self.flow:
                    frappe.throw(_("WhatsApp Flow is required for flow content type"))

                flow_doc = frappe.get_doc("WhatsApp Flow", self.flow)

                if not flow_doc.flow_id:
                    frappe.throw(_("Flow must be created on WhatsApp before sending"))

                # Determine flow mode - draft flows can be tested with mode: "draft"
                flow_mode = None
                if flow_doc.status != "Published":
                    flow_mode = "draft"
                    frappe.msgprint(_("Sending flow in draft mode (for testing only)"), indicator="orange")

                # Get first screen if not specified
                flow_screen = self.flow_screen
                if not flow_screen and flow_doc.screens:
                    flow_screen = flow_doc.screens[0].screen_id

                data["type"] = "interactive"
                data["interactive"] = {
                    "type": "flow",
                    "body": {"text": self.message or "Please fill out the form"},
                    "action": {
                        "name": "flow",
                        "parameters": {
                            "flow_message_version": "3",
                            "flow_id": flow_doc.flow_id,
                            "flow_cta": self.flow_cta or flow_doc.flow_cta or "Open",
                            "flow_action": "navigate",
                            "flow_action_payload": {
                                "screen": flow_screen
                            }
                        }
                    }
                }

                # Add draft mode for testing unpublished flows
                if flow_mode:
                    data["interactive"]["action"]["parameters"]["mode"] = flow_mode

                # Add flow token - generate one if not provided (required by WhatsApp)
                flow_token = self.flow_token or frappe.generate_hash(length=16)
                data["interactive"]["action"]["parameters"]["flow_token"] = flow_token

            try:
                self.notify(data)
                self.status = "Success"
            except Exception as e:
                self.status = "Failed"
                frappe.throw(f"Failed to send message {str(e)}")
        elif self.type == "Outgoing" and self.message_type == "Template" and not self.message_id:
            self.send_template()

        self.create_whatsapp_profile()

    def send_template(self):
        """Send template."""
        template = frappe.get_doc("WhatsApp Templates", self.template)
        data = {
            "messaging_product": "whatsapp",
            "to": format_number(self.to),
            "type": "template",
            "template": {
                "name": template.actual_name or template.template_name,
                "language": {"code": template.language_code},
                "components": [],
            },
        }

        if template.sample_values:
            field_names = template.field_names.split(",") if template.field_names else template.sample_values.split(",")
            parameters = []
            template_parameters = []

            if self.body_param is not None:
                parsed = json.loads(self.body_param)
                if isinstance(parsed, list):
                    # Array format: [{"type": "text", "value": "..."}]
                    for item in parsed:
                        val = item.get("value", item.get("text", "")) if isinstance(item, dict) else str(item)
                        parameters.append({"type": "text", "text": val})
                        template_parameters.append(val)
                elif isinstance(parsed, dict):
                    # Dict format: {"field1": "val1", ...}
                    for param in parsed.values():
                        parameters.append({"type": "text", "text": param})
                        template_parameters.append(param)
            elif self.flags.custom_ref_doc:
                custom_values = self.flags.custom_ref_doc
                for field_name in field_names:
                    value = custom_values.get(field_name.strip())
                    parameters.append({"type": "text", "text": value})
                    template_parameters.append(value)                    

            else:
                if self.reference_doctype and self.reference_name:
                    ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)
                    for field_name in field_names:
                        value = ref_doc.get_formatted(field_name.strip())
                        parameters.append({"type": "text", "text": value})
                        template_parameters.append(value)

            self.template_parameters = json.dumps(template_parameters)
            data["template"]["components"].append(
                {
                    "type": "body",
                    "parameters": parameters,
                }
            )

        if template.header_type and template.header_type in ("IMAGE", "DOCUMENT", "VIDEO"):
            media_url = None
            if self.attach:
                media_url = self.attach if self.attach.startswith("http") else f'{frappe.utils.get_url()}{self.attach}'
            elif template.sample:
                media_url = template.sample if template.sample.startswith("http") else f'{frappe.utils.get_url()}{template.sample}'

            if media_url:
                media_type = template.header_type.lower()
                data['template']['components'].append({
                    "type": "header",
                    "parameters": [{
                        "type": media_type,
                        media_type: {
                            "link": media_url
                        }
                    }]
                })

        if template.buttons:
            button_parameters = []
            mpm_index = None
            for idx, btn in enumerate(template.buttons):
                if btn.button_type == "Quick Reply":
                    button_parameters.append({
                        "type": "button",
                        "sub_type": "quick_reply",
                        "index": str(idx),
                        "parameters": [{"type": "payload", "payload": btn.button_label}]
                    })
                elif btn.button_type == "Call Phone":
                    button_parameters.append({
                        "type": "button",
                        "sub_type": "phone_number",
                        "index": str(idx),
                        "parameters": [{"type": "text", "text": btn.phone_number}]
                    })
                elif btn.button_type == "Visit Website":
                    # Only send parameters for dynamic URL buttons
                    # Static URL buttons must NOT have parameters (WhatsApp API error #132018)
                    if btn.url_type == "Dynamic":
                        # Support chatbot injected button params
                        if hasattr(self, "_button_params") and self._button_params and str(idx) in self._button_params:
                            url = self._button_params[str(idx)]
                        elif self.reference_doctype and self.reference_name:
                            ref_doc = frappe.get_doc(self.reference_doctype, self.reference_name)
                            url = ref_doc.get_formatted(btn.website_url)
                        else:
                            url = btn.website_url
                        button_parameters.append({
                            "type": "button",
                            "sub_type": "url",
                            "index": str(idx),
                            "parameters": [{"type": "text", "text": url}]
                        })
                elif btn.button_type == "Flow":
                    button_parameters.append({
                        "type": "button",
                        "sub_type": "flow",
                        "index": str(idx),
                        "parameters": [{"type": "action", "action": {
                            "flow_token": frappe.generate_hash(length=16)
                        }}]
                    })
                elif btn.button_type == "Copy Code":
                    # Copy Code buttons get the coupon code from body_param or ref doc
                    code = btn.button_label
                    if hasattr(self, "_button_params") and self._button_params and str(idx) in self._button_params:
                        code = self._button_params[str(idx)]
                    button_parameters.append({
                        "type": "button",
                        "sub_type": "copy_code",
                        "index": str(idx),
                        "parameters": [{"type": "coupon_code", "coupon_code": code}]
                    })
                elif btn.button_type == "MPM":
                    mpm_index = idx
                # Catalog buttons need no parameters at send time

            if button_parameters:
                data['template']['components'].extend(button_parameters)

        # MPM (Multi-Product Message) template support
        if self.product_sections:
            sections = json.loads(self.product_sections) if isinstance(self.product_sections, str) else self.product_sections
            data["template"]["components"].append({
                "type": "button",
                "sub_type": "mpm",
                "index": str(mpm_index if mpm_index is not None else 0),
                "parameters": [{
                    "type": "action",
                    "action": {
                        "thumbnail_product_retailer_id": self.thumbnail_product_retailer_id or "",
                        "sections": sections,
                    }
                }]
            })

        self.notify(data)

    def _get_catalog_id(self):
        """Get the Meta catalog ID from the linked WhatsApp Catalog."""
        if not self.catalog:
            frappe.throw(_("Please select a WhatsApp Catalog"))
        catalog_id = frappe.db.get_value("WhatsApp Catalog", self.catalog, "catalog_id")
        if not catalog_id:
            frappe.throw(_("Selected catalog has no Catalog ID. Please sync the catalog first."))
        return catalog_id

    def notify(self, data):
        """Notify."""
        whatsapp_account = frappe.get_doc(
            "WhatsApp Account",
            self.whatsapp_account,
        )
        token = whatsapp_account.get_password("token")

        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        }
        try:
            response = make_post_request(
                f"{whatsapp_account.url}/{whatsapp_account.version}/{whatsapp_account.phone_id}/messages",
                headers=headers,
                data=json.dumps(data),
            )
            self.message_id = response["messages"][0]["id"]

        except Exception as e:
            res = frappe.flags.integration_request.json().get("error", {})
            error_message = res.get("Error", res.get("message"))
            frappe.get_doc(
                {
                    "doctype": "WhatsApp Notification Log",
                    "template": "Text Message",
                    "meta_data": frappe.flags.integration_request.json(),
                }
            ).insert(ignore_permissions=True)

            frappe.throw(msg=error_message, title=res.get("error_user_title", "Error"))

    def format_number(self, number):
        """Format number."""
        if number.startswith("+"):
            number = number[1 : len(number)]

        return number

    @frappe.whitelist()
    def send_read_receipt(self):
        data = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": self.message_id
        }

        settings = frappe.get_doc(
            "WhatsApp Account",
            self.whatsapp_account,
        )

        token = settings.get_password("token")

        headers = {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        }
        try:
            response = make_post_request(
                f"{settings.url}/{settings.version}/{settings.phone_id}/messages",
                headers=headers,
                data=json.dumps(data),
            )

            if response.get("success"):
                self.status = "marked as read"
                self.save()
                return response.get("success")

        except Exception as e:
            res = frappe.flags.integration_request.json().get("error", {})
            error_message = res.get("Error", res.get("message"))
            frappe.log_error("WhatsApp API Error", f"{error_message}\n{res}")


def on_doctype_update():
    frappe.db.add_index("WhatsApp Message", ["reference_doctype", "reference_name"])


@frappe.whitelist()
def send_template(to, reference_doctype, reference_name, template):
    try:
        doc = frappe.get_doc({
            "doctype": "WhatsApp Message",
            "to": to,
            "type": "Outgoing",
            "message_type": "Template",
            "reference_doctype": reference_doctype,
            "reference_name": reference_name,
            "content_type": "text",
            "template": template
        })

        doc.save()
    except Exception as e:
        raise e
