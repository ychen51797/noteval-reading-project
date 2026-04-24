---
name: noteval_extractor
description: >-
  Agent workflow to extract note valuation / trustee payment report information
  from PDFs: segment with segment_pdf, navigate via _page_index.md, fill
  extraction-templates.md (tables, checklist, source text) per section, then
  validate with validate_noteval.py (writes validation_report.md). Use
  when the user wants human-in-the-loop or agent-led extraction, markdown
  outputs, completeness checks, or a pipeline before/ alongside read_noteval
  scripts.
---

# noteval_extractor

You are the **note valuation extraction agent**. Your job is to turn a trustee / note valuation **PDF** into **structured markdown** in an output directory, with **traceable source text** and a **completeness checklist**, then (when available) run validation.

This skill is **agent procedure**. For **programmatic** USB / Deutsche parsing, use **`read_noteval_usbank`**, **`read_noteval_deutsche`**, or **`read_noteval_logical_disb`** as appropriate.

## Prerequisites

- Python with **`pypdf`** (`pip install pypdf`).
- **`segment_pdf.py`** from **CS-Structured-Skills** (`rmbs-deal-doc-extractor/scripts/segment_pdf.py`), or set **`NOTEVAL_SEGMENT_PDF`**, or use **`--segment-script`** on the workflow runner.
- **`noteval_extractor/scripts/pdf_workflow.py`** (runs Step 1: segmentation). The repo may also ship **`scripts/pdf_workflow.py`** as a thin wrapper to the same script.

## Workflow overview

| Step | Action |
|------|--------|
| **1** | Segment the PDF (`noteval_extractor/scripts/pdf_workflow.py`) into `_chunks/`, `_page_index.md`, `_manifest.md`. |
| **2** | Read **`_page_index.md`** to map sections to page numbers. |
| **3** | Load **`references/extraction-templates.md`** — strict per-file templates (**01**, **02**, **04**, **07**; no **03**/**05**; **06** deprecated). |
| **4** | For each extraction target: locate pages → read **`_chunks/`** → fill template → write under **`<output-dir>/`**. |
| **5** | Run **`validate_noteval.py`** (when present); write **`validation_report.md`** to **`<output-dir>/`**. |

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

Omit `--deal-paths` / `--output-root` to use defaults: `noteval_extractor/test/deal_paths.csv` if present, otherwise **`deal_paths.csv` in the parent folder of the repo** (e.g. `…/projects/deal_paths.csv`). Output root defaults to `noteval_extractor/output`. Each PDF is written to `output/<stem>/`. Rows with `status` ≠ `ok` are skipped when a `status` column exists.

**Artifacts produced** (by `segment_pdf.py`):

- **`<output-dir>/_chunks/`** — text files such as `pages_001_030.txt` (page markers + raw `pypdf` text).
- **`<output-dir>/_page_index.md`** — table of page → short preview (navigation).
- **`<output-dir>/_manifest.md`** — chunk list and sizes.

Segmentation does **not** interpret sections; that is your job in Step 4.

---

## Step 2: Read the page index

Open **`<output-dir>/_page_index.md`**.

- Scan previews to find **Note Valuation Report**, **Distribution**, **waterfall**, **class** / **ISIN** tables, **Determination** / **Payment** dates, **Section 10.7**, **11.1**, etc., depending on the deal.
- Record **page ranges** (inclusive) per extraction target before reading chunks (saves tokens and keeps context tight).

---

## Step 3: Extraction templates

Use **`noteval_extractor/references/extraction-templates.md`** as the **canonical layout** for each markdown deliverable: **`01`**, **`02`**, **`04`**, and **`07`** (there is **no** `03_*.md` or **`05_*.md`** — class-distribution pages and **per-class deferred interest** belong in **`02`**; **`06`** is deprecated in favor of **`04`**). It mirrors the RMBS doc-extractor style: fixed filenames, stable table headers, fenced templates, and checklists per file. Class-level identifiers use separate **`ISIN`** and **`CUSIP`** columns in **`02`** (and deal-level split in **`01`** document routing) — do not merge into one field.

Every extraction file must include, in order:

1. **Extracted Data** — structured tables / fields the downstream **noteval analysis** needs.
2. **Completeness Checklist** — checkboxes for required data points (tranches, fees, dates, …).
3. **Source Text** — **verbatim** excerpts from **`_chunks/`** that you used (enough to audit; prefix blocks with **Page N**).

For a one-off single-topic file only, you may use the shorter pointer in **`references/extraction_template.md`**, but prefer **`extraction-templates.md`** for full runs.

Refine **`extraction-templates.md`** over time; do not invent a conflicting layout without updating the reference.

---

## Step 4: Extract section by section

For **each extraction target** below, repeat:

1. Use **Step 2** mapping to pick **page numbers** for this target.
2. Open the matching **`_chunks/pages_*.txt`** files and read only the needed page ranges.
3. Fill **Extracted Data** tables/fields per **`extraction-templates.md`**.
4. Tick every applicable item in **Completeness Checklist** (or mark **N/A** with one-line justification).
5. Paste **Source Text** from the chunk files (quote blocks or fenced excerpts; label **Page N**).
6. Write the file to **`<output-dir>/`** using the names in **`extraction-templates.md`**, e.g. `01_report_metadata.md`, `02_tranche_class_balances.md`, `04_interest_principal_waterfall.md`, `07_extraction_summary.md` (omit N/A optional legacy files but record them in `07_extraction_summary.md`). **Do not** create `03_*.md` or **`05_*.md`** — per-class distribution grids (**Distribution in US$**, etc.) and **deferred interest** go in **`02`** per the template. **`02`** primary (and **Tranche by listing** / **Distribution grid**) tables include **`Interest payable`** and **`Principal payable`** alongside **Interest payment** / **Principal payment** when the trustee reports due/payable vs paid separately (or payable-only). When the same **economic** tranche appears under **144A / Reg S / AI** (etc.) with **different CUSIPs**, use **`02`** **primary** row + optional **`### Tranche by listing`** and set **`07`** flag **Multi-listing tranches**.

### Extraction targets (initial set)

Adjust names to the PDF; add files if the deal has extra sections.

| # | Target | Typical hints in page index |
|---|--------|------------------------------|
| 1 | **Report metadata** → `01_report_metadata.md` | Report title, payment / determination / distribution dates, deal name; **`Payment date`** = **`Distribution date`** by business definition for CLO trustee reports (same calendar date in both columns); **Next Payment:** in headers fills both when that is the only anchor (`extraction-templates.md` **File 01**) |
| 2 | **Tranche / class balances (+ optional distribution / multi-listing)** → `02_tranche_class_balances.md` | Note Valuation, **Distribution in US$** (or similar), **`### Summary`** optional **Total payment / total amount payable** when the class / voucher / distribution exhibit prints a trustee aggregate; **primary** table + optional **`### Tranche by listing`** (144A / Reg S / …), **Deferred interest**, interest/principal, supplementary lines — **any trustee**; **Interest payment** / **Principal payment** may stay blank when the PDF has **only** payable / due columns; **Ending balance** (and beginning) **as printed** — no recomputation (`extraction-templates.md` **File 02**) |
| 4 | **Interest / principal waterfall** (grid and/or logical ladder) → `04_interest_principal_waterfall.md` | Waterfall, Section 11.1 / Application of …, Computershare ladders, fees, Paid / Available |
| 7 | **Summary** → `07_extraction_summary.md` | Compiled counts, flags, cross-checks |

**`04` — indenture / Payment Date Report three-column grids:** Some CLO **Payment Date Report** exhibits (indenture **Section 11.1**, *Disbursements from Payment Account*) print **Amount Due**, **Payment**, and **Running Balance**. Map into the stable template columns as: **Amount Due** → **`Amount payable`** (what is **due** for that priority line — obligation / accrued amount; **not** necessarily cash paid), **Payment** → **`Amount paid`** (cash **actually disbursed**), **Running Balance** → **`Amount available / running`** (remainder after the step). Prose **interest due** / **amounts due** aligns with **payable**; it may **exceed** **paid** when a line is capped, partially paid, or unpaid. For **fee-style** questions (“what left the account?”), use **Payment** / **Amount paid**; for “what was owed on the line?”, use **Amount Due** / **Amount payable**. Add a short **`### Column mapping`** in **`04`** when this layout applies (see **`references/extraction-templates.md`** blockquote under File 04).

Cross-check ambiguous tables against **`read_noteval_usbank`** / **`read_noteval_deutsche`** skills when automating the same layouts later.

---

## Step 5: Validate

Run:

```powershell
py -3 noteval_extractor/scripts/validate_noteval.py "<output-dir>"
```

**`noteval_extractor/scripts/validate_noteval.py`** — checks required files (`01`, `02`, `07`), at least one class row in `02`, fee-like lines in `04` waterfall when present; warns if **all** tranches have **Interest payment**, **Interest payable**, and **Dividend** each zero/blank; warns if **all** tranches have **Original**, **Beginning**, and **Ending** balance each zero/blank (sub-only deals with seniors at zero **pass** when the sub row has nonzero balances). Writes **`validation_report.md`** into **`<output-dir>/`**. Use **`--strict`** to exit with code 1 on warnings as well as errors.

If the script is unavailable, do a **manual validation pass** — re-open each `0*_*.md` (and `07_extraction_summary.md`), confirm every checklist item is addressed, and add **`validation_report.md`** yourself.

---

## Optional: install as a Cursor project skill

Copy **`noteval_extractor/`** to **`.cursor/skills/noteval_extractor/`** in the project so the agent loads it by default (do not use the reserved `skills-cursor` namespace).

## Optional: Noteval Extractor subagent (Cursor)

For delegation in chat, use **`noteval_extractor/agents/noteval-extractor-agent.md`** — the same definition is committed at **`.cursor/agents/noteval-extractor-agent.md`** for Cursor Desktop when this repo is the project root. Copy either path to your user or other project **`.cursor/agents/`** if you want the subagent listed there. Ask: *Use the **noteval-extractor-agent** with output directory …*
