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
- [ ] At least one of: determination / payment / distribution date extracted (or N/A with reason)
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
**Source:** Note Valuation Report tables, class summary, certificate principal / notional lines, and **any per-class distribution grid** the trustee prints (e.g. **“Distribution in US$”**, prior/current principal, interest paid — **any trustee**, not only Deutsche Bank).

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

### Class balance table (primary)
| Class | ISIN | CUSIP | Original balance | Beginning balance | Interest payment | Principal payment | Deferred interest | Dividend | Ending balance | Notes |
|-------|------|-------|------------------|-------------------|------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | |

> **Identifiers — ISIN vs CUSIP:** Use **two columns** so downstream loads map cleanly (nullable per identifier). **ISIN:** typically **12** characters (often starts with a **2-letter** country code, e.g. `XS…`, `US…`). **CUSIP:** **9** alphanumeric characters (North American issues). When the PDF prints only one identifier, put it in the correct column and leave the other **blank** (do not duplicate the same value in both). If the report prints a **combined** label (e.g. “ISIN/CUSIP”) or an ambiguous string, use **Notes** once and place the value in the column that matches length/format; if truly ambiguous, prefer **CUSIP** for 9-char US-style IDs and **ISIN** for 12-char IDs. Include **Original balance** when the report shows original face / original principal / “orig” balance (Deutsche and U.S. Bank note-valuation layouts often do); otherwise leave blank or `N/A` once per row or section in **Notes**. If the PDF does not show a column (e.g. no dividend or no deferred-interest line), leave that cell blank or `N/A` and say so once in **Notes** for that row or section.
>
> **Deferred interest:** Map the trustee’s **deferred interest** for each class from the class / NVR table — labels vary (**Interest Deferred Payable**, **Deferred Interest**, **Default / Deferred Interest Payable**, combined PIK columns, etc.). Use **one** column (**Deferred interest**) for the amount the PDF attributes to deferred interest on that tranche; if the report prints **two** deferred-style columns, choose the cell that matches the heading for *interest* deferred (or document both in **Notes** with a single primary cell). **Do not** repeat per-class **Deferred interest** in **`05_note_balance_deferred_interest.md`** — keep issuer-level / aggregate lines in **`05`** only.
>
> **Balances and amounts:** Use plain numeric cells (no embedded `(N)` in the number). Put IO / notional / structural commentary in **Notes**.

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| | | |

### Distribution grid (optional — e.g. “Distribution in US$”, prior/current principal, interest paid)
| Class | ISIN | CUSIP | Prior principal balance | Current principal balance | Principal paid | Interest paid | Other columns (name + value) | Notes |
|-------|------|-------|------------------------|---------------------------|----------------|----------------|------------------------------|-------|
| | | | | | | | | |

### Cross-checks (distribution grid, if used)
| Check | Value |
|-------|-------|
| Sum of principal paid (detail) | |
| Stated total (if any) | |
| Match? (Y/N / partial) | |

### Tranche by listing (optional — 144A / Reg S / AI / other programs)
Use when the **same economic class** appears on **multiple** trustee tables with **different CUSIPs/ISINs**. Keeps **one row per security listing**; the **primary** table above stays **one row per economic tranche** (consolidated or lead slice — say which in **Notes**).

| Economic class | Listing / program | ISIN | CUSIP | Original balance | Beginning balance | Interest payment | Principal payment | Deferred interest | Dividend | Ending balance | Notes |
|----------------|-------------------|------|-------|------------------|-------------------|------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | |

### Cross-checks (multi-listing, if used)
| Check | Result |
|-------|--------|
| Sum of principal (or notional) across listing rows vs primary tranche / PDF | |
| Match? (Y/N / partial) | |

## Completeness Checklist
- [ ] Every class row from the primary table captured (or explicitly listed as omitted with reason)
- [ ] **Class** with **ISIN** and/or **CUSIP** in the correct columns when printed (leave unused identifier blank)
- [ ] **Original balance** when the report prints it (or N/A with reason)
- [ ] **Beginning balance** and **ending balance** (or mapped from report labels such as prior/current principal)
- [ ] **Interest payment**, **principal payment**, **Deferred interest** (per tranche, from the PDF class table — see column note), and **dividend** captured when the report includes them (or marked N/A with reason)
- [ ] Totals row matches sum of detail rows (or discrepancy noted)
- [ ] Optional **Distribution grid** filled or marked N/A when the PDF has a separate class-distribution page
- [ ] **Multi-listing:** if 144A / Reg S / AI (etc.) **slices** exist for the same class, **`### Tranche by listing`** filled **or** **N** with reason; **`07`** flag **Multi-listing tranches** matches

## Source Text
(Paste full class table(s) from chunks; **Page N** per block — include **each** listing block used for **`### Tranche by listing`**)
```

---

### Deal layout families (proceeds / disbursements)

Reports differ in **how** they print cash application — not only by trustee name:

| Layout | What it looks like | Typical output |
|--------|--------------------|----------------|
| **Grid / table waterfall** | Named columns (Paid, Available, Running, Optimal, …) in a wide table | **`04_interest_principal_waterfall.md`** |
| **Indenture-style** | Legal **Section 11.1** (or similar) priority text, clause letters `(A)(B)…`, sometimes **two** currency amounts at the end of each line | **`06_logical_disbursements.md`** (clause ladder); optionally **`04`** if you also map those amounts into the waterfall columns |
| **Logical disbursement style** | “Application of … Proceeds”, `(i)`–`(v)` ladders, Computershare-style **two decimals per row** without full grid headers (see **`read_noteval_logical_disb`**) | **`06_logical_disbursements.md`** |

A single deal can blend styles (e.g. indenture body + a small summary grid). Choose the file(s) that match how the PDF is structured; say in **`07_extraction_summary.md`** which family drove `04` vs `06`.

---

## File 04: Interest / principal waterfall

**Filename:** `04_interest_principal_waterfall.md`  
**Relationship to `06_logical_disbursements.md`:** **Not duplicates.** `04` is a **column-oriented waterfall** (Priority + **Amount paid** / **Amount payable** / **Amount available or running** + optional fee mirror) for trustees that print explicit multi-column proceeds tables (e.g. Deutsche **Available / Optimal / Paid / Unpaid**). `06` is a **clause-oriented ladder** (Section reference + **Clause / step** + single **Amount** + **Continuations**) for indenture-style **Section 11.1** or Computershare “Application of …” prose. **Same pages can inform both** on some CLOs (e.g. U.S. Bank 11.1 with two trailing amounts): then either fill **`04` only** as a mapped waterfall, **`06` only** as the clause ladder, **or** both if downstream needs both shapes — if both, avoid repeating the same **Source Text** verbatim twice (point from one file to the other in **Notes** and keep one full paste).

**Source:** Waterfall, disbursements, “Application of … Proceeds”, fee tables, Paid vs Available / Running columns — follow **this deal’s** labels.

```markdown
# Interest and Principal Waterfall

## Extracted Data

### Section identification
| Field | Value |
|-------|-------|
| Section title(s) as printed | |
| Funds type (interest / principal / combined) | |

### Waterfall table
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| | | | | | | |

> **Fee-style rows:** Prefer **amount paid** (or the column the trustee labels as paid/settled) over “remaining” or discretionary picks. If the report has multiple $ columns, name each column exactly as printed and map consistently across rows.

### Fees extracted separately (optional mirror)
| Fee name | Rate or basis (if stated) | Paid | Notes |
|----------|----------------------------|------|-------|
| | | | |

## Completeness Checklist
- [ ] Full waterfall section captured in table form (or multi-table with clear headings)
- [ ] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [ ] All fee lines that affect note valuation captured
- [ ] Subtotals / totals match detail or variance explained

## Source Text
(Paste the full waterfall section; **Page N**)
```

---

## File 05: Note balance and deferred interest

**Filename:** `05_note_balance_deferred_interest.md`  
**Source:** Note balance summary, **issuer- or fee-level** deferred amounts, cumulative lines — **if present.** Per-tranche **Deferred interest** on the class table belongs in **`02_tranche_class_balances.md`** only; **do not** rebuild a per-class deferred-interest grid in **`05`**.

```markdown
# Note Balance and Deferred Interest

## Extracted Data

### Section present?
| Field | Value |
|-------|-------|
| Section present (Y/N) | |

### Note balance table
| Line item | Amount | Notes |
|-----------|--------|-------|
| | | |

### Deferred / accrued interest (issuer or aggregate — not per tranche)
| Description | Amount | Notes |
|-------------|--------|-------|
| | | |

> **Do not** duplicate per-tranche **Deferred interest** from the NVR / class table here — that column lives only in **`02`**.

## Completeness Checklist
- [ ] Section exists or marked absent
- [ ] Note balance lines match report labels
- [ ] Issuer-level / aggregate deferred or fee-deferral mechanics captured if shown (per-tranche deferred interest is **not** required here — see **`02`**)
- [ ] Totals agree or variance explained

## Source Text
(**Page N** blocks)
```

---

## File 06: Logical disbursements (e.g. Section 11.1)

**Filename:** `06_logical_disbursements.md`  
**Relationship to `04_interest_principal_waterfall.md`:** See **File 04** — `06` captures **indenture clause structure** and continuations; `04` captures **tabular paid vs available/running** semantics. Pure **Section 11.1** schedules often map cleanly to **`06`**; use **`04`** when you need the wide waterfall columns and fee mirror, or when the deal does not use an 11.1-style ladder at all.

**Source:** “Application of Interest Proceeds”, “Application of Principal Proceeds”, Computershare-style ladders, clause (i)–(v) — **if present.**

```markdown
# Logical Disbursements

## Extracted Data

### Section present?
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

> Roll up indented / “first / second / third” continuations under the parent clause in **Item description** or **Notes** so each major line is one logical row.

## Completeness Checklist
- [ ] Section exists or marked absent
- [ ] Each major clause line has amounts aligned to correct column
- [ ] Continuations tied to parent bullets
- [ ] Determination / payment dates repeated here if stated in this section

## Source Text
(**Page N**; paste ladder verbatim)
```

---

## File 07: Extraction summary

**Filename:** `07_extraction_summary.md`  
**Source:** Compiled from **`01`**, **`02`**, **`04`**, **`05`**, **`06`** (there is **no** `03_*.md` deliverable).

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
| Waterfall lines in 04 | |
| Logical disbursement rows in 06 | |
| Fee rows (approx) | |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | | **Y** when a **Distribution in US$** (or similar) grid is folded into **`02`**; **N** if absent |
| Multi-listing tranches? | | **Y** when the same **economic** class appears under **multiple programs** (e.g. 144A / Reg S) with **different ISINs and/or CUSIPs** — see **`02`** **`### Tranche by listing`**; **N** if one listing only |
| Has waterfall / proceeds table? | | |
| Has deferred interest section? | | |
| Has logical disbursements (11.1-style)? | | |

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
| 05_note_balance_deferred_interest.md | |
| 06_logical_disbursements.md | |

## Completeness Checklist
- [ ] All applicable files **01**, **02**, **04**, **05**, **06** exist or N/A documented here (no `03`)
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
