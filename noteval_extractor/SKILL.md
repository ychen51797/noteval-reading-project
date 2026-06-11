---
name: noteval_extractor
description: >-
  Agent-led extraction of CLO and note valuation trustee payment PDFs into
  structured markdown (01–04): segment via pdf_workflow/batch_segment, navigate
  _page_index.md (Wells Fargo dual PDFs use _page_index_waterfall.md +
  _chunks_waterfall/), fill extraction-templates.md, validate with
  validate_noteval.py, then map_valuation_fees.py for 05. Covers Computershare
  PDD/IDD pdfplumber mapping, Distribution in US$ fixed layouts, waterfall vs
  class-balance scope, and Administrative Expenses grids. Use whenever the user
  wants noteval extraction, trustee report parsing, fill extraction templates,
  batch segment deals, markdown outputs with source text, completeness checks,
  or a human-in-the-loop pipeline before/alongside read_noteval scripts — even
  if they only mention payment date reports, class balances, or waterfall fees.
  Set NOTEVAL_DRAFT_API_KEY when using server.py / noteval_llm.
---

# noteval_extractor

You are the **note valuation extraction agent**. Turn trustee / note valuation **PDF text** (one PDF for most trustees, **two** for Wells Fargo) into **structured markdown** with **traceable source text**, a **completeness checklist**, validation, and fee mapping.

## Deliverables

| Step | File | Who |
|------|------|-----|
| 1 | `01_report_metadata.md` | Agent |
| 2 | `02_tranche_class_balances.md` | Agent |
| 3 | `03_interest_principal_waterfall.md` | Agent |
| 4 | `04_extraction_summary.md` | Agent |
| 5 | `05_valuation_relevant_fees.md` | **`map_valuation_fees.py`** (not hand-authored) |

**Canonical layouts:** `references/extraction-templates.md` (Files **01**–**05**).

**Domain depth (read when needed):**

- **`references/file-02-domain-rules.md`** — Distribution in US$ column layouts, Computershare pdfplumber CUSIP→class, class-name protocol, principal vs balance mapping.
- **`references/xml-export.md`** — XML export from **`05`**.

For **programmatic** zero-LLM parsing or PDF reconciliation, use the **`read_noteval`** skill — not this agent workflow. Capture clause ladders and Section 11.1 disbursements in **`03`** per **`extraction-templates.md`**; do not re-derive layouts here when **`read_noteval`** already covers them.

## Non-negotiable gates

- **`02` vs `03` scope** — Class / distribution / deferred interest in **`02`** only. Fee grids, Section 11.1 waterfalls, and admin expense vouchers in **`03`** only. Never paste an admin grid into **`02`**.
- **Fees → `05`, not `03`** — Do **not** add **`### Valuation-relevant fees`** under **`03`** on new runs. Capture fee cash in **`### Waterfall table`** and/or **`### Disbursement ladder`** with **Amount paid** on each fee line, then run **`map_valuation_fees.py`**. **`### Administrative Expenses grid`** is audit / voucher tie-out only — not a source for **`05`**.
- **Computershare PDD/IDD** — Read **`_chunks_structured/pdd_idd_pdfplumber.md` first**; never nth-position CUSIP↔class pairing. See **`references/file-02-domain-rules.md`**.
- **Validate loop** — After **`02`** (and before finishing), run **`validate_noteval.py`**; fix Rule 5 roll-forward warnings on Distribution in US$ rows before ship.
- **Source Text** — Verbatim from **`_chunks/`** or **`_chunks_waterfall/`** with **Page N** labels.

---

## Prerequisites

- Python with **`pypdf`** (`pip install pypdf`). **`pdfplumber`** strongly recommended — **`pdf_workflow.py`** writes **`_chunks_structured/pdd_idd_pdfplumber.md`** for Computershare PDD/IDD (authoritative CUSIP→class; also used by **`export_noteval_xml.py`**).
- **`segment_pdf.py`** from CS-Structured-Skills, or set **`NOTEVAL_SEGMENT_PDF`**, or **`--segment-script`** on the workflow runner.
- **`noteval_extractor/scripts/pdf_workflow.py`** for Step 1 segmentation.

### Environment variables (LLM / web UI)

When using **`server.py`** or **`noteval_llm.py`**, set an API key:

| Variable | Purpose |
|----------|---------|
| **`NOTEVAL_DRAFT_API_KEY`** or **`OPENAI_API_KEY`** | Completions endpoint key |
| **`NOTEVAL_DRAFT_BASE_URL`** | OpenAI-compatible base URL (default `https://api.openai.com/v1`) |
| **`NOTEVAL_DRAFT_MODEL`** | Model id (default `gpt-5.4`) |
| **`NOTEVAL_INDEX_PREVIEW_ENRICH`** | `1` = LLM-rewrite page index previews after segmentation; `0` = rule-only |
| **`NOTEVAL_DRAFT_USE_TOOLS`** | Default on — chunk/index tool calling; `0` for single bundle mode |

```powershell
$env:NOTEVAL_DRAFT_API_KEY = "your-key-here"
```

Do not commit secrets. See full env table in repo docs if tuning index preview or vision rasterization.

---

## Workflow overview

| Step | Action |
|------|--------|
| **1** | Segment PDF(s) → `_chunks/`, `_page_index.md`, `_manifest.md` (+ waterfall tree for Wells Fargo) |
| **2** | Read page index(es); map sections to page ranges |
| **3** | Load **`extraction-templates.md`** |
| **4** | Extract **`01`**–**`04`** section by section |
| **5** | **`validate_noteval.py`** → read **`validation_report.md`**; fix errors and material warnings |
| **6** | After **`01`**–**`04`**: **`map_valuation_fees.py`** → **`05_valuation_relevant_fees.md`** + **`fee_mapping_report.md`** (automatic in SDK / UI pipeline when **`03`** is in scope); re-validate |

---

## Wells Fargo vs single-PDF trustees

**Single PDF (typical U.S. Bank):** One **`_chunks/`** tree. **`01`**, **`02`**, **`03`** all from **`_page_index.md`** + **`_chunks/`**.

**Wells Fargo (two PDFs):** Same output folder, two segmentation stacks:

| Role | Artifacts |
|------|-----------|
| Note valuation | **`_page_index.md`**, **`_chunks/`**, **`_manifest.md`** |
| Waterfall | **`_page_index_waterfall.md`**, **`_chunks_waterfall/`**, **`_manifest_waterfall.md`** |

**Routing:** **`01`** / **`02`** from note-val tree only. **`03`** waterfall ladder and fee **Amount paid** from **`_chunks_waterfall/`** when it exists — **not** from note-val **`_chunks/`** for those amounts. **Always** attach note-val **`_chunks/`** for a **separate Administrative Expenses** statement when present (**`### Administrative Expenses grid`** + grid Source Text). Document dual segmentation in **`04`**.

**Wells Fargo two-number rows:** Left **`$`** = **Amount paid**; right = running / available unless **`### Column mapping`** says otherwise.

**Waterfall vs fees:** **`### Waterfall table`** / ladder captures the full priority picture for audit. Class interest/principal stay authoritative in **`02`**. Fee typing (**Main category**, **Sub category**, **Amount paid**) is produced in **`05`** by the mapper — not duplicated by hand in **`03`**.

---

## Step 1: Segment the PDF

From repository root:

```powershell
py -3 noteval_extractor/scripts/pdf_workflow.py "<path-to.pdf>" "<output-dir>"
```

**Exactly two arguments:** PDF path and output directory. Use a **per-deal subfolder** (e.g. `output/825275100_20260316/`).

**Batch:**

```powershell
py -3 noteval_extractor/scripts/batch_segment.py --deal-paths noteval_extractor/test/deal_paths.csv --output-root noteval_extractor/output
```

Wells Fargo rows with **`waterfall_path`** populate both trees in the same deal folder.

**Artifacts:** `_chunks/`, `_page_index.md`, `_manifest.md`, optional `_chunks_structured/pdd_idd_pdfplumber.md`, optional `_*_waterfall*` set.

### Index enrichment (UI pipeline)

After segmentation, the UI may run **`noteval_index_preview.py`** to LLM-tag index previews. Disable with **`NOTEVAL_INDEX_PREVIEW_ENRICH=0`**.

### Vision / table escalation (Computershare PDD+IDD)

When linear **`_chunks/`** text loses spatial layout (multi-CUSIP, dual PDD+IDD), prefer pdfplumber first, then table extraction or vision on cropped page images. Default LLM draft uses tool calling without screenshots unless **`NOTEVAL_DRAFT_PAGE_IMAGES=1`**.

---

## Very large PDFs (300+ pages)

Use **`_page_index.md`** to locate sections; read only matching **`_chunks/pages_*.txt`** ranges per **`_manifest.md`**. No end-to-end read required.

**No tranche/waterfall content:** **`02`** / **`03`** may be **N/A** with honest Source Text and **`04`** documentation. Validation may still expect minimal structure — resolve per project convention.

---

## Step 2: Read the page index

Open **`<output-dir>/_page_index.md`** always. If **`_page_index_waterfall.md`** exists, use it for **`03`** waterfall pages (page numbers are **per PDF**).

Map: metadata → **`01`**; class / distribution / PDD / IDD → **`02`**; waterfall / Section 11.1 / admin grids → **`03`**. Record **inclusive page ranges** before reading chunks.

For admin grids, search section titles and row labels — not only exact column phrases. **Deutsche Bank NVR:** admin grid from **Administrative Expenses** block only, not cap formula rows.

---

## Step 3: Extraction templates

Use **`references/extraction-templates.md`** — fixed filenames, stable headers, three-part structure per file:

1. **Extracted Data**
2. **Completeness Checklist**
3. **Source Text** (verbatim, **Page N**)

**ETL note:** ISIN/CUSIP in **`02`** listing tables only when **`Multi-listing = Y`**. Primary **`Class`** is economic tranche name.

---

## Step 4: Extract section by section

For each target:

1. Pick page numbers from Step 2 (correct index per Wells Fargo routing).
2. Read only needed chunk ranges. **Computershare `02`:** read **`pdd_idd_pdfplumber.md` first**.
3. Fill **Extracted Data** per template.
4. Tick checklist items **only after** the matching subsection exists.
5. Paste **Source Text**.
6. Write **`01`**–**`04`** to **`<output-dir>/`**.

### File `02` (summary)

Read **`references/file-02-domain-rules.md`** before editing class tables. Highlights:

- Trustee-specific **Distribution in US$** fixed layouts (Deutsche, US Bank wide voucher, BNY Notes Information, Computershare PDD/IDD, Citibank opening/closing).
- **pdfplumber-first** CUSIP→class; one primary row per Note Class section.
- **`Principal payment`** from principal distribution column only — never ending balance.
- Dual PDD+IDD exhibits: merge by economic class; balances from principal exhibit.
- **SUB / Distribution Summary** zero-dividend rule; **Preference Share** as primary rows; NVR **Periodic Interest Amount** → **`Interest payment`**.

Run **`validate_noteval.py`** after each **`02`** save when working Distribution in US$ layouts.

### File `03` (summary)

**Include when present:**

- **`### Waterfall table`** and/or **`### Disbursement ladder`** / **`### Logical / clause waterfall`**
- **`### Administrative Expenses grid`** (only when PDF prints a separate admin table)
- **`### Column mapping`** for waterfall and admin grid payment columns
- **`### Other waterfall lines`** for structural / unmapped rows

**Do not include on new runs:** **`### Valuation-relevant fees`** (that is **`05`**).

**Fees workflow:**

1. Extract raw waterfall / ladder rows with **Amount paid** on fee lines (+ admin grid for audit).
2. Ensure **paid vs payable** columns match printed headers (Amount Due / Payment / Running Balance; Citibank Distribution / Per Cap / Balance — see **`extraction-templates.md`** File **03**).
3. Run **`map_valuation_fees.py`** — mapper applies **Sub category** literals (`trustee_expenses`, `collateral_admin_fees`, `senior_management_fees`, `tax_gross_amounts`, etc.).

**Non-fee lines** (class interest/principal, residual distributions, swap structural steps) stay in waterfall table / **`02`** — not in **`05`**.

### Extraction targets

| # | Output | Typical index hints |
|---|--------|---------------------|
| 1 | `01_report_metadata.md` | Title, payment / determination dates, deal name |
| 2 | `02_tranche_class_balances.md` | Distribution in US$, PDD/IDD, class summary — **no admin grids** |
| 3 | `03_interest_principal_waterfall.md` | Section 11.1, Application of Proceeds, admin expense grid |
| 4 | `04_extraction_summary.md` | Counts, flags, dual-segmentation note, multi-listing flag |

---

## Step 5: Validate

```powershell
py -3 noteval_extractor/scripts/validate_noteval.py "<output-dir>"
```

Checks required files, class rows in **`02`**, waterfall sanity in **`03`**, **WARN** when fee-like **`03`** rows exist but **`05`** is missing. Use **`--strict`** for merge gates.

Fix before finishing:

- **Rule 5** principal roll-forward on Distribution in US$ → column mis-map
- **Rule 5b/5c/5d** PDD column issues
- Missing **`05`** when **`03`** has fee disbursements

---

## Step 6: Map valuation fees

**Runs automatically** after SDK / LLM pipeline extraction when **`03`** is in targets. When invoking the agent manually in Cursor, run this yourself immediately after saving **`01`**–**`04`**:

```powershell
py -3 noteval_extractor/scripts/map_valuation_fees.py "<output-dir>"
```

Always run when **`03`** was written (the script is idempotent). Produces **`05_valuation_relevant_fees.md`** and **`fee_mapping_report.md`**. Re-run after **`03`** edits. Review skipped / ambiguous lines in the mapping report.

**Sub category literals** and fee taxonomy: **`extraction-templates.md`** Files **03** and **05**.

---

## Optional: install as Cursor skill

Copy **`noteval_extractor/`** to **`.cursor/skills/noteval_extractor/`** in the project.

## Optional: subagent delegation

Use **`agents/noteval-extractor-agent.md`** (or **`.cursor/agents/noteval-extractor-agent.md`**) for focused extraction runs: *Use the **noteval-extractor-agent** with output directory …*
