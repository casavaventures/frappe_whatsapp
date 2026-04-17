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
from frappe.utils import now_datetime

from frappe_whatsapp.utils import get_whatsapp_account


def get_account_credentials(account_name):
    """Get WhatsApp Account credentials as a dict.

    Shared helper used by both the Document class methods and standalone functions.
    """
    settings = frappe.get_doc("WhatsApp Account", account_name)
    token = settings.get_password("token")
    return {
        "token": token,
        "url": settings.url,
        "version": settings.version,
        "business_id": settings.business_id,
        "app_id": settings.app_id,
        "headers": {
            "authorization": f"Bearer {token}",
            "content-type": "application/json",
        },
    }


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
                frappe.throw(frappe._("Please set a default outgoing WhatsApp Account or Select available WhatsApp Account"))
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
        if file_name.startswith('/files/'):
            file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}/public{file_name}'
        elif file_name.startswith('/private/'):
            file_path = f'{frappe.utils.get_bench_path()}/sites/{frappe.utils.get_site_base_path()[2:]}{file_name}'
        else:
            frappe.throw(f"Invalid file path: {file_name}. Must start with /files/ or /private/")
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
        creds = get_account_credentials(self.whatsapp_account)
        self._token = creds["token"]
        self._url = creds["url"]
        self._version = creds["version"]
        self._business_id = creds["business_id"]
        self._app_id = creds["app_id"]
        self._headers = creds["headers"]

    def on_trash(self):
        """Local delete only. Does NOT call Meta API.

        Use delete_from_meta() to explicitly delete from Meta.
        """
        pass

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
def delete_from_meta(template_name):
    """Delete a template from Meta and then trash the local doc.

    Error handling:
    - 404: template already gone on Meta, still trash locally
    - 401/403: auth failure, show reauth message, do NOT trash
    - 5xx/timeout: transient error, show error, do NOT trash
    """
    doc = frappe.get_doc("WhatsApp Templates", template_name)
    creds = get_account_credentials(doc.whatsapp_account)

    url = f"{creds['url']}/{creds['version']}/{creds['business_id']}/message_templates?name={doc.actual_name}"

    try:
        make_request("DELETE", url, headers=creds["headers"])
        frappe.delete_doc("WhatsApp Templates", template_name, force=True)
        frappe.db.commit()
        return {"status": "success", "message": "Template deleted from Meta and locally."}
    except Exception:
        if not hasattr(frappe.flags.integration_request, 'json'):
            frappe.log_error(title=f"Delete from Meta failed: {template_name}")
            frappe.throw("An unexpected error occurred while deleting the template from Meta.")

        try:
            response = frappe.flags.integration_request
            status_code = response.status_code if hasattr(response, 'status_code') else 0
            res = response.json().get("error", {})

            if status_code == 404 or res.get("error_user_title") == "Message Template Not Found":
                frappe.delete_doc("WhatsApp Templates", template_name, force=True)
                frappe.db.commit()
                return {"status": "success", "message": "Template was already deleted on Meta. Removed locally."}

            if status_code in (401, 403):
                frappe.throw(
                    msg=f"Authentication failed for WhatsApp Account '{doc.whatsapp_account}'. Please reauthorize the token.",
                    title="Auth Error",
                )

            error_message = res.get("error_user_msg", res.get("message", "Unknown error"))
            frappe.log_error(title=f"Delete from Meta failed: {template_name}")
            frappe.throw(
                msg=error_message,
                title=res.get("error_user_title", "Error"),
            )
        except (json.JSONDecodeError, KeyError, AttributeError):
            frappe.log_error(title=f"Delete from Meta failed: {template_name}")
            frappe.throw("An unexpected error occurred while deleting the template from Meta.")


@frappe.whitelist()
def fetch():
    """Fetch templates from Meta for all active WhatsApp Accounts.

    Syncs templates, marks orphans as 'Deleted on Meta', handles pagination.
    """
    active_accounts = frappe.get_all(
        "WhatsApp Account",
        filters={"status": "Active"},
        fields=["name"],
    )

    if not active_accounts:
        frappe.throw("No active WhatsApp Accounts found. Please configure at least one.")

    seen_templates = set()  # (actual_name, whatsapp_account) tuples seen from Meta
    successful_accounts = []  # accounts whose fetch succeeded

    for account_ref in active_accounts:
        account_name = account_ref.name
        try:
            creds = get_account_credentials(account_name)
        except Exception:
            frappe.log_error(title=f"WhatsApp template sync: failed to get credentials for {account_name}")
            continue

        try:
            all_templates = _fetch_all_pages(creds)
        except Exception:
            frappe.log_error(title=f"WhatsApp template sync: API call failed for account {account_name}")
            continue

        successful_accounts.append(account_name)

        for template in all_templates:
            seen_templates.add((template["name"], account_name))
            _upsert_template(template, account_name)

    # Orphan detection: mark templates not seen from Meta for successful accounts
    _mark_orphans(seen_templates, successful_accounts)

    frappe.db.commit()
    return "Successfully synced templates from Meta"


def _fetch_all_pages(creds):
    """Fetch all template pages from Meta API, following pagination."""
    all_templates = []
    url = f"{creds['url']}/{creds['version']}/{creds['business_id']}/message_templates"

    while url:
        response = make_request("GET", url, headers=creds["headers"])
        all_templates.extend(response.get("data", []))
        url = response.get("paging", {}).get("next")

    return all_templates


def _upsert_template(template, account_name):
    """Create or update a local template doc from Meta API data."""
    existing = frappe.db.exists(
        "WhatsApp Templates",
        {"actual_name": template["name"], "whatsapp_account": account_name},
    )

    if existing:
        doc = frappe.get_doc("WhatsApp Templates", existing)
    else:
        doc = frappe.new_doc("WhatsApp Templates")
        doc.template_name = template["name"]
        doc.actual_name = template["name"]

    doc.status = template["status"]
    doc.language_code = template["language"]
    doc.category = template["category"]
    doc.id = template["id"]
    doc.whatsapp_account = account_name
    doc.last_synced = now_datetime()

    for component in template.get("components", []):
        if component["type"] == "HEADER":
            doc.header_type = component["format"]
            if component["format"] == "TEXT":
                doc.header = component["text"]
        elif component["type"] == "FOOTER":
            doc.footer = component["text"]
        elif component["type"] == "BODY":
            doc.template = component["text"]
            if component.get("example"):
                if component["example"].get("body_text"):
                    doc.sample_values = ",".join(
                        component["example"]["body_text"][0]
                    )
        elif component["type"] == "BUTTONS":
            doc.set("buttons", [])
            if existing:
                frappe.db.delete("WhatsApp Button", {"parent": doc.name, "parenttype": "WhatsApp Templates"})

            type_map = {
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
                btn["button_type"] = type_map.get(button["type"], button["type"])
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


def _mark_orphans(seen_templates, successful_accounts):
    """Mark local templates not found on Meta as 'Deleted on Meta'.

    Only checks templates belonging to accounts whose fetch succeeded.
    Never auto-deletes. User can manually clean up.
    """
    if not successful_accounts:
        return

    local_templates = frappe.get_all(
        "WhatsApp Templates",
        filters={"whatsapp_account": ["in", successful_accounts]},
        fields=["name", "actual_name", "whatsapp_account", "status"],
    )

    for tmpl in local_templates:
        key = (tmpl.actual_name, tmpl.whatsapp_account)
        if key not in seen_templates and tmpl.status != "Deleted on Meta":
            frappe.db.set_value("WhatsApp Templates", tmpl.name, "status", "Deleted on Meta")

            # Log if any notifications reference this template
            notifications = frappe.get_all(
                "WhatsApp Notification",
                filters={"template": tmpl.name},
                fields=["name"],
            )
            if notifications:
                notification_names = ", ".join([n.name for n in notifications])
                frappe.log_error(
                    title=f"Orphaned WhatsApp Template: {tmpl.name}",
                    message=f"Template '{tmpl.actual_name}' was not found on Meta but is referenced by "
                            f"WhatsApp Notifications: {notification_names}. "
                            f"The template has been marked as 'Deleted on Meta'.",
                )


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
