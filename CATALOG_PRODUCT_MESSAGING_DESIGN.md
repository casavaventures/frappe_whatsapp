# System Design: WhatsApp Catalog Product Messaging

## Objective

Enable sending product advertisements from the synced WhatsApp Catalog to customers — using Single Product, Multi-Product, Catalog, and Catalog Template messages — by extending the existing Bulk WhatsApp Message and WhatsApp Message infrastructure.

---

## Current State

### What Exists

| Component | Status | How It Works |
|---|---|---|
| **WhatsApp Catalog** | Done | Syncs products from Meta via `GET /{catalog_id}/products`. Push edits back via `POST /{product_id}`. Stores: product_id, retailer_id, name, price, availability, inventory, images, etc. |
| **WhatsApp Templates** | Done | Syncs from Meta. Supports BODY/HEADER/FOOTER/BUTTONS components. Used by notifications and bulk. |
| **WhatsApp Message** | Done | Sends text, template, interactive (button/list), flow messages. `before_insert()` builds payload → `notify()` calls Meta API. Supports `body_param` JSON for template variables. |
| **WhatsApp Notification** | Done | Auto-triggers on DocType events or scheduler. Calls `send_template_message()` which builds payload from doc fields, handles attachments, dynamic button URLs. |
| **Bulk WhatsApp Message** | Done | Submittable doc. Queues one WhatsApp Message per recipient via `frappe.enqueue_doc()`. Supports: Individual recipients or Recipient List, Template with Common/Unique variables, Attach media, Progress tracking + retry failed. |
| **WhatsApp Recipient List** | Done | Import recipients from any DocType with filters. Stores mobile_number, recipient_name, recipient_data (JSON for template variables). |

### What's Missing

| Gap | Description |
|---|---|
| Product content types in WhatsApp Message | `product`, `product_list`, `catalog_message` not supported as content_type |
| Product fields on WhatsApp Message | No catalog link, product_retailer_id, product_sections fields |
| Product mode in Bulk WhatsApp Message | Bulk only supports `use_template` (template) mode — no product message mode |
| Product picker UI | No way to browse synced catalog and pick products when composing |
| MPM template support | Catalog template messages (for cold outreach) not handled in send_template() |

---

## WhatsApp Product Message Types (Meta API)

### 1. Single Product Message

Rich card with image, title, price, description from catalog. Requires 24hr window.

```json
{
  "messaging_product": "whatsapp",
  "to": "919876543210",
  "type": "interactive",
  "interactive": {
    "type": "product",
    "body": { "text": "Check out this product!" },
    "footer": { "text": "Tap to view details" },
    "action": {
      "catalog_id": "CATALOG_ID",
      "product_retailer_id": "SKU_123"
    }
  }
}
```

### 2. Multi-Product Message

Up to 30 products in up to 10 sections. Requires 24hr window.

```json
{
  "messaging_product": "whatsapp",
  "to": "919876543210",
  "type": "interactive",
  "interactive": {
    "type": "product_list",
    "header": { "type": "text", "text": "Our Top Picks" },
    "body": { "text": "Browse our featured products" },
    "footer": { "text": "Tap to view" },
    "action": {
      "catalog_id": "CATALOG_ID",
      "sections": [
        {
          "title": "New Arrivals",
          "product_items": [
            { "product_retailer_id": "SKU_001" },
            { "product_retailer_id": "SKU_002" }
          ]
        },
        {
          "title": "Best Sellers",
          "product_items": [
            { "product_retailer_id": "SKU_010" },
            { "product_retailer_id": "SKU_011" }
          ]
        }
      ]
    }
  }
}
```

### 3. Catalog Message

Entire catalog browsable in WhatsApp. Requires 24hr window.

```json
{
  "messaging_product": "whatsapp",
  "to": "919876543210",
  "type": "interactive",
  "interactive": {
    "type": "catalog_message",
    "body": { "text": "Browse our full catalog!" },
    "action": {
      "name": "catalog_message",
      "parameters": {
        "thumbnail_product_retailer_id": "SKU_FEATURED"
      }
    }
  }
}
```

### 4. Catalog Template Message (MPM Template)

Pre-approved template with product sections. **No 24hr window required** — this is the key for mass advertising.

```json
{
  "messaging_product": "whatsapp",
  "to": "919876543210",
  "type": "template",
  "template": {
    "name": "intro_catalog_offer",
    "language": { "code": "en" },
    "components": [
      {
        "type": "body",
        "parameters": [
          { "type": "text", "text": "Summer Sale" }
        ]
      },
      {
        "type": "button",
        "sub_type": "mpm",
        "index": 0,
        "parameters": [
          {
            "type": "action",
            "action": {
              "thumbnail_product_retailer_id": "SKU_FEATURED",
              "sections": [
                {
                  "title": "On Sale",
                  "product_items": [
                    { "product_retailer_id": "SKU_001" },
                    { "product_retailer_id": "SKU_002" }
                  ]
                }
              ]
            }
          }
        ]
      }
    ]
  }
}
```

---

## Implementation Plan

### Phase 1: Extend WhatsApp Message (Core Sending)

#### 1.1 Add fields to `WhatsApp Message` DocType

| New Field | Type | Depends On | Description |
|---|---|---|---|
| catalog | Link → WhatsApp Catalog | `content_type in (product, product_list, catalog_message)` | Source catalog |
| product_retailer_id | Data | `content_type == product` | Single product retailer ID |
| product_sections | Code (JSON) | `content_type == product_list` | Sections array for multi-product |
| thumbnail_product_retailer_id | Data | `content_type == catalog_message` | Featured product thumbnail |
| header | Data | `content_type == product_list` | Header text for product list |
| footer | Data | `content_type in (product, product_list)` | Footer text |

Add to `content_type` Select options: `product`, `product_list`, `catalog_message`

#### 1.2 Add send methods to `whatsapp_message.py`

In `before_insert()`, add routing for new content types:

```python
elif self.content_type == "product":
    self._send_single_product()
elif self.content_type == "product_list":
    self._send_multi_product()
elif self.content_type == "catalog_message":
    self._send_catalog_message()
```

Each method builds the correct Meta API payload (as shown above) and calls `self.notify(data)`.

#### 1.3 Add MPM support to `send_template()`

When a template has an MPM button and `product_sections` is set on the message:

```python
# In send_template(), after existing button handling:
if self.product_sections:
    sections = json.loads(self.product_sections)
    data["template"]["components"].append({
        "type": "button",
        "sub_type": "mpm",
        "index": mpm_button_index,
        "parameters": [{
            "type": "action",
            "action": {
                "thumbnail_product_retailer_id": self.thumbnail_product_retailer_id or "",
                "sections": sections,
            }
        }]
    })
```

---

### Phase 2: Extend Bulk WhatsApp Message

The existing Bulk WhatsApp Message already handles:
- Recipients (Individual table or Recipient List link)
- Queueing (`frappe.enqueue_doc` per recipient)
- Progress tracking (`get_progress()`)
- Retry failed (`retry_failed()`)
- Template variables (Common/Unique via `body_param`)
- Status management (Draft → Queued → In Progress → Completed/Partially Failed)
- Scheduled time

#### 2.1 Add fields to `Bulk WhatsApp Message` DocType

| New Field | Type | Depends On | Description |
|---|---|---|---|
| message_mode | Select | — | Options: `Template`, `Product`, `Product List`, `Catalog`, `Catalog Template`. Replaces `use_template` check. |
| catalog | Link → WhatsApp Catalog | `message_mode in (Product, Product List, Catalog, Catalog Template)` | Source catalog |
| product_retailer_id | Data | `message_mode == Product` | Single product to send |
| product_sections | Code (JSON) | `message_mode in (Product List, Catalog Template)` | Sections with products |
| thumbnail_product_retailer_id | Data | `message_mode in (Catalog, Catalog Template)` | Featured product |
| body_text | Small Text | `message_mode in (Product, Product List, Catalog)` | Body text for interactive messages |
| header_text | Data | `message_mode == Product List` | Header for multi-product |
| footer_text | Data | `message_mode in (Product, Product List)` | Footer text |

#### 2.2 Update `create_single_message()` in `bulk_whatsapp_message.py`

Currently it creates a WhatsApp Message with `message_type = "Template"` or `"Text"`. Extend to handle product modes:

```python
def create_single_message(self, recipient):
    wa_message = frappe.new_doc("WhatsApp Message")
    wa_message.to = recipient.get("mobile_number")
    wa_message.bulk_message_reference = self.name

    if self.whatsapp_account:
        wa_message.whatsapp_account = self.whatsapp_account

    if self.message_mode == "Template":
        # Existing template logic (unchanged)
        wa_message.message_type = "Template"
        wa_message.template = self.template
        wa_message.content_type = "text"
        if recipient.get("recipient_data") and self.variable_type == "Unique":
            wa_message.body_param = recipient.get("recipient_data")
        elif self.template_variables and self.variable_type == "Common":
            wa_message.body_param = self.template_variables
        if self.attach:
            wa_message.attach = self.attach

    elif self.message_mode == "Product":
        wa_message.message_type = "Manual"
        wa_message.content_type = "product"
        wa_message.catalog = self.catalog
        wa_message.product_retailer_id = self.product_retailer_id
        wa_message.message = self.body_text or ""
        wa_message.footer = self.footer_text or ""

    elif self.message_mode == "Product List":
        wa_message.message_type = "Manual"
        wa_message.content_type = "product_list"
        wa_message.catalog = self.catalog
        wa_message.product_sections = self.product_sections
        wa_message.header = self.header_text or "Products"
        wa_message.message = self.body_text or ""
        wa_message.footer = self.footer_text or ""

    elif self.message_mode == "Catalog":
        wa_message.message_type = "Manual"
        wa_message.content_type = "catalog_message"
        wa_message.catalog = self.catalog
        wa_message.thumbnail_product_retailer_id = self.thumbnail_product_retailer_id or ""
        wa_message.message = self.body_text or ""

    elif self.message_mode == "Catalog Template":
        # Template + MPM product sections
        wa_message.message_type = "Template"
        wa_message.template = self.template
        wa_message.content_type = "text"
        wa_message.product_sections = self.product_sections
        wa_message.thumbnail_product_retailer_id = self.thumbnail_product_retailer_id or ""
        if recipient.get("recipient_data") and self.variable_type == "Unique":
            wa_message.body_param = recipient.get("recipient_data")
        elif self.template_variables and self.variable_type == "Common":
            wa_message.body_param = self.template_variables

    wa_message.status = "Queued"
    wa_message.insert(ignore_permissions=True)
```

#### 2.3 Update Bulk WhatsApp Message JS

Show/hide fields based on `message_mode`:

```javascript
frappe.ui.form.on('Bulk WhatsApp Message', {
    message_mode(frm) {
        // Template mode: show template, variable_type, template_variables, attach
        // Product mode: show catalog, product_retailer_id, body_text, footer_text
        // Product List mode: show catalog, product_sections, header_text, body_text, footer_text
        // Catalog mode: show catalog, thumbnail_product_retailer_id, body_text
        // Catalog Template mode: show template + catalog + product_sections + thumbnail
    }
});
```

---

### Phase 3: Product Picker UI

#### 3.1 Product Picker Dialog (`public/js/product_picker.js`)

A reusable dialog to browse synced catalog and pick products:

```
┌─────────────────────────────────────────────┐
│  Select Products from Catalog               │
├─────────────────────────────────────────────┤
│  Catalog: [WhatsApp Catalog ▾]              │
│  Search:  [____________] [🔍]              │
│                                             │
│  ☑ SKU_001  iPhone 15 Pro       ₹1,29,900  │
│  ☑ SKU_002  Samsung Galaxy S24  ₹89,999    │
│  ☐ SKU_003  Pixel 9             ₹79,999    │
│  ☑ SKU_010  MacBook Air M3      ₹1,14,900  │
│                                             │
│  Selected: 3 products                       │
│                                             │
│  [Cancel]                  [Add Products]   │
└─────────────────────────────────────────────┘
```

```javascript
frappe.whatsapp = frappe.whatsapp || {};

frappe.whatsapp.pick_products = function({ catalog, multi, callback }) {
    // 1. Fetch products: frappe.call → get WhatsApp Catalog Item children
    // 2. Render checkable list with search filter
    // 3. On "Add Products", callback([{ product_retailer_id, product_name, price }])
};
```

#### 3.2 Section Builder Dialog (for Multi-Product / MPM Template)

```
┌─────────────────────────────────────────────┐
│  Build Product Sections                     │
├─────────────────────────────────────────────┤
│  Section 1: [New Arrivals___________] [×]  │
│    • SKU_001 iPhone 15 Pro                  │
│    • SKU_002 Samsung S24                    │
│    [+ Add Products]                         │
│                                             │
│  Section 2: [Best Sellers___________] [×]  │
│    • SKU_010 MacBook Air                    │
│    [+ Add Products]                         │
│                                             │
│  [+ Add Section]                            │
│                                             │
│  [Cancel]               [Save Sections]     │
└─────────────────────────────────────────────┘
```

Outputs JSON:
```json
[
  {
    "title": "New Arrivals",
    "product_items": [
      { "product_retailer_id": "SKU_001" },
      { "product_retailer_id": "SKU_002" }
    ]
  },
  {
    "title": "Best Sellers",
    "product_items": [
      { "product_retailer_id": "SKU_010" }
    ]
  }
]
```

#### 3.3 Integration Points

Add "Pick Products" buttons to:
- WhatsApp Message form (when content_type is product/product_list/catalog_message)
- Bulk WhatsApp Message form (when message_mode involves products)

---

### Phase 4: Extend WhatsApp Notification for MPM Templates

#### 4.1 Add fields to `WhatsApp Notification` DocType

| New Field | Type | Description |
|---|---|---|
| product_sections | Code (JSON) | Default product sections for catalog template |
| thumbnail_product_retailer_id | Data | Featured product for MPM thumbnail |

#### 4.2 Update `send_template_message()` in `whatsapp_notification.py`

After existing button handling (line ~226), add MPM support:

```python
# Append MPM component if product_sections is configured
if self.product_sections:
    sections = json.loads(self.product_sections)
    data["template"]["components"].append({
        "type": "button",
        "sub_type": "mpm",
        "index": 0,
        "parameters": [{
            "type": "action",
            "action": {
                "thumbnail_product_retailer_id": self.thumbnail_product_retailer_id or "",
                "sections": sections,
            }
        }]
    })
```

This lets DocType event notifications (e.g., "When Sales Order is submitted, send catalog template to customer") include product recommendations.

---

## Data Flow

```
┌──────────────────┐
│  Meta Commerce   │
│  Manager         │
└────────┬─────────┘
         │ Sync (GET /{catalog_id}/products)
         ▼
┌──────────────────┐       Push edits
│  WhatsApp        │◄───── (POST /{product_id})
│  Catalog         │
│  (Frappe)        │
└────────┬─────────┘
         │ Product data (retailer_id, catalog_id)
         │
         ├──────────────────────────────────────────┐
         ▼                                          ▼
┌──────────────────────┐              ┌──────────────────────┐
│  WhatsApp Message    │              │  Bulk WhatsApp       │
│  (Single send)       │              │  Message             │
│                      │              │                      │
│  content_type:       │              │  message_mode:       │
│  • product           │              │  • Template          │
│  • product_list      │              │  • Product           │
│  • catalog_message   │              │  • Product List      │
│  • text (MPM tmpl)   │              │  • Catalog           │
└──────────┬───────────┘              │  • Catalog Template  │
           │                          └──────────┬───────────┘
           │                   Creates 1 WhatsApp │
           │                   Message per        │
           │                   recipient          │
           ▼                          ▼
┌─────────────────────────────────────────────────┐
│             Meta WhatsApp Cloud API             │
│        POST /{phone_id}/messages                │
│                                                 │
│  • type: interactive / product                  │
│  • type: interactive / product_list             │
│  • type: interactive / catalog_message          │
│  • type: template (with MPM button component)   │
└─────────────────────────────────────────────────┘
                         │
                         ▼
               ┌──────────────────┐
               │  Customer's      │
               │  WhatsApp        │
               └──────────────────┘
```

---

## Key Constraints

| Constraint | Detail |
|---|---|
| **24-hour window** | Interactive messages (`product`, `product_list`, `catalog_message`) can ONLY be sent within 24hrs of last customer message. For cold outreach, use **Catalog Template (MPM)**. |
| **Max 30 products** | Multi-product messages: max 30 items across max 10 sections |
| **Max 1 catalog per WABA** | Only one catalog per WhatsApp Business Account |
| **`catalog_management` permission** | Token must have this scope for product sync/push |
| **Product must be approved** | Only `review_status = approved` products can be sent |
| **Catalog must be visible** | `is_catalog_visible` must be enabled for catalog messages |
| **Template approval** | Catalog templates (MPM) need Meta approval before sending |

---

## API Permissions Required

| Permission | Purpose |
|---|---|
| `whatsapp_business_messaging` | Send all message types |
| `whatsapp_business_management` | Manage templates, account settings |
| `catalog_management` | Sync products, push updates |

All three must be on the same System User token.

---

## Which Message Type to Use When

| Scenario | Message Type | 24hr Window? |
|---|---|---|
| Customer asks about a product in chat | Single Product | Yes (within conversation) |
| Share curated collection during conversation | Multi-Product | Yes (within conversation) |
| Let customer browse full catalog in chat | Catalog Message | Yes (within conversation) |
| **Mass advertising to all customers** | **Catalog Template (MPM)** via Bulk | **No** |
| **Promotional campaign to customer segment** | **Catalog Template (MPM)** via Bulk | **No** |
| Auto-send products on Sales Order creation | Catalog Template via Notification | **No** |

**For bulk advertising, always use Catalog Template (MPM)** — it's the only type that works outside the 24-hour window and it flows through the existing Bulk WhatsApp Message infrastructure.

---

## References

- [WhatsApp Cloud API Messages Reference](https://developers.facebook.com/docs/whatsapp/cloud-api/reference/messages/)
- [Sell Products & Services Guide](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/sell-products-and-services/)
- [Catalog Templates](https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates/catalog-templates/)
- [Product Catalog API](https://developers.facebook.com/docs/marketing-api/reference/product-catalog/products/)
- [Commerce Settings API](https://developers.facebook.com/docs/whatsapp/cloud-api/guides/sell-products-and-services/set-commerce-settings/)
