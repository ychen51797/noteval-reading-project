# Extraction output template (noteval_extractor)

**Canonical per-file templates** (same style as RMBS `extraction-templates.md`):  
→ **[extraction-templates.md](extraction-templates.md)** — use that document for filenames `01_report_metadata.md` through `07_extraction_summary.md`, stable column headers, and section-by-section fenced templates.

This file is a **minimal single-topic fallback** when you only need one small artifact; still use the three-part structure:

1. **Extracted Data**
2. **Completeness Checklist**
3. **Source Text** (verbatim from `_chunks/`, **Page N** labels)

---

## Optional YAML header

```yaml
---
source_pdf: "<path>"
extraction_target: "<topic>"
pdf_pages_used: "<e.g. 12-18>"
extracted_at: "<ISO-8601>"
---
```

---

## Revision log

| Version | Change |
|---------|--------|
| 0.1 | Initial scaffold |
| 0.2 | Point to extraction-templates.md for full multi-file templates |
