---
name: noteval_extractor
description: >-
  Agent workflow to extract note valuation / trustee payment report information
  from PDFs: segment with segment_pdf, navigate via _page_index.md (and for Wells
  Fargo optionally _page_index_waterfall.md + _chunks_waterfall/), fill
  extraction-templates.md (tables, checklist, source text) per section, then
  validate with validate_noteval.py (writes validation_report.md). Use
  when the user wants human-in-the-loop or agent-led extraction, markdown
  outputs, completeness checks, or a pipeline before/ alongside read_noteval
  scripts.
---

# noteval_extractor

You are the **note valuation extraction agent**. Your job is to turn trustee / note valuation **PDF text** (one PDF for most trustees, **two** for Wells Fargo after `batch_segment.py`) into **structured markdown** in an output directory, with **traceable source text** and a **completeness checklist**, then (when available) run validation.

This skill is **agent procedure**. For **programmatic** USB / Deutsche parsing, use **`read_noteval_usbank`**, **`read_noteval_deutsche`**, or **`read_noteval_logical_disb`** as appropriate.

## Prerequisites

- Python with **`pypdf`** (`pip install pypdf`).
- **`segment_pdf.py`** from **CS-Structured-Skills** (`rmbs-deal-doc-extractor/scripts/segment_pdf.py`), or set **`NOTEVAL_SEGMENT_PDF`**, or use **`--segment-script`** on the workflow runner.
- **`noteval_extractor/scripts/pdf_workflow.py`** (runs Step 1: segmentation). The repo may also ship **`scripts/pdf_workflow.py`** as a thin wrapper to the same script.

### Environment variables (LLM / web UI)

If you use the repo’s **`server.py`** web UI or anything that calls **`noteval_llm.py`** (OpenAI-compatible chat completions), **set an API key** before starting the server; otherwise LLM calls will fail.

| Variable | Required | Purpose |
|----------|----------|---------|
| **`NOTEVAL_DRAFT_API_KEY`** | Set this **or** `OPENAI_API_KEY` | Preferred API key for the completions endpoint. |
| **`OPENAI_API_KEY`** | Fallback | Used when `NOTEVAL_DRAFT_API_KEY` is unset. |
| **`NOTEVAL_DRAFT_BASE_URL`** | No | Base URL without trailing slash (default `https://api.openai.com/v1`). Point at any OpenAI-compatible provider if needed. |
| **`NOTEVAL_DRAFT_MODEL`** | No | Model id (default `gpt-4o-mini`). |
| **`NOTEVAL_DRAFT_USAGE_LOG`** | No | Path to append JSONL usage lines; default under repo **`logs/noteval_draft_api_usage.log`**. Set to `0` or `off` to disable. |
| **`NOTEVAL_DRAFT_PRICE_INPUT_PER_1M`** / **`NOTEVAL_DRAFT_PRICE_OUTPUT_PER_1M`** | No | Optional USD per 1M tokens for cost estimates (override built-in table). |

**Windows (PowerShell, current session):**

```powershell
$env:NOTEVAL_DRAFT_API_KEY = "your-key-here"
# optional:
# $env:NOTEVAL_DRAFT_BASE_URL = "https://api.openai.com/v1"
# $env:NOTEVAL_DRAFT_MODEL = "gpt-4o-mini"
```

**macOS / Linux (bash, current session):**

```bash
export NOTEVAL_DRAFT_API_KEY="your-key-here"
# optional:
# export NOTEVAL_DRAFT_BASE_URL="https://api.openai.com/v1"
# export NOTEVAL_DRAFT_MODEL="gpt-4o-mini"
```

Persist keys the usual way for your OS (User environment variables on Windows, `~/.profile` / shell rc on Unix). Do not commit secrets into the repo.

## Workflow overview

| Step | Action |
|------|--------|
| **1** | Segment the PDF (`noteval_extractor/scripts/pdf_workflow.py`) into `_chunks/`, `_page_index.md`, `_manifest.md`. |
| **2** | Read **`_page_index.md`** to map sections to page numbers. |
| **3** | Load **`references/extraction-templates.md`** — strict per-file templates (**01**–**04** in order; no standalone **`05_*.md`**; **06** deprecated). |
| **4** | For each extraction target: locate pages → read **`_chunks/`** (and **`_chunks_waterfall/`** when present) → fill template → write under **`<output-dir>/`**. |
| **5** | Run **`validate_noteval.py`** (when present); write **`validation_report.md`** to **`<output-dir>/`**. |

---

## Wells Fargo vs single-PDF trustees (e.g. U.S. Bank)

**Single PDF (typical U.S. Bank and similar):** `get_file_path.py` / `deal_paths.csv` has **`pdf_path`** only ( **`waterfall_path`** empty). `batch_segment.py` writes one set under **`<output-dir>/`**: **`_chunks/`**, **`_page_index.md`**, **`_manifest.md`**. Tranche / distribution / class tables **and** waterfall or fee grids usually all appear in that one PDF — map everything from **`_page_index.md`**, read **`_chunks/`** for **`01`**, **`02`**, and **`03`**, and cite that same tree in **Source Text**.

**Wells Fargo (two PDFs, one deal folder):** `deal_paths.csv` has **`pdf_path`** (Note Valuation Report — tranche / class / distribution style content) and **`waterfall_path`** (Waterfall Calculations Report — waterfall fees and related calculations). `batch_segment.py` still uses **one** output folder per deal and payment date (e.g. **`825275100_20260316/`**), but produces **two** segmentation stacks:

| Role | Artifacts |
|------|-----------|
| Note valuation (`pdf_path`) | **`_page_index.md`**, **`_chunks/`**, **`_manifest.md`** |
| Waterfall (`waterfall_path`) | **`_page_index_waterfall.md`**, **`_chunks_waterfall/`**, **`_manifest_waterfall.md`** |

**Extraction routing:** Use **`_page_index.md`** + **`_chunks/`** for **`01`** and **`02`** (and any note-val-only pages). Use **`_page_index_waterfall.md`** + **`_chunks_waterfall/`** for **`03`** waterfall / fee lines that live only on the Waterfall Calculations PDF. If a fee line truly appears in both PDFs, prefer one source and note it in **`04_extraction_summary.md`**. **Source Text** must quote from the chunk file (and page) you actually used — label whether the excerpt came from the **note-val** tree or the **waterfall** tree (e.g. path **`_chunks/...`** vs **`_chunks_waterfall/...`**). In **`04_extraction_summary.md`**, state explicitly that the run used **dual segmentation (Wells Fargo)** when the waterfall artifacts exist.

---

## Step 1: Segment the PDF

Run from the **repository root** (the folder that contains `noteval_extractor/`). This wraps `segment_pdf.py`:

```powershell
py -3 noteval_extractor/scripts/pdf_workflow.py "<path-to.pdf>" "<output-dir>"
```

Equivalent (if present):

```powershell
py -3 scripts/pdf_workflow.py "<path-to.pdf>" "<output-dir>"
```

**Exactly two arguments:** (1) path to the **`.pdf`** file, (2) **one** output directory where `_chunks/` and the index will be written (created if needed). Do not pass a third path — that triggers `unrecognized arguments`.

**Per-PDF output folder (recommended):** Use a **dedicated subfolder per report** so runs never overwrite each other. Put all runs under one parent (e.g. `noteval_extractor/output/`), and name the **leaf** folder after the **PDF file stem** (filename without `.pdf`), e.g. `180118_175.pdf` → `...\output\180118_175\`, or `197545_1.pdf` → `...\output\197545_1\`. The script creates that leaf directory; you do not need to create it first.

**Batch segmentation from `deal_paths.csv`:** After `get_file_path.py` writes paths, run:

```powershell
py -3 noteval_extractor/scripts/batch_segment.py --deal-paths noteval_extractor/test/deal_paths.csv --output-root noteval_extractor/output
```

Omit `--deal-paths` / `--output-root` to use defaults: `noteval_extractor/test/deal_paths.csv` if present, otherwise **`deal_paths.csv` in the parent folder of the repo** (e.g. `…/projects/deal_paths.csv`). Output root defaults to `noteval_extractor/output`. Each row is written under **`output/<deal_id>_YYYYMMDD/`** when `deal_id` and `payment_date` are present, else **`output/<pdf-stem>/`**. If **`waterfall_path`** is set (Wells Fargo), the note PDF populates the unsuffixed **`_chunks/`** / index / manifest and the waterfall PDF populates **`*_waterfall*`** artifacts in the **same** folder (see **Wells Fargo vs single-PDF** above). Rows with `status` ≠ `ok` are skipped when a `status` column exists.

**Artifacts produced** (by `segment_pdf.py`; each run writes one set — `batch_segment.py` may run twice into the same deal folder for Wells Fargo, adding the suffixed waterfall set):

- **`<output-dir>/_chunks/`** — text files such as `pages_001_030.txt` (page markers + raw `pypdf` text).
- **`<output-dir>/_page_index.md`** — table of page → short preview (navigation).
- **`<output-dir>/_manifest.md`** — chunk list and sizes.
- **`<output-dir>/_chunks_waterfall/`**, **`_page_index_waterfall.md`**, **`_manifest_waterfall.md`** — only when **`waterfall_path`** was segmented for that deal folder.

Segmentation does **not** interpret sections; that is your job in Step 4.

---

## Very large PDFs (e.g. 300+ pages)

Payment / trustee PDFs may be **very long** (300+ pages or more). The method does **not** change:

1. Use **`<output-dir>/_page_index.md`** to find which pages mention metadata, classes, waterfall, fees, or similar.
2. Open **only** the **`<output-dir>/_chunks/pages_*.txt`** files (and byte ranges within them) that cover those page numbers — see **`_manifest.md`** for chunk boundaries.

You do **not** need to read the entire PDF end-to-end if the index already shows where the useful sections live.

### No tranche or waterfall in the PDF (or not in the searched pages)

If, after a reasonable pass over the **index** and the **relevant chunks**, there is **no** material that supports **`02`** (tranche / class balances) and/or **`03`** (waterfall / proceeds), that is **acceptable**:

- Write **`01`** and **`04_extraction_summary.md`** from whatever exists (cover, TOC, headers).
- For **`02`** / **`03`**, use **N/A** prose, empty primary tables where the template allows, and **Source Text** that quotes the closest evidence (e.g. “no notes table in extracted pages”) or the TOC lines you used to decide **N/A**.
- In **`04_extraction_summary.md`**, state explicitly that **tranche** and/or **waterfall** content was **absent** (or not located), and which page ranges were checked.

Downstream tooling may have nothing to consume for **`02`** / **`03`** on that run — that is expected for some report types or redacted bundles. If you run **`validate_noteval.py`**, it may still expect minimal structure in **`02`**; resolve per project convention (e.g. honest **N/A** row, or skip validation when the report truly has no class exhibit).

---

## Step 2: Read the page index

Open **`<output-dir>/_page_index.md`** (always — this indexes the **note valuation** / primary PDF).

- Scan previews to find **Note Valuation Report**, **Distribution**, **class** / **ISIN** tables, **Determination** / **Payment** dates, and any note-val PDF content you need for **`01`** / **`02`**.
- If **`_page_index_waterfall.md`** exists (Wells Fargo), open it **separately** and map **page ranges for waterfall / fee / calculation content** for **`03`**. Page numbers are **per PDF** (page 1 in the waterfall index is page 1 of the Waterfall Calculations Report, not the note valuation file).
- For **single-PDF** trustees, the same **`_page_index.md`** often still lists **waterfall** / **Section 11.1** / fees — use that one index for everything.
- Record **page ranges** (inclusive) per extraction target before reading chunks (saves tokens and keeps context tight).

---

## Step 3: Extraction templates

Use **`noteval_extractor/references/extraction-templates.md`** as the **canonical layout** for each markdown deliverable: **`01`**, **`02`**, **`03`**, **`04`** (four files in order; **no** standalone **`05_*.md`** — class-distribution pages and **per-class deferred interest** belong in **`02`**; **`06`** is deprecated in favor of **`03`**). It mirrors the RMBS doc-extractor style: fixed filenames, stable table headers, fenced templates, and checklists per file. Class-level identifiers use separate **`ISIN`** and **`CUSIP`** columns in **`02`** (and deal-level split in **`01`** document routing) — do not merge into one field.

Every extraction file must include, in order:

1. **Extracted Data** — structured tables / fields the downstream **noteval analysis** needs.
2. **Completeness Checklist** — checkboxes for required data points (tranches, fees, dates, …).
3. **Source Text** — **verbatim** excerpts from **`_chunks/`** (and from **`_chunks_waterfall/`** when Wells Fargo waterfall PDF was the source) that you used (enough to audit; prefix blocks with **Page N** and make the file path explicit when both trees exist).

For a one-off single-topic file only, you may use the shorter pointer in **`references/extraction_template.md`**, but prefer **`extraction-templates.md`** for full runs.

Refine **`extraction-templates.md`** over time; do not invent a conflicting layout without updating the reference.

---

## Step 4: Extract section by section

For **each extraction target** below, repeat:

1. Use **Step 2** mapping to pick **page numbers** for this target (note-val index vs waterfall index per **Wells Fargo vs single-PDF** above).
2. Open the matching **`_chunks/pages_*.txt`** or **`_chunks_waterfall/pages_*.txt`** files and read only the needed page ranges.
3. Fill **Extracted Data** tables/fields per **`extraction-templates.md`**.
4. Tick every applicable item in **Completeness Checklist** (or mark **N/A** with one-line justification).
5. Paste **Source Text** from the chunk files (quote blocks or fenced excerpts; label **Page N**).
6. Write the file to **`<output-dir>/`** using the names in **`extraction-templates.md`**, e.g. `01_report_metadata.md`, `02_tranche_class_balances.md`, `03_interest_principal_waterfall.md`, `04_extraction_summary.md` (omit N/A optional legacy files but record them in **`04_extraction_summary.md`**). **Do not** create **`05_*.md`** — per-class distribution grids (**Distribution in US$**, etc.) and **deferred interest** go in **`02`** per the template. **`02`** primary (and **Tranche by listing** / **Distribution grid**) tables include **`Interest payable`** and **`Principal payable`** alongside **Interest payment** / **Principal payment** when the trustee reports due/payable vs paid separately (or payable-only). When the same **economic** tranche appears under **144A / Reg S / AI** (etc.) with **different CUSIPs**, or the **same class label** repeats on **multiple CUSIP rows** (Computershare-style), use **`02`** **primary** row (**class-level totals**) + optional **`### Tranche by listing`** (**one row per CUSIP**, each with a **`CUSIP line id`** per **`extraction-templates.md`**) and set **`04`** (summary) flag **Multi-listing tranches** when any class has **>1** CUSIP row.

**Dual principal / interest exhibits (e.g. *Principal Distribution Detail* + *Interest Distribution Detail*, same CUSIPs):** **Required** when both appear in the PDF: fill **`02`** **principal** columns from the **principal** grid and **interest rate / interest payment / interest payable** (and deferred when printed) from the **interest** grid — merge by **CUSIP** / class. Do not populate **interest** cells only from the principal grid when that grid shows **0.00** but the interest exhibit shows **non-zero** amounts for the same line. Quote **both** exhibits in **`02` Source Text**. See **`extraction-templates.md` File 02** (*Dual exhibits*).

### Extraction targets (initial set)

Adjust names to the PDF; add files if the deal has extra sections.

| # | Target | Typical hints in page index |
|---|--------|------------------------------|
| 1 | **Report metadata** → `01_report_metadata.md` | Report title, payment / determination / distribution dates, deal name; **`Payment date`** = **`Distribution date`** by business definition for CLO trustee reports (same calendar date in both columns); **Next Payment:** in headers fills both when that is the only anchor (`extraction-templates.md` **File 01**) |
| 2 | **Tranche / class balances (+ optional distribution / multi-listing)** → `02_tranche_class_balances.md` | Note Valuation, **Distribution in US$** (or similar), **separate *Principal* vs *Interest* distribution detail pages** (merge **both** into primary + optional distribution grid by CUSIP — see **`extraction-templates.md` File 02** *Dual exhibits*), **`### Summary`** optional **Total payment / total amount payable** when the class / voucher / distribution exhibit prints a trustee aggregate; **primary** table + optional **`### Tranche by listing`** (multi-CUSIP / 144A / Reg S / … — **`CUSIP line id`** on each listing row), **Deferred interest**, interest/principal, supplementary lines — **any trustee**; **Interest payment** / **Principal payment** may stay blank when the PDF has **only** payable / due columns; **Ending balance** (and beginning) **as printed** — no recomputation; if **interest paid** (or balance) **includes** **deferred interest** while both columns print, **Notes** the inclusive relationship — **do not** sum them as additive (`extraction-templates.md` **File 02**) |
| 3 | **Interest / principal waterfall** (grid and/or logical ladder) → `03_interest_principal_waterfall.md` | Waterfall, Section 11.1 / Application of …, Computershare ladders, fees, Paid / Available — single-PDF trustees: scan **`_page_index.md`**; Wells Fargo: prefer **`_page_index_waterfall.md`** / **`_chunks_waterfall/`** for fee-only calculation pages. **Do not** duplicate per-class **interest/principal** lines in **`03`** when the same amounts are already in **`02`** — keep class cash in **`02`**, use **`03`** for fees/structural lines + **verbatim Source Text**. Always add **`### Valuation-relevant fees`** (seven types: trustee **fee** only when separately stated; **trustee expense / counsel / legal** lines paid via the trustee → roll into **administrative expense** in one row; issuer fee; collateral admin; senior / subordinated management fee; hedge fee) plus **`Other`** — per **`extraction-templates.md`**. |
| 4 | **Summary** → `04_extraction_summary.md` | Compiled counts, flags, cross-checks; note **dual segmentation (Wells Fargo)** when **`_chunks_waterfall/`** was used |

**`03` — indenture / Payment Date Report three-column grids:** Some CLO **Payment Date Report** exhibits (indenture **Section 11.1**, *Disbursements from Payment Account*) print **Amount Due**, **Payment**, and **Running Balance**. Map into the stable template columns as: **Amount Due** → **`Amount payable`** (what is **due** for that priority line — obligation / accrued amount; **not** necessarily cash paid), **Payment** → **`Amount paid`** (cash **actually disbursed**), **Running Balance** → **`Amount available / running`** (remainder after the step). Prose **interest due** / **amounts due** aligns with **payable**; it may **exceed** **paid** when a line is capped, partially paid, or unpaid. For **fee-style** questions (“what left the account?”), use **Payment** / **Amount paid**; for “what was owed on the line?”, use **Amount Due** / **Amount payable**. Add a short **`### Column mapping`** in **`03`** when this layout applies (see **`references/extraction-templates.md`** blockquote under File **03**).

**`03` — Citibank (and similar) “Distribution / Per Cap / Balance” waterfalls:** Some **Citibank** trustee **Section 11.1** disbursement pages use headers like **Distribution**, **Per Cap**, and **Balance** (or **Total Admin Exp Distribution Per Cap Balance** style OCR) instead of **Amount Due / Payment / Running Balance**. In that layout, the **Distribution** column (and, on many deals, the **Per Cap** column when it carries the step’s cash-applied figure) is the **cash paid / settled** amount for the row — map it to template **`Amount paid`**. Map **Balance** to **`Amount available / running`**. If a separate **due** / **payable** column is absent, leave **`Amount payable`** blank or derive only when the indenture text for that clause clearly states an obligation amount; document once in **`03`** **`### Column mapping`**.

Cross-check ambiguous tables against **`read_noteval_usbank`** / **`read_noteval_deutsche`** skills when automating the same layouts later.

---

## Step 5: Validate

Run:

```powershell
py -3 noteval_extractor/scripts/validate_noteval.py "<output-dir>"
```

**`noteval_extractor/scripts/validate_noteval.py`** — checks required files (`01`, `02`, `04_extraction_summary.md`), at least one class row in `02`, fee-like lines in `03` waterfall when present; warns if **all** tranches have **Interest payment**, **Interest payable**, and **Dividend** each zero/blank; warns if **all** tranches have **Original**, **Beginning**, and **Ending** balance each zero/blank (sub-only deals with seniors at zero **pass** when the sub row has nonzero balances). Writes **`validation_report.md`** into **`<output-dir>/`**. Use **`--strict`** to exit with code 1 on warnings as well as errors.

If the script is unavailable, do a **manual validation pass** — re-open each `01`–`04` markdown file, confirm every checklist item is addressed, and add **`validation_report.md`** yourself.

---

## Optional: install as a Cursor project skill

Copy **`noteval_extractor/`** to **`.cursor/skills/noteval_extractor/`** in the project so the agent loads it by default (do not use the reserved `skills-cursor` namespace).

## Optional: Noteval Extractor subagent (Cursor)

For delegation in chat, use **`noteval_extractor/agents/noteval-extractor-agent.md`** — the same definition is committed at **`.cursor/agents/noteval-extractor-agent.md`** for Cursor Desktop when this repo is the project root. Copy either path to your user or other project **`.cursor/agents/`** if you want the subagent listed there. Ask: *Use the **noteval-extractor-agent** with output directory …*
