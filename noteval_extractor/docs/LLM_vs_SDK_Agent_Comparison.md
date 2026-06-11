# Noteval extraction: UI LLM vs SDK agent (technical)

Generated reference for engineers. Regenerate Word: `py -3 noteval_extractor/scripts/build_llm_vs_sdk_comparison_docx.py`.

## 1. Architecture at a glance

Both paths consume the same segmentation artifacts after `pdf_workflow.py` or batch segmentation:

- `_page_index.md`, `_manifest.md`, `_chunks/pages_*.txt`
- Optional Wells Fargo: `_page_index_waterfall.md`, `_chunks_waterfall/`, `_manifest_waterfall.md`

| Dimension | UI LLM (chunk bundle) | UI LLM (function calling) | SDK agent |
|-----------|------------------------|---------------------------|-----------|
| Entry | `server.py` → `/api/extraction/pipeline/start` | Same API + `use_tools: true` | `cursor_sdk_compare/run-extract.mjs` |
| Runtime | OpenAI chat completions (single user message per deliverable) | OpenAI chat completions + **tools** loop | Cursor SDK `Agent.create` + `agent.send` |
| Model | `NOTEVAL_DRAFT_MODEL` (default `gpt-5.4`) | Same | `CURSOR_MODEL` (default `composer-2.5`) |
| API key | `NOTEVAL_DRAFT_API_KEY` / `OPENAI_API_KEY` | Same | `CURSOR_API_KEY` |
| Output folder | `<dealId>_<mmddyyyy>` | Same | `<dealId>_<mmddyyyy>_sdk` |
| Navigation | Python before each API call | Model calls tools each turn | Model uses Read/Grep/Shell each turn |
| Deliverables | 4 pipeline steps (01–04) | 4 steps × N tool turns each | One agent job writes 01–04 |
| Validate | Pipeline can run `validate_noteval.py` | Same | Omitted in default SDK prompt |

## 2. Shared segmentation foundation

| Artifact | Purpose |
|----------|---------|
| `_chunks/pages_XXX_YYY.txt` | Full text with `--- Page N of T ---` headers (pypdf) |
| `_page_index.md` | Per-page preview (navigation / keyword scoring) |
| `_manifest.md` | Maps page ranges → chunk filenames |
| Chunk size (default 30) | Storage split only; typical noteval PDFs ≤30 pages → one chunk file |

## 3. UI LLM mode A — chunk bundle (default)

**Checkbox:** Function calling **on** by default (uncheck or `use_tools: false` / `NOTEVAL_DRAFT_USE_TOOLS=0` for chunk bundle).

Pipeline per deliverable (01–04):

1. Optional `noteval_index_preview.py` — LLM rewrites `_page_index.md` previews.
2. `noteval_chunk_select` — score pages from index; `chunks_covering_pages` via manifest.
3. `filter_chunk_text_to_pages` — only selected pages in chunk text.
4. `noteval_llm.build_user_message` + `openai_chat_completion` — **one** API call.
5. **02 only:** optional PDF page PNGs (`noteval_page_render`) when layout rules match.

**Limitation:** The model cannot request another page mid-call. Wrong page set → wrong columns (e.g. ending balance → principal payment).

## 4. UI LLM mode B — function calling (tools)

**Default:** Function calling **on** (`NOTEVAL_DRAFT_USE_TOOLS` unset or `1`; UI checkbox checked). Override with checkbox off, `use_tools: false`, or `NOTEVAL_DRAFT_USE_TOOLS=0`.

Implementation: `noteval_llm.openai_chat_completion_with_tools` + `noteval_llm_tools.py`.

Per deliverable loop (max turns default 14, `NOTEVAL_DRAFT_MAX_TOOL_TURNS`):

1. POST `/v1/chat/completions` with `tools` + `tool_choice: auto`.
2. If model returns `tool_calls`, server runs `execute_tool`, appends `role: tool` messages, repeats.
3. If model returns markdown with no tool calls, that text becomes the deliverable file.

**Declared tools (fixed list, not Cursor’s full toolbelt):**

| Tool | Purpose |
|------|---------|
| `read_page_index` | `_page_index.md` or waterfall index |
| `read_manifest` | Page range → chunk file map |
| `read_chunk_pages` | Text for listed 1-based PDF pages (uses manifest + page filter) |
| `read_template_excerpt` | File 01–04 template section |
| `read_structured_tables` | 02 only — optional pdfplumber MD |
| `read_prior_deliverables` | 04 only — 01–03 on disk |

**Not available in tool mode:** page PNG vision for 02; arbitrary repo Grep/Shell; re-read SKILL.md from disk each turn (SKILL/agent text still injected in the initial user message, capped).

**Batch:** `Run batch LLM extraction` spreads `collectLlmPipelineBody()` — same `use_tools` for every queued deal.

## 5. SDK agent — Cursor tools (different from LLM tools)

Launch: `Agent.create({ local: { cwd: REPO_ROOT } })`; `agent.send(prompt)`.

The model uses **Cursor’s** local executor tools (Read, Write, Grep, Shell, …), not the six functions in `noteval_llm_tools.py`.

Typical flow:

1. Read `noteval-extractor-agent.md` and `SKILL.md` once.
2. Read `_page_index.md`; plan page ranges per deliverable.
3. Read `_manifest.md`; open only needed `_chunks/pages_*.txt` (or Grep `--- Page N ---`).
4. Read `extraction-templates.md` per file section when writing.
5. Write `01`–`04`; validation is a separate step unless the operator runs it.

**Differences from LLM function calling:**

| Aspect | LLM tools (`noteval_llm_tools`) | SDK agent tools |
|--------|----------------------------------|-----------------|
| Tool surface | 4–6 fixed functions | Full IDE-style Read/Grep/Shell/Write |
| Repo access | Only files under deal folder via tools | Whole repo cwd |
| SKILL / templates | Pasted/capped in first message | Read from disk, any section |
| Session shape | 4 isolated jobs (01–04) | One long multi-turn run |
| Vision | No PNG attachment in tool mode | Manual / SKILL-driven |
| Validate in-run | Pipeline optional | Default SDK script skips validate |

## 6. Page index and manifest (both LLM modes + SDK)

1. **`_page_index.md`** — which page has which section (semantic).
2. **`_manifest.md`** — which chunk file contains pages X–Y (mechanical).
3. **`_chunks/`** — actual text.

- **Bundle LLM:** Python scores index → manifest picks files → filter pages → one completion.
- **Tool LLM:** Model calls `read_page_index` → `read_manifest` → `read_chunk_pages([...])`.
- **SDK:** Model Read/Grep equivalents on the same files.

## 7. Program-slice rollup (02)

Names like `A-R-144A` + `A-R-REGS` → one primary row **`A-R`** + listing rows (see `extraction-templates.md`). Applies to all paths; SDK often follows this more consistently than one-shot bundle LLM.

## 8. When to use which

| Use case | Recommendation |
|----------|----------------|
| Fast UI batch, predictable routing | LLM chunk bundle |
| Wrong pages in bundle; need model-driven reads | LLM function calling |
| Highest quality, Wells Fargo dual PDF, validate-and-fix | SDK agent |
| 02 needs vision PNGs on server | LLM chunk bundle (tools off) |
| No Cursor API on server | LLM only (bundle or tools) |

## 9. Short noteval only — cost, time, pros/cons

Production today uses **short** noteval PDFs (~**12–20 pages**, usually one chunk file). Figures below are for that scope (not 300-page books). Segmentation adds **~30–90 s** per PDF (not in API $ below).

### 9.1 Default models and list pricing

| Path | Default model | USD / 1M tokens (input → output) |
|------|---------------|----------------------------------|
| LLM | `gpt-5.4` | **$2.50 → $15.00** (`noteval_llm.py`) |
| SDK | `composer-2` | **$0.50 → $2.50** + ~**$0.25 / 1M** Cursor token rate (`sdk_usage_log.mjs`) |

Costs are **estimates** from `logs/noteval_draft_api_usage.log` and `logs/noteval_sdk_usage.log`.

### 9.2 Cost per deal (one full 01–04 pipeline)

| Path | Typical | Range (repo logs, 16–18 pg) |
|------|---------|----------------------------|
| LLM chunk bundle | **$0.03–$0.08** | Batch ~$0.03/deal |
| LLM function calling | **$1.00–$1.50** | Tools pipelines ~$1.0–$1.2; reruns up to ~$2.5 |
| SDK `composer-2` | **$0.75–$1.50** | Often $0.7–$1.6; outliers $2–$5 |

Bundle is **~30–50× cheaper** than tools on API $ for the same short PDF.

### 9.3 Wall-clock time per deal

| Path | Typical |
|------|---------|
| LLM chunk bundle | **~4–10 min** |
| LLM function calling | **~12–30 min** |
| SDK agent | **~2–8 min** (logged `duration_ms` often 60–165 s on 16–18 pg) |

### 9.4 Pros — LLM function calling

- Model picks pages (fewer bundle wrong-page errors).
- OpenAI key only; batch UI supports checkbox.
- Pipeline validate + optional index enrich.
- Fixed, auditable tool list (`noteval_llm_tools.py`).

### 9.5 Cons — LLM function calling

- **~20–40×** bundle cost on short deals.
- Slower than bundle; often slower than SDK on short PDFs.
- No 02 vision PNGs in tool mode.
- Narrow tools vs SDK; four separate 01–04 jobs.
- Quality usually below SDK on rollup / paid columns.

### 9.6 Pros — SDK agent

- Best quality on messy layouts (program-slice rollup, column mapping).
- Full SKILL + templates from disk; Read/Grep/Shell.
- `*_sdk` folder for safe compare.
- Competitive **time and $** on short noteval in logs.

### 9.7 Cons — SDK agent

- `CURSOR_API_KEY`, Node, `cursor_sdk_compare` setup.
- Cost less predictable; occasional $2–$5 runs.
- Validate not in default SDK prompt.
- More operator complexity than UI LLM button.

### 9.8 Tools vs SDK (short noteval)

| | LLM tools | SDK |
|--|-----------|-----|
| $/deal | ~$1–$1.50 | ~$0.75–$1.50 |
| Time | ~12–30 min | ~2–8 min |
| Quality | Good | Best |

## 10. One-page mental model

```
Segment PDF → _page_index + _manifest + _chunks
     ├─ LLM bundle:  Python picks pages → 4× completion     (~$0.05, ~5 min)
     ├─ LLM tools:   Model picks pages → 4× tool loop      (~$1+, ~20 min)
     └─ SDK agent:   Read/Grep → one agent run             (~$1, ~5 min)
```

## Key source files

- `server.py` — pipeline, `_gather_chunk_bundle`, `_draft_deliverable_core`, `use_tools`
- `noteval_chunk_select.py` — index-driven selection, manifest parse
- `noteval_llm.py` — `openai_chat_completion`, `openai_chat_completion_with_tools`
- `noteval_llm_tools.py` — tool definitions and `execute_tool`
- `noteval_index_preview.py` — optional index enrichment
- `noteval_extractor/scripts/pdf_workflow.py` — segmentation
- `cursor_sdk_compare/run-extract.mjs` — SDK agent
- `static/app.js` — `collectLlmPipelineBody()`, batch LLM
