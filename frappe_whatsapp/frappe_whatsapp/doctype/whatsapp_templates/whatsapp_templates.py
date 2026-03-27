"""Create whatsapp template."""

# Copyright (c) 2022, Shridhar Patil and contributors
# For license information, please see license.txt
import os
import json
import frappe
import magic
from frappe.model.document import Document
from frappe.integrations.utils import make_post_request, make_request
from frappe.desk.form.utils import get_pdf_link

from frappe_whatsapp.utils import get_whatsapp_account

class WhatsAppTemplates(Document):
    """Create whatsapp template."""

    def validate(self):
        self.set_whatsapp_account()
        if not self.language_code or self.has_value_changed("language"):
            lang_code = frappe.db.get_value("Language", self.language) or "en"
            self.language_code = lang_code.replace("-", "_")

        if self.header_type in ["IMAGE", "DOCUMENT", "VIDEO"] and self.sample:
            self.get_session_id()
            self.get_media_id()

        # MPM and Catalog buttons require a header
        if self.buttons:
            for btn in self.buttons:
                if btn.button_type in ("MPM", "Catalog") and not self.header_type:
                    frappe.throw(f"A header is required for templates with a {btn.button_type} button.")

        if not self.is_new():
            self.update_template()

    def set_whatsapp_account(self):
        """Set whatsapp account to default if missing"""
        if not self.whatsapp_account:
            default_whatsapp_account = get_whatsapp_account()
            if not default_whatsapp_account:
                throw(_("Please set a default outgoing WhatsApp Account or Select available WhatsApp Account"))
            else:
                self.whatsapp_account = default_whatsapp_account.name

    def get_session_id(self):
        """Upload media."""
        self.get_settings()
        file_path = self.get_absolute_path(self.sample)
        mime = magic.Magic(mime=True)
        file_type = mime.from_file(file_path)

        payload = {
            'file_length': os.path.getsize(file_path),
            'file_type': file_type,
            'messaging_product': 'whatsapp'
        }

        response = make_post_request(
            f"{self._url}/{self._version}/{self._app_id}/uploads",
            headers=self._headers,
            data=json.loads(json.dumps(payload))
        )
        self._session_id = response['id']

    def get_media_id(self):
        self.get_settings()

        headers = {
                "authorization": f"OAuth {self._token}"
            }
        file_name = self.get_absolute_path(self.sample)
        with open(file_name, mode='rb') as file: # b is important -> binary
            file_content = file.read()

        payload = file_content
        response = make_post_request(
            f"{self._url}/{self._version}/{self._session_id}",
            headers=headers,
            data=payload
        )

        self._media_id = response['h']

    def get_absolute_path(self, file_name):
        if(file_name.startswith('/files/')):
            file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}/public{file_name}'
        if(file_name.startswith('/private/')):
            file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}{file_name}'
        return file_path


    def after_insert(self):
        if self.template_name:
            self.actual_name = self.template_name.lower().replace(" ", "_")

        self.get_settings()
        data = {
            "name": self.actual_name,
            "language": self.language_code,
            "category": self.category,
            "components": self._build_components(),
        }

        try:
            response = make_post_request(
                f"{self._url}/{self._version}/{self._business_id}/message_templates",
                headers=self._headers,
                data=json.dumps(data),
            )
            self.id = response["id"]
            self.status = response["status"]
            self.db_update()
        except Exception as e:
            res = frappe.flags.integration_request.json().get("error", {})
            error_message = res.get("error_user_msg", res.get("message"))
            frappe.throw(
                msg=error_message,
                title=res.get("error_user_title", "Error"),
            )

    def update_template(self):
        """Update template to meta."""
        self.get_settings()
        data = {"components": self._build_components()}

        try:
            make_post_request(
                f"{self._url}/{self._version}/{self.id}",
                headers=self._headers,
                data=json.dumps(data),
            )
        except Exception as e:
            raise e

    def _build_components(self):
        """Build template components array for Meta API."""
        components = []

        # Body
        body = {"type": "BODY", "text": self.template}
        if self.sample_values:
            body["example"] = {"body_text": [self.sample_values.split(",")]}
        components.append(body)

        # Header
        if self.header_type:
            components.append(self.get_header())

        # Footer
        if self.footer:
            components.append({"type": "FOOTER", "text": self.footer})

        # Buttons
        if self.buttons:
            button_block = {"type": "BUTTONS", "buttons": []}
            for btn in self.buttons:
                b = {"type": btn.button_type, "text": btn.button_label}

                if btn.button_type == "Visit Website":
                    b["type"] = "URL"
                    b["url"] = btn.website_url
                    if btn.url_type == "Dynamic" and btn.example_url:
                        b["example"] = btn.example_url.split(",")
                elif btn.button_type == "Call Phone":
                    b["type"] = "PHONE_NUMBER"
                    b["phone_number"] = btn.phone_number
                elif btn.button_type == "Quick Reply":
                    b["type"] = "QUICK_REPLY"
                elif btn.button_type == "Catalog":
                    b["type"] = "CATALOG"
                elif btn.button_type == "MPM":
                    b["type"] = "MPM"
                elif btn.button_type == "Copy Code":
                    b["type"] = "COPY_CODE"
                    b.pop("text", None)
                    b["example"] = btn.button_label
                elif btn.button_type == "Flow":
                    b["type"] = "FLOW"
                    if btn.flow_name:
                        b["flow_name"] = btn.flow_name
                    if btn.flow_id:
                        b["flow_id"] = btn.flow_id
                    if btn.flow_action:
                        b["flow_action"] = btn.flow_action

                button_block["buttons"].append(b)

            components.append(button_block)

        return components

    def get_settings(self):
        """Get whatsapp settings."""
        settings = frappe.get_doc("WhatsApp Account", self.whatsapp_account)
        self._token = settings.get_password("token")
        self._url = settings.url
        self._version = settings.version
        self._business_id = settings.business_id
        self._app_id = settings.app_id

        self._headers = {
            "authorization": f"Bearer {self._token}",
            "content-type": "application/json",
        }

    def on_trash(self):
        self.get_settings()
        url = f"{self._url}/{self._version}/{self._business_id}/message_templates?name={self.actual_name}"
        try:
            make_request("DELETE", url, headers=self._headers)
        except Exception:
            res = frappe.flags.integration_request.json().get("error", {})
            if res.get("error_user_title") == "Message Template Not Found":
                frappe.msgprint(
                    "Deleted locally", res.get("error_user_title", "Error"), alert=True
                )
            else:
                frappe.throw(
                    msg=res.get("error_user_msg"),
                    title=res.get("error_user_title", "Error"),
                )

    def get_header(self):
        """Get header format."""
        header = {"type": "HEADER", "format": self.header_type}
        if self.header_type == "TEXT":
            header["text"] = self.header
            if self.sample:
                samples = self.sample.split(", ")
                header.update({"example": {"header_text": samples}})
        elif self.header_type in ("IMAGE", "DOCUMENT", "VIDEO"):
            if not self.sample:
                key = frappe.get_doc(self.doctype, self.name).get_document_share_key()
                link = get_pdf_link(self.doctype, self.name)
            header.update({"example": {"header_handle": [self._media_id]}})

        return header

@frappe.whitelist()
def fetch():
    """Fetch templates from meta."""
    """Later improve this code to pass a whatsapp account remove the js funcation so that it is called from whatsapp account doctype """
    account = get_whatsapp_account(account_type='outgoing')
    if not account:
        frappe.throw("Please configure a default outgoing WhatsApp Account first.")
        
    if account.status != 'Active':
        frappe.throw(f"Default outgoing WhatsApp Account {account.name} is not Active.")

    whatsapp_accounts = [account]

    for account in whatsapp_accounts:
        # get credentials
        token = account.get_password("token")
        url = account.url
        version = account.version
        business_id = account.business_id

        headers = {"authorization": f"Bearer {token}", "content-type": "application/json"}

        try:
            # Delete old templates that don't belong to the active default outgoing account
            frappe.db.sql(
                "DELETE FROM `tabWhatsApp Button` WHERE parent IN "
                "(SELECT name FROM `tabWhatsApp Templates` WHERE whatsapp_account != %s)",
                (account.name,)
            )
            frappe.db.sql("DELETE FROM `tabWhatsApp Templates` WHERE whatsapp_account != %s", (account.name,))

            response = make_request(
                "GET",
                f"{url}/{version}/{business_id}/message_templates",
                headers=headers,
            )

            for template in response["data"]:
                # set flag to insert or update
                flags = 1
                if frappe.db.exists("WhatsApp Templates", {"actual_name": template["name"]}):
                    doc = frappe.get_doc("WhatsApp Templates", {"actual_name": template["name"]})
                else:
                    flags = 0
                    doc = frappe.new_doc("WhatsApp Templates")
                    doc.template_name = template["name"]
                    doc.actual_name = template["name"]

                doc.status = template["status"]
                doc.language_code = template["language"]
                doc.category = template["category"]
                doc.id = template["id"]
                doc.whatsapp_account = account.name

                # update components
                for component in template["components"]:

                    # update header
                    if component["type"] == "HEADER":
                        doc.header_type = component["format"]

                        # if format is text update sample text
                        if component["format"] == "TEXT":
                            doc.header = component["text"]
                    # Update footer text
                    elif component["type"] == "FOOTER":
                        doc.footer = component["text"]

                    # update template text
                    elif component["type"] == "BODY":
                        doc.template = component["text"]
                        if component.get("example"):
                            # Check if 'body_text' exists before trying to access it
                            if component["example"].get("body_text"):
                                doc.sample_values = ",".join(
                                    component["example"]["body_text"][0]
                                )

                    # Update buttons
                    elif component["type"] == "BUTTONS":
                        doc.set("buttons", [])
                        frappe.db.delete("WhatsApp Button", {"parent": doc.name, "parenttype": "WhatsApp Templates"})
                        typeMap = {
                            "URL": "Visit Website",
                            "PHONE_NUMBER": "Call Phone",
                            "QUICK_REPLY": "Quick Reply",
                            "FLOW": "Flow",
                            "CATALOG": "Catalog",
                            "MPM": "MPM",
                            "COPY_CODE": "Copy Code",
                        }

                        for i, button in enumerate(component.get("buttons", []), start=1):
                            btn = {}
                            btn["button_type"] = typeMap.get(button["type"], button["type"])
                            btn["button_label"] = button.get("text", "")
                            btn["sequence"] = i

                            if button["type"] == "URL":
                                btn["website_url"] = button.get("url")
                                if btn["website_url"] and "{{" in btn["website_url"]:
                                    btn["url_type"] = "Dynamic"
                                else:
                                    btn["url_type"] = "Static"

                                if button.get("example"):
                                    btn["example_url"] = ",".join(button["example"])
                            elif button["type"] == "PHONE_NUMBER":
                                btn["phone_number"] = button.get("phone_number")
                            elif button["type"] == "FLOW":
                                btn["flow_id"] = button.get("flow_id", "")
                                btn["flow_name"] = button.get("flow_name", "")
                                btn["flow_action"] = button.get("flow_action", "")
                            elif button["type"] == "COPY_CODE":
                                btn["button_label"] = button.get("example", button.get("text", ""))

                            doc.append("buttons", btn)

                upsert_doc_without_hooks(doc, "WhatsApp Button", "buttons")

            return "Successfully fetched templates from meta"

        except Exception as e:
            # Check if frappe.flags.integration_request is set and has a .json() method
            if hasattr(frappe.flags.integration_request, 'json'):
                try:
                    res = frappe.flags.integration_request.json().get("error", {})
                    error_message = res.get("error_user_msg", res.get("message"))
                    frappe.throw(
                        msg=error_message,
                        title=res.get("error_user_title", "Error"),
                    )
                except (json.JSONDecodeError, KeyError):
                    # Handle cases where the response is not valid JSON or lacks the 'error' key
                    frappe.throw(f"An unexpected error occurred while fetching templates: {e}")
            else:
                # Handle cases where frappe.flags.integration_request doesn't exist or isn't a proper response object
                frappe.throw(f"An unexpected server error occurred: {e}")

def upsert_doc_without_hooks(doc, child_dt, child_field):
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
