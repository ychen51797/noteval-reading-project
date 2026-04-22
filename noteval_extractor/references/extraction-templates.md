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
| ISIN / deal ID on report | |
| Currency | |
| Page range covering this report (PDF pages) | |

## Completeness Checklist
- [ ] Report title captured exactly (or noted if unreadable OCR)
- [ ] At least one of: determination / payment / distribution date extracted (or N/A with reason)
- [ ] Deal or trust name identified
- [ ] Trustee or paying agent identified (or N/A)
- [ ] Currency identified (or N/A)

## Source Text
(Paste header/title/date lines from `_chunks/`; prefix each block with **Page N**)
```

---

## File 02: Tranche / class balances

**Filename:** `02_tranche_class_balances.md`  
**Source:** Note Valuation Report tables, class summary, certificate principal / notional lines.

```markdown
# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | |
| Table name(s) as printed | |
| Currency | |

### Class balance table (primary)
| Class | ISIN or CUSIP | Beginning balance | Interest payment | Principal payment | Deferred interest | Dividend | Ending balance | Notes |
|-------|---------------|-------------------|------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | |

> **Column use:** Include **ISIN or CUSIP** when the report shows it; otherwise leave blank and note in **Notes**. If the PDF does not show a column (e.g. no dividend or no deferred-interest line), leave that cell blank or `N/A` and say so once in **Notes** for that row or section.
>
> **Balances and amounts:** Use plain numeric cells (no embedded `(N)` in the number). Put IO / notional / structural commentary in **Notes**.

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| | | |

## Completeness Checklist
- [ ] Every class row from the main table captured (or explicitly listed as omitted with reason)
- [ ] **Class** and **ISIN or CUSIP** (when printed) for each line
- [ ] **Beginning balance** and **ending balance** (or mapped from report labels such as prior/current principal)
- [ ] **Interest payment**, **principal payment**, **deferred interest**, and **dividend** captured when the report includes them (or marked N/A with reason)
- [ ] Totals row matches sum of detail rows (or discrepancy noted)

## Source Text
(Paste full class table(s) from chunks; **Page N** per block)
```

---

## File 03: Distribution in US$

**Filename:** `03_distribution_usd.md`  
**Source:** “Distribution in US$”, class distribution grid, prior/current principal, interest — **only if this section exists in the PDF.**

If absent, create the file with a one-line **Extracted Data** note: `Section not present in this PDF.` and checklist items marked N/A.

```markdown
# Distribution in US$

## Extracted Data

### Section present?
| Field | Value |
|-------|-------|
| Section present (Y/N) | |

### Distribution table
| Class | Prior principal balance | Current principal balance | Principal paid | Interest paid | Other columns (name + value) | Notes |
|-------|------------------------|---------------------------|----------------|----------------|------------------------------|-------|
| | | | | | | |

### Cross-checks
| Check | Value |
|-------|-------|
| Sum of principal paid (detail) | |
| Stated total (if any) | |
| Match? (Y/N / partial) | |

## Completeness Checklist
- [ ] Confirmed section exists or documented as absent
- [ ] All classes in distribution grid captured
- [ ] Principal and interest paid columns use **Paid** (or report-equivalent) semantics — not confused with “available” unless report uses one column only
- [ ] Totals reconciled or variance explained

## Source Text
(Paste Distribution in US$ tables; **Page N**)
```

---

## File 04: Interest / principal proceeds or waterfall

**Filename:** `04_interest_principal_proceeds.md`  
**Source:** Waterfall, disbursements, “Application of … Proceeds”, fee tables, Paid vs Available / Running columns — follow **this deal’s** labels.

```markdown
# Interest and Principal Proceeds / Waterfall

## Extracted Data

### Section identification
| Field | Value |
|-------|-------|
| Section title(s) as printed | |
| Funds type (interest / principal / combined) | |

### Waterfall / proceeds table
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| | | | | | | |

> **Fee-style rows:** Prefer **amount paid** (or the column the trustee labels as paid/settled) over “remaining” or discretionary picks. If the report has multiple $ columns, name each column exactly as printed and map consistently across rows.

### Fees extracted separately (optional mirror)
| Fee name | Rate or basis (if stated) | Paid | Notes |
|----------|----------------------------|------|-------|
| | | | |

## Completeness Checklist
- [ ] Full waterfall or proceeds section captured in table form (or multi-table with clear headings)
- [ ] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [ ] All fee lines that affect note valuation captured
- [ ] Subtotals / totals match detail or variance explained

## Source Text
(Paste the full waterfall / proceeds section; **Page N**)
```

---

## File 05: Note balance and deferred interest

**Filename:** `05_note_balance_deferred_interest.md`  
**Source:** Note balance summary, deferred interest, cumulative — **if present.**

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

### Deferred / accrued interest (if separate)
| Class or note | Deferred interest (begin) | Additions | Payments | Ending | Notes |
|---------------|---------------------------|-----------|----------|--------|-------|
| | | | | | |

## Completeness Checklist
- [ ] Section exists or marked absent
- [ ] Note balance lines match report labels
- [ ] Deferred interest mechanics captured if shown
- [ ] Totals agree or variance explained

## Source Text
(**Page N** blocks)
```

---

## File 06: Logical disbursements (e.g. Section 11.1)

**Filename:** `06_logical_disbursements.md`  
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
**Source:** Compiled from files 01–06.

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
| Has Distribution in US$? | | |
| Has waterfall / proceeds table? | | |
| Has deferred interest section? | | |
| Has logical disbursements (11.1-style)? | | |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | |
| Waterfall paid totals vs distribution totals (if comparable) | |
| Internal consistency (dates same across files) | |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | |
| 02_tranche_class_balances.md | |
| 03_distribution_usd.md | |
| 04_interest_principal_proceeds.md | |
| 05_note_balance_deferred_interest.md | |
| 06_logical_disbursements.md | |

## Completeness Checklist
- [ ] All applicable files 01–06 exist or N/A documented here
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
