# Copyright (c) 2022, Shridhar Patil and Contributors
# See license.txt

import json
from unittest.mock import patch, MagicMock

import frappe
from frappe_whatsapp.testing import IntegrationTestCase


TEMPLATE_MODULE = "frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates"


class TestWhatsAppTemplates(IntegrationTestCase):
    """Tests for WhatsApp Templates doctype."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._ensure_test_account()
        cls._ensure_second_test_account()

    @classmethod
    def _ensure_test_account(cls):
        if not frappe.db.exists("WhatsApp Account", "Test WA Tmpl Account"):
            account = frappe.get_doc({
                "doctype": "WhatsApp Account",
                "account_name": "Test WA Tmpl Account",
                "status": "Active",
                "url": "https://graph.facebook.com",
                "version": "v17.0",
                "phone_id": "tmpl_test_phone_id",
                "business_id": "tmpl_test_business_id",
                "app_id": "tmpl_test_app_id",
                "webhook_verify_token": "tmpl_test_verify_token",
                "is_default_incoming": 1,
                "is_default_outgoing": 1,
            })
            account.insert(ignore_permissions=True)
            frappe.db.commit()

    @classmethod
    def _ensure_second_test_account(cls):
        if not frappe.db.exists("WhatsApp Account", "Test WA Tmpl Account 2"):
            account = frappe.get_doc({
                "doctype": "WhatsApp Account",
                "account_name": "Test WA Tmpl Account 2",
                "status": "Active",
                "url": "https://graph.facebook.com",
                "version": "v17.0",
                "phone_id": "tmpl_test_phone_id_2",
                "business_id": "tmpl_test_business_id_2",
                "app_id": "tmpl_test_app_id_2",
                "webhook_verify_token": "tmpl_test_verify_token_2",
                "is_default_incoming": 0,
                "is_default_outgoing": 0,
            })
            account.insert(ignore_permissions=True)
            frappe.db.commit()

    def setUp(self):
        # Set password within each test's transaction scope
        from frappe.utils.password import set_encrypted_password
        set_encrypted_password("WhatsApp Account", "Test WA Tmpl Account", "test_tmpl_token", "token")
        set_encrypted_password("WhatsApp Account", "Test WA Tmpl Account 2", "test_tmpl_token_2", "token")
        # Clear ALL defaults then set ours (db.set_value bypasses on_update hooks)
        frappe.db.sql("UPDATE `tabWhatsApp Account` SET is_default_outgoing=0, is_default_incoming=0")
        frappe.db.set_value("WhatsApp Account", "Test WA Tmpl Account", {
            "is_default_outgoing": 1,
            "is_default_incoming": 1,
        })

    def tearDown(self):
        # Use SQL-level delete to avoid triggering on_trash (which calls get_settings)
        frappe.db.delete("WhatsApp Templates", {"template_name": ["like", "test_tmpl_%"]})
        frappe.db.delete("WhatsApp Templates", {"template_name": ["like", "test_msg_template%"]})
        frappe.db.commit()

    def _make_template_without_hooks(self, **kwargs):
        """Create a template directly in DB to avoid Meta API calls."""
        template_name = kwargs.get("template_name", "test_tmpl_basic")
        language_code = kwargs.get("language_code", "en")
        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": template_name,
            "actual_name": template_name.lower().replace(" ", "_"),
            "template": kwargs.get("template", "Hello {{1}}"),
            "category": kwargs.get("category", "TRANSACTIONAL"),
            "language": kwargs.get("language", frappe.db.get_value("Language", {"language_code": "en"}) or "en"),
            "language_code": language_code,
            "whatsapp_account": kwargs.get("whatsapp_account", "Test WA Tmpl Account"),
            "status": kwargs.get("status", "APPROVED"),
            "id": kwargs.get("id", f"tmpl_id_{template_name}"),
            "header_type": kwargs.get("header_type", ""),
            "header": kwargs.get("header", ""),
            "footer": kwargs.get("footer", ""),
            "sample_values": kwargs.get("sample_values", ""),
        })
        doc.db_insert()
        frappe.db.commit()
        return frappe.get_doc("WhatsApp Templates", doc.name)

    def test_template_autoname(self):
        """Test template autoname format: actual_name-language_code-whatsapp_account."""
        doc = self._make_template_without_hooks(template_name="test_tmpl_autoname")
        self.assertEqual(doc.name, "test_tmpl_autoname-en-Test WA Tmpl Account")

    @patch("frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.make_post_request")
    def test_language_code_set_on_validate(self, mock_post):
        """Test language_code is derived from language field on validate."""
        mock_post.return_value = {}
        doc = self._make_template_without_hooks(template_name="test_tmpl_langcode")
        doc.language_code = ""
        doc.language = frappe.db.get_value("Language", {"language_code": "en"}) or "en"
        doc.validate()
        self.assertTrue(len(doc.language_code) > 0)

    def test_set_whatsapp_account_default(self):
        """Test whatsapp_account is set to default if missing."""
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_default_acct",
            whatsapp_account=""
        )
        doc.whatsapp_account = ""
        doc.set_whatsapp_account()
        self.assertTrue(len(doc.whatsapp_account) > 0)

    def test_get_absolute_path_public_files(self):
        """Test get_absolute_path for public files."""
        doc = self._make_template_without_hooks(template_name="test_tmpl_path")
        path = doc.get_absolute_path("/files/test_image.png")
        self.assertIn("/public/files/test_image.png", path)

    def test_get_absolute_path_private_files(self):
        """Test get_absolute_path for private files."""
        doc = self._make_template_without_hooks(template_name="test_tmpl_priv_path")
        path = doc.get_absolute_path("/private/files/test_doc.pdf")
        self.assertIn("/private/files/test_doc.pdf", path)

    def test_get_header_text(self):
        """Test get_header for TEXT header type."""
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_hdr_text",
            header_type="TEXT",
            header="Order Update"
        )
        header = doc.get_header()
        self.assertEqual(header["type"], "HEADER")
        self.assertEqual(header["format"], "TEXT")
        self.assertEqual(header["text"], "Order Update")

    def test_get_header_text_with_sample(self):
        """Test get_header for TEXT header with sample values."""
        doc = self._make_template_without_hooks(
            template_name="test_tmpl_hdr_sample",
            header_type="TEXT",
            header="Hello {{1}}",
            sample_values="John"
        )
        doc.sample = "John"
        header = doc.get_header()
        self.assertEqual(header["format"], "TEXT")
        self.assertIn("example", header)
        self.assertEqual(header["example"]["header_text"], ["John"])

    def test_get_settings(self):
        """Test get_settings loads WhatsApp Account credentials."""
        doc = self._make_template_without_hooks(template_name="test_tmpl_settings")
        doc.get_settings()
        self.assertEqual(doc._url, "https://graph.facebook.com")
        self.assertEqual(doc._version, "v17.0")
        self.assertEqual(doc._business_id, "tmpl_test_business_id")

    @patch("frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.make_post_request")
    def test_after_insert_creates_template_on_meta(self, mock_post):
        """Test after_insert sends template to Meta API."""
        mock_post.return_value = {
            "id": "new_template_id_123",
            "status": "PENDING",
        }

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_insert",
            "template": "Test body {{1}}",
            "sample_values": "World",
            "category": "TRANSACTIONAL",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.insert(ignore_permissions=True)

        self.assertTrue(mock_post.called)
        call_args = mock_post.call_args
        sent_data = json.loads(call_args.kwargs.get("data", call_args[1].get("data", "")))
        self.assertEqual(sent_data["name"], "test_tmpl_insert")
        self.assertEqual(sent_data["language"], "en")
        self.assertEqual(sent_data["category"], "TRANSACTIONAL")
        self.assertTrue(any(c["type"] == "BODY" for c in sent_data["components"]))

    @patch("frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.make_post_request")
    def test_after_insert_with_footer(self, mock_post):
        """Test template creation includes footer in components."""
        mock_post.return_value = {"id": "tmpl_footer_id", "status": "PENDING"}

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_footer",
            "template": "Body text",
            "footer": "Reply STOP to opt out",
            "category": "MARKETING",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.insert(ignore_permissions=True)

        call_args = mock_post.call_args
        sent_data = json.loads(call_args.kwargs.get("data", call_args[1].get("data", "")))
        footer_components = [c for c in sent_data["components"] if c["type"] == "FOOTER"]
        self.assertEqual(len(footer_components), 1)
        self.assertEqual(footer_components[0]["text"], "Reply STOP to opt out")

    @patch("frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates.make_post_request")
    def test_after_insert_with_buttons(self, mock_post):
        """Test template creation includes buttons."""
        mock_post.return_value = {"id": "tmpl_btn_id", "status": "PENDING"}

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_buttons",
            "template": "Click below",
            "category": "TRANSACTIONAL",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.append("buttons", {
            "button_type": "Quick Reply",
            "button_label": "Yes",
        })
        doc.append("buttons", {
            "button_type": "Visit Website",
            "button_label": "Visit",
            "website_url": "https://example.com",
            "url_type": "Static",
        })
        doc.insert(ignore_permissions=True)

        call_args = mock_post.call_args
        sent_data = json.loads(call_args.kwargs.get("data", call_args[1].get("data", "")))
        button_components = [c for c in sent_data["components"] if c["type"] == "BUTTONS"]
        self.assertEqual(len(button_components), 1)
        buttons = button_components[0]["buttons"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["type"], "QUICK_REPLY")
        self.assertEqual(buttons[1]["type"], "URL")

    @patch(f"{TEMPLATE_MODULE}.make_post_request")
    @patch(f"{TEMPLATE_MODULE}.make_request")
    def test_on_trash_does_not_call_meta(self, mock_request, mock_post):
        """REGRESSION: on_trash must NOT call Meta API (local delete only)."""
        mock_post.return_value = {"id": "tmpl_trash_id", "status": "PENDING"}

        doc = frappe.get_doc({
            "doctype": "WhatsApp Templates",
            "template_name": "test_tmpl_trash",
            "template": "Delete me",
            "category": "TRANSACTIONAL",
            "language": frappe.db.get_value("Language", {"language_code": "en"}) or "en",
            "language_code": "en",
            "whatsapp_account": "Test WA Tmpl Account",
        })
        doc.insert(ignore_permissions=True)

        mock_request.reset_mock()
        doc.delete()

        # on_trash should NOT have called Meta's DELETE API
        for call in mock_request.call_args_list:
            if call[0] and call[0][0] == "DELETE":
                self.fail("on_trash should NOT call Meta DELETE API")

    @patch(f"{TEMPLATE_MODULE}.get_account_credentials")
    @patch(f"{TEMPLATE_MODULE}._fetch_all_pages")
    def test_fetch_templates_from_meta(self, mock_fetch_pages, mock_creds):
        """Test the fetch whitelisted function."""
        mock_creds.return_value = {"url": "https://graph.facebook.com", "version": "v17.0",
                                   "business_id": "bid", "headers": {}, "token": "t", "app_id": "a"}
        mock_fetch_pages.return_value = [
            {
                "name": "test_tmpl_fetched",
                "status": "APPROVED",
                "language": "en",
                "category": "UTILITY",
                "id": "fetched_tmpl_id",
                "components": [
                    {"type": "BODY", "text": "Hello {{1}}, your order is ready"},
                    {"type": "FOOTER", "text": "Thank you"},
                ]
            }
        ]

        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import fetch
        result = fetch()
        self.assertEqual(result, "Successfully synced templates from Meta")

    def test_upsert_doc_without_hooks(self):
        """Test upsert_doc_without_hooks inserts and updates correctly."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import upsert_doc_without_hooks

        doc = self._make_template_without_hooks(template_name="test_tmpl_upsert")

        # Update template text
        doc.template = "Updated body text"
        upsert_doc_without_hooks(doc, "WhatsApp Button", "buttons")

        doc.reload()
        self.assertEqual(doc.template, "Updated body text")

    # --- delete_from_meta tests ---

    @patch(f"{TEMPLATE_MODULE}.make_request")
    def test_delete_from_meta_success(self, mock_request):
        """delete_from_meta: success path deletes from Meta and locally."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import delete_from_meta

        doc = self._make_template_without_hooks(template_name="test_tmpl_del_ok")
        mock_request.return_value = {}

        result = delete_from_meta(doc.name)

        self.assertEqual(result["status"], "success")
        self.assertFalse(frappe.db.exists("WhatsApp Templates", doc.name))

    @patch(f"{TEMPLATE_MODULE}.make_request")
    def test_delete_from_meta_404(self, mock_request):
        """delete_from_meta: 404 means already gone on Meta, still trash locally."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import delete_from_meta

        doc = self._make_template_without_hooks(template_name="test_tmpl_del_404")

        response_mock = MagicMock()
        response_mock.status_code = 404
        response_mock.json.return_value = {"error": {"error_user_title": "Message Template Not Found"}}
        frappe.flags.integration_request = response_mock

        mock_request.side_effect = Exception("Not Found")

        result = delete_from_meta(doc.name)
        self.assertEqual(result["status"], "success")
        self.assertFalse(frappe.db.exists("WhatsApp Templates", doc.name))

    @patch(f"{TEMPLATE_MODULE}.make_request")
    def test_delete_from_meta_auth_failure(self, mock_request):
        """delete_from_meta: 401/403 shows reauth message, does NOT trash locally."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import delete_from_meta

        doc = self._make_template_without_hooks(template_name="test_tmpl_del_auth")

        response_mock = MagicMock()
        response_mock.status_code = 401
        response_mock.json.return_value = {"error": {"message": "Invalid token"}}
        frappe.flags.integration_request = response_mock

        mock_request.side_effect = Exception("Unauthorized")

        self.assertRaises(frappe.ValidationError, delete_from_meta, doc.name)
        # Template should still exist locally
        self.assertTrue(frappe.db.exists("WhatsApp Templates", doc.name))

    @patch(f"{TEMPLATE_MODULE}.make_request")
    def test_delete_from_meta_server_error(self, mock_request):
        """delete_from_meta: 5xx shows error, does NOT trash locally."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import delete_from_meta

        doc = self._make_template_without_hooks(template_name="test_tmpl_del_5xx")

        response_mock = MagicMock()
        response_mock.status_code = 500
        response_mock.json.return_value = {"error": {"message": "Internal Server Error"}}
        frappe.flags.integration_request = response_mock

        mock_request.side_effect = Exception("Server Error")

        self.assertRaises(frappe.ValidationError, delete_from_meta, doc.name)
        self.assertTrue(frappe.db.exists("WhatsApp Templates", doc.name))

    # --- fetch() tests ---

    @patch(f"{TEMPLATE_MODULE}.get_account_credentials")
    @patch(f"{TEMPLATE_MODULE}._fetch_all_pages")
    def test_fetch_multi_account(self, mock_fetch_pages, mock_creds):
        """fetch() syncs templates from all active accounts."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import fetch

        mock_creds.return_value = {"url": "https://graph.facebook.com", "version": "v17.0",
                                   "business_id": "bid", "headers": {}, "token": "t", "app_id": "a"}

        mock_fetch_pages.return_value = [
            {"name": "test_tmpl_multi", "status": "APPROVED", "language": "en",
             "category": "UTILITY", "id": "id1", "components": [{"type": "BODY", "text": "Hello"}]},
        ]

        result = fetch()
        self.assertIn("Successfully", result)

        # Both accounts should have the template
        self.assertTrue(frappe.db.exists("WhatsApp Templates",
                        {"actual_name": "test_tmpl_multi", "whatsapp_account": "Test WA Tmpl Account"}))
        self.assertTrue(frappe.db.exists("WhatsApp Templates",
                        {"actual_name": "test_tmpl_multi", "whatsapp_account": "Test WA Tmpl Account 2"}))

    @patch(f"{TEMPLATE_MODULE}.get_account_credentials")
    @patch(f"{TEMPLATE_MODULE}._fetch_all_pages")
    def test_fetch_partial_failure(self, mock_fetch_pages, mock_creds):
        """fetch() skips orphan cleanup for accounts whose API call failed."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import fetch

        # Pre-create a template for account 2
        self._make_template_without_hooks(
            template_name="test_tmpl_partial",
            whatsapp_account="Test WA Tmpl Account 2",
        )

        mock_creds.return_value = {"url": "https://graph.facebook.com", "version": "v17.0",
                                   "business_id": "bid", "headers": {}, "token": "t", "app_id": "a"}

        call_count = [0]
        def side_effect(creds):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"name": "test_tmpl_partial_new", "status": "APPROVED", "language": "en",
                         "category": "UTILITY", "id": "id1", "components": [{"type": "BODY", "text": "Hello"}]}]
            raise Exception("API failure for account 2")

        mock_fetch_pages.side_effect = side_effect

        fetch()

        # Template from account 2 should NOT be marked as orphan (account 2 failed)
        tmpl = frappe.db.get_value("WhatsApp Templates",
                                   {"actual_name": "test_tmpl_partial", "whatsapp_account": "Test WA Tmpl Account 2"},
                                   "status")
        self.assertEqual(tmpl, "APPROVED")

    @patch(f"{TEMPLATE_MODULE}.get_account_credentials")
    @patch(f"{TEMPLATE_MODULE}._fetch_all_pages")
    def test_fetch_marks_orphans(self, mock_fetch_pages, mock_creds):
        """fetch() marks templates not found on Meta as 'Deleted on Meta'."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import fetch

        # Pre-create a template that won't be returned by Meta
        orphan = self._make_template_without_hooks(template_name="test_tmpl_orphan")

        mock_creds.return_value = {"url": "https://graph.facebook.com", "version": "v17.0",
                                   "business_id": "bid", "headers": {}, "token": "t", "app_id": "a"}

        # Return a different template from Meta (orphan not included)
        mock_fetch_pages.return_value = [
            {"name": "test_tmpl_other", "status": "APPROVED", "language": "en",
             "category": "UTILITY", "id": "id_other", "components": [{"type": "BODY", "text": "Other"}]},
        ]

        fetch()

        orphan.reload()
        self.assertEqual(orphan.status, "Deleted on Meta")

    @patch(f"{TEMPLATE_MODULE}.get_account_credentials")
    @patch(f"{TEMPLATE_MODULE}._fetch_all_pages")
    def test_fetch_orphan_with_notification_logs_warning(self, mock_fetch_pages, mock_creds):
        """fetch() logs an error when an orphaned template is referenced by a notification."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import fetch

        orphan = self._make_template_without_hooks(template_name="test_tmpl_orphan_notif")

        # Create a WhatsApp Notification referencing this template
        if frappe.db.exists("DocType", "WhatsApp Notification"):
            notif_exists = frappe.db.exists("WhatsApp Notification", {"template": orphan.name})
            if not notif_exists:
                frappe.db.sql(
                    "INSERT INTO `tabWhatsApp Notification` (name, template, modified, modified_by, owner, creation, docstatus) "
                    "VALUES (%s, %s, NOW(), 'Administrator', 'Administrator', NOW(), 0)",
                    (f"test_notif_{orphan.name[:30]}", orphan.name),
                )
                frappe.db.commit()

        mock_creds.return_value = {"url": "https://graph.facebook.com", "version": "v17.0",
                                   "business_id": "bid", "headers": {}, "token": "t", "app_id": "a"}
        mock_fetch_pages.return_value = []

        error_count_before = frappe.db.count("Error Log", {"error": ["like", f"%{orphan.actual_name}%"]})

        fetch()

        error_count_after = frappe.db.count("Error Log", {"error": ["like", f"%{orphan.actual_name}%"]})
        self.assertGreater(error_count_after, error_count_before)

        # Clean up notification
        frappe.db.sql("DELETE FROM `tabWhatsApp Notification` WHERE name LIKE 'test_notif_%'")
        frappe.db.commit()

    @patch(f"{TEMPLATE_MODULE}.get_account_credentials")
    @patch(f"{TEMPLATE_MODULE}._fetch_all_pages")
    def test_fetch_account_scoped_upsert(self, mock_fetch_pages, mock_creds):
        """Same template name on different accounts creates separate docs."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import fetch

        mock_creds.return_value = {"url": "https://graph.facebook.com", "version": "v17.0",
                                   "business_id": "bid", "headers": {}, "token": "t", "app_id": "a"}
        mock_fetch_pages.return_value = [
            {"name": "test_tmpl_shared", "status": "APPROVED", "language": "en",
             "category": "UTILITY", "id": "id_shared", "components": [{"type": "BODY", "text": "Shared template"}]},
        ]

        fetch()

        # Should have two separate docs, one per account
        acct1 = frappe.db.exists("WhatsApp Templates",
                                 {"actual_name": "test_tmpl_shared", "whatsapp_account": "Test WA Tmpl Account"})
        acct2 = frappe.db.exists("WhatsApp Templates",
                                 {"actual_name": "test_tmpl_shared", "whatsapp_account": "Test WA Tmpl Account 2"})
        self.assertTrue(acct1)
        self.assertTrue(acct2)
        self.assertNotEqual(acct1, acct2)

    @patch(f"{TEMPLATE_MODULE}.make_request")
    def test_fetch_pagination(self, mock_request):
        """fetch() follows pagination cursors to get all templates."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import _fetch_all_pages

        creds = {
            "url": "https://graph.facebook.com",
            "version": "v17.0",
            "business_id": "bid",
            "headers": {"authorization": "Bearer test"},
        }

        call_count = [0]
        def side_effect(method, url, headers=None):
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "data": [{"name": "test_tmpl_page1", "status": "APPROVED", "language": "en",
                              "category": "UTILITY", "id": "p1", "components": []}],
                    "paging": {"next": "https://graph.facebook.com/v17.0/bid/message_templates?after=cursor1"},
                }
            return {
                "data": [{"name": "test_tmpl_page2", "status": "APPROVED", "language": "en",
                          "category": "UTILITY", "id": "p2", "components": []}],
            }

        mock_request.side_effect = side_effect
        templates = _fetch_all_pages(creds)

        self.assertEqual(len(templates), 2)
        self.assertEqual(templates[0]["name"], "test_tmpl_page1")
        self.assertEqual(templates[1]["name"], "test_tmpl_page2")
        self.assertEqual(call_count[0], 2)

    def test_get_account_credentials(self):
        """get_account_credentials returns correct structure."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import get_account_credentials

        creds = get_account_credentials("Test WA Tmpl Account")
        self.assertEqual(creds["url"], "https://graph.facebook.com")
        self.assertEqual(creds["version"], "v17.0")
        self.assertEqual(creds["business_id"], "tmpl_test_business_id")
        self.assertEqual(creds["app_id"], "tmpl_test_app_id")
        self.assertIn("authorization", creds["headers"])
        self.assertIn("Bearer", creds["headers"]["authorization"])

    @patch(f"{TEMPLATE_MODULE}.get_account_credentials")
    @patch(f"{TEMPLATE_MODULE}._fetch_all_pages")
    def test_fetch_sets_last_synced(self, mock_fetch_pages, mock_creds):
        """fetch() sets the last_synced timestamp on templates."""
        from frappe_whatsapp.frappe_whatsapp.doctype.whatsapp_templates.whatsapp_templates import fetch

        mock_creds.return_value = {"url": "https://graph.facebook.com", "version": "v17.0",
                                   "business_id": "bid", "headers": {}, "token": "t", "app_id": "a"}
        mock_fetch_pages.return_value = [
            {"name": "test_tmpl_synced", "status": "APPROVED", "language": "en",
             "category": "UTILITY", "id": "id_synced", "components": [{"type": "BODY", "text": "Synced"}]},
        ]

        fetch()

        last_synced = frappe.db.get_value("WhatsApp Templates",
                                          {"actual_name": "test_tmpl_synced", "whatsapp_account": "Test WA Tmpl Account"},
                                          "last_synced")
        self.assertIsNotNone(last_synced)
