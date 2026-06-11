# Noteval XML export — specification (v3 document / schema_version 3)

Canonical spec for a **machine-readable XML** artifact derived from the four markdown deliverables (`01`–`04`). This document is the **single source of truth** for export shape and field semantics; implement parsers/exporters against it.

**Inputs:** Read only the completed markdown under `noteval_extractor/output/<deal>_<date>/` — **`01_report_metadata.md`**, **`02_tranche_class_balances.md`**, **`03_interest_principal_waterfall.md`**. Optionally read **`04_extraction_summary.md`** for flags or validation metadata later; the core economics payload does **not** require **`04`**.

**Output:** One XML file per deal folder. **Filename (normative):** **`{deal_id}_{payment_date}.xml`** — same pattern as the output directory basename (e.g. folder `869358159_20260420` → file **`869358159_20260420.xml`**). **`deal_id`** and the calendar suffix are the same tokens used for `noteval_extractor/output/<deal_id>_<payment_date>/` (deal identifier + **YYYYMMDD** payment date from §1.1). Normalize **`01`** dates to **`YYYYMMDD`** for the filename; if the folder name already encodes the date, the exporter **should** match the folder suffix to avoid drift.

**Root element:** Use **`schema_version="3"`** for the baseline shape. Use **`schema_version="4"`** when tranche mapping is applied (`export_noteval_xml.py --map-tranches`): **`metadata`** includes **`deal_id`**, each **`<class>`** / **`<line>`** may carry **`moodystrancheid`**, **`map_tier`**, **`map_status`**, and optional **`trustee_tranche_name`** / **`map_message`** attributes.

**Deliverable 01 (mapping workflow):** When exporting with **`--map-tranches`**, the deal folder should contain **`01_report_metadata.xml`** (generated from **`01_report_metadata.md`** if needed). Combined export reads **`01`** from XML in that mode; metadata parsing lives in **`export_noteval_xml.py`**. **Schema 2** dropped **`<listings>`**; **schema 3** additionally omits **`metadata`** deal-level **`deal_isin`** / **`deal_cusip`**, and **`<line>`** under **`<identifiers>`** carries **only** **`isin`** and **`cusip`** attributes (omit each attribute when absent or **`N/A`**). **Schema 1** included **`<listings>`** and older identifier attributes.

---

## 1. Business rules (normative)

### 1.1 Payment date vs distribution date

For **note valuation / trustee payment** reports, **Payment date** and **Distribution date** describe the **same** business event (cash distribution / payment). See **`extraction-templates.md`** File **01** (*Payment date vs Distribution date*).

**XML:** Emit **one** element for this event:

| XML element / attribute | Source | Rule |
|-------------------------|--------|------|
| **`payment_date`** | **`01`** → **`### Key dates`** | Populate from **`Payment date`** **or** **`Distribution date`** when only one column is filled, or when both match. **Do not** emit two separate top-level calendar fields for the same event. |

**If both columns exist and differ:** Prefer **`Payment date`** as the value of **`payment_date`**, set attribute **`date_source="payment_date"`** (or `distribution_date` if you intentionally prefer the other), and include a short **`date_mismatch_note`** (or equivalent) so downstream knows the PDF showed two dates. This case should be rare for true noteval-style reports.

### 1.2 ISIN / CUSIP — tranche level from **`02`**

Per **`extraction-templates.md`** File **02**, **ISIN** and **CUSIP** for **security lines** are authored in **`### Tranche by listing`** when **`Multi-listing tranches?`** = **Y**; **`### Class balance table (primary)`** and **`### Distribution grid`** omit those columns.

**XML (schema 3):**

- **Source of truth** for tranche-line identifiers remains **`02`** — read from **`### Tranche by listing`** (group rows by **`Economic class`** / match to **`### Class balance table (primary)`** **`Class`**).
- **`<classes>`:** Each **`<class>`** may include **`<identifiers>`** when listing rows map to that class: one **`<line>`** per **`02`** listing row that has at least one of **`isin`** / **`cusip`** after normalizing **`N/A`**. **`<line>`** attributes are **only** **`isin`** and **`cusip`** (both optional). **Do not** emit **`cusip_line_id`**, **`listing_program`**, or other listing-table columns on **`<line>`** in schema **3**.
- **Do not** emit deal- or header-level **ISIN** / **CUSIP** from **`01`** **Document routing** in **`metadata`** for schema **3** (no **`deal_isin`** / **`deal_cusip`**).

---

## 2. XML document outline (schema 3)

```xml
<noteval_export schema_version="3">
  <metadata>...</metadata>
  <classes>...</classes>
  <valuation_fees>
    <fee main_category="..." sub_category="..." priority="..." amount_paid="..."/>
    <administrative_expenses_grid_total>...</administrative_expenses_grid_total>
  </valuation_fees>
</noteval_export>
```

### 2.1 `<metadata>` — from **`01`** (markdown or **`01_report_metadata.xml`**)

| Content | Source |
|---------|--------|
| **`deal_id`** (schema **4** only) | Folder basename / **`01`** XML **`deal_id`** — Moodys deal id (**`moodysdealid`**) |
| Deal / trust / series name | **`01`** **Deal / trust / series name** |
| Report title | **`01`** **Report title** (optional) |
| **`payment_date`** | **`01`** **Key dates** (see §1.1) |
| Determination date, record date, etc. | **`01`** as needed |
| Currency | **`01`** **Currency** (and/or **`02`** **Summary** if you align with template) |
| Trustee / administrator | **`01`** |

**Not in schema 3:** **`deal_isin`**, **`deal_cusip`** (and any other **`01`** document-routing identifier blobs).

### 2.2 `<classes>` — from **`02`** primary **+** identifiers from listing

One child per row in **`### Class balance table (primary)`** (economic **Class** grain).

Include at minimum: **printed class name**, **original / beginning / ending** principal balances as extracted, **interest rate**, **interest payment / payable**, **principal payment / payable**, **deferred interest**, **dividend** — mirror the **`02`** template columns you persist in markdown.

**Identifiers under each class:** For every **`Economic class`** in **`### Tranche by listing`** that maps to this **primary** **`Class`**, emit one **`<line>`** per row (same order as **`02`**) with **only** **`isin`** and **`cusip`** when present. Skip rows that would produce an empty **`<line>`** (both missing or **`N/A`**). If no lines remain, omit **`<identifiers>`** entirely.

**Tranche mapping (schema 4):** After **`map_tranches.py`** resolution, set **`moodystrancheid`** on **`<class>`** and each **`<line>`** when known. **Tier 1 — CUSIP present (always):** lookup **only** `[CDOnet_DL].CUSTOM_CDONET_TRANCHE_DATA` (via CUSIP…CUSIP9); **`map_tier="cusip"`**. No name fallback when a CUSIP was supplied but CDOnet has no hit. **Tier 2 — no CUSIP:** **`map_class`** / normalized class name ↔ `ems.noteval_tranche_mapping.trustee_tranche_name` → **`tranche_id`**; **`map_tier="name"`**. Add **`map_status`**, and optional **`trustee_tranche_name`** / **`map_message`**. Emit **`map_class`** on **`<class>`** (schema 3 and 4).

**Example:**

```xml
<class name="A">
  <original_balance>...</original_balance>
  <beginning_balance>...</beginning_balance>
  <ending_balance>...</ending_balance>
  <interest_rate>...</interest_rate>
  <interest_payment>...</interest_payment>
  <principal_payment>...</principal_payment>
  <identifiers>
    <line isin="isin1" cusip="cusip1"/>
    <line cusip="cusip2"/>
  </identifiers>
</class>
```

Paired **`<line>`** with both **isin** and **cusip** is **preferred** when the PDF provides both; otherwise emit whichever attributes exist.

### 2.3 `<valuation_fees>` — from **`03`**

**`<fee>` rows:** One child per data row in **`05_valuation_relevant_fees.md`** (or legacy **`03`** **`### Valuation-relevant fees`**): **Main category**, **Sub category** / legacy **`fee_type`**, **Amount paid**, and optional **`priority`**. **`05`** is rolled up by **Sub category** (summed **Amount paid**); **`priority`** is omitted (**—**) when multiple waterfall steps were combined. Line-level steps are in **`fee_mapping_report.md`** (see **`extraction-templates.md`** File **05**).

**`<administrative_expenses_grid_total>` (optional):** When **`03`** includes a populated **`### Administrative Expenses grid`** with a printed **Totals** / **Total …** (or equivalent aggregate) row in the grid’s **cash-paid** column (the same column named in **`### Column mapping`** as **Paid on the Distribution Date** / payment-on-distribution), emit **one** child element **under `<valuation_fees>`** whose text content is that **aggregate paid** amount — **normalized** per §3 (plain decimal string, no currency symbol, **no** thousands separators). This element is the **schedule total** from the admin / expense voucher grid (reference for fees), used downstream as the authoritative **total administrative expense** figure from the PDF even when individual **`### Valuation-relevant fees`** lines itemize components.

**Parsing:** Skip **`Sub Total`** rows; prefer the **last** body row whose first column indicates a grand **total** (e.g. contains **Total** / **Totals** but not a **Sub Total**-only label). If the grid is **N/A** or no total row is parseable, **omit** `<administrative_expenses_grid_total>`.

If **`### Valuation-relevant fees`** is **N/A** with no fee rows, emit no **`<fee>`** children; you may still emit **`<administrative_expenses_grid_total>`** when the grid supplies a total.

---

## 3. Data representation

- **Money:** Plain decimal strings **without** currency symbols in XML (e.g. `2514062.40`); currency lives in **`metadata`**.
- **N/A / blank:** Omit the element, use empty content, or use a documented sentinel — pick one convention and keep it stable in the exporter.
- **Character encoding:** UTF-8.

---

## 4. Validation and workflow

- Run **`validate_noteval.py`** on the deal folder **before** XML export so **`02`** / **`03`** conform to project checks (including **`### Valuation-relevant fees`** when applicable).
- Optional: XSD + golden-file tests per **`schema_version`**.

---

## 5. Changelog

| Version | Summary |
|---------|---------|
| **4** | **`metadata`** **`deal_id`**. **`<class>`** / **`<line>`** tranche mapping attributes (**`moodystrancheid`**, **`map_tier`**, **`map_status`**, …). Deliverable **`01_report_metadata.xml`**. Export flag **`--map-tranches`**. |
| **3** | No **`deal_isin`** / **`deal_cusip`** in **`metadata`**. **`<line>`** has **only** **`isin`** / **`cusip`** (no **`cusip_line_id`**, **`listing_program`**). Root **`schema_version="3"`**. Optional **`<administrative_expenses_grid_total>`** under **`<valuation_fees>`** (grid schedule total). |
| **2** | **`<listings>`** removed; identifiers under **`<class>`** only. **`schema_version="2"`**. |
| **1** | Initial spec: metadata (incl. deal-level IDs), **`classes`**, **`listings`**, **`valuation_fees`**. Filename **`{deal_id}_{payment_date}.xml`**. |

When you change this file in a breaking way, bump **`schema_version`** on the XML root and append a row above.
