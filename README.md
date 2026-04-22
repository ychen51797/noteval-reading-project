# noteval-reading-project

From extracting note valuations to validation and data flowing toward our database.

## Contents

- **`noteval_extractor/`** — Agent-led pipeline: segment PDFs (`scripts/pdf_workflow.py`), fill templated markdown (`references/extraction-templates.md`), run `noteval_extractor/scripts/validate_noteval.py`. See `noteval_extractor/SKILL.md`.
- **`scripts/pdf_workflow.py`** — Optional repo-root wrapper that delegates to `noteval_extractor/scripts/pdf_workflow.py`.
