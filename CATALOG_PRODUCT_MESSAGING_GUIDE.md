# WhatsApp Catalog & Product Messaging — User Guide

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Setting Up the Catalog](#setting-up-the-catalog)
3. [Syncing Products from Meta](#syncing-products-from-meta)
4. [Editing & Pushing Products Back to Meta](#editing--pushing-products-back-to-meta)
5. [Sending Product Messages](#sending-product-messages)
   - [Single Product Message](#single-product-message)
   - [Multi-Product Message](#multi-product-message)
   - [Catalog Message](#catalog-message)
   - [Catalog Template (MPM) — For Bulk Advertising](#catalog-template-mpm--for-bulk-advertising)
6. [Bulk Product Messaging](#bulk-product-messaging)
7. [Automated Product Notifications](#automated-product-notifications)
8. [Product Picker UI](#product-picker-ui)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

Before using catalog and product messaging features, ensure:

1. **WhatsApp Account** is configured and Active in Frappe (`WhatsApp Account` DocType)
2. **Meta System User Token** has these permissions:
   - `whatsapp_business_messaging` — send messages
   - `whatsapp_business_management` — manage templates
   - `catalog_management` — sync/push product catalog data
3. **Product Catalog** exists in Meta Commerce Manager with products added
4. **Catalog ID** is noted from Meta Commerce Manager > Your Catalog > Settings

### How to Add `catalog_management` Permission

1. Go to **Meta Business Suite > Settings > Business Settings**
2. Navigate to **Users > System Users**
3. Select your System User and click **Generate New Token**
4. Select your App and add **catalog_management** along with existing permissions
5. Copy the new token and update it in your **WhatsApp Account** settings in Frappe

---

## Setting Up the Catalog

### Step 1: Add Catalog ID to WhatsApp Account

1. Go to **WhatsApp Account** in Frappe
2. Scroll down to the **Catalog Settings** section
3. Enter your **Catalog ID** from Meta Commerce Manager
4. Save

> **Finding your Catalog ID:** In Meta Commerce Manager, go to your Catalog > Settings. The Catalog ID is displayed at the top.

---

## Syncing Products from Meta

### From the List View

1. Go to **WhatsApp Catalog** list
2. Click **Sync from Meta** button in the top-right
3. Wait for the sync to complete
4. A new catalog document will be created with all your products

### From an Existing Catalog Document

1. Open any **WhatsApp Catalog** document
2. Click **Sync from Meta** button
3. The catalog and all products will be refreshed from Meta

### What Gets Synced

The sync fetches all product data from Meta including:

| Field | Description |
|---|---|
| Product ID | Meta's internal product ID (read-only) |
| Retailer ID | Your SKU/product code (read-only) |
| Product Name | Display name |
| Price / Currency | Product price (converted from cents) |
| Sale Price | Discounted price with start/end dates |
| Availability | in stock / out of stock / available for order / discontinued |
| Condition | new / refurbished / used |
| Brand, Category, Product Type | Classification fields |
| Color, Size, Gender, Age Group, Material, Pattern | Product attributes |
| Inventory | Stock quantity |
| URLs | Product URL, image URL, additional image URLs |
| Description | Full product description |
| Visibility & Review Status | Meta's approval status (read-only) |

Commerce settings (catalog visibility, cart enabled) are also synced.

---

## Editing & Pushing Products Back to Meta

You can edit product data in Frappe and push changes back to Meta.

### Editing Products

1. Open a **WhatsApp Catalog** document
2. In the **Products** table, edit any field (name, price, description, availability, etc.)
3. Fields marked as **read-only** (Product ID, Retailer ID, Visibility, Review Status) cannot be edited — they are managed by Meta

### Pushing Changes to Meta

1. After editing, click **Actions > Push to Meta**
2. Confirm the action
3. Only **changed** products are sent to Meta — unchanged products are skipped
4. A summary shows how many products were updated and any errors

> **Price format:** Enter prices as decimal values (e.g., `15.00`). They are automatically converted to Meta's cents format (1500) when pushing.

---

## Sending Product Messages

Product messages can be sent from the **WhatsApp Message** DocType. There are 4 types:

### Single Product Message

Sends a rich product card with image, title, price, and description.

**Requires:** Active conversation (customer messaged within last 24 hours)

1. Create a new **WhatsApp Message**
2. Set **Type** = Outgoing, **Message Type** = Manual
3. Set **Content Type** = `product`
4. In **Product Settings**:
   - **Catalog**: Select your WhatsApp Catalog
   - **Product Retailer ID**: Enter the SKU, or click **Pick Product** to browse
5. Optionally set **Message** (body text) and **Footer**
6. Enter the recipient number in **TO** and save

### Multi-Product Message

Sends up to 30 products organized in sections (max 10 sections).

**Requires:** Active conversation (24-hour window)

1. Create a new **WhatsApp Message**
2. Set **Content Type** = `product_list`
3. In **Product Settings**:
   - **Catalog**: Select your catalog
   - **Product Header**: Header text (e.g., "Our Top Picks")
   - Click **Build Sections** to visually create sections and add products
4. Set **Message** (body text) and optional **Footer**
5. Save

### Catalog Message

Lets the customer browse your entire catalog inside WhatsApp.

**Requires:** Active conversation (24-hour window)

1. Create a new **WhatsApp Message**
2. Set **Content Type** = `catalog_message`
3. In **Product Settings**:
   - **Catalog**: Select your catalog
   - **Thumbnail Product Retailer ID**: Optional — pick a featured product via **Pick Product**
4. Set **Message** (body text)
5. Save

### Catalog Template (MPM) — For Bulk Advertising

This is the key message type for **mass advertising**. It uses a pre-approved template with embedded product sections. **No 24-hour window required.**

1. Create an MPM template in Meta Business Manager first
2. Sync templates in Frappe (**WhatsApp Templates > Sync from Meta**)
3. Create a new **WhatsApp Message**
4. Set **Message Type** = Template
5. Select the MPM **Template**
6. Set **Product Sections** (JSON) and **Thumbnail Product Retailer ID**
7. Save

> For bulk advertising, use the **Bulk WhatsApp Message** (see below).

---

## Bulk Product Messaging

The **Bulk WhatsApp Message** DocType now supports product messaging via the **Message Mode** field.

### Available Message Modes

| Mode | What It Sends | 24hr Window? | Best For |
|---|---|---|---|
| **Template** | Standard template message | No | General notifications |
| **Product** | Single product card | Yes | Active conversations |
| **Product List** | Multi-product with sections | Yes | Active conversations |
| **Catalog** | Full catalog browse | Yes | Active conversations |
| **Catalog Template** | Template + product sections (MPM) | **No** | **Mass advertising** |

### Sending a Bulk Product Campaign

#### For Mass Advertising (Catalog Template mode — recommended)

1. Go to **Bulk WhatsApp Message** > New
2. Set a **Title** (e.g., "Summer Sale 2026")
3. **Message Mode** = `Catalog Template`
4. **Recipients**: Add individual numbers or select a **Recipient List**
5. In the **Message** section:
   - Select your approved MPM **Template**
   - Set **Variable Type** and **Template Variables** if your template has parameters
6. In **Product Settings**:
   - **Catalog**: Select your catalog
   - Click **Product > Build Sections** to create product sections
   - Click **Product > Pick Thumbnail** to set the featured product
7. **Submit** to queue messages for sending

#### For Single Product Blast (Product mode)

1. **Message Mode** = `Product`
2. Set **Catalog** and click **Product > Pick Product** to select the product
3. Set **Body Text** and optional **Footer Text**
4. Submit

#### For Multi-Product Blast (Product List mode)

1. **Message Mode** = `Product List`
2. Set **Catalog** and click **Product > Build Sections**
3. Set **Body Text**, **Header Text**, and optional **Footer Text**
4. Submit

### Monitoring Progress

After submission:
- Click **Check Progress** to see sent/failed/queued counts with a progress bar
- Click **Retry Failed Messages** to requeue any failed messages

---

## Automated Product Notifications

Use **WhatsApp Notification** to automatically send product catalog messages when DocType events occur (e.g., when a Sales Order is submitted).

### Setting Up an MPM Notification

1. Go to **WhatsApp Notification** > New
2. Configure the trigger:
   - **Notification Type**: DocType Event
   - **Reference DocType**: e.g., Sales Order
   - **DocType Event**: e.g., After Submit
   - **Field Name**: The mobile number field on the DocType
3. Select your approved MPM **Template**
4. Set **Fields** for template parameters
5. Scroll to **Catalog Product Sections (MPM)**:
   - **Product Sections**: Enter the JSON sections array
   - **Thumbnail Product Retailer ID**: Set the featured product SKU
6. Set **Condition** if needed (e.g., `doc.grand_total > 1000`)
7. Save and enable

**Example:** Auto-send a catalog of recommended products when a customer's Sales Order is submitted:

```json
[
  {
    "title": "You May Also Like",
    "product_items": [
      { "product_retailer_id": "SKU_001" },
      { "product_retailer_id": "SKU_002" },
      { "product_retailer_id": "SKU_003" }
    ]
  }
]
```

---

## Product Picker UI

The product picker provides a visual way to select products instead of manually entering retailer IDs.

### Single Product Picker

Available when:
- WhatsApp Message: content_type = `product` or `catalog_message`
- Bulk WhatsApp Message: message_mode = `Product`

Click **Pick Product** (or **Pick Thumbnail**) to open a dialog where you can:
- Select a catalog
- Search products by name or retailer ID
- Click to select a product

### Section Builder

Available when:
- WhatsApp Message: content_type = `product_list`
- Bulk WhatsApp Message: message_mode = `Product List` or `Catalog Template`

Click **Build Sections** to open a dialog where you can:
- Add/remove sections (max 10)
- Name each section
- Add products to each section via the multi-product picker
- Remove individual products from sections
- See total product count (max 30)

The builder outputs the JSON directly into the Product Sections field.

---

## Troubleshooting

### "No Catalog ID configured"

**Cause:** The Catalog ID field is empty in your WhatsApp Account settings.

**Fix:** Go to WhatsApp Account > Catalog Settings > enter your Catalog ID from Meta Commerce Manager.

### "Missing catalog_management Permission"

**Cause:** Your WhatsApp API token doesn't have permission to access catalog data.

**Fix:** Generate a new System User token in Meta Business Manager with `catalog_management` permission added. Update the token in WhatsApp Account settings.

### "No changes detected. Nothing to push."

**Cause:** You clicked "Push to Meta" but no product fields were modified.

**Fix:** This is expected behavior. Only modified products are pushed. Edit some product data first, then push.

### Products not appearing in picker

**Cause:** Catalog hasn't been synced yet.

**Fix:** Click "Sync from Meta" on the WhatsApp Catalog to fetch products.

### Interactive product messages failing

**Cause:** Likely a 24-hour window issue — interactive messages (product, product_list, catalog_message) require the customer to have messaged within the last 24 hours.

**Fix:** Use **Catalog Template (MPM)** mode instead. It works without the 24-hour window restriction and is the recommended approach for advertising.

### MPM template message failing

**Cause:** The template may not be approved yet, or the product sections JSON is malformed.

**Fix:**
1. Ensure the template is approved in Meta Business Manager
2. Verify the product sections JSON format:
```json
[
  {
    "title": "Section Title",
    "product_items": [
      { "product_retailer_id": "YOUR_SKU" }
    ]
  }
]
```
3. Ensure all retailer IDs exist in your catalog and products are approved

### Price showing incorrectly after sync

**Cause:** Meta stores prices in cents (e.g., 1500 = $15.00).

**Fix:** The sync automatically converts cents to decimal. If prices look wrong, check the original values in Meta Commerce Manager.

---

## Quick Reference: Which Message Type to Use

| Scenario | Message Mode | 24hr Required? |
|---|---|---|
| Customer asks about a product in chat | Product | Yes |
| Share curated collection during conversation | Product List | Yes |
| Let customer browse full catalog | Catalog | Yes |
| **Mass advertising to all customers** | **Catalog Template** | **No** |
| **Promotional campaign to segment** | **Catalog Template** | **No** |
| Auto-send products on order creation | Notification + MPM | **No** |

**For bulk advertising, always use Catalog Template (MPM)** — it's the only type that works outside the 24-hour conversation window.
