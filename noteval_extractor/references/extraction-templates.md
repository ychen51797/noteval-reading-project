# Note Valuation / Trustee Report — Extraction Output Templates

This file defines the **strict template** for each extraction output file produced from **note valuation**, **distribution**, **waterfall**, or related **trustee payment** PDFs. The extraction agent MUST follow these templates so outputs stay consistent, auditable, and (when implemented) machine-validatable.

**Deliverable set (agent: four files):** `01_report_metadata.md` → `02_tranche_class_balances.md` → `03_interest_principal_waterfall.md` → `04_extraction_summary.md`. **Post-agent (script):** `05_valuation_relevant_fees.md` via **`map_valuation_fees.py`** from the **`03`** waterfall (fee roll-up is **not** in **`02`** or **`03`** for new runs). Per-class distribution grids and deferred-interest lines stay in **`02`**. Deprecated: **`06_logical_disbursements.md`** — fold logical ladders into **`03`**. **Optional machine export:** XML reads **`05`** (fallback: legacy fee table in **`03`**) — see **`noteval_extractor/references/xml-export.md`**.

**Workflow (not layout):** Very large PDFs (e.g. **300+** pages) still use **`_page_index.md`** plus targeted **`_chunks/`** reads. If the PDF has **no** tranche or waterfall content to extract, **`02`** / **`03`** may be **N/A** with clear **`04`** (summary) documentation — see **`noteval_extractor/SKILL.md`** (*Very large PDFs* and *No tranche or waterfall*).

## Table of contents

**Deliverables (agent order):**

1. [Template structure (all files)](#template-structure-applies-to-all-output-files)
2. [File 01 — Report metadata](#file-01-report-metadata)
3. [File 02 — Tranche / class balances](#file-02-tranche--class-balances)
4. [File 03 — Interest / principal waterfall](#file-03-interest--principal-waterfall)
5. [File 04 — Extraction summary](#file-04-extraction-summary)
6. [File 05 — Valuation-relevant fees (post-extraction)](#file-05-valuation-relevant-fees-post-extraction--not-agent-filled)

**Other:**

- [File 06 — Logical disbursements (deprecated)](#file-06-logical-disbursements--deprecated-use-file-03)
- [Agent metadata block (optional)](#agent-metadata-block-optional-first-lines)

> **Out of scope:** Original vs **revised/amended** report comparison (`06_revised_report_comparison.md`) is **not** part of noteval_extractor — use the **revised-report-checker** skill and `compare_revised_report.py` separately.

**File 02 — jump topics** (blockquotes under [File 02](#file-02-tranche--class-balances)):

| Topic | Search for |
|-------|------------|
| Dual PDD + IDD exhibits | **Dual exhibits** |
| Multi-CUSIP / 144A / Reg S | **Multi-listing**, **Two CUSIPs** |
| Distribution in US$ wide voucher | **wide voucher header reconstruction** |
| Principal vs ending balance | **Principal payment != Ending balance** |
| Computershare Sub Totals / pdfplumber | **Sub Totals alignment**, **pdfplumber** |
| SUB / F footer, zero coupon | **SUB / F footer**, **zero coupon**, **Distribution Summary** |
| Notes Information (BNY) | **Notes Information grid** |
| NVR Periodic Interest | **Periodic Interest Amount** |
| Preference Share equity rows | **Preference Share** |
| Ending zero paydown | **Ending zero paydown** |
| Fixed column layouts (summary) | **`references/file-02-domain-rules.md`** in repo |

**File 03 — jump topics** (under [File 03](#file-03-interest--principal-waterfall)):

| Topic | Search for |
|-------|------------|
| Wells Fargo dual PDF | **Wells Fargo (dual PDF** |
| Fees belong in **05**, not **03** | **Valuation-relevant fees — not in File `03`** |
| Admin grid vs waterfall | **Administrative Expenses grid** |
| Column mapping (Due / Payment / Running) | **Amount Due**, **Column mapping** |
| Citibank Distribution / Per Cap / Balance | **Citibank** (File 03 template + SKILL) |
| Fee Sub category literals | **Main category vs Sub category**, **PDF wording → `fee_type`** |
| Mapper behavior | **`map_valuation_fees.py`** |

---

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

Use **stable table headers** below; do not rename columns (future `validate_noteval.py` may key off them — e.g. **Class**, **Beginning balance**, **Interest payment** — not **ISIN**/**CUSIP** in **primary**).

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
**Source:** Note Valuation Report tables, class summary, certificate principal / notional lines, **any per-class distribution grid** the trustee prints (e.g. **“Distribution in US$”**, prior/current principal, interest paid — **any trustee**, not only Deutsche Bank), **including when principal and interest are on separate exhibits** (merge into **`02`** per the **Dual exhibits** rule below), **and** when the trustee prints a **separate per-class rate / fixing exhibit** (e.g. **Interest Rate Fixing**, **Notes Information - Interest Rate Fixing**, **Floating rate** / **benchmark + margin** — merge **`Interest rate`** per the **third-table** blockquote below), and **optional report-level payment totals** printed with or beneath those tables (e.g. voucher **Total amount payable**, distribution **grand total** — captured in **`### Summary`**, not **`01`**).

**`02` does not include an Administrative Expenses grid or valuation fee roll-up:** When the PDF prints a separate **Administrative Expenses** (or similar) fee table, capture it **only** in **`03_interest_principal_waterfall.md`** — optional **`### Administrative Expenses grid`** plus **`### Waterfall table`**. Fee typing (**Main category** / **Sub category**) is **`05_valuation_relevant_fees.md`** via **`map_valuation_fees.py`**, not **`02`**. **Do not** add admin grids or fee **$** rows under **`02` Extracted Data**.

> **FAQ — “Why would we put an Administrative Expenses grid in `02`?”** **We would not.** **`02`** is only for **class / tranche** economics (principal, interest, balances, multi-listing). Fee detail belongs in **`03`** (waterfall / admin grid) and **`05`** (mapped fee roll-up after extraction).

**There is no `03_` file.** Capture distribution-style grids in **`02`**: extend the primary class table, add **`### Supplementary lines`** **only** for **issuer-level / aggregate** items **not** on a class row (never duplicate **Administrative Expenses** / fee **$** here — those stay in **`03`**), and/or add a second table under **Extracted Data** (e.g. `### Distribution grid (if present)`) with stable columns and the same **Source Text** rules.

**Dual exhibits — *Principal Distribution Detail* vs *Interest Distribution Detail* (or same pattern under other trustee headings):** The PDF often prints **two** per-CUSIP grids for the **same** payment date: typically **(1)** **Principal Distribution Detail** (or equivalent) — principal, balances, factors — and **(2)** **Interest Distribution Detail** (or equivalent) — interest accrual and interest amounts. **Merge rule (align **principal** and **interest** exhibits by **economic Class**; when **`Multi-listing tranches?`** = **Y**, use **`### Tranche by listing`** **`CUSIP`** / **`ISIN`** rows to key each security line — **`### Class balance table (primary)`** and **`### Distribution grid`** **omit** **ISIN**/**CUSIP** so class rows are not tied to a single identifier; when **`Multi-listing`** = **N**, merge by **Class** label / consistent row order; **still** capture **each printed per-class CUSIP/ISIN** in **`### Tranche by listing`** whenever the report prints them (see **Identifiers** blockquote below — **required for XML / tranche mapping**)):** **`Principal payment`** and **`Principal payable`** (and **Beginning balance** / **Ending balance** / other **principal** fields) come from the **principal** table **only** — do **not** take **`Principal payment`** from the interest table, and do **not** set **`Ending balance`** from the interest exhibit or from inference when the **principal** table prints an **Ending balance** (or equivalent) for that class / CUSIP. In **`02`**, the template column **`Ending balance`** means **ending principal balance**: copy the trustee’s **Ending balance** (or **Ending principal balance** / **Current principal balance** when that column is clearly the post-distribution principal) from the **principal** exhibit — **not** original face, **not** a pool-wide **SUB** aggregate from another page unless that row is explicitly the same economic line. **`Interest payment`** and **`Interest payable`** (and **`Deferred interest`** when printed on that exhibit) come from the **interest** table **only** — do **not** take **`Interest payment`** from the principal table. **Phrasing over column position (LLMs / OCR):** Raw **`_chunks/`** text often has **unreliable left-to-right field order** (e.g. **Computershare** with **headers above or below** the number block). **Do not** assign **`02`** / **`03`** fields primarily by “nth token after `CUSIP`.” **Prefer printed labels and titles** in the chunk or PDF: **Ending Balance**, **Principal distribution** / **Principal distributed** (when the heading names a **$** column for principal **actually paid** this period → **`Principal payment`** — **not** **Principal Distribution Factor** or other **factor** cells), **Beginning balance**, **Coupon** / **Coupon rate**, **Interest Distribution**, **Paid on the Distribution Date**, clause lines **(C) … Management**, etc. Use **positional rules only** when no label or **consistent header row** can be matched across rows; **Notes** once if mapping was inferred without headings. **Sparse interest lines:** If a line shows only **`CUSIP` + decimals**, still **join the nearest visible column headers** from the same page (above or below the strip) before guessing; **never** map **factor**-labeled columns (**Period Beginning Balance Factor**, **Principal Distribution Factor**, **Ending Balance Factor**, **~1000.00000000**-style **full accrual** cells, or ambiguous decimals that track **original face**) to **`Interest rate`**. **Never map factors to `Interest rate`.** **`Interest rate`** must come from headings that literally read **Coupon**, **Coupon rate**, **Interest rate**, **All-in rate**, or an equivalent **accrual**-named column on **Interest Distribution Detail** (including headers printed **below** the grid in some Computershare extracts). **Shifted-interest-$ (SUB / PIK / deferral):** When **Coupon** is **0** but another **$** is clearly **Interest distribution** / **paid interest** **by label** or by **shared column header** across other CUSIP rows, copy that **$** to **`Interest payment`** (and **`Interest paid`** in **`### Distribution grid`**) — **do not** leave **`Interest payment`** **0.00** when a **labeled** interest column shows a **large non-zero** amount for that CUSIP. **`Interest rate`:** **Prefer the interest-detail coupon column when present:** **Interest Distribution Detail** often prints **Coupon**, **Coupon rate**, **Annual coupon**, **Current coupon**, **Floating rate**, **All-in rate**, **Note rate**, or similar **per-class accrual** cells. If **any** such column on **(B)** is populated for that **Class** / **CUSIP**, copy it **verbatim** into **`Interest rate`** in **primary** (and **`### Tranche by listing`**) — **do not** skip it, leave **`Interest rate`** blank, or wait for a **rate-fixing** page when **(B)** already shows the coupon. **Otherwise** copy from **whichever** exhibit prints the accrual — **only** the **principal** grid, a combined **Note Valuation Report** table, or **(C)** a **dedicated Interest Rate Fixing** / **floating-rate determination** page (see **third-table** blockquote next). If **both** **(B)** and **(C)** (or principal vs interest) print a rate for the same class, prefer the column that is clearly the **period accrual** for note interest, and **Notes** once if headings differ. The **principal** grid may show **0.00** or blank in interest-like columns; **ignore** those for **`Interest payment`** / **`Interest rate`** when the **interest** exhibit has the real values. **Do not** leave **`Interest payment`** / **`Interest rate`** as **0.00** copied only from the principal grid when the **interest** grid shows **non-zero** interest or a printed rate for that CUSIP. **`Interest rate`** in **primary** is **required** whenever **any** merged exhibit prints a rate for that economic class — **do not** populate **`Interest rate`** **only** in **`### Distribution grid`** while leaving **primary** blank for the same period (the grid may **duplicate** the rate for audit, but **primary** remains the **authoritative** class row for downstream). If column order differs between exhibits, map by **printed heading / caption text first**; use **field order** only when headings are missing or ambiguous, and **Notes** once per row if inferred. When you also fill **`### Distribution grid`**, **`Interest paid`** / **`Interest payable`** there must **match** the **interest** exhibit; **principal** columns must **match** the **principal** exhibit — **not** stay **0.00** while **Source Text** quotes non-zero lines from the other table.

> **Raster / vision assist — dual PDD + IDD and multi-CUSIP:** When the deal has **both** **Principal Distribution Detail** and **Interest Distribution Detail** (or equivalent **separate** principal vs interest grids) **and** **>1** **CUSIP** line per **economic** class (**`Multi-listing`** = **Y**), **`_chunks/`** text alone may **not** preserve **column–cell alignment** or **Note Class** labels (headers off-page, **Sub Totals** blocks, stacked footers). In that case **prefer** (a) **PDF page images** or **table crops** with **manual** markup, or (b) **table extraction** / **vision models** on those regions to recover **which heading owns each $** and **which CUSIP row belongs to which class**, then fill **`02`** and document provenance in **`Notes`** / **`04`**. The **noteval UI** draft endpoint (`server.py` / `noteval_llm`) can **attach PNG renders automatically** when heuristics match (see **`noteval_extractor/SKILL.md`**); that path uses **PyMuPDF** and **`_manifest.md` Source PDF**. Plain left-to-right token rules stay a **fallback**, not the primary method for those layouts — see **`noteval_extractor/SKILL.md`** *When to add raster / table images or vision*.

> **`Interest rate` — not `Interest type` (Floating / Variable / Fixed):** Many payment-date grids print **`Interest type`**, **`Rate type`**, or **`Index type`** with categorical values **Floating**, **Variable**, **Fixed**, **Float**, etc. Those labels are **not** numeric accruals — **do not** copy them into template **`Interest rate`**. Use **N/A** (or blank) in **`Interest rate`** when that is the only “rate-like” column on the row, and map **`Interest rate`** from **Coupon** / **Coupon rate** / **Spread** / **Rate** / **All-in rate** / **SOFR** / **margin** / rate-fixing columns that contain **digits** and/or **%**. Optional **Notes** once per table (e.g. *Interest type = Floating; accrual from Coupon column*). **`Floating rate`** as a **column title** is fine **only** when the **cell** is numeric (e.g. **4.25%**), not when the cell is the word **Floating** alone.

> **Interest rate — third table / “rate fixing” (when (B) has no coupon column):** Many trustees print **(A)** **Principal Distribution Detail**, **(B)** **Interest Distribution Detail** (often with **Coupon** / **Coupon rate** → map to **`Interest rate`** first per **Dual exhibits**), and **(C)** a **separate** per-class **rate** exhibit when the trustee splits rate from **$** — titles vary (**Interest Rate Fixing**, **Notes Information - Interest Rate Fixing**, **Floating Rate Notes**, **Determination of … Rate**, **Benchmark + margin**). Use **(C)** when **(B)** truly has **no** accrual column for that line, or when **(C)** is the **authoritative** period rate update. **Do not** leave **`Interest rate`** blank while **(B)** shows a populated **Coupon** / **coupon rate** (or equivalent) for that **Class** / **CUSIP**. Include **(C)** in **`02` Source Text** when used. **Before finalizing `02`:** scan **`_page_index.md`** (and open matching **`_chunks/`** pages) for *rate*, *coupon*, *fixing*, *benchmark*, *margin*, *SOFR*, *EURIBOR*, *SONIA*.

> **Primary class row — interest columns (not “principal-only” zeros):** Treat **`Interest rate`**, **`Interest payment`**, and **`Interest payable`** as **wrong** if they are **blank** or **0.00** **only** because the row was filled from a **principal-only** table while **any** interest-bearing exhibit in the **same** payment package shows a **non-zero** rate, **non-zero** interest paid/payable, or a **Coupon** / **Periodic Interest** / **Interest paid** column for that **same** economic class or CUSIP (**Interest Distribution Detail**, **Notes Information - Interest**, **Distribution in US$**, combined **Note Valuation Report** line with interest, aggregate **Periodic Interest Amount** blocks keyed to class, etc.). **Coupon / coupon rate on Interest Distribution Detail** maps **directly** to **`Interest rate`** — do **not** ignore it. Also check a **third** **rate-fixing** / **floating-rate** page when **(B)** has **no** coupon column (see **Interest rate — third table**). **`Interest rate`** may still be correct when taken **only** from the principal table if that is where the trustee prints the accrual — but **never** leave **`Interest payment`** solely from the principal table when the **interest** table has the paid/payable figure. **Re-open** the interest pages in **`_chunks/`**, merge per **Dual exhibits**, and align **primary** before finalizing **`02`**. **0.00** / blank is acceptable **only** when the **interest** source for that class is also zero/blank or **Notes** document a true **non-accrual** / structural exception. **Multi-listing:** each **`### Tranche by listing`** row still takes **principal** from the **principal** exhibit and **interest** from the **interest** exhibit for that CUSIP; **`Interest rate`** from whichever exhibit prints it for that line (including **rate-fixing**).

**> **Principal payment != Ending balance — read the `Principal Distribution` column, never the balance columns (required):** `Principal payment` must come from the **`Principal Distribution`** column (or equivalent: *Prin Dist*, *Principal Paid*, *Principal Payment*) of the **Principal Distribution Detail** exhibit — **never** from the **Ending Balance**, **Current Balance**, **Original Face**, or any other balance column. The most common agent error is placing the **Ending balance** (or Beginning balance) into `Principal payment` — this is **always wrong**. **Proof check:** on any period where no principal is distributed, `Principal Distribution = 0.00` for every class and `Ending balance = Beginning balance` (the class carries its balance unchanged). If you see `Principal payment = Beginning balance` or `Principal payment = Ending balance` in any row, that is a mis-read — correct it to `0.00` and put the trustee-printed ending balance into `Ending balance`. **Computershare PDD five-column band** (linearized pypdf text): the five numbers per Sub Totals band are **Original Face | Beginning Balance | Principal Distribution | Deferred Interest | Ending Balance** — the **third number** (often 0.00) is Principal Distribution; the **fifth** is Ending Balance. Do not read the fifth into `Principal payment`. The **Note/Equity Balances** page prints `Original Balance | Current Balance` — `Current Balance` = Ending balance, not a principal payment. **Concrete example — deal 868122450 A-R:** Beginning = 465,000,000.00, Principal Distribution = 0.00, Ending = 465,000,000.00; `Principal payment = 0.00`, `Ending balance = 465,000,000.00`. Setting `Principal payment = 465,000,000.00` (= the ending balance) is **wrong**.

Multi-listing (same economic class, several printed lines / CUSIPs — e.g. **SUB** with **three** rows, or **144A** / **Reg S** / **AI** slices):** Use **both** layers so nothing is lost and class-level numbers stay auditable.

1. **`### Tranche by listing`** — **Mandatory whenever the report prints a per-class or per-line CUSIP/ISIN** (including **one CUSIP per class** on **Distribution Summary**, **Distribution in US$**, PDD/IDD, etc.). **When `Multi-listing tranches?` = Y:** **one row per printed security line** under that economic class (if the PDF shows **three** SUB lines, extract **three** listing rows). Each row needs a **unique `CUSIP line id`**. Copy amounts **verbatim** per line. Do **not** collapse multiple PDF lines into a single listing row. **When `Multi-listing tranches?` = N** but CUSIPs/ISINs **are** printed: **still** populate listing — typically **one row per primary class** with **`Economic class`** = primary **`Class`** and the printed **CUSIP** / **ISIN** (economics may mirror **primary** or repeat key balance columns). **Only** omit listing (row count **0**) when the captured exhibits truly print **no** per-class security identifier anywhere. **Do not** leave CUSIPs **only** in **Source Text** or **Notes**.

2. **`### Class balance table (primary)`** — **One row per economic class** (e.g. one **SUB** row). **Do not** add **ISIN** or **CUSIP** columns here — **primary** is **Class** + economics only; **ISIN**/**CUSIP** belong in **`### Tranche by listing`** whenever printed (and deal-level IDs in **`01`** **Document routing** when applicable). Prefer the trustee’s **printed class / subtotal** for that class (e.g. **SUB** ending **47,950,000.00**) when the exhibit shows it — copy it **exactly**, do not recompute. If the PDF shows **only** slice lines and **no** printed combined row for the class, either: (**a**) populate primary **SUB** with **Notes** that balances are **derived** (e.g. “Ending = sum of `L001`–`L003`”), or (**b**) leave primary numeric cells blank / partial and point **Notes** to **`### Tranche by listing`** — state the convention once in **`04_extraction_summary.md`**. Do **not** use a random “lead” CUSIP row as the primary row when a printed **class total** exists.

3. **`### Cross-checks (multi-listing)`** — When **`### Tranche by listing`** has **data** rows, sum listing rows (principal / ending, as applicable) vs primary row and vs any **printed** PDF total; explain **partial** / **N** with reason. When listing is **empty** (no CUSIPs in report), omit this subsection or mark checks **N/A**.

4. **`### Summary`** — Set **Multi-listing tranches?** to **Y** if **any** economic class has **>1** listing row / CUSIP line under the same label; **N** when **at most one** CUSIP (or security line) per economic class. **Rows in ### Tranche by listing** = total populated listing rows (**including** one row per class when Multi-listing = **N** but CUSIPs are printed); **0** only when **no** per-class CUSIP/ISIN appears in the report. **Max CUSIPs under one economic class label** = max over classes.

**Computershare-style (same class label repeated on several CUSIP rows):** Same rules: **primary** = one row per **economic** class (trustee **printed** subtotal when shown, else derived with **Notes**); **listing** = **one row per CUSIP line** the PDF shows for that label, with **`Listing / program`** when printed else **`CUSIP slice`** / line ordinal. **`CUSIP line id`** is required on **every populated** listing row. See **Worked example: SUB, three listing lines** after the **File 02** template block below.

> **Two CUSIPs (or more) under one economic class (144A / Reg S / AI, etc.):** The trustee often prints **one** **Note Class** label (e.g. **B1**, **SUB**) with **multiple** **CUSIP** lines (different programs). **Do not** conclude the class has **no** balance or **no** cash **only** because **one** **CUSIP** row is **all 0.00** — another slice or the **class subtotal** block aligned with that label (often **below** the CUSIP grid on Computershare extracts) may carry the **real** **Original** / **Beginning** / **interest** / **principal** figures for that **economic** class. Use **`### Tranche by listing`** (**one row per CUSIP**) and set **`Multi-listing tranches?` = Y** when **>1** **CUSIP** maps to the same printed class. **`### Class balance table (primary)`** uses the trustee **class-level** line when it exists; **`Interest rate`** on each **listing** row comes from **that** **CUSIP**’s **Coupon Rate** / **Interest rate** cell on **Interest Distribution Detail** — **primary** may **Notes** when one slice is **0.00000%** coupon but class-level **interest** **$** is non-zero (dual-line economics).

> **Computershare multi-CUSIP section -- Sub Totals = class aggregate (required):** When pdfplumber groups **two or more CUSIPs** under the same **Note Class** header (including three or more CUSIPs -- e.g. two paid-down + one active, or three with split balances), the **Sub Totals: row is the sum of ALL CUSIPs in that section** and is the correct value for the **primary Beginning balance**. Use the trustee-printed Sub Totals directly -- do not try to recompute the aggregate yourself. **Do not** use only the active CUSIP individual balance and ignore paid-down slices -- that produces a wrong (lower) primary balance. Every CUSIP in the section, even those with 0.00 individual balance, goes in Tranche by listing under the same Economic class; do not reassign a 0.00-balance CUSIP to a different class. **Concrete example -- deal 825519711 E-RR:** pdfplumber Note Class section E-RR contains **97988QBJ2** (0.00, paid-down) and **97988QBK9** (60,000,000.00, active); pdfplumber Sub Totals = **60,000,000.00**; therefore **E-RR primary Beginning balance = 60,000,000.00** (0 + 60M). Both CUSIPs go in Tranche by listing under Economic class = E-RR. The SUB token visible after the Sub Totals numbers in the glued pdfplumber first-column is the **next section header** -- it does not make QBJ2 or QBK9 belong to SUB. EMS moodystrancheid 869519604 confirms both CUSIPs = E-RR. **Setting E-RR beginning balance to 0.00 is wrong** and indicates only QBJ2 was captured while QBK9 was missed or mis-routed.

> **Exact printed class name — same vs different:** Compare trustee **Class** / note **name** text after **trimming leading/trailing whitespace only** (preserve internal spacing and punctuation as printed). **If two or more data lines share exactly the same name** → treat as the **same economic class**: **one** **`### Class balance table (primary)`** row; if **>1** printed line exists for that name (e.g. multiple **CUSIPs**), set **`Multi-listing tranches?` = Y** and use **`### Tranche by listing`** (**one row per printed security line**) per the rules above. **Program slices (144A / Reg S / AI):** Names like **SUB-144A**, **SUB-REGS**, **A-144A**, **A-R-144A**, **A-R-REGS**, **B1 Reg S** are usually **one economic tranche** (**SUB**, **A**, **B**, …) with **multiple listings** — **not** separate **primary** rows when **`Multi-listing`** = **Y** and a **$** class table exists (see **Distribution in US$ — primary authority** below). **If names differ in substance** (e.g. **Subordinated Preferred Return Notes** vs **Subordinated Notes**, **Performance Notes** vs **Senior Notes**) → **different** economic classes → **each** gets its **own** **primary** row. **Do not** skip distinct economic classes because a name is “similar”; **do not** put every **144A/Reg S** slice in **primary** when the rollup rules apply. **A-R-144A** + **A-R-REGS** → primary **`A-R`** only (same tranche; program suffix is not part of **`Class`**).

> **Distribution in US$ — primary authority (NVR + factor / PDD layouts):** When the payment package prints **Distribution in US$**, **Note Valuation Report** (or equivalent) with **class-level $** (balances, interest paid, totals) **and** also prints **Factor Information per 1000 of Original Face** / **Principal Distribution Detail** with **~1000**-scale factors, treat the **Distribution in US$ / NVR $ table** as **authoritative for primary** **`Beginning balance`**, **`Ending balance`**, **`Interest payment`**, and **`Principal payment`** (period cash). On that **$** table the trustee’s **prior/current principal** pair maps **directly** to template balances: **`Prior principal balance`** → **`Beginning balance`**; **`Current principal balance`** → **`Ending balance`** (same **Class** row). **Do not** use **Original balance** or factor-grid **$** for beginning/ending. **Do not** copy **factor per 1000** cells into balance or interest **$** columns. **Primary** = **one row per economic class** (**A**, **B**, **SUB**, …): prefer the trustee **class subtotal** or **Total** line on the **$** exhibit; if only slice lines have **$**, **sum** listing rows for that economic class and **Notes** once. **Listing** = **one row per printed slice** (**SUB-144A**, **A-REGS**, …) with **$** from the **same $ exhibit** (per-line NVR / Distribution in US$), **not** from the factor grid. **PDD / factor page** → **`Interest rate`** from **Current Coupon** when printed (often on **Distribution in US$** or **Coupon Rates**); **Deutsche Bank NVR:** **do not** concatenate **Index** + **Spread** into **`Interest rate`**; **period principal distributed** → **`Principal payment`**; factor **~1000** values only in **Notes** if needed for audit. Fill **`### Distribution grid`** from the **$** table when present (mirror prior/current principal and interest paid).

> **Distribution in US$ — wide voucher header reconstruction (header-first, required):** A common layout (US Bank / Deutsche / Computershare wide voucher) prints the **Distribution in US$** row with **wrapped, multi-line headers** that **`_chunks/`** flattens into **concatenated camel-jammed strings** (e.g. `Face Value Face ValueBalanceInterestPaymentPaid PaidInterestFace ValueBalanceClass` followed by `Original OriginalPrincipalCapitalizedTotalPrincipalInterestOptimalOriginalPrincipal` and `Percent ofCurrentPercent ofPrior`). **Do not** map cells by **left-to-right position**, **first/second numeric**, **last numeric**, **largest dollar**, presence of a **`$`** sigil, or any other **positional** rule on this layout — column order **varies across trustees and even across pages**, and any positional anchor will silently mis-map the row when the trustee inserts an **Optimal Principal**, **Capitalized Interest**, **Total Payment**, or extra **percentage** column.
>
> **Required procedure — reconstruct the header before reading any row:**
> 1. **Quote the full header block** (every wrapped header line above and/or below the data band) in **`## Source Text`** for **`02`**, **verbatim** as it appears in `_chunks/`.
> 2. **Split the camel-jammed tokens** into the underlying column titles by inserting word breaks before each capital letter (e.g. `BalanceInterestPaymentPaidPaidInterestFaceValueBalance` → `Balance | Interest | Payment | Paid | Paid | Interest | Face Value | Balance`). Stack the wrapped lines vertically per column to recover full titles such as **Original Face Value**, **Beginning Principal Balance**, **Interest Capitalized**, **Total Payment**, **Principal Paid**, **Optimal Principal**, **Current Coupon**, **Prior Coupon**, **Original Face Value**, **Interest Paid**, **Ending Principal Balance**, **Class**.
> 3. **Verify the header by arithmetic on the printed `Total` row** (every Distribution in US$ exhibit prints a `Total` row at the bottom). For each candidate column assignment, the **`Total Payment`** column must equal **`Principal Paid` + `Interest Paid`** for **every** non-zero data row, and **`Ending Principal Balance`** must equal **`Beginning Principal Balance` − `Principal Paid`** (within rounding) for any row with non-zero `Principal Paid`. If the arithmetic does **not** tie under the candidate header, the split is wrong — re-split before reading data values.
> 4. **Map cells to template fields by reconstructed header title only:**
>    - **Beginning Principal Balance** → **`Beginning balance`**
>    - **Ending Principal Balance** → **`Ending balance`** (do **not** use **Total Payment** for this)
>    - **Principal Paid** → **`Principal payment`** (do **not** use **Optimal Principal** — that is a separate column, usually `0.00`)
>    - **Interest Paid** → **`Interest payment`**
>    - **Current Coupon** → **`Interest rate`**
>    - **Original Face Value** → **`Original balance`**
> 5. **Record the reconstructed header in a `### Column mapping` block** at the top of **`## Extracted Data`** for **`02`** (or in a per-row **Notes** cell when only one row is anomalous), naming **as-printed → template** for each `02` field copied from this exhibit.
>
> **Self-check before saving `02`:** run `python noteval_extractor/scripts/validate_noteval.py <output-dir>` and read **`validation_report.md`**. Rule 5 (principal roll-forward, `Ending ≈ Beginning + Deferred − Principal payment`) **will fire** when this header reconstruction is wrong — typically with a single-class delta equal to that class's **`Interest payment`** (sign of mapping **`Ending balance`** to the **Total Payment** column). Treat any roll-forward warning on a **Distribution in US$**-sourced row as a **header reconstruction failure** until proven otherwise: re-split the camel-jammed header, re-tie the `Total` row arithmetic, re-map by title, and re-run validation. Do **not** suppress the warning with **Notes** unless the trustee's own printed columns also fail the arithmetic (rare; document explicitly in **Notes** with the failing line quoted).
>
> **Worked example (deal `825496775`, payment 2026-04-22, line `E-2-144A`).** The chunk row is one concatenated line; do **not** map by position. Reconstructed header (post-split) is **Original Face | Beginning Principal | Interest Capitalized | Principal Paid | Total Payment | Optimal Principal | Current Coupon | Prior Coupon | Original Face $ | Interest Paid | Ending Principal Balance | Class**. Correct mapping:
> - **`Original balance`** = `6,000,000.00`
> - **`Beginning balance`** = `328,437.40`
> - **`Principal payment`** = `328,437.40` (Principal Paid column; **not** Optimal Principal `0.00`, **not** Total Payment `334,707.80`)
> - **`Interest payment`** = `6,270.40`
> - **`Ending balance`** = `0.00` (Ending Principal Balance column; **not** `334,707.80`, which is `Principal Paid + Interest Paid`)
> - **`Interest rate`** = `5.4740%`
>
> Arithmetic check on the printed `Total` row confirms the header: `Total Payment 334,707.80 = Principal Paid 328,437.40 + Interest Paid 6,270.40` for E-2; flat lines tie at `0.00 = 0.00 + 0.00`. The earlier (incorrect) extraction set **`Ending balance` = 334,707.80** and **`Principal payment` = 0.00**, which `validate_noteval` flagged with `delta = 6,270.40 = E-2 Interest payment` — the diagnostic fingerprint of a Total Payment ↔ Ending Balance swap on this layout.

> **`Class` / `Economic class` — trustee **Note Class** / **Class** labels, not the leading **CUSIP** token:** Fill **`Class`** (**primary**, **`### Distribution grid`**) and **`Economic class`** (**listing**) from the trustee’s **printed** economic tranche name — headings and column titles such as **Note Class**, **Class**, **Tranche**, **SUB**, **B-1**, **Certificate**, etc., including labels on **subtotal** / **footer** rows **above or below** a **headerless** numeric strip. **Do not** copy the **CUSIP** / **ISIN** that often **starts** each sparse **Principal Distribution Detail** / **Interest Distribution Detail** line into **`Class`** just because it is the **first** token in **`_chunks/`** — that id belongs in **`CUSIP`** / **`ISIN`** on **`### Tranche by listing`** whenever the report prints it. If a line is **only** ``CUSIP + decimals``, infer the economic class from **visible** **Note Class** / **Class** context on the **same PDF page** (or the next **`_chunks/`** page), then **Notes** once; **never** treat **CUSIP** as the class **name** for **primary**.

> **Computershare — “Sub Totals:” = per-tranche CUSIP aggregate (every class, not `SUB`):** On ruled **Principal / Interest Distribution Detail** and **Interest Distribution Detail** tables, **every** printed **Note Class** section ends with a **Sub Totals:** row — **A-R**, **B-R**, **F-R**, **SUB**, **X**, etc. The word **Sub Totals** is **accounting shorthand** (subtotal of the CUSIP listing lines in that section); it is **not** the **`SUB`** note class and **not** “subordinated notes only.” Each section: **Note Class** on the **first row** with the **first CUSIP** in **Identifier**; **continuation rows** = **more CUSIPs** for **that** class (144A / Reg S, paid-down vs active, or **split balances**); **Sub Totals:** = **sum of those CUSIP lines** for **that** **Note Class** only. When **two or more CUSIPs** split one tranche (e.g. **SUB** **87246LAA2** **43.35M** + **G8828TAA0** **8.65M** → **52M** aggregate), **primary** **`Original balance`**, **`Beginning balance`**, **`Ending balance`**, and period **principal** / **interest** come from **Sub Totals:** — **not** from a single CUSIP row. Per-CUSIP amounts → **`### Tranche by listing`** only. In **`_chunks/`** text the same label may appear **above** numeric strips — same rule. **Do not** set **`Class`** = **SUB** because **Sub Totals:** appears. **Only** use **SUB** when **Note Class** **literally** names **SUB** / **Subordinated**. **D**, **D-R**, and **D-RR** are **separate** sections each with **their own** **Sub Totals:** band. Cross-check **Section 11.1** when the chunk is headerless; re-open the PDF if **Note Class** is missing.

> **Computershare PDD/IDD — refinance-chain Sub Totals alignment (required):** Many CLO packages print **Principal Distribution Detail** and **Interest Distribution Detail** as a **vertical refinance history**: stacked **Note Class** labels (**A-R**, **A1**, **A1-R3**, **B-R**, **C-R**, **C1**, **D-R**, **CR**, **CRR**, **CR2**, …) parallel to a stack of **Sub Totals:** **$** bands. **Each distinct printed label is its own economic class** → **one primary row** in **`### Class balance table (primary)`** — **do not** treat **A-R**, **B-R**, **C-R**, etc. as non-economic "section headers" or skip them because a "live" class appears later in the chain.
>
> **`_chunks/` text-order trap:** pypdf often emits **(1)** **Identifier** / **CUSIP** lines, **(2)** the **Note Class** label stack, **(3)** **Sub Totals** **$** lines — with column headers (**Original Face**, **Period Beginning Balance**, …) **after** the numbers. **Do not** map **Original balance** or **Beginning balance** by CUSIP row order alone, by skipping **-R** labels, or by copying the **previous** class's **Original Face** onto the next label (classic **off-by-one** failure — e.g. deal **824169432** where **C-R+** rows inherited wrong **Original balance**).
>
> **Required alignment (PDD and IDD):**
> 1. On each page, collect **every** **Sub Totals:** (or class footer) **$** band — quote verbatim in **Source Text**. Count **only** bands whose **first field** is a principal **Original Face** / balance **$** for that class (ignore header/footer **Sub Totals:** lines that precede the numeric strip).
> 2. Collect **every** distinct **Note Class** string in the **label stack** on that page (PDF table order, top → bottom).
> 3. **Pair by index on the same page:** **nth** label ↔ **nth** **Sub Totals** block for **Original balance** (**first principal $** in that band on PDD), **Beginning balance**, **Ending balance**, **Principal payment**, and (on IDD) **Interest payment**. **Do not** take **Original balance** from the **nth CUSIP row's Original Face** when step 3 uses the label stack — the three blocks (**CUSIP strip**, **label stack**, **Sub Totals stack**) are separate in **`_chunks/`**; confusing CUSIP order with label order causes **mid-page off-by-one** (e.g. deal **824431650**: **B-R**–**C1** carried the **previous** class's **21M** / **72M** instead of the paired Sub Totals band).
> 4. **CUSIP** / **Identifier** rows → **`### Tranche by listing`** (and **Original Face** tie-out below); they **do not** replace step 3 for **primary** when **Sub Totals** exist for that class name.
> 5. **Multi-CUSIP (144A / Reg S):** **primary** uses the **class Sub Totals** when printed; listing rows use per-CUSIP lines. **Do not** assign the first CUSIP's **Original Face** to the second economic class in the refinance chain (e.g. deal **824431650** — omitting **A-R** shifted **384M** onto **A1**).
>
> **Verification (required before saving `02`):**
> - **Count check:** **# labels** = **# Sub Totals bands** on the page (or **Notes** once if not).
> - **CUSIP tie-out (single-CUSIP classes):** After step 3, each class's **Original balance** should equal that section's **CUSIP Original Face** when the PDF prints one CUSIP per class — if **B-R** primary shows **21M** but **88432FAS8** prints **72M**, the label↔band pairing is off by one; re-pair from the **Sub Totals stack**, not the CUSIP strip.
> - **Structured layout hint:** When **`_chunks_structured/pdd_idd_pdfplumber.md`** exists, use its **Note Class** column + dedicated **`Sub Totals:`** rows to confirm pairing — **ignore** the **tail class token** glued after a CUSIP line (that names the **next** section). Prefer pdfplumber **Original Face** on the **Sub Totals** row over positional reading of linear **`_chunks/`**.
> - **Page-break orphans:** After the label stack on a page, scan for **additional CUSIP + Sub Totals** bands **without** a matching label on that page (e.g. **88432FAU3** **1.35M** after **X** on page 3) — add **`### Tranche by listing`** (or **Notes**) so no CUSIP line is dropped.
>
> **Refinance naming (-R / -RR / numeric 2):** **-R** = refinanced once; **-RR** = twice; **CR2** = same role as **CRR** when that is what prints. Latest line (**CRR**, **D-RR**, …) often carries period cash; **CR**, **C-R**, **D** may be paid down (**0.00** period beginning on **Sub Totals**) — still **one primary row each**, mapped from **that** class's **Sub Totals**, **not** rolled into the longer name.
>
> **Preflight before saving `02`:** (a) Every **Note Class** quoted in **Source Text** appears in **primary** or **Omitted / noted**. (b) **-R** / **-RR** rows have **Original balance** from **their** **Sub Totals** band, not the next class's amount. (c) Label count = **Sub Totals** band count per page (or explained). (d) **CUSIP tie-out:** single-CUSIP classes — **Original balance** matches that CUSIP's **Original Face** when both are printed. (e) When downstream **orig_balance** QA mismatches **-R** / **B-R**+ rows, re-read step 3 — usually **off-by-one** (often mid-stack, not only at **A-R**). **`validate_noteval.py`** cross-checks IDD footer stacks against **`_chunks/`** when present.
>
> **Do not** assign class from a **tail token** glued after **Sub Totals** or a **CUSIP** line in `_chunks_structured/pdd_idd_pdfplumber.md` or linearized `_chunks/` — wrong-band tails are common (e.g. **C1-R3** after **B-R3**'s block). **C1-R3** and **C2-R3** are **different** classes — **each** gets a **primary** row. See also **Footer / stacked class labels vs CUSIP rows** below for 144A / Reg S.

> **SUB / F footer — multiple CUSIPs (do not group by footer, required):** On **PDD/IDD**, **two or more CUSIP lines** often stack **above** or **near** a **SUB**, **F**, or other **Note Class** footer in **`_chunks/`**. A **tail token** (e.g. **`SUB`**, **`F`**) glued after the **first** CUSIP's **Sub Totals** line usually names the **next** section — **not** that CUSIP's economic class. **Do not** assume **every** CUSIP in that vertical block is **SUB** (or **F**) because they appear near the same footer. **Required:** **one `### Tranche by listing` row per CUSIP**; set **`Economic class`** from **that CUSIP's own** **Sub Totals** band and **Original Face** (pdfplumber **Identifier** row + **Sub Totals:** row) — **not** from the shared footer label. **Primary SUB** (or **F**) includes **only** CUSIPs that belong to that class; **do not** roll paid-down **F** / **E** CUSIPs into **SUB** primary or sum their originals into **SUB** **Original balance**. Example: deal **824169432** — **31679NAN4** (**12M**) is class **F**, **31679NAQ7** (**34.2M**) is **SUB**; both sit near a **SUB** footer but **must not** both be tagged **SUB**. When footer wording and per-CUSIP economics disagree, trust **each CUSIP's Sub Totals + Original Face** (and listing / CDOnet tie-out), **not** the footer word alone.

> **SUB / zero coupon — Interest Distribution on IDD (when IDD exists):** On a **separate** **Interest Distribution Detail** exhibit, **SUB** (and similar subordinated lines) often show **Coupon 0.00000** but **non-zero** cash in the **Interest Distribution** column on **CUSIP** rows and on the **class Sub Totals / footer** row. Map that footer **Interest Distribution** **$** into **`Interest payment`** and **`Interest paid`** — **do not** leave **0.00** because a **period-beginning** subtotal line shows **0.00** in the interest column. **Do not** apply this rule when **Distribution Summary** / **Distribution in US$** shows **Dividends 0.00** and principal balance **declined** (see next blockquote).

> **SUB / subordinated — Distribution Summary / NVR when dividends 0 and principal balance falls (required):** When **Distribution Summary**, **Distribution in US$**, or equivalent **class-level $** table shows **Dividends** **0.00** (or blank), **0%** / **0.0000%** coupon, and **Closing / Ending / Current principal balance** **<** **Opening / Beginning / Prior principal balance**, treat **`Principal payment`** (and **`Principal paid`** in **`### Distribution grid`**) as **Beginning − Ending** for that class. Set **`Interest payment`** / **`Interest payable`** **0.00** and **`Dividend`** **0.00**. **Do not** map the trustee **Accrued Interest** / **Current Payable** column to **`Interest payment`** when the **$** equals the balance roll-forward and dividends are **0** — those labels are often residual economics, not period interest cash. **Notes** may cite waterfall **payment on the Subordinated Notes** when the same amount appears there.

> **Notes Information grid (BNY Payment Date Report / Note Valuation Report — required column map):** When the class exhibit is titled **Notes Information**, **reconstruct the column headers from the header block in Source Text** (they often wrap across lines: `Interest Due`, `Deferred Interest Due`, `Interest Paid`, `Deferred Interest Paid`, …). Map **only** by those **printed labels** — **never** by “which € amount comes after **All In Rate**” or any other **positional** rule.
> - **Interest Due** → **`Interest payable`**
> - **Deferred Interest Due** → **`Deferred interest`** (due/accrual component)
> - **Interest Paid** → **`Interest payment`** — **required** when non-zero
> - **Deferred Interest Paid** → **`Deferred interest`** (paid deferred component when that column is populated)
> - **All In Rate** → **`Interest rate`** only (the rate cell — not a money column)
> - **Beginning Principal Outstanding** → **`Beginning balance`**; **Ending Principal Outstanding** → **`Ending balance`**; **Principal Paid** → **`Principal payment`**
> **All In Rate / coupon 0.00000% on Subordinated Notes is normal** — it is **not** a signal that cash interest is zero and **not** a reason to put a non-zero **Interest Paid** figure into **`Deferred interest`**. Use the **Interest Paid** column (confirm with the **Total** row in the same column). **Forbidden:** inferring column meaning from order after the rate when headers are present in the chunk.

> **Distribution Report — Section 10.5(b) class summary (CIFC / Citibank style):** When the cover exhibit is **DISTRIBUTION REPORT** (Section **10.5(b)** indenture certification), map **by subsection label** on page 1 (and rate lines on later pages in the same package):
> - **(ii)(A)** / **Amount of principal payments to be made** — **`Principal payment`** when numeric; **`-`** → blank / **0.00**
> - **Aggregate Outstanding Amount of the [Class]** (before principal payments block) → **`Beginning balance`**
> - **Aggregate Outstanding Amount … after principal payments** — **`Ending balance`**
> - **(ii)(C) The interest payable in respect of each Class of Secured Notes** + per-class **$** lines → **`Interest payable`** (label says payable — **do not** move to **`Interest payment`** unless the PDF also prints a separate **paid** / **payment** column for secured notes)
> - **(iii) the Note Interest Rate and accrued interest for each applicable Class of Secured Notes** (OHA / Citibank **DISTRIBUTION REPORT** with subsection **(iv)** Section **11.1(a)(i)** on the same pages): per-class **rate** → **`Interest rate`**; per-class **accrued interest $** from **(iii)** → **`Interest payment`** **only** when subsection **(iv)** shows a **non-zero** matching **$** on the corresponding **accrued and unpaid interest on the Class [X] Notes** clause **(E)**, **(H)**, **(K)**, **(N)**, etc. Leave **`Interest payable`** **blank** — the PDF does **not** clearly label the **(iii)** **$** as payable vs paid; **do not** duplicate the same **$** into **both** columns. **`-`** on waterfall → **`Interest payment`** **0.00** or blank. **Notes** once (*subsection (iii); waterfall (iv) paid $ — ambiguous payable/paid wording*).
> - **(ii)(D) The payments on the Subordinated Notes** (or equivalent **payments on** subordinated / income notes) + per-class **$** → **`Interest payment`** — **required**; **not** **`Interest payable`** only
> - **(v) Applicable Periodic Rate** (or **notice setting forth the Applicable Periodic Rate**) on a later page → **`Interest rate`** per class — **read that page** via **`read_chunk_pages`** when the index or page 1 references subsection **(v)**; **do not** ship **`02`** with blank **`Interest rate`** when page 4 (or equivalent) prints **%** per class

> **Note Valuation Report — Periodic Interest Amount (required):** When the class exhibit is a **NOTE VALUATION REPORT** (Section **10.5(b)** / indenture NVR style) and prints **Periodic Interest Amount on [Class] …** with a numeric **$** for that class, map that **$** to **`Interest payment`** in **`### Class balance table (primary)`**. **Do not** put **Periodic Interest Amount** in **`Interest payable`** only while leaving **`Interest payment`** blank — on NVR this label **is** the per-class period interest line for the payment date (same authority as **Interest paid** on distribution grids). **`- $`** / dash-only → **`Interest payment`** **0.00** or blank with **Notes**. **Beginning balance** ← **Aggregate Principal Amount … as of the Calculation Date** (or equivalent); **Ending balance** ← **Aggregate Principal Amount … after giving effect to … principal payments**; **Principal payment** ← **Amount of principal payments to be made …** when a numeric **$** is printed (**`- $`** → blank / **N/A**). **Do not** substitute partial **03** waterfall class-interest **Paid** for NVR **Periodic Interest Amount** when NVR already prints the class **$**.

> **Note Valuation Report — Interest payable to [Class] Notes (indenture subsection (2), required):** When the NVR (or equivalent **Section 10.5(b)** certification) lists per-class lines **Interest payable to Class [X] Notes** / **Interest payable to the Subordinated Notes** with a numeric **$** (and **no** separate **interest paid** / **interest payment** column for that class on the same exhibit), that **$** **is** the period **interest cash** for the payment date — map it to **`Interest payment`** **and** **`Interest payable`** (same value in both columns). **Do not** leave **`Interest payment`** **N/A** / blank while only **`Interest payable`** is populated. This is **not** the general “payable-only, do not infer paid” rule — indenture NVR uses **payable to [Class]** wording for the **disbursement amount**. **`- $`** / **$0.00** → **0.00** in both columns. **Notes** once if helpful (*NVR subsection (2); no separate paid column*). Distinct from **(ii)(C)** aggregate **interest payable in respect of each Class** blocks on some **Distribution Report** covers — those stay **`Interest payable`** unless a separate **paid** column exists; per-line **Interest payable to Class A-2 Notes** **$** lines follow **this** blockquote.

> **Preference Share / Preferred Shares — primary row required (never supplementary-only):** Whenever the payment package’s **class / tranche summary** (e.g. **Note Details and Payment Summary**, **Distribution in US$**, **Payment Date Report** class grid, combined **Note Valuation Report** per-class table) lists **Preference Share**, **Preferred Share(s)**, **Preferred Shares**, or equivalent **equity** **on the same exhibit as note classes**, add **one row** in **`### Class balance table (primary)`** using the **printed label verbatim**. Map **Original balance**, **Beginning balance**, **Interest payment**, **Principal payment**, and **Ending balance** from the **same column labels** as notes (see **Note Details … stacked columns** below). **Include every printed class line on that summary** — notes **and** equity — in **primary**; count them in **`### Summary`** **Number of classes / tranches listed**. **Do not** skip equity because it is “not a note” or because waterfall **(K)** / **(L)** mentions **Preferred Shares** — **`03`** does **not** replace **`02`** for per-class economics. **`### Supplementary lines`** is **only** for **issuer-level / aggregate** items **with no class row on the summary** (e.g. deal-wide deferred interest total) — **never** park **Preference Share** / **Preferred Shares** there when that label appears **on the class summary alongside tranches**. **Interest rate** may be **blank** / **N/A** when rate-fixing pages list notes only. Equity rows may fail **principal roll-forward** arithmetic — copy **trustee figures verbatim** and **Notes** once if ending ≠ beginning − principal paid.

> **Note Details and Payment Summary — stacked columns (Owl Rock / similar distribution reports):** When the class exhibit is titled **Note Details and Payment Summary** (or equivalent) and **`_chunks/`** lists **one class per line** repeated for several **row labels** (often with **headers printed after the numbers** in pypdf order), map **by column label**, **not** by the first **From Principal Proceeds** / **From Interest Proceeds** snippet alone. Typical printed rows (wording varies slightly):
> - **Original Commitment Amount of Notes** → **`Original balance`**
> - **Aggregate Amount of Notes at the beginning of the Due Period** (or *…beginning of the Due Period*) → **`Beginning balance`**
> - **Amount of Interest Payments made to the Notes** / **From Interest Proceeds** (interest-paid column) → **`Interest payment`**
> - **Amount of Principal Payments to be made to the Notes** / **From Principal Proceeds** (principal-paid column for that vertical block) → **`Principal payment`**
> - **`Aggregate Outstanding Amount of Notes after giving effect to Principal Payments`** → **`Ending balance`** (ending **principal** outstanding — **required**; **not** **`Original balance`**, **not** **`Beginning balance`**)
> **`-`**, blank, or dash-only in the outstanding column → **`Ending balance`** **`0.00`**. **`Percentage of the Original Commitment after the Payment Date`** **`0.00%`** for a class confirms full paydown when paired with zero outstanding. When **multiple** **From Principal Proceeds** blocks appear in linearized text, use the block aligned with **Amount of Principal Payments to be made to the Notes** (same class row order as beginning/outstanding columns) — **do not** stop at the first block where seniors show **`-`** if a later block in the same column carries the redemption **$**. **Preflight:** **`Ending balance`** must match the **Aggregate Outstanding … after Principal Payments** row for that class (or **0.00** when printed **`-`** / **0%** after Payment Date).

> **Ending zero paydown — fill `Principal payment` automatically (model / pipeline):** After **`Beginning balance`** and **`Ending balance`** are set from the trustee (including **Aggregate Outstanding Amount of Notes after giving effect to Principal Payments** when that row is printed — **not** guessed), **fill `Principal payment`** for that class **only when all** of:
> 1. **`Principal payment`** is **0.00**, blank, or **N/A**
> 2. **`Beginning balance` > 0**
> 3. **`Ending balance` = 0.00** from a printed outstanding / current-principal column (**`-`** / dash in **Aggregate Outstanding … after Principal Payments** counts as **0.00**)
> 4. **Waterfall corroboration:** Section **11.1** / principal waterfall (**`03`** **`### Waterfall table`** / **`### Disbursement ladder`**, or the same pages in **`_chunks/`** when drafting **`02`**) shows **class principal** **Amount paid** for that class that **matches `Beginning balance`** within normal rounding (same economic class label / note name — exclude fees, admin, reinvestment/deposit structural lines)
>
> Then set **`Principal payment`** to that **waterfall class-principal Amount paid** (which equals **`Beginning balance`** when the match holds). **Do not** set **`Principal payment` = `Beginning balance`** by roll-forward inference alone without the waterfall match. **Notes** once (e.g. *Ending 0 after principal; waterfall principal paid = beginning*). **Do not** apply when **`Ending balance` > 0** or equals **`Beginning balance`** (flat pool — use the printed **principal payments** column on the class summary instead). **Do not** copy **`Ending balance`** into **`Principal payment`**.

> **Refinance suffix -R / -RR (and numeric 2 — CR vs CRR vs CR2, …):** See **Computershare PDD/IDD — refinance-chain Sub Totals alignment** above for the full procedure. **Quick reminder:** **one primary row per printed Note Class** (use **CR2** verbatim when that is what the trustee prints); **Original balance** and **Beginning balance** from **that** class's **Sub Totals** block (**nth label → nth block** on the same page) — **do not** roll **CRR** / **CR2** / **D-RR** amounts into **CR** / **C-R** because names share a prefix; paid-down legacy rows (**0.00** period beginning) still get their **own** primary row.

> **Footer / stacked class labels vs CUSIP rows (Computershare):** **Note Class** / subtotal labels printed **below** the CUSIP grid are **not** always **one-to-one** with “**row *n* in the grid** = **nth** label” reading down. When **144A** and **Reg S** CUSIPs belong to the **same** economic class (e.g. **A** + **83610JAA4** and **A** + **G8284JAA9**), both listing rows use **Economic class A** — **do not** map the **Reg S** line to **B1** (or the next footer label) **only** because of vertical order next to **A** / **B1** / **B2** text blocks. **After** those **A** lines, the **next** **CUSIP** row (e.g. **83610JAC0**) may still align with the trustee’s **B1** subtotal and **Class B-1** interest in the indenture — cross-check the **B1** block and waterfall wording (**Class B-1 Interest**), not assumed **B2** from grid order alone.

```markdown
# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | |
| Table name(s) as printed | |
| Currency | |
| Multi-listing tranches? | **Y** / **N** — **Y** if any economic class has **>1** printed listing line / CUSIP under the **same** label; **N** when **at most one** CUSIP per class. **Either way**, populate **`### Tranche by listing`** whenever the report prints per-class **CUSIP** / **ISIN** (see **Identifiers** blockquote). |
| Rows in **`### Tranche by listing`** (CUSIP-grain count) | Total populated listing rows (e.g. four classes × one CUSIP each → **4**; three SUB lines → **3**); **0** only when **no** per-class CUSIP/ISIN is printed |
| Max CUSIPs under one economic class label | Max over classes of “lines under one **economic** class label” (e.g. SUB with three lines → **3**) |
| Total payment / total amount payable (if stated) | |

> **Money cells — omit currency symbols in Extracted Data:** In **`## Extracted Data`** tables (**`01`–`04`**), put **plain numbers** in amount columns (**no** leading **€**, **$**, **£**, etc.) — preserve grouping and decimals as printed (e.g. `2,463,864.43` or trustee-localized separators). Record the deal currency once in **`### Summary`** **Currency** (and **`01`** when the template has **Currency** / **Document routing**). **`## Source Text`** stays **verbatim** from **`_chunks/`** (symbols may appear there).

> **Non-numeric placeholders (`02` and `03` — pipeline):** When the PDF puts **any non-numeric word or token** where **money**, a **fee amount**, or a **numeric interest rate** is expected — not only **Residual** — e.g. **Residual**, **Nil**, **Various**, **N/A**, **n/a**, **TBD**, **Pending**, **None**, **--**, dash-only cells, or other **trustee / OCR placeholders** with **no** parseable number (and for **rates**, no digits/**%**-style accrual), use **`N/A`** or leave the cell **blank** (money columns may use **`0.00`** when zero is correct). **Do not** copy those literals into **`02`** / **`03`** **Extracted Data** cells meant for ETL/XML (**`Interest rate`**, **`Interest payment`**, waterfall **Amount paid** / **payable**, etc.). **Legitimate rate text** with digits or **%** (e.g. **5.2500%**, **SOFR + 450 bps**) stays **verbatim** per **Interest rate (accrual)**. **`## Source Text`** still quotes the trustee **verbatim**. Optional **Notes** once.

> **Total payment / total amount payable (Summary only):** When the **same exhibit** as the class / voucher / distribution table prints a **single trustee aggregate** for the payment (e.g. *Total Payment*, *Total Amount Payable*, *Total Cash Distribution*, *Total distribution*, voucher **total line** summing **Total amount payable** across classes), capture it in **`Total payment / total amount payable (if stated)`** under **`### Summary`**. Use **N/A** when no such line exists. **Do not** copy a figure from **`03`** waterfall **unless** the PDF repeats that same total on the class / voucher page; if ambiguous, **N/A** and quote the line in **`02` Source Text**. **`Ending balance`** on class rows stays **principal only** — do not put this aggregate in the **Ending balance** column.

### Class balance table (primary)
| Class | Original balance | Beginning balance | Interest rate | Interest payment | Interest payable | Principal payment | Principal payable | Deferred interest | Dividend | Ending balance | Notes |
|-------|------------------|-------------------|---------------|------------------|------------------|-------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | |

> **`Class` — printed tranche name (required):** Copy the trustee **Note Class** / **Class** / **Tranche** cell **verbatim** from each row (punctuation, **Note**/**Notes**, **Holder**, **Reinvesting**, hyphenation). **Do not** normalize to internal shorthand (**SUB**, **M**, **A-1**, **RH**) unless the **PDF prints exactly that** on that row. One **primary** row per **printed** label unless the template’s multi-listing rules place CUSIP lines in **`### Tranche by listing`**. **`### Tranche by listing`** **`Economic class`** uses the same rule when populated. **Preference Share / Preferred Shares** on the class summary = **one primary row** (same rule as **Class A Notes** — not **`### Supplementary lines`**).

> **Sanity check before you ship `02`:** Scan **`### Class balance table (primary)`** (and **`### Tranche by listing`** when it has **data** rows): if senior / mezz rows show **0.00** or blank **`Interest rate`** / **`Interest payment`** while **`## Source Text`** includes a non-zero **interest** exhibit **or** a **rate-fixing / coupon** exhibit for those classes, the merge failed — fix **Dual exhibits** + **third-table rate** mapping, not validation-only **Notes**. **Also:** if **`Principal payment`** matches **Beginning balance** (or **Ending balance**) for a class but **`## Source Text`** **Principal Distribution Detail** shows **0.00** (or blank) for **period** principal **paid** / **distributed** while balances are unchanged, you mapped a **balance** (or wrong column) into **`Principal payment`** — fix per **PDD balance ≠ principal paid** below; **`validate_noteval`** **principal roll-forward** flags this pattern. **Also:** if **`## Source Text`** lists **Preference Share** / **Preferred Shares** on the **class summary** but **primary** has **no** matching row, extraction is **incomplete** — add the primary row; do **not** leave equity **only** under **`### Supplementary lines`**.

> **Interest rate (accrual):** Per-class **rate used to accrue interest** for the period (or as-of the report), copied **verbatim** from the exhibit when it is a **numeric rate** (e.g. **%**, **bps**, or **SOFR + spread** when printed as the all-in accrual). When the coupon / rate cell is **any non-numeric word or placeholder** (no digits / meaningful **%** accrual), use **`N/A`** or **blank** in **`Interest rate`** (see **Non-numeric placeholders** above) — **do not** store arbitrary trustee words as the rate string for ETL. PDF headings vary — common labels include **Interest rate**, **All-in rate**, **Coupon**, **Coupon rate**, **Current rate**, **Note rate** — map them all into this single column **`Interest rate`**. **Interest Distribution Detail:** when that grid prints **Coupon** / **Coupon rate** / **Annual coupon** (or similar) **per class/CUSIP**, that value **is** the **`Interest rate`** cell for the merged row — **always** copy it into **primary** (do not treat coupon as “display only”). **Dual exhibits + optional rate-fixing page:** if **(B)** has no coupon column, use **(C)** or whichever other exhibit carries the accrual (see blockquotes **Dual exhibits** and **Interest rate — third table**). **Tip:** On many CLO / note-valuation class tables, **coupon rate** (or **Coupon** / **Annual coupon**) **is** the tranche **interest rate** for the period — when that column is the printed per-class accrual, fill **`Interest rate`** from it (same semantics as a heading literally named *Interest rate*). If the report prints **both** a base index and a spread **and** a single combined all-in figure, prefer the **printed all-in / combined** accrual rate; otherwise concatenate or use **Notes** once. Leave **blank** / **`N/A`** when the trustee does **not** print a per-class accrual rate **anywhere** in the captured payment-package class exhibits (and **Notes** “no printed rate”). **Equity / subordinate** classes often print **no** meaningful **Coupon** and may show **0%** (or an empty rate cell) **while still paying cash interest** on **Interest Distribution Detail** — copy **Coupon** **as printed** for what it is, but **still** merge **cash interest** and (when printed) **all-in** / **effective** rate from the **interest** exhibit per **Subordinated (SUB) notes**; do **not** treat **0%** coupon alone as “no interest” or an extraction completeness issue. **Downstream QA** (outside this template) may apply business rules for those tranches.

> **Interest payment vs Interest payable:** **`Interest payment`** = cash **paid** / distributed to the class for the period (labels vary: *interest paid*, *interest distribution*, *payment*, settled amount). **`Interest payable`** = amount **due** / **accrued** / contractually **payable** for the period. When the PDF prints **only** payable / due / accrued and **no** paid amount (or paid is genuinely zero while payable is positive), leave **`Interest payment`** **blank** or **`N/A`** / null — **do not** copy payable into payment — **except** when **Dividend / Accrued Dividends with no Interest paid** applies (dividend-style **$** with **Interest paid** **0.00** → map dividend to **`Interest payment`**), or when **Note Valuation Report — Interest payable to [Class] Notes** applies (indenture subsection **(2)** per-class **Interest payable to … Notes** **$** → fill **both** **`Interest payment`** and **`Interest payable`** — that label **is** the period interest cash). When the PDF prints **both** paid and payable columns on a **grid** exhibit, fill **both** separately. Copying payable → payment is allowed **only** when the report clearly uses one figure for both concepts (NVR **Interest payable to**, **Periodic Interest Amount**, etc. — say so once in **Notes**).

> **Subordinated (**SUB**) / equity-style notes — coupon 0% or N/A is normal; still capture cash interest:** Indentures often show **Coupon** **0**, **0.00%**, **N/A**, or blank for **subordinated** tranches while **Interest Distribution Detail** still prints **non-zero cash interest** in another column (paid / distribution / “interest” amount, sometimes **after** a run of **0.00** cells on the same row). **Business rule:** **zero or not-applicable coupon does not imply zero interest.** Never infer **`Interest payment`** = **0** from the coupon column alone. Always take **`Interest payment`** / **`Interest paid`** / **`Interest payable`** from the **interest** exhibit using **printed column titles** (or the **same column index** as sibling senior lines **on that same IDD grid**, when headers are consistent). **`Interest rate`:** when **Coupon** is **0** / blank but the row prints an **all-in** / **effective** / other **percentage** that matches the economics, use that value for **`Interest rate`** (and **Notes** once, e.g. *Coupon 0%; cash interest and all-in rate from IDD*) so downstream knows this is **instrument design**, not a missing field. **Preflight (dual PDD + IDD):** in **`## Source Text`**, find the **SUB** (or **sub**) **CUSIP** line on **Interest Distribution Detail** and confirm **`Interest payment`** in **`### Class balance table (primary)`** / **`### Distribution grid`** / **`### Tranche by listing`** matches that exhibit **before** shipping **`02`**.

> **Single exhibit — interest vs principal cash (heading-first, any layout):** For a **combined** class / NVR row, put each amount in the **`02`** column that matches the **trustee column title** (or the **shared header row** used by sibling classes on the same exhibit) in **`## Source Text`** — e.g. headings **Interest Payment** / **Interest paid** / **Interest distribution** map to **`Interest payment`** or **`Interest payable`** per that label; **Principal Payment** / **Principal distributed** / **Principal paid** map to **`Principal payment`** or **`Principal payable`**. **Trustee column order is not standardized** across deals; **do not** infer interest vs principal from **horizontal position alone**, from the **markdown template column order**, or from how another deal’s PDF lined up. **Do not** copy an amount that sits under an **interest**-headed column into **`Principal payment`** (or the reverse) because a different report stacks columns differently. **Accrual-day integers** (**No. of Days**, **Days in period**, etc.) are **not** money — **never** map them into **`Interest payable`** or any other amount column (see **`noteval_extractor/SKILL.md`** Step 4, **Day counts**). When headers are missing or OCR-garbled, infer cautiously and **Notes** once — still **never** treat a day-count integer as a currency cell.

> **Principal payment vs Principal payable:** **`Principal payment`** = principal actually **paid** / distributed this period. Trustee headings often read **Principal distribution**, **Principal distributed**, **Distribution of principal**, **Principal paid**, or similar **$** columns on the **principal** exhibit — when the label clearly refers to **period cash principal** (not **Original balance**, **factor**, or **pool** mechanics), map that **$** to **`Principal payment`**. **Do not** map **Principal Distribution Factor** (or other **factor**-labeled cells) into **`Principal payment`**. **`Principal payable`** = principal **due** / scheduled / contractually payable. When the PDF shows **only** principal payable and **no** principal paid (or paid is blank while payable is populated), leave **`Principal payment`** **blank** or **`N/A`** / null — **do not** fabricate paid from payable. When **both** exist, fill **both**.

> **Principal Distribution Detail (PDD) — outstanding / factor ≠ period principal paid:** Some **Computershare**-style **PDD** rows repeat **notional** or **pool** **$** (often numerically equal to **Beginning** / **current outstanding** in **`02`**) and print **factor**-like values (e.g. **1000.00000000**). Those fields are **not** **`Principal payment`**. **`Principal payment`** (and **`Principal paid`** in **`### Distribution grid`**) must map **only** to the column that is **period** **principal distributed** / **paid** for that line — often **0.00** when no amortization. **Preflight:** if **Ending balance** = **Beginning balance** per trustee but **`Principal payment`** = full **notional**, re-read the PDD row against headers; **`validate_noteval`** **principal roll-forward** (`ending ≈ beg + deferred − principal pmt`) catches this. **`### Cross-checks (distribution grid)`** **Sum of principal paid** must sum **paid** principal columns, **not** outstanding balances.

> **Anti-pattern — positional dollar heuristics (forbidden as primary method):** Heuristics such as “**the last amount on the line**,” “**the next dollar column after zeros**,” “**the largest $ on the row**,” “**nth numeric after the CUSIP**,” or “**the €/$ after All In Rate / coupon %**” are **not** reliable in raw **`_chunks/`** text (headers wrap, columns mis-order, **Subordinated** rows may show **0.00000% All In Rate** beside a large **Interest Paid**). **Do not** infer **`Interest payment`**, **`Deferred interest`**, or **`Principal payment`** from those shortcuts. **Required approach:** read the **header block** (even if split across lines), assign each amount to the column whose **title** matches, and use the **Total** row to verify column alignment. Positional guesses are allowed **only** when **no** header words can be matched anywhere on the page — **Notes** once, and still **never** treat **0% All In Rate** alone as “no interest paid.” See **Subordinated (SUB) notes** and **Notes Information grid** above.

> **Beginning balance and Ending balance (principal):** Copy **Beginning balance** and **Ending balance** **exactly** from the trustee’s printed class / summary row (labels vary: *prior / current*, *beginning / ending*, *outstanding*, *principal balance*, etc.). When **`### Distribution grid`** (or **Distribution in US$** in **Source Text**) is present, **`Ending balance`** = **`Current principal balance`** and **`Beginning balance`** = **`Prior principal balance`** for that **Class** (same row on the **$** table). **Do not** recompute, adjust, or “correct” **Ending balance** from other columns (e.g. beginning ± principal paid ± interest). **Do not** put **Original balance** into **Ending balance** when **Current principal balance** is printed. If printed columns do not arithmetic-tie, keep the trustee figures and explain once in **Notes** — the **Ending balance** cell must reflect the **report**, not a derived value.
>
> **Multi-listing (primary row for a class that also has listing rows):** Prefer a **verbatim** trustee **class / subtotal** row (e.g. one **SUB** line with combined **Ending balance**). If the PDF has **no** printed combined row, the primary **SUB** (etc.) row may carry **Notes**-documented **derived** totals (**sum of listing `CUSIP line id` rows**) or leave amounts blank and point to **`### Tranche by listing`** — per multi-listing rules **before** this template; state the convention in **`04_extraction_summary.md`** once.

> **Identifiers — ISIN / CUSIP (listing-first, required when printed):** **`### Class balance table (primary)`** and **`### Distribution grid`** **do not** include **ISIN** or **CUSIP** columns — fill **economic `Class`** and numeric fields only. Put **ISIN** and **CUSIP** in **`### Tranche by listing`** (**one row per printed security line**) **whenever the report prints them** — including **one CUSIP per class** on **Distribution Summary**, **Termination Report**, **Distribution in US$**, PDD/IDD, etc. **Multi-listing = N** does **not** exempt identifier capture; it only means **one** listing row per economic class. Use **two columns** in listing (nullable per identifier). **ISIN:** typically **12** characters (e.g. `XS…`, `US…`). **CUSIP:** **9** alphanumeric characters. When the PDF prints only one identifier, put it in the matching column and leave the other **blank**. Deal- or cover-level IDs stay in **`01`** **Document routing**. **Do not** reintroduce **ISIN**/**CUSIP** columns into **primary**. **Do not** leave identifiers **only** in **Source Text** — downstream **XML export** and **tranche mapping** read listing only. Include **Original balance** in **primary** when the report shows it at class level; per-line originals may also appear in **listing**.

> **Database / warehouse mapping:** Use **primary** **`Class`** as the **economic tranche / class name**. Use **`### Tranche by listing`** for **security-grain** loads and **tranche_id** resolution: join on **`Economic class`** (same as **primary** **`Class`**) plus **`ISIN`** and/or **`CUSIP`** when populated, **`CUSIP line id`** as a **stable key** within this **`02`** file, and **`Listing / program`** (144A / Reg S / AI, etc.) when needed. **Do not** read **ISIN**/**CUSIP** from **primary** — only from **listing**.

>
> **Deferred interest:** Map the trustee’s **deferred interest** for each class from the class / NVR table — labels vary (**Interest Deferred Payable**, **Deferred Interest**, **Default / Deferred Interest Payable**, combined PIK columns, etc.). Use **one** column (**Deferred interest**) for the amount the PDF attributes to deferred interest on that tranche; if the report prints **two** deferred-style columns, choose the cell that matches the heading for *interest* deferred (or document both in **Notes** with a single primary cell). **Issuer-level or aggregate** deferred (not on a class row) — add **`### Supplementary lines`** entries or **Notes** under **`02`**; there is **no** separate **`05`** deliverable. **Do not** use **`### Supplementary lines`** for **Administrative Expenses** or other **fee** / **waterfall** cash — those belong **only** in **`03`** (**`### Administrative Expenses grid`**, **`### Waterfall table`**, **`### Valuation-relevant fees`**).

> **Dividend / Accrued Dividends with no Interest paid (any tranche label):** When **that class row** on the **class / trustee summary / Payment Date Report** exhibit prints a **non-zero** dividend-style **$** (**Accrued Dividends**, **Accrued dividend**, **Dividend**, **Income distribution**, **TOTAL PAYABLE**, etc.) and the **Interest paid** column on **that same class table** is **0.00** or blank, map the dividend **$** to **`Interest payment`** and **`Interest payable`** (and **`Interest paid`** in **`### Distribution grid`** when used) — **not** to template **`Dividend`**. Applies regardless of printed class name — e.g. **Subordinated Notes**, **SUB**, **M Notes** / **Class M**, **Income Notes**, **Preferred Return** equity-style lines. Leave **`Dividend`** **blank** / **`0.00`** / **`N/A`** and **Notes** once. **Do not** duplicate the same economic **$** in both **`Interest payment`** and **`Dividend`**.

> **`02` class table ≠ `03` waterfall Paid (default):** **`Interest payment`** on the class / Distribution Summary exhibit is **authoritative** when that table prints a **non-zero Interest paid / Interest payment** column. **Exception — SUB / subordinated with blank Interest paid but waterfall cash:** When **Interest payment** / **Interest paid** on the **class table** is **0.00** or blank **and** the **interest-proceeds** waterfall ( **`03`** **`### Waterfall table`**, **`### Disbursement ladder`**, or **`### Other waterfall lines`**) shows **non-zero** **Payment** / **Amount paid** on a line to **Holders of the Subordinated Notes** (or equivalent sub noteholder distribution on the **interest** ladder — e.g. U.S. Bank clause **(V)**, Computershare **(R)** remaining interest to subordinated, **payment on the Subordinated Notes** on **interest** proceeds), **fill `Interest payment`** (and **`Interest paid`** in **`### Distribution grid`**) from that **interest-waterfall** **$** — **required** when **`03`** is available. **Do not** leave **`Interest payment`** **0.00** when only **Amount Current Payable** / **TOTAL PAYABLE** is non-zero **if** the interest waterfall already shows the **paid** sub cash (often **less than** total payable when principal-waterfall **(R)** also pays sub noteholders). **`Interest payable`** may still come from **Current Payable** / accrued columns on the class table. **Do not** use **principal-proceeds** residual / incentive **(U)(ii)** / duplicate sub lines for **`Interest payment`** when the **interest** ladder already paid the same sub cash — **except** the **IRR hurdle** rule below. When the class table shows **Accrued Dividends** / **TOTAL PAYABLE** with **Interest paid** **0.00** **and** there is **no** matching sub line on the **interest** waterfall, use the **Dividend / Accrued Dividends** rule above.
>
> **`02` waterfall-only package (no PDD / IDD / class $ table — required):** When the PDF prints **only** **Section 11.1** (or equivalent) **Interest Proceeds** + **Principal Proceeds** clause ladders with trailing **`$`** pairs and **no** per-class balance / **Distribution in US$** exhibit, fill **`### Class balance table (primary)`** from those ladders: **one row per distinct printed class / payee name**; **`Amount paid`** at each step = **first** **`$`** on that clause line; **`$0.00` `$X`** on later lines = **running balance** (nothing paid at that step). Quote full label stacks + **`$`** bands in **`## Source Text`**. Document in **Summary** that balances / rates / CUSIPs are not printed.
>
> **SUB IRR hurdle on principal proceeds (required):** Clauses **to the Holders of the Subordinated Notes until … Internal Rate of Return** (mirror **(V)** on **11.1(a)(i)** and **(T)** on **11.1(a)(ii)**) pay **return / hurdle economics** — map non-zero **first `$`** to **`Interest payment`**, **not** **`Principal payment`**, **even when** the cash comes from **Principal Proceeds received** and the line sits on the **principal** ladder. **Do not** classify as **`Principal payment`** just because the source pool is principal proceeds (failure: **830482172** — **625,000.00** at **(T)** is sub **interest**, not principal). **`Principal payment`** on secured-note rows from **11.1(a)(ii)** applies only when the clause pays **principal** on that class (redemption / amortization), not when it pays **accrued and unpaid interest on** **Class A-1** / **A-2** / **B** from the principal pool (**$0.00** paid at those steps when **`$0.00` `$625,000.00`** shows running balance only).
>
> **Inclusive amounts — do not double-count:** When the PDF makes clear that one printed figure **already includes** another (e.g. **Interest payment** embeds the **Deferred interest** component, or **Ending balance** includes accrued/deferred interest while **Deferred interest** is still shown as a **breakout**), copy **both** cells **verbatim** and explain once in **Notes** (e.g. “162,351.94 includes 42,596.17 deferred per trustee”). **Do not** add those columns together as if they were separate, non-overlapping pieces of the same total — they are **not** additive. The same rule applies to any other **nested** disclosure (sub-line + total line). In **`04` Cross-checks**, do not imply **Interest payment + Deferred interest** (or similar) as a gross total when one column is **inclusive** of the other.
>
> **Balances and amounts:** Use plain numeric cells (no embedded `(N)` in the number). Put IO / notional / structural commentary in **Notes**. **Ending balance** stays **as printed** (see blockquote above).

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| | | |

> **Administrative / valuation fees — not here:** Do **not** copy **Administrative Expenses**, trustee / collateral admin / management fees, or other **payment-package fee** lines into this table. Those amounts are **`03`** (waterfall / optional admin grid) and **`05`** (fee roll-up after **`map_valuation_fees.py`**). **Reserve** **`### Supplementary lines`** for **issuer-level or balance-sheet–style** disclosures **not** on a class row (e.g. aggregate deferred interest), **not** for duplicating fee grids from the admin section or Section 11.1. **Do not** put **Preference Share**, **Preferred Shares**, or any **class / tranche line that appears on the same summary table as notes** here — those belong in **`### Class balance table (primary)`** when the report includes them.

### Distribution grid (optional — e.g. “Distribution in US$”, prior/current principal, interest paid)
> **Prior / current principal → Beginning / Ending:** **`Prior principal balance`** on this grid is **beginning principal** for the period → copy into **`Beginning balance`** in **`### Class balance table (primary)`** (and **listing** when used). **`Current principal balance`** is **ending principal** → copy into **`Ending balance`**. Mirror the same pair in this subsection when you fill **`### Distribution grid`** from **Distribution in US$**.

> **Dual *Principal* vs *Interest* distribution pages:** When the trustee prints **two** tables, map **`Principal paid`** / **`Principal payable`** (and prior/current principal balances) from the **principal** table and **`Interest paid`** / **`Interest payable`** from the **interest** table; put **`Interest rate`** from the **interest** table’s **Coupon** / **Coupon rate** / **Annual coupon** / **Note rate** column when present for that row, else from **whichever** table prints the accrual (including a **third** **Interest Rate Fixing**-style page — see **Interest rate — third table** under **Dual exhibits**), and carry the same merged **`Interest rate`** into **`### Class balance table (primary)`** (see **Dual exhibits**).

> **Interest rate:** When this exhibit prints a per-class accrual / **all-in** rate (including **Coupon** / **Coupon rate** when that column is the printed accrual), copy it into **`Interest rate`** here **and** carry the same merged values into **`### Class balance table (primary)`** **`Interest rate`** for the matching **Class** row (see **Dual exhibits**). Do **not** use this subsection as the **only** place the rate appears when the primary table has an **`Interest rate`** column. **0%** / blank in the **Coupon** column on **SUB** / **subordinated** rows is common — still carry **cash interest** from the **interest** **$** columns; when **Coupon** is **0** but another column prints the **economic** rate (**all-in** / **effective**), use that for **`Interest rate`** and **Notes** once (see **Subordinated (SUB) notes** in **Class balance table** blockquotes).

> **Interest paid** / **Interest payable** and **Principal paid** / **Principal payable:** Same null rules as the primary class table — payable-only or paid-only columns are fine; leave the unused paid or payable cells blank / `N/A` rather than inferring — **except** indenture NVR **Interest payable to [Class] Notes** lines map the same **$** to **Interest paid** and **Interest payable** (see **Note Valuation Report — Interest payable to [Class] Notes** above).

| Class | Prior principal balance | Current principal balance | Interest rate | Principal paid | Principal payable | Interest paid | Interest payable | Other columns (name + value) | Notes |
|-------|------------------------|---------------------------|---------------|----------------|-------------------|----------------|------------------|------------------------------|-------|
| | | | | | | | | | |

### Cross-checks (distribution grid, if used)
| Check | Value |
|-------|-------|
| Sum of principal paid (detail) | |
| Stated total (if any) | |
| Match? (Y/N / partial) | |

### Tranche by listing (security identifiers + multi-CUSIP / 144A / Reg S / AI slices)
Use **whenever the report prints a per-class or per-line CUSIP/ISIN**, and **always** when the **same economic class** appears on **multiple** CUSIP rows (Computershare-style, 144A / Reg S / AI, etc.). **One row per printed security line** — if the PDF shows **N** lines for class **SUB**, this subsection has **N** rows for **SUB** (not one rolled-up row). When **Multi-listing = N** but each class has **one** printed CUSIP (e.g. U.S. Bank **Distribution Summary** with **Issue Name | CUSIP | …**), still add **one listing row per class** with that CUSIP. The **primary** table holds class economics; **listing** holds identifiers (and may mirror economics for audit).

> **When Multi-listing tranches? = N with printed CUSIPs:** Populate listing with **one row per class** — **`Economic class`** = primary **`Class`**, **`CUSIP`** / **`ISIN`** from the report, **`Listing / program`** blank or **`CUSIP on class row`**. Economics columns may mirror **primary** or repeat key fields from the same exhibit row.

> **When no per-class CUSIP/ISIN is printed:** Omit **`### Tranche by listing`** or leave it without data rows; **Summary** listing row count = **0**.

> **CUSIP line id (required on every populated row in this subsection):** Machine-stable key for downstream ETL and deduplication. **Must be unique within this `02` file** (no duplicate ids). **CUSIP** stays the trustee’s identifier from the PDF; **`CUSIP line id`** is an extra surrogate so pipelines can reference a row even when **Economic class** repeats or extraction order drifts. Pick **one** scheme and document it once in **`04_extraction_summary.md`** or **`Notes`**: (**A**) Monotonic ids **`L001`**, **`L002`**, … in the same order as the PDF / Source Text; (**B**) Composite ASCII id, e.g. **`{YYYYMMDD}-{class_slug}-{CUSIP}-{seq}`** (`20260420-A2R-26829CBA4-01`); (**C**) a printed trustee row key if the report provides one. If two rows would collide, extend with **`-a` / `-b`** and explain in **Notes**.

| CUSIP line id | Economic class | Listing / program | ISIN | CUSIP | Original balance | Beginning balance | Interest rate | Interest payment | Interest payable | Principal payment | Principal payable | Deferred interest | Dividend | Ending balance | Notes |
|---------------|----------------|-------------------|------|-------|------------------|-------------------|---------------|------------------|------------------|-------------------|-------------------|-------------------|----------|----------------|-------|
| | | | | | | | | | | | | | | | |

### Cross-checks (multi-listing, if used)
> **When `### Tranche by listing`** has **no** data rows:** Omit this subsection **or** mark each check **N/A**.

| Check | Result |
|-------|--------|
| **`CUSIP line id`** values all unique (no duplicates) | |
| Sum of principal (or notional) across listing rows vs primary tranche / PDF | |
| Match? (Y/N / partial) | |

## Completeness Checklist
- [ ] Every class row from the primary table captured (or explicitly listed as omitted with reason)
- [ ] **Distinct printed class names:** every **different** trustee **Class** / note **name** (exact string after trim) has a **primary** row — **do not** skip because a name is similar to another (**Exact printed class name — same vs different** blockquote above). **Identical** names on **>1** line → **Multi-listing** + **listing**, not extra **primary** rows.
- [ ] **Computershare PDD/IDD refinance-chain:** Every distinct **Note Class** in the PDD/IDD label stack (**A-R**, **B-R**, **C-R**, **-RR**, …) has a **primary** row; **Original balance** aligned **nth label → nth Sub Totals band** on the same page — **not** from CUSIP strip order; **CUSIP tie-out** (single-CUSIP classes: **Original balance** = that CUSIP's **Original Face**); page-break orphan CUSIPs captured in **listing**; **Source Text** quotes full label stack + **Sub Totals** bands (**Computershare PDD/IDD — refinance-chain Sub Totals alignment** blockquote)
- [ ] **SUB / F footer — multiple CUSIPs:** When **>1 CUSIP** appears near a **SUB** / **F** footer, **each CUSIP** has its own **listing** row with **`Economic class`** from **that CUSIP's Sub Totals** — **not** both tagged **SUB** because of the footer (**SUB / F footer — multiple CUSIPs** blockquote; e.g. **824169432** **31679NAN4** = **F**, **31679NAQ7** = **SUB**)
- [ ] **Class** and economics correct in **primary** / **distribution** (**no** **ISIN**/**CUSIP** there); **`### Tranche by listing`** has **ISIN** / **CUSIP** for **every** printed per-class security line (**Multi-listing** **Y** or **N**); deal-level IDs in **`01`**
- [ ] **Database mapping:** Plan ETL joins from **primary** **`Class`** to **listing** **`Economic class`** + **`ISIN`** / **`CUSIP`** / **`CUSIP line id`** (and **`Listing / program`**); identifiers for load **not** taken from **primary** (see **`extraction-templates.md`** **Database / warehouse mapping**)
- [ ] **Original balance** when the report prints it (or N/A with reason)
- [ ] **Beginning balance** and **Ending balance** taken **directly** from the report; when **Distribution in US$** / **`### Distribution grid`** exists, **Ending balance** = **Current principal balance** and **Beginning balance** = **Prior principal balance** per class — **no** recomputed ending principal and **no** **Original balance** in **Ending balance**
- [ ] **Distribution in US$ wide voucher (US Bank / Deutsche / Computershare):** **header reconstructed before reading data** — camel-jammed wrapped headers split into column titles, split **verified by `Total` row arithmetic** (`Total Payment = Principal Paid + Interest Paid`; `Ending = Beginning − Principal Paid` on non-zero rows), and every **`02`** field copied **by title** (Beginning Principal Balance → **`Beginning balance`**, Ending Principal Balance → **`Ending balance`**, Principal Paid → **`Principal payment`** — **not** Total Payment, **not** Optimal Principal, **not** by left-to-right position or `$` sigil). **`### Column mapping`** in **`## Extracted Data`** records the as-printed → template mapping. See **Distribution in US$ — wide voucher header reconstruction** blockquote and the `825496775` **E-2-144A** worked example
- [ ] **`02` self-validation loop run:** `python noteval_extractor/scripts/validate_noteval.py <output-dir>` executed after writing **`02_tranche_class_balances.md`**; **`validation_report.md`** read; any **Rule 5 (principal roll-forward)** warning on a **Distribution in US$** row treated as a **header reconstruction failure** (typical fingerprint: single-class delta = that class's **`Interest payment`** = Total Payment ↔ Ending balance swap), fixed by re-splitting the header and re-mapping by title, then validator re-run until Rule 5 passes (or the failure documented in **Notes** with the trustee's own non-tying line quoted)
- [ ] **`Interest payment`** / **`Interest payable`** on each class row come from the **interest** exhibit when **Principal** and **Interest** distribution tables are separate; **`Interest rate`** **first** matches **Coupon** / **coupon rate** on **Interest Distribution Detail** when that column (or the **first percentage-like field after balance** on headerless lines) is populated — else **whichever** other exhibit prints the accrual — including a **third** **Interest Rate Fixing** / **floating-rate** page when present — **not** spurious **0.00** / blanks copied only from a **principal-only** grid when the **interest** line shows a **non-zero** coupon or interest for that class (**Dual exhibits**); **Notes** only for true trustee **zero** / non-accrual cases
- [ ] **Interest rate third-table pass:** **`_page_index.md`** / chunks searched for **rate-fixing** / **benchmark** exhibits when **Interest Distribution Detail** has **no** **Coupon** column; when **(B)** prints **Coupon** / **coupon rate**, **`Interest rate`** is filled from **(B)** (**not** left blank after merging only principal + interest **$** tables)
- [ ] **`Interest rate`** is **not** **`Interest type`** only (**Floating** / **Variable** / **Fixed**) — use **numeric** **Coupon** / **Spread** / **%** / rate-fixing columns (**`Interest rate` — not `Interest type`** blockquote)
- [ ] **Interest payment**, **Interest payable**, **Principal payment**, **Principal payable**, **Deferred interest** (per tranche, from the PDF class table — see column notes), and **dividend** captured when the report includes them (or blank / N/A with reason); **payment** cells may stay blank when the PDF is **payable-only** (do not infer paid from payable); if one column **includes** another (e.g. interest includes deferred), **Notes** once — **no** spurious sum of overlapping components
- [ ] **Separate principal vs interest distribution exhibits:** When the trustee prints **two** grids (e.g. *Principal Distribution Detail* + *Interest Distribution Detail*) for the **same** period and CUSIPs, **`### Class balance table (primary)`** (and **`### Distribution grid`** when used) **must combine both** — **`Principal payment`** / **`Principal payable`** (and principal balances) from the **principal** table; **`Interest payment`** / **`Interest payable`** from the **interest** table; **`Interest rate`** from **Interest Distribution Detail** **Coupon** / coupon-like field **when present** — else **whichever** table prints the accrual for that row (often a **third** **Interest Rate Fixing** page); **Source Text** must quote **principal**, **interest amount** (including **coupon** column or position on sparse lines), and **rate-fixing** (when used) page blocks (see **Dual exhibits** rule above)
- [ ] **SUB / subordinated — Distribution Summary (dividends 0, balance down):** When **Dividends** are **0.00** and **Ending** principal **<** **Beginning**, **`Principal payment`** = **Beginning − Ending**; **`Interest payment`** / **`Interest payable`** **0.00** (see **SUB / subordinated — Distribution Summary** blockquote)
- [ ] **SUB / subordinated — IDD (when present):** **Interest Distribution Detail** footer **Interest Distribution** **$** mapped when **non-zero** and **not** overridden by Distribution Summary principal rule above
- [ ] **Dividend without Interest paid:** Non-zero **dividend** with blank **Interest paid** → **`Interest payment`** from dividend **$**; when **Dividends** are **0.00** on Distribution Summary, **`Dividend`** **0.00** and use principal rule above if balance fell
- [ ] **PDD — principal paid vs balance:** When **Ending** **<** **Beginning**, **`Principal payment`** may equal the roll-forward even without a **Principal Repayment** line; when balances are **flat**, do **not** copy ending balance as **`Principal payment`**; run **`validate_noteval`**
- [ ] **`Interest rate`** in **`### Class balance table (primary)`** populated whenever the PDF prints an accrual / coupon / all-in rate for that class on **any** merged exhibit — **not** only in **`### Distribution grid`** / listing while primary stays blank (unless the PDF truly omits a class-level rate and **Notes** explain)
- [ ] **Supplementary lines:** only **issuer-level / aggregate** items **not** on a class row (or **N/A**); **no** **Administrative Expenses** or other **fee** lines duplicated from **`03`**
- [ ] **No `### Administrative Expenses grid`** (or equivalent fee-only table) under **`02`** — admin / fee grids belong in **`03`** only
- [ ] Totals row matches sum of detail rows (or discrepancy noted)
- [ ] Optional **Distribution grid** filled or marked N/A when the PDF has a separate class-distribution page
- [ ] **Multi-listing / multi-CUSIP:** set **`Multi-listing tranches?`** = **Y** when **>1** CUSIP/line under the **same** economic class; **N** when **at most one** CUSIP per class. **Either way**, fill **`### Tranche by listing`** with **CUSIP** / **ISIN** whenever the report prints them (**one row per PDF security line**, each with **`CUSIP line id`**); **`04`** (summary) flag **Multi-listing tranches** matches
- [ ] When **`### Tranche by listing`** has **data** rows: every row has a **unique `CUSIP line id`**; **Summary** counts (**CUSIP-grain row count**, **max CUSIPs per class**) match populated rows; **primary** class row uses **printed** class total when the PDF shows it, else **Notes** explain **derived** vs listing. When **no** per-class CUSIP/ISIN is printed, listing row count = **0** and cross-checks for listing are **N/A**
- [ ] **Total payment / total amount payable** in **`### Summary`** when the trustee prints a payment-period aggregate on the class / voucher / distribution exhibit (or **N/A** with reason)

## Source Text
(Paste full class table(s) from chunks; **Page N** per block — when **`### Tranche by listing`** is **populated**, include **each** listing block used for it (that is where **ISIN**/**CUSIP** align to amounts). When **principal** and **interest** distribution exhibits are **separate pages**, include **both** blocks (principal + interest) so the merge in **`### Class balance table (primary)`** is auditable. When a **third** **Interest Rate Fixing** / **floating-rate** (or similar) exhibit supplies **`Interest rate`**, include that block too. Preserve **PDF row order** when assigning **`CUSIP line id`** sequence unless reordering is documented in **Notes**.)
```

#### Worked example: SUB (or any class) with three printed listing lines

| Layer | Rule |
|-------|------|
| **Primary** | One row, economic class **SUB**. **Ending balance** (and other class-level columns) = **trustee-printed** combined line when the exhibit shows it (e.g. **47,950,000.00**). If there is **no** printed combined row, use **Notes**: e.g. `Derived: sum of listing L001–L003` for the affected columns, or leave primary amounts blank and point to listing — document once in **`04_extraction_summary.md`**. |
| **`### Tranche by listing`** | **Three rows** for **three** PDF lines: **`L001`**, **`L002`**, **`L003`**; **Economic class** = **SUB** on each; **CUSIP** / **Listing / program** per the PDF; numbers **copied per line**, not summed here. |
| **`### Cross-checks (multi-listing)`** | e.g. Sum of listing **Ending balance** = primary **SUB** **Ending balance** (or match stated PDF total); **Match?** **Y** / **partial** with explanation. |

#### Worked example: U.S. Bank Distribution Summary — one CUSIP per class (Multi-listing = N, listing still required)

Deal **867036019** (Termination Report): **Distribution Summary** prints **Issue Name | CUSIP | balances** on one row per class. **Multi-listing = N** (one CUSIP each), but **listing is mandatory** for identifiers.

| Layer | Rule |
|-------|------|
| **Primary** | Four rows: **Subordinate Notes**, **Senior Preferred Return Notes**, **Subordinate Preferred Return**, **Performance Notes** — economics only, **no CUSIP** column. |
| **`### Tranche by listing`** | Four rows (**L001**–**L004**): **Economic class** matches **Class**; **CUSIP** from the same exhibit row (**64133JAC8**, **64133JAE4**, **64133JAG9**, **64133JAJ3**); economics may mirror primary. |
| **Summary** | **Multi-listing** = **N**; **Rows in listing** = **4** (not **0**). |

Illustrative excerpt:

```markdown
### Summary
| Multi-listing tranches? | N |
| Rows in ### Tranche by listing | 4 |

### Tranche by listing
| CUSIP line id | Economic class | Listing / program | ISIN | CUSIP | Original balance | Beginning balance | Interest rate | Interest payment | … | Ending balance | Notes |
| L001 | Subordinate Notes | CUSIP on class row | | 64133JAC8 | 44,375,000.00 | 44,375,000.00 | 0.00000 | 545,936.22 | … | 44,375,000.00 | Distribution Summary p.3 |
| L002 | Senior Preferred Return Notes | CUSIP on class row | | 64133JAE4 | … | … | … | … | … | … | |
```

Illustrative excerpt (replace all numbers and ids with the deal’s PDF):

```markdown
### Class balance table (primary)
| Class | … | Interest rate | … | Ending balance | Notes |
|-------|---|---------------|---|----------------|-------|
| SUB | … | 0.00% or all-in from IDD | … | 47,950,000.00 | Printed SUB total on Principal Detail; **Interest payment** from **Interest Distribution Detail** even when **Coupon** is **0%** / N/A — see **Subordinated (SUB) notes** |

### Tranche by listing (optional …)
| CUSIP line id | Economic class | Listing / program | ISIN | CUSIP | Beginning balance | Interest rate | … | Ending balance | Notes |
|---------------|----------------|-------------------|------|-------|-------------------|---------------|---|----------------|-------|
| L001 | SUB | 144A | N/A | 12345ABC7 | … | 0.00% | … | 19,900,000.00 | First SUB line on p.4 |
| L002 | SUB | Reg S | N/A | 12345ABD5 | … | 0.00% | … | 17,925,000.00 | Second |
| L003 | SUB | AI | N/A | 12345ABE3 | … | 0.00% | … | 10,125,000.00 | Third |

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
| **Logical disbursement style** | “Application of … Proceeds”, `(i)`–`(v)` ladders, Computershare-style **two decimals per row** without full grid headers | **`03_interest_principal_waterfall.md`** — **`### Logical / clause waterfall`** |

A single deal can blend styles (e.g. indenture body + a small summary grid). Use the matching **`03`** subsection(s); say in **`04_extraction_summary.md`** whether the capture was **grid**, **logical/clause**, or **both**.

---

## File 03: Interest / principal waterfall

**Filename:** `03_interest_principal_waterfall.md`  
**Scope:** All **interest / principal proceeds application** belongs here: **multi-column grid waterfalls** *and* **logical / clause ladders** (indenture **Section 11.1**, Computershare **“Application of … Proceeds”**, `(i)`–`(v)` ladders with bare decimals — capture under **`### Logical / clause waterfall`** / **`### Disbursement ladder`** in this file). **Do not** create **`06_logical_disbursements.md`** for new extractions; that file is **deprecated** (see **File 06**). If a deal prints **both** a grid and a clause ladder, use **both** subsections in **`03`**; avoid pasting the same **Source Text** twice — cross-reference in **Notes** and keep one full verbatim block. **Placeholder amounts:** Same rule as **File `02`** — if a waterfall **Amount paid** / **payable** / running cell shows **any non-numeric word or token** (not a parseable number), use **`N/A`** or blank in **Extracted Data**; keep the literal only in **`## Source Text`**.

**Wells Fargo (dual PDF — `_*_waterfall*` segmentation):** When the deal folder contains **`_chunks_waterfall/`** and **`_page_index_waterfall.md`**, the **Waterfall Calculations Report** is the **only** source for **`03`**: map pages with **`_page_index_waterfall.md`**, read **only** **`_chunks_waterfall/pages_*.txt`** for **`03` Extracted Data** and **`03` Source Text** — including **`### Waterfall table`**, **`### Valuation-relevant fees`** (the **fee-only roll-up** from that waterfall — see next paragraph), and fee-related lines in **`### Other waterfall lines`**. **Do not** copy **`03`** fee **$** or fee **Source Text** from **`_chunks/`** (note valuation PDF) when the waterfall chunk tree exists. **`01`** / **`02`** remain **`_chunks/`** only.

> **Wells Fargo — two-number rows (Waterfall Calculations Report):** In **`_chunks_waterfall/`**, many priority lines print **exactly two** currency amounts with **little or no** column header. **Default for that exhibit** (when **`### Column mapping`** does not document otherwise): **left** = **cash paid** → **`Amount paid`**, **right** = **running / remainder** → **`Amount available / running`**. Other trustees’ two-number ladders may differ — always document **this deal** in **`### Column mapping`** when not using the Wells default. **Do not** use the running/remainder column as **`Amount paid`** or for **`05`** fee roll-up.

**Wrap-up vs `02` (no duplicate class cash):** Per-class **interest payment**, **interest payable**, **principal payment**, and **principal payable** for note **classes** (A, B, SUB, etc.) are **authoritative in `02`** (primary table and/or **`### Distribution grid`**). In **`03` Extracted Data**, **do not** repeat the same class-level interest/principal lines row-by-row when they are the **same economic amounts** already captured in **`02`** for that payment date. Keep the **full** trustee priority in **`## Source Text`** (verbatim) for audit. In **`### Waterfall table`** / ladder, you may use **one** summary pointer row in **Notes** (e.g. “Class interest & principal: see **`02`**) or **omit** redundant class rows; still extract **fees**, **expenses**, **account / structural** lines, and anything **not** represented in **`02`**. **Wells Fargo:** fee and waterfall **Source Text** for **`03`** comes **only** from **`_chunks_waterfall/`** (see paragraph above).

**Valuation-relevant fees (fee-only roll-up — downstream):** **`### Valuation-relevant fees`** is **not** a separate waterfall exhibit: it is a **clean-up view of the same payment** already captured in **`### Waterfall table`** / **`### Disbursement ladder`** / **`### Logical / clause waterfall`** (and in **`## Source Text`**). **Do not** populate this roll-up from **`### Administrative Expenses grid`** — that grid is **audit / voucher tie-out** only; fee **`Amount paid`** / **Sub category** (leaf code) come **only** from the **waterfall / ladder** exhibits (reconcile voucher **gross** vs cap in **Notes** / **`04`** when helpful). **Include only** lines that are **fees** for valuation modeling — **exclude** class **interest** / **principal** (authoritative in **`02`**), **swap** / account **structural** steps, and other **non-fee** rows (**those stay** in **`### Waterfall table`** or **`### Other waterfall lines`**). **Never** label **“To the payment of … interest on the Class … Notes”**, **debt payment sequence** steps, **“Remaining … Proceeds … Subordinated Notes”** distributions, **“to the holders of the Subordinated Notes”**, **“payment on the Subordinated Notes”**, **“interest on the Subordinated Notes”**, **“Payment of remaining Interest Proceeds”** / **“Payment of remaining Principal Proceeds”** (including a **single** step that pays **both** buckets **to noteholders** / **pro rata**), or similar **note cashflows** / **proceeds distribution** lines as **`coissuer_fees`**, **`trustee_expenses`**, **`subordinate_management_fees`**, or any other **Sub category** literal — those are **not** trustee expense leaves (they belong in **`### Waterfall table`**, **`### Other waterfall lines`**, and class economics in **`02`**). **`subordinate_management_fees`** requires explicit **management** / **manager** / **collateral management** wording (e.g. **Subordinated Management Fee**) — **not** the word **subordinated** alone. **Categorize** each retained fee line (**Main category** + **Sub category**) for the next ingestion step; **amounts** must **agree** with the waterfall row you are rolling up (same period; **Notes** if the PDF only shows a lump you mapped to multiple leaves). **Computershare-style ladders:** the same priority may show **admin** twice — e.g. clause **(B)** “up to the … Cap” and later **(O)** “Administrative Expenses **not** paid pursuant to **(B)** …” with **additional** paid amounts (e.g. second **To the Bank** line) — extract **each** paid admin/fee line that maps to a leaf, **do not** drop the second block. Not every waterfall line is a “fee” for modeling. **Always** fill **`### Valuation-relevant fees`** with **only** allowed **Sub category** literals when the PDF includes them (map printed wording into the cell — see table below). **Do not** label class **interest** / **principal** distributions as fees. Other lines (**swap breakage**, generic “expenses” not in the list, **structural** steps without a matching type) stay in **`### Waterfall table`** or **`### Other waterfall lines (non-fee / structural)`**, not in **`### Valuation-relevant fees`**, unless they clearly match an allowed literal (including **`other_fees_01`**–**`03`** under **Main category** **`Other`** when applicable). **Exception — clause (Q) Note / Debt Payment Sequence:** When the ladder prints **(Q)** **make payments in accordance with the Note Payment Sequence** (or **Debt payment sequence** with the same aggregate routing semantics) with a **non-zero** waterfall **`Amount paid`**, include **one** matching row in **`### Valuation-relevant fees`**: **Main category** **`Other`**, **Sub category** **`other_fees_01`** (then **`other_fees_02`** / **`other_fees_03`** in **waterfall order** when additional **Other**-bucket lines already use earlier codes) — **do not** use **`trustee_expenses`**, **`collateral_admin_fees`**, **`coissuer_fees`**, or other **admin / management / tax / hedge** leaves for that line. **Per-class** “interest on Class … Notes” / “principal on Class …” application lines stay authoritative in **`02`** / **`### Waterfall table`** without a duplicate **fee-type** mislabel; **(Q)** is the **sequence / routing** step, not a vendor fee. **Exception — combined post-(A)(2) admin + post-(C) hedge (any priority label):** When a ladder line’s **printed text** **jointly** references **Administrative Expenses not paid pursuant to … (A)(2)** and **Hedge Agreement amounts not paid pursuant to … (C)** (or clearly equivalent wording), **regardless** of whether the trustee marks that step **(S)**, **(W)**, **(O)**, etc., include **non-zero** **`Amount paid`** in **`### Valuation-relevant fees`** — map **`administrator_expenses`** and **`fees_to_hedge_counterparty`** when **`## Source Text`** shows **separate** paid sub-amounts for admin vs hedge; **one** combined paid cell ⇒ **one** valuation row + **Notes** (prefer **`administrator_expenses`** when the line **leads** with **Administrative Expenses**). Preserve the **verbatim** priority label from the PDF in **`### Waterfall table`** / ladder. **Do not** omit that line’s paid cash because **(A)(2)** or **(C)** appeared earlier.

**Main category vs Sub category vs export key (`fee_type`):** Each fee row uses **Main category** (rollup — **Administrative expense**, **Management fees**, **Tax**, **Hedge**, or **Other**) + **Sub category** (leaf — **exact** snake_case string from the **same closed set** historically labeled **`fee_type`** in XML/DB feeds). **Display:** readers see a **two-level** label — e.g. **Tax** → **`tax_gross_amounts`**, **Administrative expense** → **`trustee_expenses`** or **`collateral_admin_fees`**, **Management fees** → **`senior_management_fees`**. **Sub category** is the **stable export key**; downstream pipelines may still serialize it as a field named **`fee_type`**. **`senior_management_fees`** and **`subordinate_management_fees`** use **Main category** **`Management fees`**. **`subordinate_management_fees`** is the **cross-deal normalized** type for junior / subordinated **management** fee lines (any CLO that pays that economics — **not** a mandate that your warehouse column is spelled identically; map in ETL if needed). **`subordinated_management_fees`** (extra *d*) is an **alternate spelling** still **accepted** in older markdown for validation; **prefer `subordinate_management_fees`** in **new** extractions. **`tax_gross_amounts`** and **`fees_to_hedge_counterparty`** use mains **`Tax`** and **`Hedge`** respectively (**not** **`Administrative expense`**, even when a warehouse groups “tax gross-up” with admin). **`hedge_fees`** is an **alternate** leaf name still **accepted** in older markdown / validation — **prefer `fees_to_hedge_counterparty`** in **new** extractions. **`coissuer_fees`**, **`trustee_expenses`**, **`collateral_admin_fees`**, and **`administrator_expenses`** use **Main category** **`Administrative expense`** — **never** **`Management fees`**, **`Tax`**, or **`Hedge`** for those literals. **`collateral_admin_fees`**: use **Main category** **`Administrative expense`** when the printed line names **collateral** … **management** / **manager** / **administrative** / **administration** / **administrator** (OCR variants) **and** **does not** name **Senior** or **Subordinate** / **subordinated** **management** in the title (see *PDF wording → `fee_type`*); **Senior** / **Subordinate** titled **collateral management** → **`senior_management_fees`** / **`subordinate_management_fees`**, not **`collateral_admin_fees`**. **Repeat** the same **Main category** on multiple rows when the PDF itemizes several leaves under that band (e.g. several **`Administrative expense`** rows with different **Sub category** values).

| Main category | Sub category values (same set as normalized **`fee_type`** / XML export leaf) |
|---------------|-----------------------------------------------|
| **Administrative expense** | **`trustee_expenses`**, **`collateral_admin_fees`** (collateral **management** / **manager** / **administrative** / **administrator** **without** **Senior** / **Subordinate** in the title — see *PDF wording → `fee_type`*), **`administrator_expenses`**, **`coissuer_fees`** |
| **Management fees** | **`senior_management_fees`**, **`subordinate_management_fees`** (includes **Incentive Management Fee** / **subordinated incentive fee** / **performance fee** per mapper — **`subordinated_management_fees`** is an **alternate spelling** (older files); same economics |
| **Tax** | **`tax_gross_amounts`** |
| **Hedge** | **`fees_to_hedge_counterparty`** — **`hedge_fees`** is an **alternate** (older files); same semantics |
| **Other** | **`other_fees_01`**, **`other_fees_02`**, **`other_fees_03`** — when **two or more** distinct fee lines belong under **Main category** **`Other`** (no better mapped leaf), assign **`other_fees_01`** / **`02`** / **`03`** in **waterfall order**. A **single** **Other**-rollup fee row uses **`other_fees_01`**. **`expense_reserve_account`** — cash paid to fund the **Expense Reserve Account** (e.g. **Payment of Administrative Expenses (if any) not received, to the Expense Reserve Account**); mapped by **`map_valuation_fees.py`**. |

**Reference — extended warehouse / standard `fee_type` vocabulary (user crosswalk):** Downstream databases or cashflow models may use a **broader** set of stable **`fee_type`** / column codes than the **allowed literals** table above. The **grouped taxonomy** below is the same master set of identifiers, organized for **warehouse / UI / ETL** — **not every deal uses every code**. Some codes overlap template literals (map **`trustee_expenses`** → **`trustee_expenses`** / **`administrator_expenses`** in **ETL**, or keep nuance in **`### Waterfall table`** text / **`Notes`** / **`04`**). For **new** markdown in **`### Valuation-relevant fees`**, **Sub category** (or legacy **`fee_type`** column) must still be one of the **allowed template literals** unless your project extends **`validate_noteval.py`**.

> **Warehouse taxonomy vs File 03 `Main category`:** The **six** bands below are **business / warehouse** groupings. They do **not** all map 1:1 to the five **`### Valuation-relevant fees`** **Main category** rows (**Administrative expense**, **Management fees**, **Tax**, **Hedge**, **Other**): e.g. **`tax_gross_amounts`** / **`deferred_tax_gross_amounts`** are **tax gross-up** in the warehouse sense but in **File 03** use **Main category** **`Tax`** (not **`Administrative expense`**). **Reserve-account** and **cure** codes often describe **account / structural** waterfall lines — keep them in **`### Waterfall table`** / **`### Other waterfall lines`** when they are **not** typed fee leaves; only lift into **`### Valuation-relevant fees`** when they match an **allowed** **Sub category** literal (same set as **`fee_type`** in validation).

**1 — Management fees** — base, senior, subordinate, incentive, successor, rebate, and **deferred** variants

- **`management_fees`** (base / generic management when distinguished from senior/sub)
- **`senior_management_fees`**, **`senior_management_fees_2`**
- **`subordinate_management_fees`**, **`subordinate_management_fees_2`**
- **`incentive_management_fees`**, **`incentive_management_fees_2`**
- **`successor_management_fees`**
- **`management_fees_rebate`**
- **`deferred_management_fees`**
- **`deferred_senior_management_fees`**, **`deferred_senior_management_fees_2`**
- **`deferred_subordinate_management_fees`**, **`deferred_subordinate_management_fees_2`**
- **`deferred_incentive_management_fees`**, **`deferred_incentive_management_fees_2`**
- **`deferred_successor_management_fees`**
- **`deferred_management_fees_rebate`**

**2 — Retention fees** — including **lettered** tranches (**A1**, **A2**, **B1**, **B2**) and numbered **`retention_fees`**, **`retention_fees_2`**, **`retention_fees_3`**

- **`RETENTION_FEE_A1`**, **`RETENTION_FEE_A2`**, **`RETENTION_FEE_B1`**, **`RETENTION_FEE_B2`**
- **`retention_fees`**, **`retention_fees_2`**, **`retention_fees_3`**
- **`deferred_retention_fees`**, **`deferred_retention_fees_2`**

**3 — Reserve accounts** — interest reserve, replenishment, reinvestment, expense (incl. reimbursement), liquidity, loss replenishment, **apex revolver**; plus **cure / diversion** labels where deals use these codes

- **`interest_reserve_account`**
- **`replenishment_reserve_account`**
- **`reinvestment_account`**
- **`expense_reserve_account`**, **`expense_reimbursement_account`**
- **`liquidity_facility`**
- **`loss_replenishment_account`**
- **`apex_revolver`**
- **`interest_diversion_cure`**, **`overcollateralization_cure`** — *often modeled with reserve / OC mechanics; classify per deal and indenture text.*

**4 — Administrative expenses** — trustee, administrator, collateral admin, co-issuer, preference share agent, **tax gross-up** (warehouse label; File **03** uses **Main category** **`Tax`** for **`tax_gross_amounts`** — see bullets below)

- **`trustee_expenses`** → map to template **`trustee_expenses`** / **`administrator_expenses`** as appropriate in **ETL**
- **`deferred_trustee_expenses`**
- **`administrator_expenses`**, **`deferred_administrator_expenses`**
- **`collateral_admin_fees`**
- **`coissuer_fees`**, **`deferred_coissuer_fees`**
- **`preference_share_agent_fees`**
- **`tax_gross_amounts`**, **`deferred_tax_gross_amounts`** — *File **03**: **Main category** **`Tax`** + **`tax_gross_amounts`** (see *Waterfall clause (A)* and **PDF wording → `fee_type`**).*

**5 — Hedge counterparty** — current (**`fees_to_hedge_counterparty`**) and **deferred** (**`deferred_fees_to_hedge_counterparty`**)

- **`fees_to_hedge_counterparty`** — *canonical template literal; **Main category** **`Hedge`**.*
- **`deferred_fees_to_hedge_counterparty`**
- **`hedge_fees`** — *alternate leaf name; **Main category** **`Hedge`** — still **accepted** in older files; prefer **`fees_to_hedge_counterparty`** in new extractions.*

**6 — Other fees** — three **bespoke / miscellaneous** buckets (**`other_fees_01`** … **`other_fees_03`**)

- **`other_fees_01`**, **`other_fees_02`**, **`other_fees_03`** — *File **03**: **Main category** **`Other`** when multiple distinct **Other**-rollup fee lines; see allowed-literals table.*

**Flat alphabetical index** (same codes as §1–§6; for quick search)

```text
administrator_expenses
apex_revolver
collateral_admin_fees
coissuer_fees
deferred_administrator_expenses
deferred_coissuer_fees
deferred_fees_to_hedge_counterparty
deferred_incentive_management_fees
deferred_incentive_management_fees_2
deferred_management_fees
deferred_management_fees_rebate
deferred_retention_fees
deferred_retention_fees_2
deferred_senior_management_fees
deferred_senior_management_fees_2
deferred_subordinate_management_fees
deferred_subordinate_management_fees_2
deferred_successor_management_fees
deferred_tax_gross_amounts
deferred_trustee_expenses
expense_reimbursement_account
expense_reserve_account
fees_to_hedge_counterparty
hedge_fees
incentive_management_fees
incentive_management_fees_2
interest_diversion_cure
interest_reserve_account
liquidity_facility
loss_replenishment_account
management_fees
management_fees_rebate
other_fees_01
other_fees_02
other_fees_03
overcollateralization_cure
preference_share_agent_fees
replenishment_reserve_account
reinvestment_account
RETENTION_FEE_A1
RETENTION_FEE_A2
RETENTION_FEE_B1
RETENTION_FEE_B2
retention_fees
retention_fees_2
retention_fees_3
senior_management_fees
senior_management_fees_2
subordinate_management_fees
subordinate_management_fees_2
successor_management_fees
tax_gross_amounts
trustee_expenses
```

**PDF wording → `fee_type` (quick map):** corporate / U.S. **trustee** line as its own paid line → **`trustee_expenses`**; when the **same printed line** names **both** **trustee** and **collateral administrator** / **collateral administration** (combined label), → **`trustee_expenses`** — **not** **`collateral_admin_fees`**; **collateral management** / **collateral manager** / **collateral administrative** / **collateral administration** / **collateral administrator** (OCR spelling variants) when the **printed title** **does not** also name **trustee** and **does not** name **Senior** or **Subordinate** / **subordinated** **management** → **`collateral_admin_fees`** (**Main category** **`Administrative expense`**); **Senior** in the title with **collateral management** (e.g. **Senior Collateral Management Fee** / **Fees**, often **clause (C)** and sometimes on the **Administrative Expenses** grid) → **`senior_management_fees`** (**Main category** **`Management fees`**) — **not** **`collateral_admin_fees`**; **Independent accountants, agents and counsel of Issuer** (and close variants: **independent accountants** + **counsel**, **agents and counsel of the Issuer**) → **Main category** **`Administrative expense`**, **Sub category** **`administrator_expenses`** — **not** **`coissuer_fees`** or **`Other`**; generic bundled **administrative expense** / counsel / rating / “other person” admin bucket (no better leaf) → **`administrator_expenses`**; **issuer** **contractual fee** (printed **Issuer fee** / **Co-Issuer fee**, not accountants/counsel professionals) → **`coissuer_fees`**; other **base / senior** management fees to the servicer (non–collateral-administration semantics) → **`senior_management_fees`** the same way (**Main category** **`Management fees`**, **not** **`Administrative expense`**); **subordinate** / **subordinated** **management** or **collateral management** fee, **Subordinate Collateral Management Fee(s)**, **Subordinated Management Fee**, **manager** / **management** **fee** when the line clearly refers to the **junior** / **subordinate** manager tier (not generic “manager” admin), or **to pay** / **pay** … **subordinate** … **management** or **manager** → **`subordinate_management_fees`** (**Main category** **`Management fees`**) — **include** in **`### Valuation-relevant fees`**; **do not** use **`subordinate_management_fees`** for **holders of the Subordinated Notes**, **payment on the Subordinated Notes**, or **interest on the Subordinated Notes** (noteholder cash — **`02`** / **`### Other waterfall lines`**); **do not** file under **`### Other waterfall lines`** or **`administrator_expenses`** when wording is explicitly **subordinate** / **junior** **management**; **hedge** transaction fee / amounts to **hedge counterparties** → **`fees_to_hedge_counterparty`** (**`hedge_fees`** alternate in legacy files); standalone **tax** / withholding line → **`tax_gross_amounts`**.

> **Waterfall clause (A) — issuer / Co-Issuer taxes:** A **Section 11.1**-style **(A)** (or first-priority) line **payment of taxes** / **taxes owed by the Issuer** or **Co-Issuers** is **`Tax`** + **`tax_gross_amounts`** in **`### Valuation-relevant fees`** (map **paid** / **payable** from the waterfall). **Not** a substitute for leaving tax **only** in **`### Other waterfall lines`**; **Issuer** wording does **not** mean “admin expense” — use **`tax_gross_amounts`**.

**Unmapped or uncertain fee lines:** Do **not** add extra columns to **`### Valuation-relevant fees`** — that table is **only** **Main category** | **Sub category** | **Amount paid**. Keep **verbatim labels**, **due vs paid** detail, and **classification notes** in **`### Waterfall table`** / **`### Other waterfall lines`**, **`## Source Text`**, **`04_extraction_summary.md`**, or **Notes** elsewhere in **`03`**. **Main category** **`Other`** + **Sub category** **`other_fees_01`** / **`02`** / **`03`** is for the **Other** rollup band when multiple distinct lines need typed leaves (see mapping table) — it is **not** a substitute for documenting ambiguity in prose outside the three-column table.

**Administrative expense block — itemized vs total:** Many waterfalls nest **trustee fee**, **collateral administrator fee**, legal, audit, **issuer fee**, etc. **Senior / subordinate management fees**, **tax**, and **hedge** lines are **separate** business categories — map them to **Main categories** **`Management fees`**, **`Tax`**, and **`Hedge`** (not **`Administrative expense`**). **If the PDF prints separate amounts** for lines that map to distinct literals (**`trustee_expenses`**, **`collateral_admin_fees`**, **`administrator_expenses`**, **`coissuer_fees`**, …), you **may** fill **`### Valuation-relevant fees`** with **one row per literal** for **leaf-level** export — set **Main category** from the *Main category vs Sub category* table (**`collateral_admin_fees`**, **`trustee_expenses`**, **`coissuer_fees`**, and most **`administrator_expenses`** are **`Administrative expense`**; **`senior_management_fees`** / **`subordinate_management_fees`** are **`Management fees`**) — do **not** merge itemized **`trustee_expenses`** or **`collateral_admin_fees`** into **`administrator_expenses`** only because they appear under an admin heading **when you are using the itemized path**. **`coissuer_fees`** rows also use **Main category** **`Administrative expense`**. **If the PDF prints only a single total** for administrative or senior expenses **without** itemized sub-lines that map to those types, use **one** row: **Main category** **`Administrative expense`**, **`fee_type`** **`administrator_expenses`**, with **`Amount paid`** from the **waterfall / ladder** row that carries that **paid** admin cash (cap, **To the Bank** lump, etc.). **Do not** take **`### Valuation-relevant fees`** **`Amount paid`** from the **Administrative Expenses** **grid** (including printed **Total** / **Paid on the Distribution Date** voucher aggregates) — keep those figures in **`### Administrative Expenses grid`** / **`## Source Text`** and **Notes** for tie-out (voucher **gross** vs waterfall **cap**). **Still** use **separate** **`senior_management_fees`** / **`subordinate_management_fees`**, **`tax_gross_amounts`**, **`fees_to_hedge_counterparty`** rows when the **waterfall** prints those as **distinct** lines.

**Counsel / trustee reimbursements (roll-up when not itemized as `trustee_expenses`):** **Trustee expense**, **counsel / legal / professional** reimbursements paid via the trustee that **do not** appear as a distinct **contractual trustee fee** line mapped to **`trustee_expenses`** — roll their amounts into **one** **`administrator_expenses`** row with **Main category** **`Administrative expense`** (combined with other admin-only detail on the same row, or the sole admin row when only a total is shown). **Independent accountants, agents and counsel of Issuer** is always **`administrator_expenses`** / **`Administrative expense`** when it appears as its own waterfall line (distinct from **`coissuer_fees`**).

> **`map_valuation_fees.py` — accrued admin cap line:** **Accrued and unpaid Administrative Expenses up to the Administrative Expense Cap** (and close variants) is a **real fee cash row** → **Main category** **`Administrative expense`**, **Sub category** **`administrator_expenses`**. **Do not** skip it as a ladder subtotal/header — only omit true block labels (e.g. **Administrative Expenses block**, **Taxes and Administrative Expenses** aggregate).

> **`map_valuation_fees.py` — Collateral Manager management tiers:** **Senior Management Fee** (including **Senior Management Fee due and payable to the Collateral Manager**) → **`senior_management_fees`**. **Subordinated Management Fee … Collateral Manager** → **`subordinate_management_fees`**. **Incentive Management Fee** (including **x% of remaining Interest/Principal Proceeds to the Collateral Manager as the Incentive Management Fee**, **subordinated incentive fee**, **performance fee**) → **`subordinate_management_fees`** — same leaf as contractual subordinated management; **not** **`incentive_management_fees`**. **Deferred Incentive Management Fees** → **`subordinate_management_fees`**. Generic **collateral management** / **collateral administrator** / **Management Fee due and payable to the Collateral Manager** **without** **Senior** / **Subordinate** / **Incentive** in the title → **`collateral_admin_fees`** (**Main category** **`Administrative expense`**). **Trustee and Collateral Administrator** (or similar **combined** trustee + collateral-admin label on **one** line) → **`trustee_expenses`**, not **`collateral_admin_fees`**. **Senior Collateral Management Fee** (no **due and payable to the Collateral Manager** wording) stays **`senior_management_fees`**.

**Source:** Waterfall tables, disbursement schedules, “Application of … Proceeds”, **Administrative Expenses** voucher tables (for **`### Administrative Expenses grid`** / tie-out **only** — **not** for **`### Valuation-relevant fees`** **`Amount paid`**), Paid vs Available / Running — follow **this deal’s** labels.

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

> **Two-number rows (Computershare and similar):** When a row shows **two** currency amounts with little or no column header, **do not assume left = paid** — order **varies by trustee**. Use printed labels on the page, the **same column index** as sibling priority lines when headers are consistent, or **`### Column mapping`** for **this deal** (many Wells Fargo waterfall chunks use **left = paid**, **right = running**; other trustees may differ). Document once in **`### Column mapping`** or **Notes** when you infer position without headers.

> **Lockstep — `## Source Text` vs structured tables (File `03`):** Treat **`## Source Text`** as the **canonical numeric transcript** for the waterfall / ladder pages you used. **Do not** fill **`### Waterfall table`**, **`### Disbursement ladder`**, or running-balance columns by **carrying forward** the prior row’s balance across a new **parent clause** (e.g. after **(M)** into **(O)**) without **re-reading** the **next** printed **paid** amount and **next** standalone balance line for that step. **Recommended order:** (**1**) Paste **`## Source Text`** verbatim from **`_chunks/`** for the full **Application of … Proceeds** block. (**2**) Walk the PDF **in clause order**; for each step, copy **Amount paid** (or two-number **left**) and **Amount available / running** (or the **next line** balance / two-number **right**) **from the same step** — never assume **0.00** because an earlier block used similar wording. (**3**) **Clause (B)** vs **clause (O)**:** **(B)** is admin **up to the cap**; **(O)** is **Administrative Expenses not paid pursuant to (B)** — often another **“(a) first, To the Bank …”** line with **different** **paid** dollars; extract **both**; **`validate_noteval.py`** may WARN when **Source Text** shows a non-zero **(O)(a)** paid amount but **`### Waterfall table`** **`O(a)`** **`Amount paid`** is **0.00**. (**4**) After edits, run **`validate_noteval.py`** on the output folder before ship.

> **Multi-column waterfalls — headers first (all trustees):** **Column order is not portable** across trustees or deals. Map each **`$`** to template fields using **printed column titles** on **this** exhibit (and the same header row on **sibling** lines) — **not** by fixed left-to-right position, **not** by “last **`$`** on the line,” and **not** by assuming Payable|Paid|Running always appear in the same order. Record the mapping in **`### Column mapping`** with **as-printed** headers → template fields. Use **positional** rules (**1st / 2nd / left / right `$`**) **only** when headers are missing or OCR dropped them — **Notes** once per exhibit. **Due/payable** synonyms → **`Amount payable`**; **Paid/Payment/Settled** → **`Amount paid`**; **Running/Available/Available for Disbursements/Balance** (post-step pool) → **`Amount available / running`**; **Unpaid/Remaining** → **`Other amount columns`**. **Never** copy **due** or **available/running** into **`Amount paid`**. When the **paid** column is **`0.00`**, **`Amount paid`** = **`0.00`** even if **due** or **available** is non-zero.

> **Indenture-style three columns (example — U.S. Bank / many Schedule G grids):** When headers read **Amount Due**, **Payment**, and **Running Balance** (wording varies; **order may differ**), map **by label**: **Amount Due** (or **Due**) → **`Amount payable`**; **Payment** (or **Paid**) → **`Amount paid`**; **Running Balance** → **`Amount available / running`**. Due may exceed paid when partially paid or unpaid.

> **Schedule G four-field rows (example — one common layout):** When the header row is **`Due | Paid | Running Balance | Unpaid`** in that reading order, assign each amount under **that** heading — **not** by assuming every trustee uses the same left-to-right order. Example under those headers: **`$971.04 $0.00 $0.00 $971.04`** → payable **971.04**, paid **0.00**, unpaid **971.04**. Another trustee may print **Payment** before **Amount Due** or use different labels — **`### Column mapping`** must describe **this** PDF. **`map_valuation_fees.py`** uses waterfall **`Amount paid`** only.

> **Citibank-style Section 11.1 (Distribution / Per Cap / Balance):** Some **Citibank** deals print **Distribution**, **Per Cap**, and **Balance** (wording varies; OCR may run headers together). Treat **Distribution** as **`Amount paid`** when that column is the trustee’s cash-applied amount for the step; **Per Cap** often carries the same **paid** semantics per note / pro rata slice — map to **`Amount paid`** (and/or **`Other amount columns`**) per the exhibit, not as “remaining funds.” Map **Balance** to **`Amount available / running`**. Document the mapping in **`03`** **`### Column mapping`** when this layout applies.

> **Clause-only Section 11.1 (no column headers — `map_valuation_fees.py`):** When the PDF prints **indenture priority prose** with a **trailing `$`** per line (common **Citibank** distribution reports) and **no** multi-column grid, fill **`### Disbursement ladder`** with **one row per payee** and a **single** **Amount** per row. Set **Layout** = **Logical only**; **omit** **`### Waterfall table`** or document **N/A** in **Notes** — **do not** leave a header-only empty grid. **`map_valuation_fees.py` uses the ladder as primary** when the waterfall grid has no fee rows. When the deal prints **both** a grid and a clause ladder, use **Both** but **do not double-count fees**: record each fee **$** in **`### Waterfall table` OR **`### Disbursement ladder`**, not both — prefer the **grid** for fee lines; the ladder may carry class cash with **Notes** `see 02` / `see waterfall table`. The mapper **dedupes** the same **priority + Amount paid** across tables; **`### Continuations / sub-lines`** must not repeat fee **$** already in the ladder/waterfall. **Anti-pattern:** combined payees and compound amounts (`54.42; 2,343.73`) — **split** into separate rows.

### Waterfall table (grid / multi-column — when the PDF prints named columns)
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| | | | | | | |

> **Abbreviated grid (preferred when `02` is complete):** If the PDF’s waterfall lists **each class** interest/principal step and those amounts **match** **`02`**, you may **omit** those class rows here and document once in **Notes** (see **Wrap-up vs `02`** above). Keep rows for **fees**, **valuation-relevant admin/manager/trustee/issuer/hedge/tax** lines, **swap** and other **non-class** steps, and any line **not** mirrored in **`02`**.

> **Fee-style rows:** **`Amount paid`** = cash from the trustee’s **Paid** / **Payment** / **Settled** column **only** (match the **header**, not column index). **Do not** use **Available**, **Running Balance**, **Available for Disbursements**, or other **remaining-pool** columns for **`Amount paid`** or **`05`** fee roll-up — those belong in **`Amount available / running`**. If the report has multiple **`$`** columns, name each **as-printed** in **`### Column mapping`** and map **by header** on every row — **not** by a fixed column index across trustees.

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

> **One amount per row (required for automated `05`):** Each **Amount** cell must hold **exactly one** parseable currency value. **Do not** join multiple disbursements with **`;`**, **`,`**, or **and** in one cell (e.g. `54.42; 2,343.73`). **Do not** combine multiple payees in one **Item description** when they have **different** paid amounts — use **separate** ladder rows (and matching **`### Waterfall table`** rows).

### Continuations / sub-lines
| Parent clause | Continuation text | Amount | Notes |
|---------------|-------------------|--------|-------|
| | | | |

> Roll up indented / “first / second / third” continuations under the parent clause in **Item description** or **Notes** so each major line is one logical row. **Two trailing amounts:** use the **left** as disbursed **`Amount`** when that matches the trustee layout; mirror the **right** in **Notes** or a second amount column if you split them.

### Administrative Expenses grid (optional — separate voucher / expense table)
**When to use:** The PDF prints a dedicated **Administrative Expenses** (or similarly titled) **table** on the note valuation / payment package (often its own page), **separate** from the **Section 11.1** proceeds waterfall. **Include** this subsection **only** when that separate admin / expense **grid** exists — populate rows from the PDF. **When the PDF has no such grid:** **omit** the entire **`### Administrative Expenses grid`** heading and table from **`03`** (show **nothing** there — **no** empty pipe table, **no** placeholder **N/A** rows). **Do not** invent an admin grid from Schedule G clause text alone if the trustee did not print a tabular admin / expense exhibit. When the grid **is** present, use it for **audit / voucher tie-out** and **`## Source Text`** — **not** to **populate** **`05_valuation_relevant_fees.md`** (fee roll-up is **waterfall / ladder** **Amount paid** via **`map_valuation_fees.py`**; reconcile voucher **gross** vs waterfall **cap** in **Notes** / **`04`** when helpful).

> **Deutsche Bank / NVR — Administrative Cap and Expenses page:** The voucher-style admin exhibit is often titled **Administrative Cap and Expenses** (TOC may list **Administrative Cap and Expenses**). On that page, populate **`### Administrative Expenses grid`** **only** from the block under the **Administrative Expenses** heading — line items such as **(i) Trustee**, **(ii) Bank**, **(iii) Administrator**, **(iv) Rating Agencies**, **(v)** counsel / accountants, **(viii)** reserve, **(ix)** other fees, and a printed **Total** when shown. **Do not** put **Administrative Expenses Cap** calculation rows in the grid: **Aggregate Principal Amount**, **per annum** / **Day Count**, **Expenses paid in between payment dates**, **( A + B ) * ( C / 360 ) - D**, or the computed **Administrative Expenses Cap:** **$** total. Those cap mechanics may be referenced in **Notes** / **`04`** when reconciling to waterfall **(B)** / cap-limited **Paid** — they are **not** voucher expense line items.

> **Required — declare which column is payment (Administrative Expenses grid):** Whenever this **grid** is in scope for **`03`**, the extractor **must** identify **the payment column** — the column whose **$** are **cash actually paid or applied on this distribution date** for each expense row (labels vary; the column may lack a readable header). **Always** record this in **`### Column mapping`** with at least: (**1**) **as-printed** header text **or** **column position** (e.g. “rightmost **$** column”); (**2**) an explicit label such as **Payment column for admin expense grid** (or equivalent) tying that column to template **Paid on the Distribution Date** semantics for **this grid**; (**3**) which column(s) are **due / unpaid / obligation** → **Due** / **Unpaid** template slots. This supports **accurate grid extraction** and **human audit**; it is **not** permission to copy grid **$** into **`### Valuation-relevant fees`**. **Do not** treat **Due** / **Payable** / **Accrued** as **payment** without a stated justification in **Notes**.

> **Recognizing the admin grid when column titles differ or OCR drops them:** It is still the **Administrative Expenses grid** if the **section** is clearly an **admin / senior expenses / fee schedule** (not per-class **Section 11.1** interest–principal application) and **rows** are **expense line items** (trustee, collateral administrator, legal, rating, issuer fee, management fees, …). Printed headers vary widely: **Payment**, **Paid**, **Amount paid**, **Paid this period**, **Current payment**, **Due**, **Amount due**, **Payable**, **Accrued**, **Obligation**, **Outstanding**, **Prior** / **Unpaid** / **Carried forward**, **Balance**, abbreviated labels, **non-English** wording, headers **split across lines**, or **headers missing** with only **multiple currency columns** after each expense name. **Do not** require the exact strings **Paid on the Distribution Date** / **Due from current period** / **Unpaid from prior period** to classify the table. Add **`### Column mapping`** under **`03`**: quote or describe each **as-printed** header (or **column position** if headerless), and map to template semantics for **grid** columns only. When both **this grid** and **Section 11.1** show related admin cash, **tie out** in **Notes** (voucher gross vs **Senior Expenses Cap**, etc.). If only **one** money column appears and role is unclear, prefer treating it as **paid** when the exhibit is explicitly a **payment-date settlement** table; **Notes** once if inferred.

> **Grid vs waterfall (why both):** The **Administrative Expenses** **grid** is often where the trustee shows **rolled-up** or **voucher-style** admin cash (**totals** or **Paid on the Distribution Date** in one place). The **Section 11.1** **waterfall** shows **priority order** and **item-by-item** application. **Keep both** in **`03`**: **grid** = voucher / line-item **audit**; **waterfall** = priority + **the sole source** for **`### Valuation-relevant fees`** fee rows (**Main category** + **Sub category** + **`Amount paid`**). **Do not** treat the grid as optional for **audit** just because the waterfall lists admin again.

| Expense / fee type (as printed) | Unpaid from prior period(s) | Due from current period | Paid during the period | Paid on the Distribution Date | Notes |
|-----------------------------------|----------------------------|-------------------------|------------------------|--------------------------------|-------|
| | | | | | |

> **Voucher gross total (footer):** When the trustee prints **all** expense lines **and** a **standalone total** at the **bottom** of the same exhibit (no row label — e.g. a lone **`46,863.59`** / **`€46,863.59`** after the last line item), add a final grid row **`Total (voucher, as printed)`** (or copy the printed **Total** label) in **`Paid on the Distribution Date`** with **Notes** that this is the **voucher gross**. The **waterfall** clause **(C)** **Administrative Expenses** **Amount paid** may still be **lower** (e.g. **Senior Expenses Cap**) — **do not** silently replace the voucher total with the cap; keep **both** for tie-out.

> **Relationship to `### Valuation-relevant fees`:** **`### Valuation-relevant fees`** is filled **only** from **`### Waterfall table`** / **`### Disbursement ladder`** / **`### Logical / clause waterfall`** (plus **`### Column mapping`** for those exhibits). **`### Administrative Expenses grid`** is **optional** for **audit** — **do not** **lift** grid rows or grid **totals** into the fee roll-up. **Do not** **sum** grid **$** with waterfall **$** for the **same** economic payment as if additive.

> **Grid-only paid amounts (do not roll up):** A non-zero **Paid** / **Paid on the Distribution Date** cell on **`### Administrative Expenses grid`** (e.g. **8,250.00** or **9,137.82** on **Issuer fee**, rating-agency, or other voucher rows) **does not** by itself create a **`### Valuation-relevant fees`** row. **Each** valuation **`Amount paid`** must equal disbursed **Payment** / **Paid** on a **waterfall / ladder** line for this payment. If the **waterfall** shows **0.00** or **omits** that voucher line (cap, different bucket, not applied this date), **leave** that **$** **off** **`### Valuation-relevant fees`** — document in **`### Administrative Expenses grid`** and **Notes** / **`04`** for user reference only.

> **Waterfall fee `Paid` must roll up (do not drop):** When **`### Waterfall table`** / ladder shows **non-zero** **Payment** / **Paid** on a **fee** line (e.g. **26,525.64** on **Administrative Expenses** / **(A)(2)** / **principal (A)** funding), **include** that **`Amount paid`** in **`### Valuation-relevant fees`** — **do not** omit it because the **Administrative Expenses grid** **Total** or line items differ (e.g. **Senior Expenses Cap** vs voucher gross) or because other **grid** rows are **grid-only** this date. **Notes** gross vs cap when the two exhibits disagree; the **waterfall** disbursed figure still drives the roll-up.

> **Valuation-relevant fees — not in File `03`:** Do **not** add **`### Valuation-relevant fees`** under **`03`** for new extractions. Complete **`### Waterfall table`** and/or **`### Disbursement ladder`** with **Amount paid** / **Amount** on fee lines (at least one must have rows), then run **`map_valuation_fees.py`** → **`05_valuation_relevant_fees.md`**. The mapper prefers the **grid** when it has fee rows; otherwise the **ladder** is primary. Mapping rules and allowed **Sub category** literals are under **File 05** and the **Valuation-relevant fees** guidance above (for the mapper / human review).

### Other waterfall lines (non-fee / structural — optional)
| Item description | Amount paid | Amount payable | Notes |
|------------------|-------------|----------------|-------|
| | | | |

> Use for **swap**, **generic expense** buckets not mapped to typed **Sub category** literals (including **tax** only when it is **not** captured under **`Tax`** in **`### Valuation-relevant fees`**), **opening/closing** lines, etc. Class interest/principal already in **`02`** should **not** be duplicated here unless needed to reconcile a total (then **Notes** tie-out to **`02`**).

## Completeness Checklist
- [ ] **`### Waterfall table`** filled when a multi-column grid exists (or **omitted** / **N/A** when the deal is **clause-only** — then **`### Disbursement ladder`** must have fee rows for **`map_valuation_fees.py`**); **no** row-by-row duplication of class interest/principal already in **`02`** unless **`02`** lacks that exhibit (then extract class flows from the waterfall into **`02`** per **File 02** rules)
- [ ] **`### Column mapping`** documents **this deal’s** waterfall (and admin grid, if any) **as-printed** headers → **Amount payable** / **Amount paid** / **running** / **Unpaid** (order **not** assumed portable across trustees)
- [ ] **`### Administrative Expenses grid`:** present **only** when the PDF prints a separate admin / expense voucher **table**; **omitted entirely** when no such grid (no empty subsection); when present, **`### Column mapping`** **names the admin grid payment column** (cash paid this distribution)
- [ ] **No** **`### Valuation-relevant fees`** subsection in **`03`** — run **`map_valuation_fees.py`** after extraction for **`05_valuation_relevant_fees.md`**
- [ ] **`### Logical / clause waterfall`** filled when Section 11.1 / Application of … / Computershare-style ladders exist (or **N/A** with reason)
- [ ] **Computershare-style two-number rows:** **left** = actual disbursed in **Amount paid** / ladder **Amount** (per **Section identification** note)
- [ ] **Lockstep:** **`### Waterfall table`** / **`### Disbursement ladder`** **Amount paid** and running / available columns **match** **`## Source Text`** line-by-line for that ladder (no **0.00** grid rows where **Source Text** shows a non-zero paid for the same clause — especially **(O)** after **(M)** vs duplicate **(B)** admin wording); **`validate_noteval.py`** run on the folder before ship
- [ ] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [ ] Fee lines in **`### Waterfall table`** have **Amount paid** where the PDF shows cash disbursed (for **`map_valuation_fees.py`**); non-fee class cash stays in **`02`** / **`### Other waterfall lines`**
- [ ] Subtotals / totals match detail or variance explained
- [ ] Determination / payment dates stated in this section if printed here

## Source Text
(Paste full waterfall / ladder section(s); **Page N** — one paste if grid and ladder overlap; otherwise separate blocks)
```

---

## File 05: Valuation-relevant fees (post-extraction — not agent-filled)

**Filename:** `05_valuation_relevant_fees.md`  
**Produced by:** `noteval_extractor/scripts/map_valuation_fees.py` (reads **`03`** **`### Waterfall table`** / **`### Disbursement ladder`** fee lines with **Amount paid**). **Agents do not author this file** during 01–04 extraction.

```markdown
# Valuation-Relevant Fees

## Extracted Data

### Valuation-relevant fees
| Main category | Sub category | Priority | Amount paid |
|---------------|-------------|----------|-------------|
| | | | |

> **Priority:** Copy from **`03`** **`### Waterfall table`** **Priority** when a row is unique after roll-up. **`map_valuation_fees.py`** sums **Amount paid** for rows that share the same **Sub category** (one **`05`** row per DB fee type). When multiple waterfall steps contributed, set **Priority** to **—**; line-level steps stay in **`fee_mapping_report.md`**.

### Mapping notes
| Field | Value |
|-------|-------|
| Source | 03_interest_principal_waterfall.md |
| Row count | |

## Completeness Checklist
- [ ] Generated or updated after waterfall edits (`map_valuation_fees.py`)
- [ ] Review `fee_mapping_report.md` for skipped / ambiguous lines

## Source Text
(See `03_interest_principal_waterfall.md` — fee roll-up is derived from the waterfall / ladder.)
```

**Allowed Sub category literals:** `trustee_expenses`, `collateral_admin_fees`, `administrator_expenses`, `coissuer_fees`, `senior_management_fees`, `subordinate_management_fees` (alternate `subordinated_management_fees`; **Incentive Management Fee** / **performance fee** roll here via **`map_valuation_fees.py`**), `fees_to_hedge_counterparty` (alternate `hedge_fees`), `tax_gross_amounts`, `expense_reserve_account` (**Main category** **`Other`**), `other_fees_01`–`other_fees_03` with **Main category** **`Other`**. Full mapping guidance remains in the **Valuation-relevant fees** section above (for the mapper and human review).

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
| Valuation-relevant fee rows in 05 (`05_valuation_relevant_fees.md`) | |
| Distinct **Main category** values in 05 fees (expect subset of: Administrative expense, Management fees, Tax, Hedge, Other) | |
| Fee rows (approx, legacy / all waterfall) | |

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
| Inclusive vs additive: any **Interest payment** / **Deferred interest** (or balance) relationship where one column **includes** the other — confirm no spurious **sum** of overlapping components | |
| Multi-listing: sum of **Tranche by listing** vs primary **`02`** / PDF printed class total (if **Y**) | |
| **`02`** **`CUSIP line id`** scheme (e.g. L00n / composite) and uniqueness | |
| Waterfall paid totals vs class/distribution totals in `02` (if comparable) | |
| Internal consistency (dates same across files) | |

> **02 vs 03 cross-check (review only):** Sum **03** **class / noteholder** paid (not fees). **When `02` Interest payment is 0.00/blank** and **Interest payable** matches the **03** sum, report **Y** with math and note that **`02`** may need the Total Payable → **Interest payment** rule — **never** auto-copy waterfall into **`02`**. **When Interest payment is already populated**, compare-only (**Y** / **N**); **`02`** stays authoritative. **`validate_noteval.py`** emits the same gated **WARN**.

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
