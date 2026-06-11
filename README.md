# noteval-reading-project

From extracting note valuations to validation and data flowing toward our database.

**Optional (LLM draft page images):** Off by default. The tool-calling draft path does not attach screenshots. For legacy chunk-bundle **`02`** drafts on fragile PDD/IDD layouts, set **`NOTEVAL_DRAFT_PAGE_IMAGES=1`** and install **PyMuPDF** (`py -3 -m pip install pymupdf`). See `noteval_extractor/SKILL.md` and `noteval_llm.py`.

**Optional (structured PDD/IDD tables):** After segmentation, install **pdfplumber** (`py -3 -m pip install pdfplumber`) so `pdf_workflow.py` can write `_chunks_structured/pdd_idd_pdfplumber.md`. The draft **`02`** pipeline prepends that file to the chunk bundle when present.

## Contents

- **`noteval_extractor/`** — Agent-led pipeline: segment PDFs (`scripts/pdf_workflow.py`), fill templated markdown (`references/extraction-templates.md`), run `noteval_extractor/scripts/validate_noteval.py`. See `noteval_extractor/SKILL.md`.
- **`noteval_extractor/docs/`** — **LLM vs SDK comparison** (technical + plain language), including **function calling** vs chunk bundle vs Cursor agent. See `noteval_extractor/docs/README.md`.
- **`scripts/pdf_workflow.py`** — Optional repo-root wrapper that delegates to `noteval_extractor/scripts/pdf_workflow.py`.
