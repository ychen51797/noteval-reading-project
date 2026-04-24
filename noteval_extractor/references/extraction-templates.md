# Note Valuation / Trustee Report — Extraction Output Templates

This file defines the **strict template** for each extraction output file produced from **note valuation**, **distribution**, **waterfall**, or related **trustee payment** PDFs. The extraction agent MUST follow these templates so outputs stay consistent, auditable, and (when implemented) machine-validatable.

## Template structure (applies to ALL output files)

Every output file has **three sections in this order**:

```markdown
# [Title]

## Extracted Data
(Structured tables and key-value pairs)

## Completeness Checklist
(Checkboxes for required data points)

## Source Text
(Raw text copied from `_chunks/` — label each block with PDF page number)
```

- **Extracted Data** — what downstream analysis or `read_noteval_*` reconciliation primarily reads.
- **Source Text** — safety net: verbatim chunk excerpts with **Page N** labels so nothing is “trust me.”

Use **stable table headers** below; do not rename columns (future `validate_noteval.py` may key off them).

---

## File 01: Report metadata

**Filename:** `01_report_metadata.md`  
**Source:** Cover or header of report, title block, determination / payment / distribution dates, deal identifiers.

```markdown
# Report Metadata

## Extracted Data

### Report identification
| Field | Value |
|-------|-------|
| Report title (as printed) | |
| Deal / trust / series name | |
| Reporting period (if stated) | |
| Report date / as-of (if stated) | |
| Trustee / administrator name | |

### Key dates
| Field | Value |
|-------|-------|
| Determination date | |
| Payment date | |
| Distribution date | |
| Record date (if stated) | |
| Other named dates (list) | |

> **Payment date vs Distribution date (business definition):** For CLO / trustee **payment and distribution reports**, **Payment date** and **Distribution date** are the **same** business event (cash distribution / payment to noteholders). Keep **both** template columns populated with that **one** date whenever the PDF gives a single anchor (e.g. **Payment Date**, **Next Payment:**, **distribution** on the same calendar day). Do not leave **`Distribution date`** as N/A while **`Payment date`** is filled unless the PDF explicitly shows two different dates (rare — explain in **Notes** / **Other named dates** if so).

> **Next Payment:** When the cover, title block, TOC, or section header prints **Next Payment:** (or **Next payment:**) followed by a date and no clearer **Payment Date** label exists, use that date for **both** **`Payment date`** and **`Distribution date`**. Note the source once in **Other named dates** if helpful.

### Document routing (if stated)
| Field | Value |
|-------|-------|
| ISIN (deal- or header-level, if printed) | |
| CUSIP (deal- or header-level, if printed) | |
| Other deal ID / series code (if printed; not an ISIN/CUSIP) | |
| Currency | |
| Page range covering this report (PDF pages) | |

## Completeness Checklist
- [ ] Report title captured exactly (or noted if unreadable OCR)
- [ ] At least one of: determination / payment / distribution date extracted (or N/A with reason); **`Payment date`** and **`Distribution date`** match by business definition unless the PDF shows two different dates (see **Key dates** blockquotes)
- [ ] Deal or trust name identified
- [ ] Trustee or paying agent identified (or N/A)
- [ ] Currency identified (or N/A)
- [ ] **ISIN** / **CUSIP** at deal or cover level when printed (or N/A); do not merge into one cell — use the two routing fields above

## Source Text
(Paste header/title/date lines from `_chunks/`; prefix each block with **Page N**)
```

---

## File 02: Tranche / class balances

**Filename:** `02_tranche_class_balances.md`  
**Source:** Note Valuation Report tables, class summary, certificate principal / notional lines, **any per-class distribution grid** the trustee prints (e.g. **“Distribution in US$”**, prior/current principal, interest paid — **any trustee**, not only Deutsche Bank), and **optional report-level payment totals** printed with or beneath those tables (e.g. voucher **Total amount payable**, distribution **grand total** — captured in **`### Summary`**, not **`01`**).

**There is no `03_` file.** Capture distribution-style grids in **`02`**: extend the primary class table, add **Supplementary lines**, and/or add a second table under **Extracted Data** (e.g. `### Distribution grid (if present)`) with stable columns and the same **Source Text** rules.

**Multi-listing (same economic tranche, several CUSIPs/programs):** When the PDF prints **Class A Notes** (or similar) under **Rule 144A**, **Reg S**, **Accredited Investor**, etc. with **different CUSIPs/ISINs**, use **both** (to avoid data loss): (**1**) **Primary** class balance table — **one row per economic tranche**, either **consolidated** amounts (sum of slices when appropriate) or the **lead** listing (state which in **Notes**); (**2**) **`### Tranche by listing (optional)`** — **one row per security line** (economic class + **listing / program** + identifier + amounts). Set **`07`** flag **Multi-listing tranches** to **Y** / **N** and add a **cross-check** (e.g. slice principal sum vs primary row / PDF total).

```markdown
# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | |
| Table name(s) as printed | |
| Currency | |
| Multi-listing tranches? | **Y** / **N** — **Y** if **`### Tranche by listing`** is used |
| Total payment / total amount payable (if stated) | |

> **Total payment / total amount payable (Summary only):** When the **same exhibit** as the class / voucher / distribution table prints a **single trustee aggregate** for the payment (e.g. *Total Payment*, *Total Amount Payable*, *Total Cash Distribution*, *Total distribution*, voucher **total line** summing **Total amount payable** across classes), capture it in **`Total payment / total amount payable (if stated)`** under **`### Summary`**. Use **N/A** when no such line exists. **Do not** copy a figure from **`04`** waterfall **unless** the PDF repeats that same total on the class / voucher page; if ambiguous, **N/A** and quote the line in **`02` Source Text**. **`Ending balance`** on class rows stays **principal only** — do not put this aggregate in the **Ending balance** column.

### Class balance table (primary)
| Class | ISIN | CUSIP | Original balance | Beginning balance | Interest payment | Interest payable | Principal payment | Principal payable | Deferred interest | Dividend | Ending balance | Notes |
|-------|------|-------|------------------|-------------------|------------------|------------------|-------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | | |

> **Interest payment vs Interest payable:** **`Interest payment`** = cash **paid** / distributed to the class for the period (labels vary: *interest paid*, *interest distribution*, *payment*, settled amount). **`Interest payable`** = amount **due** / **accrued** / contractually **payable** for the period. When the PDF prints **only** payable / due / accrued and **no** paid amount (or paid is genuinely zero while payable is positive), leave **`Interest payment`** **blank** or **`N/A`** / null — **do not** copy payable into payment. When the PDF prints **both**, fill **both**. Copying payable → payment is allowed **only** when the report clearly uses one figure for both concepts (say so once in **Notes**).

> **Principal payment vs Principal payable:** **`Principal payment`** = principal actually **paid** / distributed this period. **`Principal payable`** = principal **due** / scheduled / contractually payable. When the PDF shows **only** principal payable and **no** principal paid (or paid is blank while payable is populated), leave **`Principal payment`** **blank** or **`N/A`** / null — **do not** fabricate paid from payable. When **both** exist, fill **both**.

> **Beginning balance and Ending balance (principal):** Copy **Beginning balance** and **Ending balance** **exactly** from the trustee’s printed class / summary row (labels vary: *prior / current*, *beginning / ending*, *outstanding*, *principal balance*, etc.). **Do not** recompute, adjust, or “correct” **Ending balance** from other columns (e.g. beginning ± principal paid ± interest). If printed columns do not arithmetic-tie, keep the trustee figures and explain once in **Notes** — the **Ending balance** cell must reflect the **report**, not a derived value.

> **Identifiers — ISIN vs CUSIP:** Use **two columns** so downstream loads map cleanly (nullable per identifier). **ISIN:** typically **12** characters (often starts with a **2-letter** country code, e.g. `XS…`, `US…`). **CUSIP:** **9** alphanumeric characters (North American issues). When the PDF prints only one identifier, put it in the correct column and leave the other **blank** (do not duplicate the same value in both). If the report prints a **combined** label (e.g. “ISIN/CUSIP”) or an ambiguous string, use **Notes** once and place the value in the column that matches length/format; if truly ambiguous, prefer **CUSIP** for 9-char US-style IDs and **ISIN** for 12-char IDs. Include **Original balance** when the report shows original face / original principal / “orig” balance (Deutsche and U.S. Bank note-valuation layouts often do); otherwise leave blank or `N/A` once per row or section in **Notes**. If the PDF does not show a column (e.g. no dividend or no deferred-interest line), leave that cell blank or `N/A` and say so once in **Notes** for that row or section.
>
> **Deferred interest:** Map the trustee’s **deferred interest** for each class from the class / NVR table — labels vary (**Interest Deferred Payable**, **Deferred Interest**, **Default / Deferred Interest Payable**, combined PIK columns, etc.). Use **one** column (**Deferred interest**) for the amount the PDF attributes to deferred interest on that tranche; if the report prints **two** deferred-style columns, choose the cell that matches the heading for *interest* deferred (or document both in **Notes** with a single primary cell). **Issuer-level or aggregate** deferred (not on a class row) — add **`### Supplementary lines`** entries or **Notes** under **`02`**; there is **no** separate **`05`** deliverable.
>
> **Balances and amounts:** Use plain numeric cells (no embedded `(N)` in the number). Put IO / notional / structural commentary in **Notes**. **Ending balance** stays **as printed** (see blockquote above).

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| | | |

### Distribution grid (optional — e.g. “Distribution in US$”, prior/current principal, interest paid)
> **Interest paid** / **Interest payable** and **Principal paid** / **Principal payable:** Same null rules as the primary class table — payable-only or paid-only columns are fine; leave the unused paid or payable cells blank / `N/A` rather than inferring.

| Class | ISIN | CUSIP | Prior principal balance | Current principal balance | Principal paid | Principal payable | Interest paid | Interest payable | Other columns (name + value) | Notes |
|-------|------|-------|------------------------|---------------------------|----------------|-------------------|----------------|------------------|------------------------------|-------|
| | | | | | | | | | | |

### Cross-checks (distribution grid, if used)
| Check | Value |
|-------|-------|
| Sum of principal paid (detail) | |
| Stated total (if any) | |
| Match? (Y/N / partial) | |

### Tranche by listing (optional — 144A / Reg S / AI / other programs)
Use when the **same economic class** appears on **multiple** trustee tables with **different CUSIPs/ISINs**. Keeps **one row per security listing**; the **primary** table above stays **one row per economic tranche** (consolidated or lead slice — say which in **Notes**).

| Economic class | Listing / program | ISIN | CUSIP | Original balance | Beginning balance | Interest payment | Interest payable | Principal payment | Principal payable | Deferred interest | Dividend | Ending balance | Notes |
|----------------|-------------------|------|-------|------------------|-------------------|------------------|------------------|-------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | | |

### Cross-checks (multi-listing, if used)
| Check | Result |
|-------|--------|
| Sum of principal (or notional) across listing rows vs primary tranche / PDF | |
| Match? (Y/N / partial) | |

## Completeness Checklist
- [ ] Every class row from the primary table captured (or explicitly listed as omitted with reason)
- [ ] **Class** with **ISIN** and/or **CUSIP** in the correct columns when printed (leave unused identifier blank)
- [ ] **Original balance** when the report prints it (or N/A with reason)
- [ ] **Beginning balance** and **Ending balance** taken **directly** from the report (or mapped label-for-label from prior/current principal columns) — **no** recomputed ending principal
- [ ] **Interest payment**, **Interest payable**, **Principal payment**, **Principal payable**, **Deferred interest** (per tranche, from the PDF class table — see column notes), and **dividend** captured when the report includes them (or blank / N/A with reason); **payment** cells may stay blank when the PDF is **payable-only** (do not infer paid from payable)
- [ ] Totals row matches sum of detail rows (or discrepancy noted)
- [ ] Optional **Distribution grid** filled or marked N/A when the PDF has a separate class-distribution page
- [ ] **Multi-listing:** if 144A / Reg S / AI (etc.) **slices** exist for the same class, **`### Tranche by listing`** filled **or** **N** with reason; **`07`** flag **Multi-listing tranches** matches
- [ ] **Total payment / total amount payable** in **`### Summary`** when the trustee prints a payment-period aggregate on the class / voucher / distribution exhibit (or **N/A** with reason)

## Source Text
(Paste full class table(s) from chunks; **Page N** per block — include **each** listing block used for **`### Tranche by listing`**)
```

---

### Deal layout families (proceeds / disbursements)

Reports differ in **how** they print cash application — not only by trustee name:

| Layout | What it looks like | Typical output |
|--------|--------------------|----------------|
| **Grid / table waterfall** | Named columns (Paid, Available, Running, Optimal, …) in a wide table | **`04_interest_principal_waterfall.md`** — **`### Waterfall table`** |
| **Indenture-style** | Legal **Section 11.1** (or similar) priority text, clause letters `(A)(B)…`, sometimes **two** currency amounts at the end of each line | **`04_interest_principal_waterfall.md`** — **`### Logical / clause waterfall`** |
| **Logical disbursement style** | “Application of … Proceeds”, `(i)`–`(v)` ladders, Computershare-style **two decimals per row** without full grid headers (see **`read_noteval_logical_disb`**) | **`04_interest_principal_waterfall.md`** — **`### Logical / clause waterfall`** |

A single deal can blend styles (e.g. indenture body + a small summary grid). Use the matching **`04`** subsection(s); say in **`07_extraction_summary.md`** whether the capture was **grid**, **logical/clause**, or **both**.

---

## File 04: Interest / principal waterfall

**Filename:** `04_interest_principal_waterfall.md`  
**Scope:** All **interest / principal proceeds application** belongs here: **multi-column grid waterfalls** *and* **logical / clause ladders** (indenture **Section 11.1**, Computershare **“Application of … Proceeds”**, `(i)`–`(v)` ladders with bare decimals — see **`read_noteval_logical_disb`**). **Do not** create **`06_logical_disbursements.md`** for new extractions; that file is **deprecated** (see **File 06**). If a deal prints **both** a grid and a clause ladder, use **both** subsections in **`04`**; avoid pasting the same **Source Text** twice — cross-reference in **Notes** and keep one full verbatim block.

**Source:** Waterfall tables, disbursement schedules, “Application of … Proceeds”, fee tables, Paid vs Available / Running — follow **this deal’s** labels.

```markdown
# Interest and Principal Waterfall

## Extracted Data

### Section identification
| Field | Value |
|-------|-------|
| Section title(s) as printed | |
| Funds type (interest / principal / combined) | |
| Layout in this file | **Grid only** / **Logical only** / **Both** |
| Section reference (if logical ladder, e.g. Section 11.1(a)(i)) | |

> **Two-number rows (Computershare and similar):** When a row shows **two** currency amounts with little or no column header (common **Computershare** pattern), treat the **left** number as **actual disbursed / settled** → **`Amount paid`** in **`### Waterfall table`**, or the primary **`Amount`** in **`### Disbursement ladder`** when that column represents paid flow. Put the **right** number in **`Amount available / running`**, a labeled **Other amount columns** cell if the PDF names it, or **Notes** if ambiguous — state once per section if needed.

> **Indenture-style three columns (e.g. U.S. Bank Payment Date Report / Section 11.1 grid):** When the PDF prints **Amount Due**, **Payment**, and **Running Balance** (or equivalent labels), map them to the template as: **Amount Due** → **`Amount payable`** (what is **due** under the priority for that line — accrued obligation or cap; **not** necessarily cash paid), **Payment** → **`Amount paid`** (cash **actually disbursed** from the account for that line), **Running Balance** → **`Amount available / running`** (remainder after the step). Prose references to **interest due** or **amounts due** align with **payable**; they may exceed **paid** when a line is partially paid or unpaid. Add a short **`### Column mapping`** under **`04`** for the deal when this layout applies.

### Waterfall table (grid / multi-column — when the PDF prints named columns)
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| | | | | | | |

> **Fee-style rows:** Prefer **amount paid** (or the column the trustee labels as paid/settled) over “remaining” or discretionary picks. If the report has multiple $ columns, name each column exactly as printed and map consistently across rows. **Computershare:** for a **two-number block** under paid-style semantics, the **left** value is **Amount paid** (see blockquote under **Section identification**).

### Logical / clause waterfall (optional — Section 11.1, Application of …, Computershare ladders)
Use when the PDF prints **prose / clause priority** instead of (or in addition to) a wide grid.

| Field | Value |
|-------|-------|
| Section present (Y/N) | |
| Section reference (e.g. Section 11.1(a)(i)) | |

### Disbursement ladder
| Clause / step | Item description | Amount | Notes |
|---------------|------------------|--------|-------|
| | | | |

### Continuations / sub-lines
| Parent clause | Continuation text | Amount | Notes |
|---------------|-------------------|--------|-------|
| | | | |

> Roll up indented / “first / second / third” continuations under the parent clause in **Item description** or **Notes** so each major line is one logical row. **Two trailing amounts:** use the **left** as disbursed **`Amount`** when that matches the trustee layout; mirror the **right** in **Notes** or a second amount column if you split them.

### Fees extracted separately (optional mirror)
| Fee name | Rate or basis (if stated) | Paid | Notes |
|----------|----------------------------|------|-------|
| | | | |

## Completeness Checklist
- [ ] **`### Waterfall table`** filled when a multi-column grid exists (or **N/A** with reason)
- [ ] **`### Logical / clause waterfall`** filled when Section 11.1 / Application of … / Computershare-style ladders exist (or **N/A** with reason)
- [ ] **Computershare-style two-number rows:** **left** = actual disbursed in **Amount paid** / ladder **Amount** (per **Section identification** note)
- [ ] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [ ] All fee lines that affect note valuation captured
- [ ] Subtotals / totals match detail or variance explained
- [ ] Determination / payment dates stated in this section if printed here

## Source Text
(Paste full waterfall / ladder section(s); **Page N** — one paste if grid and ladder overlap; otherwise separate blocks)
```

---

## File 06: Logical disbursements — **deprecated (use File 04)**

**Do not create `06_logical_disbursements.md` for new extractions.** Capture **Section 11.1**, **Application of Interest/Principal Proceeds**, Computershare **two-decimal** ladders, and clause `(i)`–`(v)` schedules in **`04_interest_principal_waterfall.md`** under **`### Logical / clause waterfall (optional)`**. Legacy deliverables may still include `06`; treat as superseded by **`04`**.

---

## File 07: Extraction summary

**Filename:** `07_extraction_summary.md`  
**Source:** Compiled from **`01`**, **`02`**, **`04`** (there is **no** `03_*.md` or **`05_*.md`** deliverable; **`06`** is deprecated — see **File 06**).

```markdown
# Extraction Summary

## Extracted Data

### Deal / report overview
| Field | Value |
|-------|-------|
| Deal name | |
| Payment / distribution date | |
| Currency | |

### Key counts
| Item | Count |
|------|-------|
| Classes in 02 | |
| Grid waterfall lines in 04 | |
| Logical / clause ladder rows in 04 | |
| Fee rows (approx) | |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | | **Y** when a **Distribution in US$** (or similar) grid is folded into **`02`**; **N** if absent |
| Multi-listing tranches? | | **Y** when the same **economic** class appears under **multiple programs** (e.g. 144A / Reg S) with **different ISINs and/or CUSIPs** — see **`02`** **`### Tranche by listing`**; **N** if one listing only |
| Has grid-style waterfall in `04`? | | |
| Has logical / clause ladder in `04` (11.1, Computershare, etc.)? | | |
| Deferred interest / supplementary deferred lines captured in `02` when printed? | | |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | |
| Multi-listing: sum of **Tranche by listing** vs primary **`02`** / PDF (if **Y**) | |
| Waterfall paid totals vs class/distribution totals in `02` (if comparable) | |
| Internal consistency (dates same across files) | |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | |
| 02_tranche_class_balances.md | |
| 04_interest_principal_waterfall.md | |
| 06_logical_disbursements.md (legacy only) | |

## Completeness Checklist
- [ ] All applicable files **01**, **02**, **04** exist or N/A documented here (no `03`, no **`05`**; **06** not required — deprecated)
- [ ] Counts and flags match body extractions
- [ ] Cross-checks run; discrepancies explained in **Notes**

## Source Text
(Optional: only if you need to attach a global cover snippet; otherwise “See per-file Source Text.”)
```

---

## Agent metadata block (optional first lines)

You may prepend this YAML block **above** the `# Title` in any file for tooling:

```yaml
---
source_pdf: "<path>"
extraction_target: "<file purpose>"
pdf_pages_used: "<e.g. 12-18>"
extracted_at: "<ISO-8601>"
---
```

Do not let this block replace the required **Extracted Data / Completeness Checklist / Source Text** sections.
