# Note Valuation / Trustee Report — Extraction Output Templates

This file defines the **strict template** for each extraction output file produced from **note valuation**, **distribution**, **waterfall**, or related **trustee payment** PDFs. The extraction agent MUST follow these templates so outputs stay consistent, auditable, and (when implemented) machine-validatable.

**Deliverable set (four files, in order):** `01_report_metadata.md` → `02_tranche_class_balances.md` → `03_interest_principal_waterfall.md` → `04_extraction_summary.md`. Per-class distribution grids and deferred-interest lines stay in **`02`** (there is **no** standalone **`05_*.md`** distribution file). Deprecated: **`06_logical_disbursements.md`** — fold logical ladders into **`03`**.

**Workflow (not layout):** Very large PDFs (e.g. **300+** pages) still use **`_page_index.md`** plus targeted **`_chunks/`** reads. If the PDF has **no** tranche or waterfall content to extract, **`02`** / **`03`** may be **N/A** with clear **`04`** (summary) documentation — see **`noteval_extractor/SKILL.md`** (*Very large PDFs* and *No tranche or waterfall*).

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

**Multi-listing (same economic class, several printed lines / CUSIPs — e.g. **SUB** with **three** rows, or **144A** / **Reg S** / **AI** slices):** Use **both** layers so nothing is lost and class-level numbers stay auditable.

1. **`### Tranche by listing`** — **Mandatory whenever `Multi-listing tranches?` = Y:** **one row per printed security line** under that economic class (if the PDF shows **three** SUB lines, extract **three** listing rows). Each row needs a **unique `CUSIP line id`** (see blockquote under that heading). Copy amounts **verbatim** per line. Do **not** collapse multiple PDF lines into a single listing row to “simplify” for downstream; consumers that only need class subtotals should **sum in ETL** from listing (or read the primary row below).

2. **`### Class balance table (primary)`** — **One row per economic class** (e.g. one **SUB** row). Prefer the trustee’s **printed class / subtotal** for that class (e.g. **SUB** ending **47,950,000.00**) when the exhibit shows it — copy it **exactly**, do not recompute. If the PDF shows **only** slice lines and **no** printed combined row for the class, either: (**a**) populate primary **SUB** with **Notes** that balances are **derived** (e.g. “Ending = sum of `L001`–`L003`”), or (**b**) leave primary numeric cells blank / partial and point **Notes** to **`### Tranche by listing`** — state the convention once in **`04_extraction_summary.md`**. Do **not** use a random “lead” CUSIP row as the primary row when a printed **class total** exists.

3. **`### Cross-checks (multi-listing)`** — Sum of listing rows (principal / ending, as applicable) vs primary row and vs any **printed** PDF total; explain **partial** / **N** with reason.

4. **`### Summary`** — Set **Multi-listing tranches?** to **Y** if **any** economic class has **>1** listing row; **Rows in `### Tranche by listing`** = row count; **Max CUSIPs under one economic class label** = max over classes. **N** only when the captured exhibit is strictly **one CUSIP (or one line) per class label**.

**Computershare-style (same class label repeated on several CUSIP rows):** Same rules: **primary** = one row per **economic** class (trustee **printed** subtotal when shown, else derived with **Notes**); **listing** = **one row per CUSIP line** the PDF shows for that label, with **`Listing / program`** when printed else **`CUSIP slice`** / line ordinal. **`CUSIP line id`** is required on every listing row. See **Worked example: SUB, three listing lines** after the **File 02** template block below.

```markdown
# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | |
| Table name(s) as printed | |
| Currency | |
| Multi-listing tranches? | **Y** / **N** — **Y** if any economic class has **>1** printed listing line / CUSIP in the captured exhibit; when **Y**, **`### Tranche by listing`** is **required** for those classes (**one row per PDF line**) |
| Rows in **`### Tranche by listing`** (CUSIP-grain count) | Total listing rows (e.g. three SUB lines → **3**); **0** only when **Multi-listing** = **N** |
| Max CUSIPs under one economic class label | Max over classes of “lines under one **economic** class label” (e.g. SUB with three lines → **3**) |
| Total payment / total amount payable (if stated) | |

> **Total payment / total amount payable (Summary only):** When the **same exhibit** as the class / voucher / distribution table prints a **single trustee aggregate** for the payment (e.g. *Total Payment*, *Total Amount Payable*, *Total Cash Distribution*, *Total distribution*, voucher **total line** summing **Total amount payable** across classes), capture it in **`Total payment / total amount payable (if stated)`** under **`### Summary`**. Use **N/A** when no such line exists. **Do not** copy a figure from **`03`** waterfall **unless** the PDF repeats that same total on the class / voucher page; if ambiguous, **N/A** and quote the line in **`02` Source Text**. **`Ending balance`** on class rows stays **principal only** — do not put this aggregate in the **Ending balance** column.

### Class balance table (primary)
| Class | ISIN | CUSIP | Original balance | Beginning balance | Interest payment | Interest payable | Principal payment | Principal payable | Deferred interest | Dividend | Ending balance | Notes |
|-------|------|-------|------------------|-------------------|------------------|------------------|-------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | | |

> **Interest payment vs Interest payable:** **`Interest payment`** = cash **paid** / distributed to the class for the period (labels vary: *interest paid*, *interest distribution*, *payment*, settled amount). **`Interest payable`** = amount **due** / **accrued** / contractually **payable** for the period. When the PDF prints **only** payable / due / accrued and **no** paid amount (or paid is genuinely zero while payable is positive), leave **`Interest payment`** **blank** or **`N/A`** / null — **do not** copy payable into payment. When the PDF prints **both**, fill **both**. Copying payable → payment is allowed **only** when the report clearly uses one figure for both concepts (say so once in **Notes**).

> **Principal payment vs Principal payable:** **`Principal payment`** = principal actually **paid** / distributed this period. **`Principal payable`** = principal **due** / scheduled / contractually payable. When the PDF shows **only** principal payable and **no** principal paid (or paid is blank while payable is populated), leave **`Principal payment`** **blank** or **`N/A`** / null — **do not** fabricate paid from payable. When **both** exist, fill **both**.

> **Beginning balance and Ending balance (principal):** Copy **Beginning balance** and **Ending balance** **exactly** from the trustee’s printed class / summary row (labels vary: *prior / current*, *beginning / ending*, *outstanding*, *principal balance*, etc.). **Do not** recompute, adjust, or “correct” **Ending balance** from other columns (e.g. beginning ± principal paid ± interest). If printed columns do not arithmetic-tie, keep the trustee figures and explain once in **Notes** — the **Ending balance** cell must reflect the **report**, not a derived value.
>
> **Multi-listing (primary row for a class that also has listing rows):** Prefer a **verbatim** trustee **class / subtotal** row (e.g. one **SUB** line with combined **Ending balance**). If the PDF has **no** printed combined row, the primary **SUB** (etc.) row may carry **Notes**-documented **derived** totals (**sum of listing `CUSIP line id` rows**) or leave amounts blank and point to **`### Tranche by listing`** — per multi-listing rules **before** this template; state the convention in **`04_extraction_summary.md`** once.

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

### Tranche by listing (use when multi-listing — 144A / Reg S / AI / other programs; **per-CUSIP / per-line under one class label**)
Use when the **same economic class** appears on **multiple** trustee tables with **different CUSIPs/ISINs**, **or** when the **same class label** is repeated on **multiple CUSIP rows** in one exhibit (Computershare-style). **One row per printed line** — if the PDF shows **N** lines for class **SUB**, this subsection has **N** rows for **SUB** (not one rolled-up row). The **primary** table stays **one row per economic class**; amounts there are the **trustee-printed class total** when present, otherwise **Notes** document **derived** sums vs listing (see multi-listing rules above this template).

> **CUSIP line id (required on every row in this subsection):** Machine-stable key for downstream ETL and deduplication. **Must be unique within this `02` file** (no duplicate ids). **CUSIP** stays the trustee’s identifier from the PDF; **`CUSIP line id`** is an extra surrogate so pipelines can reference a row even when **Economic class** repeats or extraction order drifts. Pick **one** scheme and document it once in **`04_extraction_summary.md`** or **`Notes`**: (**A**) Monotonic ids **`L001`**, **`L002`**, … in the same order as the PDF / Source Text; (**B**) Composite ASCII id, e.g. **`{YYYYMMDD}-{class_slug}-{CUSIP}-{seq}`** (`20260420-A2R-26829CBA4-01`); (**C**) a printed trustee row key if the report provides one. If two rows would collide, extend with **`-a` / `-b`** and explain in **Notes**.

| CUSIP line id | Economic class | Listing / program | ISIN | CUSIP | Original balance | Beginning balance | Interest payment | Interest payable | Principal payment | Principal payable | Deferred interest | Dividend | Ending balance | Notes |
|---------------|----------------|-------------------|------|-------|------------------|-------------------|------------------|------------------|-------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | | | | |

### Cross-checks (multi-listing, if used)
| Check | Result |
|-------|--------|
| **`CUSIP line id`** values all unique (no duplicates) | |
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
- [ ] **Multi-listing / multi-CUSIP:** if 144A / Reg S / AI (etc.) **slices** exist **or** the **same class label** has **>1** printed line / CUSIP row, **`### Tranche by listing`** has **one row per PDF line** (e.g. three SUB lines → three listing rows), **or** flag **N** with reason if strictly one line per class; **`04`** (summary) flag **Multi-listing tranches** matches
- [ ] When **`### Tranche by listing`** is used: every row has a **unique `CUSIP line id`**; **Summary** counts (**CUSIP-grain row count**, **max CUSIPs per class**) filled or **N/A** with reason; **primary** class row uses **printed** class total when the PDF shows it, else **Notes** explain **derived** vs listing
- [ ] **Total payment / total amount payable** in **`### Summary`** when the trustee prints a payment-period aggregate on the class / voucher / distribution exhibit (or **N/A** with reason)

## Source Text
(Paste full class table(s) from chunks; **Page N** per block — include **each** listing block used for **`### Tranche by listing`**. Preserve **PDF row order** when assigning **`CUSIP line id`** sequence unless reordering is documented in **Notes**.)
```

#### Worked example: SUB (or any class) with three printed listing lines

| Layer | Rule |
|-------|------|
| **Primary** | One row, economic class **SUB**. **Ending balance** (and other class-level columns) = **trustee-printed** combined line when the exhibit shows it (e.g. **47,950,000.00**). If there is **no** printed combined row, use **Notes**: e.g. `Derived: sum of listing L001–L003` for the affected columns, or leave primary amounts blank and point to listing — document once in **`04_extraction_summary.md`**. |
| **`### Tranche by listing`** | **Three rows** for **three** PDF lines: **`L001`**, **`L002`**, **`L003`**; **Economic class** = **SUB** on each; **CUSIP** / **Listing / program** per the PDF; numbers **copied per line**, not summed here. |
| **`### Cross-checks (multi-listing)`** | e.g. Sum of listing **Ending balance** = primary **SUB** **Ending balance** (or match stated PDF total); **Match?** **Y** / **partial** with explanation. |

Illustrative excerpt (replace all numbers and ids with the deal’s PDF):

```markdown
### Class balance table (primary)
| Class | … | Ending balance | Notes |
|-------|---|----------------|-------|
| SUB | … | 47,950,000.00 | Printed SUB total on Principal Detail |

### Tranche by listing (optional …)
| CUSIP line id | Economic class | Listing / program | CUSIP | Beginning balance | … | Ending balance | Notes |
|---------------|----------------|-------------------|-------|-------------------|---|----------------|-------|
| L001 | SUB | 144A | 12345ABC7 | … | … | 19,900,000.00 | First SUB line on p.4 |
| L002 | SUB | Reg S | 12345ABD5 | … | … | 17,925,000.00 | Second |
| L003 | SUB | AI | 12345ABE3 | … | … | 10,125,000.00 | Third |

### Cross-checks (multi-listing, if used)
| Check | Result |
|-------|--------|
| Sum of listing Ending balance (L001–L003) | 47,950,000.00 |
| Primary SUB Ending balance | 47,950,000.00 |
| Match? | Y |
```

---

### Deal layout families (proceeds / disbursements)

Reports differ in **how** they print cash application — not only by trustee name:

| Layout | What it looks like | Typical output |
|--------|--------------------|----------------|
| **Grid / table waterfall** | Named columns (Paid, Available, Running, Optimal, …) in a wide table | **`03_interest_principal_waterfall.md`** — **`### Waterfall table`** |
| **Indenture-style** | Legal **Section 11.1** (or similar) priority text, clause letters `(A)(B)…`, sometimes **two** currency amounts at the end of each line | **`03_interest_principal_waterfall.md`** — **`### Logical / clause waterfall`** |
| **Logical disbursement style** | “Application of … Proceeds”, `(i)`–`(v)` ladders, Computershare-style **two decimals per row** without full grid headers (see **`read_noteval_logical_disb`**) | **`03_interest_principal_waterfall.md`** — **`### Logical / clause waterfall`** |

A single deal can blend styles (e.g. indenture body + a small summary grid). Use the matching **`03`** subsection(s); say in **`04_extraction_summary.md`** whether the capture was **grid**, **logical/clause**, or **both**.

---

## File 03: Interest / principal waterfall

**Filename:** `03_interest_principal_waterfall.md`  
**Scope:** All **interest / principal proceeds application** belongs here: **multi-column grid waterfalls** *and* **logical / clause ladders** (indenture **Section 11.1**, Computershare **“Application of … Proceeds”**, `(i)`–`(v)` ladders with bare decimals — see **`read_noteval_logical_disb`**). **Do not** create **`06_logical_disbursements.md`** for new extractions; that file is **deprecated** (see **File 06**). If a deal prints **both** a grid and a clause ladder, use **both** subsections in **`03`**; avoid pasting the same **Source Text** twice — cross-reference in **Notes** and keep one full verbatim block.

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

> **Indenture-style three columns (e.g. U.S. Bank Payment Date Report / Section 11.1 grid):** When the PDF prints **Amount Due**, **Payment**, and **Running Balance** (or equivalent labels), map them to the template as: **Amount Due** → **`Amount payable`** (what is **due** under the priority for that line — accrued obligation or cap; **not** necessarily cash paid), **Payment** → **`Amount paid`** (cash **actually disbursed** from the account for that line), **Running Balance** → **`Amount available / running`** (remainder after the step). Prose references to **interest due** or **amounts due** align with **payable**; they may exceed **paid** when a line is partially paid or unpaid. Add a short **`### Column mapping`** under **`03`** for the deal when this layout applies.

> **Citibank-style Section 11.1 (Distribution / Per Cap / Balance):** Some **Citibank** deals print **Distribution**, **Per Cap**, and **Balance** (wording varies; OCR may run headers together). Treat **Distribution** as **`Amount paid`** when that column is the trustee’s cash-applied amount for the step; **Per Cap** often carries the same **paid** semantics per note / pro rata slice — map to **`Amount paid`** (and/or **`Other amount columns`**) per the exhibit, not as “remaining funds.” Map **Balance** to **`Amount available / running`**. Document the mapping in **`03`** **`### Column mapping`** when this layout applies.

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

## File 06: Logical disbursements — **deprecated (use File 03)**

**Do not create `06_logical_disbursements.md` for new extractions.** Capture **Section 11.1**, **Application of Interest/Principal Proceeds**, Computershare **two-decimal** ladders, and clause `(i)`–`(v)` schedules in **`03_interest_principal_waterfall.md`** under **`### Logical / clause waterfall (optional)`**. Legacy deliverables may still include `06`; treat as superseded by **`03`**.

---

## File 04: Extraction summary

**Filename:** `04_extraction_summary.md`  
**Source:** Compiled from **`01`**, **`02`**, and **`03`** (there is **no** separate **`05_*.md`** for distribution / deferred interest — those belong in **`02`**; **`06`** is deprecated — see **File 06**).

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
| Classes in 02 (primary table rows) | |
| Rows in **`02`** **`### Tranche by listing`** (if used) | |
| Max CUSIPs under one economic class (if >1) | |
| Grid waterfall lines in 03 | |
| Logical / clause ladder rows in 03 | |
| Fee rows (approx) | |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | | **Y** when a **Distribution in US$** (or similar) grid is folded into **`02`**; **N** if absent |
| Multi-listing tranches? | | **Y** when the same **economic** class has **multiple printed lines** / CUSIPs (listings must appear **one row per PDF line** in **`02`** **`### Tranche by listing`**); **N** if strictly one line per class in the captured exhibit |
| Has grid-style waterfall in `03`? | | |
| Has logical / clause ladder in `03` (11.1, Computershare, etc.)? | | |
| Deferred interest / supplementary deferred lines captured in `02` when printed? | | |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | |
| Multi-listing: sum of **Tranche by listing** vs primary **`02`** / PDF printed class total (if **Y**) | |
| **`02`** **`CUSIP line id`** scheme (e.g. L00n / composite) and uniqueness | |
| Waterfall paid totals vs class/distribution totals in `02` (if comparable) | |
| Internal consistency (dates same across files) | |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | |
| 02_tranche_class_balances.md | |
| 03_interest_principal_waterfall.md | |
| 04_extraction_summary.md | |
| 06_logical_disbursements.md (legacy only) | |

## Completeness Checklist
- [ ] All four deliverables **01**, **02**, **03**, **04** exist or N/A documented here (**no** standalone **`05_*.md`**; **06** not required — deprecated)
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
