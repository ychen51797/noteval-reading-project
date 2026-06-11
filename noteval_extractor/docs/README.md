# Noteval extraction documentation

| Audience | Markdown (git) | Word (regenerate) |
|----------|----------------|-------------------|
| Technical (engineers) | [LLM_vs_SDK_Agent_Comparison.md](LLM_vs_SDK_Agent_Comparison.md) | `py -3 noteval_extractor/scripts/build_llm_vs_sdk_comparison_docx.py` → `LLM_vs_SDK_Agent_Comparison.docx` |
| Plain language (ops / business) | [LLM_vs_Agent_Comparison_Plain_Language.md](LLM_vs_Agent_Comparison_Plain_Language.md) | `py -3 noteval_extractor/scripts/build_llm_vs_sdk_comparison_simple_docx.py` → `LLM_vs_Agent_Comparison_Plain_Language.docx` |

Requires `python-docx` for Word export: `pip install python-docx`.

Topics covered (May 2026):

- Three paths: **LLM chunk bundle**, **LLM function calling** (UI checkbox / batch), **SDK agent**
- How **function calling** differs from the **SDK agent** tool surface
- **Pros/cons**, **estimated cost**, and **time per deal** for **short noteval** (~12–20 pages): **gpt-5.4** vs **composer-2**
- **Page index** vs **manifest** vs **chunks**
- Program-slice rollup (**A-R-144A** + **A-R-REGS** → **A-R**)

Cost/time figures come from `logs/noteval_draft_api_usage.log` and `logs/noteval_sdk_usage.log` (approximate).
