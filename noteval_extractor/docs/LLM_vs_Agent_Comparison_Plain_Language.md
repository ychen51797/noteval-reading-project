# Noteval report extraction: plain-language guide

For business and operations readers. Technical detail: `LLM_vs_SDK_Agent_Comparison.md` (and Word exports in this folder).

## What we are doing

Trustee PDFs → structured files **01–04** (dates, class balances, waterfall, summary) → validation → fees file **05**.

Everyone starts from the same **prepared PDF folder**: a page list, a file map, and full text by page.

## Three ways to extract (not two)

| Path | In the UI | In one sentence |
|------|-----------|-----------------|
| **LLM — standard (bundle)** | Run LLM pipeline, function calling **unchecked** | The computer picks which pages to send; the model writes each output file in one go. |
| **LLM — function calling** | Same button, function calling **checked** (production default) | The model asks to open the page list, the file map, and specific pages—step by step—then writes each file. |
| **SDK agent** | Run SDK agent | A Cursor “assistant” with a full playbook reads files itself over many steps and writes into a separate `*_sdk` folder. |

## What is “function calling”?

It is **not** the same as the SDK agent, but it is similar in *spirit*.

- **Standard LLM:** We bundle the pages we think matter and send them in one package per file (01, 02, 03, 04).
- **LLM + function calling:** The model can say “show me page 2 and page 4” and the server returns that text; it may do that several times before finishing one output file.
- **SDK agent:** The model can open any project file, search, run checks—much broader than the six “open page / open template” actions the web LLM allows.

**Analogy:** Standard LLM = courier delivers a pre-packed envelope. LLM tools = recipient calls and asks for specific pages from the filing cabinet. SDK agent = analyst in the office with full building access.

## How LLM tools differ from the SDK agent

| Question | LLM function calling | SDK agent |
|----------|----------------------|-----------|
| Where does it run? | Your web server + OpenAI | Cursor cloud/local agent |
| What can it open? | Only deal folder: page list, map, chunk text, templates (via fixed actions) | Whole project + skill playbook |
| How many jobs? | Four (one per output file) | One long job for all four files |
| Can it fix validation errors in the same run? | Only if you re-run | Often yes (read report, edit, re-check) |
| Page screenshots for hard tables? | No (text only) | Depends on operator / skill |
| Batch queue? | Yes — checkbox applies to every deal in batch | Separate batch SDK button |

## The page list and the file map (no jargon)

- **Page list** (`_page_index.md`): “Page 2 = Distribution in US$”, “Page 7 = interest waterfall”, etc.
- **File map** (`_manifest.md`): “Pages 1–16 are in `pages_001_016.txt`.”
- **Chunk files**: the actual PDF text.

All three paths use the same prepared folder. They differ in **who decides which pages to read** and **how many round-trips** happen.

## Class names like A-R-144A and A-R-REGS

Those two lines are **one tranche (A-R)** with two listings (144A and REGS). The primary table should show **one row A-R**, not two rows. The listing table holds **A-R-144A** and **A-R-REGS**. Same idea as **A-144A** + **A-REGS** → **A**.

## Short noteval only (what we run today)

Most reports are **12–20 pages**. Costs are **estimates** from project usage logs (not invoices).

**Models:** web LLM = **GPT-5.4**; SDK = **Composer 2**.

### Cost per deal

| Path | Per deal (approx.) |
|------|-------------------|
| Standard LLM | **3–8 cents** |
| LLM + function calling | **$1.00–$1.50** |
| SDK agent | **75 cents–$1.50** |

### Time per deal (your wait)

| Path | Typical |
|------|---------|
| Standard LLM | **5–10 minutes** |
| LLM + function calling | **15–30 minutes** |
| SDK agent | **3–8 minutes** (often fastest on short PDFs) |

Prepare PDF first: about **½–1 minute** (same for all paths).

## Pros and cons — LLM with function calling

**Pros:** Model picks pages; OpenAI-only billing; works in **batch** with the checkbox; automatic validation; fewer wrong-page packs than standard LLM.

**Cons:** **Much more expensive** than standard LLM (~$1 vs a few cents); **longer wait** than SDK on short reports; no table screenshots; limited actions—not a full assistant; quality often still below SDK (e.g. **A-R-144A** + **A-R-REGS** should be one **A-R** row).

## Pros and cons — SDK agent

**Pros:** **Best accuracy**; reads full playbook; can search and fix in one job; separate `*_sdk` folder; on short noteval, **similar cost to LLM tools** and often **faster**.

**Cons:** Needs **Cursor API** setup; cost can spike on odd runs; validation is a separate step; more technical than one UI button.

## What to expect (summary)

| | Standard LLM | LLM + tools | SDK agent |
|--|--------------|-------------|-----------|
| Cost / deal | ~3–8¢ | ~$1–$1.50 | ~75¢–$1.50 |
| Wait time | ~5–10 min | ~15–30 min | ~3–8 min |
| Quality | Good if page list is clear | Better pages | Usually best |
| Batch | Yes | Yes (checkbox) | Yes |
| Output folder | Deal folder | Deal folder | `*_sdk` |

## Simple picture

```
Prepare PDF (page list + file map + text)
    │
    ├─ Path A — Standard LLM
    │     Rules pick pages → model writes 01, 02, 03, 04 (one shot each) → validate
    │
    ├─ Path B — LLM + function calling  ← default in UI; works in batch too
    │     Model requests pages via allowed actions → writes 01–04 → validate
    │
    └─ Path C — SDK agent
          Model reads playbook → opens files freely → writes 01–04 → validate (separate)
```

## Glossary

- **LLM:** Software that reads and writes text from instructions.
- **Function calling:** The model requests specific actions (e.g. “read pages 2–4”); the server runs them and sends results back—repeat until the file is done.
- **Agent (SDK):** Same kind of model, plus broad file and command access over one long job.
- **Skill:** Project playbook (`SKILL.md`) for how extraction must be done.
- **Segmentation:** PDF → searchable text before extraction.
- **Validation:** Automatic report (`validation_report.md`) flagging gaps or suspicious values.

## Regenerating Word documents

```powershell
py -3 noteval_extractor/scripts/build_llm_vs_sdk_comparison_docx.py
py -3 noteval_extractor/scripts/build_llm_vs_sdk_comparison_simple_docx.py
```

Requires `python-docx` (`pip install python-docx`).
