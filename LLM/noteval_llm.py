"""
``noteval_llm.py`` — OpenAI-compatible chat completions for the noteval UI extraction agent.

Uses stdlib only (urllib). Configure with environment variables:

- NOTEVAL_DRAFT_API_KEY — preferred
- OPENAI_API_KEY — fallback
- NOTEVAL_DRAFT_BASE_URL — optional (default https://api.openai.com/v1)
- NOTEVAL_DRAFT_MODEL — optional (default gpt-5.4)
- NOTEVAL_DRAFT_USAGE_LOG — optional path to append JSONL usage lines (default:
  ``<repo_root>/logs/noteval_draft_api_usage.log``). Set to ``0`` or ``off`` to disable.
- NOTEVAL_DRAFT_PRICE_INPUT_PER_1M — optional USD per 1M **input** tokens (overrides built-in table)
- NOTEVAL_DRAFT_PRICE_OUTPUT_PER_1M — optional USD per 1M **output** tokens (overrides built-in table)
- NOTEVAL_DRAFT_USE_TOOLS — default **on** (function-calling loop via ``noteval_llm_tools``). Set ``0`` / ``off`` for
  one-shot pre-built chunk bundle per deliverable.
- NOTEVAL_DRAFT_MAX_TOOL_TURNS — max model↔tool round-trips per deliverable (default ``14``).

Built-in USD/1M estimates (approximate; set the PRICE_* env vars for your provider’s list price)
are used only when both PRICE env vars are unset and the model name matches a known prefix.
"""

from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

DEFAULT_MODEL = "gpt-5.4"
DEFAULT_BASE = "https://api.openai.com/v1"

_LOG_LOCK = threading.Lock()

# Approximate list-style USD per 1M tokens (input, output). Override with env for billing accuracy.
# Longer prefixes first (``gpt-5.4-mini`` before ``gpt-5.4`` — ``startswith`` matching).
_MODEL_PRICE_USD_PER_1M: list[tuple[str, float, float]] = [
    ("gpt-5.4-mini", 0.75, 4.50),
    ("gpt-5.4", 2.50, 15.00),  # OpenAI standard API list (Mar 2026); override via PRICE_* env
    ("gpt-4o-mini", 0.15, 0.60),
    ("gpt-4.1-mini", 0.40, 1.60),
    ("gpt-4.1-nano", 0.10, 0.40),
    ("gpt-4.1", 2.00, 8.00),
    ("gpt-4o", 2.50, 10.00),
    ("gpt-4-turbo", 10.00, 30.00),
    ("gpt-3.5-turbo", 0.50, 1.50),
]


def draft_env() -> tuple[str, str, str]:
    """Return (api_key, base_url_without_trailing_slash, model)."""
    api_key = (
        os.environ.get("NOTEVAL_DRAFT_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    base = (os.environ.get("NOTEVAL_DRAFT_BASE_URL") or DEFAULT_BASE).strip().rstrip("/")
    model = (os.environ.get("NOTEVAL_DRAFT_MODEL") or DEFAULT_MODEL).strip()
    return api_key, base, model


def _usage_log_path_resolved() -> Path | None:
    raw = os.environ.get("NOTEVAL_DRAFT_USAGE_LOG", "").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return None
    if raw:
        return Path(raw).expanduser().resolve()
    root = Path(__file__).resolve().parent
    d = root / "logs"
    return (d / "noteval_draft_api_usage.log").resolve()


def draft_config_public() -> dict[str, bool | str | None]:
    key, base, model = draft_env()
    log_p = _usage_log_path_resolved()
    try:
        import noteval_llm_tools as _tools

        tools_default = _tools.draft_use_tools_enabled()
        max_tool_turns = _tools.draft_max_tool_turns()
    except ImportError:
        tools_default = True
        max_tool_turns = 14
    return {
        "configured": bool(key),
        "model": model,
        "base_url": None if base == DEFAULT_BASE else base,
        "usage_log_path": str(log_p) if log_p else None,
        "usage_log_enabled": bool(log_p),
        "use_tools_default": tools_default,
        "max_tool_turns_default": max_tool_turns,
    }


def _extract_usage_counts(body: dict) -> tuple[int | None, int | None, int | None]:
    u = body.get("usage")
    if not isinstance(u, dict):
        return None, None, None
    pt = u.get("prompt_tokens")
    if pt is None:
        pt = u.get("input_tokens")
    ct = u.get("completion_tokens")
    if ct is None:
        ct = u.get("output_tokens")
    tt = u.get("total_tokens")
    try:
        pi = int(pt) if pt is not None else None
    except (TypeError, ValueError):
        pi = None
    try:
        ci = int(ct) if ct is not None else None
    except (TypeError, ValueError):
        ci = None
    try:
        ti = int(tt) if tt is not None else None
    except (TypeError, ValueError):
        ti = None
    if ti is None and pi is not None and ci is not None:
        ti = pi + ci
    return pi, ci, ti


def _table_price_per_million(model: str) -> tuple[float, float] | None:
    m = model.strip().lower()
    for prefix, inp, out in _MODEL_PRICE_USD_PER_1M:
        if m.startswith(prefix):
            return inp, out
    return None


def _estimate_cost_usd(model: str, pt: int | None, ct: int | None) -> tuple[float | None, str | None]:
    """
    Return (cost_usd, pricing_note). ``pricing_note`` is set when cost is None or approximate.
    """
    if pt is None or ct is None:
        return None, "missing_token_counts"
    env_in = os.environ.get("NOTEVAL_DRAFT_PRICE_INPUT_PER_1M", "").strip()
    env_out = os.environ.get("NOTEVAL_DRAFT_PRICE_OUTPUT_PER_1M", "").strip()
    if env_in and env_out:
        try:
            cost = (pt * float(env_in) + ct * float(env_out)) / 1_000_000
            return round(cost, 6), "env_rates"
        except ValueError:
            return None, "invalid_env_rates"
    tab = _table_price_per_million(model)
    if tab:
        inp, out = tab
        cost = (pt * inp + ct * out) / 1_000_000
        return round(cost, 6), "builtin_table_approx"
    return None, "unknown_model_set_NOTEVAL_DRAFT_PRICE_*_PER_1M"


def _append_usage_log_line(record: dict) -> None:
    path = _usage_log_path_resolved()
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _LOG_LOCK:
        path.open("a", encoding="utf-8").write(line)


def _summarize_usage_entries(entries: list[dict]) -> dict:
    """Sum tokens / cost for JSONL objects produced by ``openai_chat_completion``."""
    n = 0
    pt = ct = 0
    tt_explicit = 0
    n_tt = 0
    cost_sum = 0.0
    n_cost = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        if "prompt_tokens" not in e and "completion_tokens" not in e and "total_tokens" not in e:
            continue
        n += 1
        p = e.get("prompt_tokens")
        c = e.get("completion_tokens")
        t = e.get("total_tokens")
        if isinstance(p, int):
            pt += p
        if isinstance(c, int):
            ct += c
        if isinstance(t, int):
            tt_explicit += t
            n_tt += 1
        cu = e.get("cost_usd")
        if cu is not None:
            try:
                cost_sum += float(cu)
                n_cost += 1
            except (TypeError, ValueError):
                pass
    tt = tt_explicit if n_tt else None
    if tt is None and (pt or ct):
        tt = pt + ct
    return {
        "requests": n,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
        "cost_usd_sum": round(cost_sum, 6) if n_cost else None,
        "lines_with_cost": n_cost,
    }


def summarize_draft_usage_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Aggregate token/cost across in-memory usage dicts (same keys as JSONL lines from
    ``openai_chat_completion``). Used by the extraction pipeline for **this run only**;
    see ``draft_usage_log_read_tail`` for file-tail summaries that may include older sessions.
    """
    return _summarize_usage_entries(records)


def draft_usage_log_read_tail(
    *,
    max_lines: int = 50,
    max_bytes: int = 512_000,
) -> dict:
    """
    Read the last non-empty lines from the usage JSONL log (bounded read from end of file).

    ``summary`` aggregates token/cost fields across successfully parsed JSON objects in that tail.
    The tail may include requests from prior runs, not only the latest pipeline.
    """
    path = _usage_log_path_resolved()
    if path is None:
        return {
            "enabled": False,
            "path": None,
            "raw_tail_lines": [],
            "parsed": [],
            "summary": None,
            "note": "usage logging disabled (NOTEVAL_DRAFT_USAGE_LOG=off)",
        }
    if not path.is_file():
        return {
            "enabled": True,
            "path": str(path),
            "raw_tail_lines": [],
            "parsed": [],
            "summary": None,
            "note": "log file not created yet (no LLM calls logged)",
        }
    try:
        data = path.read_bytes()
    except OSError as e:
        return {
            "enabled": True,
            "path": str(path),
            "raw_tail_lines": [],
            "parsed": [],
            "summary": None,
            "note": f"read error: {e}",
        }
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    text = data.decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    parsed: list[dict] = []
    for ln in tail:
        try:
            obj = json.loads(ln)
            parsed.append(obj if isinstance(obj, dict) else {"_non_object": str(obj)[:200]})
        except json.JSONDecodeError:
            parsed.append({"_unparsed_line": ln[:800]})
    usage_like = [
        x
        for x in parsed
        if isinstance(x, dict)
        and "_unparsed_line" not in x
        and "_non_object" not in x
        and ("prompt_tokens" in x or "total_tokens" in x)
    ]
    summary = _summarize_usage_entries(usage_like)
    return {
        "enabled": True,
        "path": str(path),
        "raw_tail_lines": tail,
        "parsed": parsed,
        "summary": summary,
        "note": f"aggregated over last {len(tail)} non-empty line(s) in file tail (may include older runs)",
    }


def draft_usage_log_path() -> Path | None:
    return _usage_log_path_resolved()


def draft_usage_cost_by_deal_folder(*, max_bytes: int = 2_000_000) -> dict[str, float]:
    """Estimated USD per deal folder from ``logs/noteval_draft_api_usage.log`` (sums 01–04 calls)."""
    from noteval_sdk_usage import jsonl_cost_sum_by_deal_folder

    return jsonl_cost_sum_by_deal_folder(draft_usage_log_path(), max_bytes=max_bytes)


def draft_usage_cost_latest_run_by_deal_folder(*, max_bytes: int = 2_000_000) -> dict[str, float]:
    """
    Latest LLM pipeline USD per deal folder: sum ``cost_usd`` for the last contiguous
    block of log lines per ``deal_folder`` (01–04 API calls in one pipeline run).
    """
    path = draft_usage_log_path()
    if path is None or not path.is_file():
        return {}
    try:
        data = path.read_bytes()
    except OSError:
        return {}
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    text = data.decode("utf-8", errors="replace")
    last_run: dict[str, float] = {}
    current: dict[str, float] = {}
    prev_folder: str | None = None
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        folder = obj.get("deal_folder")
        if not folder:
            continue
        cu = obj.get("cost_usd")
        if cu is None:
            continue
        try:
            cost = float(cu)
        except (TypeError, ValueError):
            continue
        key = str(folder).strip()
        if not key:
            continue
        if prev_folder is not None and key != prev_folder:
            last_run[prev_folder] = round(current.get(prev_folder, 0.0), 6)
            current[prev_folder] = 0.0
        current[key] = round(current.get(key, 0.0) + cost, 6)
        prev_folder = key
    if prev_folder is not None:
        last_run[prev_folder] = round(current.get(prev_folder, 0.0), 6)
    return last_run


SYSTEM_PROMPT = """You are a structured extraction assistant for U.S. CLO / RMBS trustee and note valuation PDFs.
You output ONE markdown file: the user's target deliverable (01–04).
Follow the template excerpt: use the same top-level `#` title, section names, and table column headers where the template shows them.
Use these sections in order when the template expects them: ## Extracted Data, ## Completeness Checklist, ## Source Text.
In ## Source Text, quote CHUNK EXCERPTS verbatim when possible. When a chunk line shows a page marker like "--- Page N of ... ---", keep or add a **Page N** label near the quoted lines.
Do not invent currency amounts, dates, CUSIPs, or class rows not supported by the chunks. **Never** copy template examples (e.g. repeated **SUB** rows with placeholder CUSIPs).

For **every deliverable with chunk text:** Read the **index-driven page map** at the top of the bundle first — it lists the only pages and `_chunks/` files selected from `_page_index.md`. Do not use content from other pages.
For **`02` (class / tranche balances):** Also read the **File 02 — layout detection** block and **`_page_index.md` roles** when present. **Prioritize** index pages tagged **Distribution in US$** / **Interest Detail** for balances and interest **$**. **Skip** pages tagged **Factor per 1000** / **Factor Information per 1000** for balance and interest **$** mapping (**Current Coupon** → **Interest rate** only — **Deutsche Bank:** **do not** concatenate **Index** + **Spread** from **Coupon Rates**). When **Distribution in US$** exists alongside factor grids, **primary $** comes from the **$** table only (see template **Distribution in US$ — primary authority**). **Primary** = **one row per economic class** (**A**, **SUB**, …); **program slices** (**SUB-144A**, **A-REGS**, …) → **`### Tranche by listing`** with per-CUSIP **$** from the **$** exhibit. Use **printed class subtotal** or **Total** on the **$** table when present; else sum listing with **Notes**. **Never** map **factor ~1000** into balances or interest **$**.
Map by **printed column headers** on **that** table (or attached page images when headers wrap) — **not** column position alone:
- **Interest paid** / **Interest Paid** → **Interest payment** (not **Interest Due** unless that column is clearly period cash paid)
- **Principal paid** / **Principal Paid** / **Principal Payments** / **Principal distribution** → **Principal payment** (period cash — **not** ending balance, **not** **Principal Distribution Factor** / **~1000** factor cells)
- **Distribution in US$** with **Prior principal balance** + **Current principal balance**: **Prior** → **Beginning balance**; **Current** → **Ending balance** (same **Class** row) — **not** **Original balance**
- **Beginning** / **Ending** / **Outstanding** → other balance columns only when those headings say balance/outstanding (when no prior/current pair on the **$** table)
- **Coupon** / **All In Rate** / **Interest rate** (numeric **%** or index+margin) → **Interest rate** — **never** **Factor**, **Distribution Factor**, or bare decimals like **19.07** / **1000** without a **%** accrual label
- **Floating**/**Fixed** alone → not **Interest rate**
**Anti-pattern — “Original only” rows:** On **Distribution in US$** / NVR **$** tables, the **first** numeric column is often **Original face** — **do not** copy it into **Original balance** and leave **Beginning balance**, **Ending balance**, **Interest payment**, and **Interest rate** as **0.00** without reading the **rest of the same row** plus **Interest Detail** / **Coupon** pages. **Complete every primary column** from the **$** exhibit; **`Interest rate`** from **Current Coupon** on **Distribution in US$** when printed (**Deutsche Bank:** not **Index** + **Spread** from **Coupon Rates**).
**Do not truncate the class list:** If Source Text shows **I-SUB-144A**, **I-SUB-REGS**, **II-SUB-144A**, **II-SUB-REGS** (or similar), **every** printed line must appear in **primary** and/or **listing** — the model often stops after **I-SUB** and drops **II-SUB** rows.
**Accrued Interest** is accrual unless the template’s Distribution Report summary rule applies. **Deferred interest** from a clearly labeled deferred / shortfall column when present.
When the chunk bundle includes ``_chunks_structured/pdd_idd_pdfplumber.md`` and/or ``_chunks_structured/payment_date_report_pdfplumber.md``, prefer their column headers and row grouping over positional guesses in linearized text; still quote ``_chunks/*.txt`` in **Source Text** (never cite structured files as Source Text).

For fee / waterfall rows (`03`): map **Amount paid** only from columns the trustee labels **Paid** / **Payment** / **Settled** (by **printed header**, not column position). Map **Available** / **Running Balance** / **Available for Disbursements** / **Balance** (post-step pool) → **Amount available / running** — **never** into **Amount paid**. **Due** / **Payable** → **Amount payable** (never **Amount paid**). Record **this deal** in **`### Column mapping`**; column order differs by trustee. **Do not** add `### Valuation-relevant fees` in `03`. Non-numeric words in money cells → **N/A** or blank in tables; keep literals in **Source Text** only.
Output ONLY the markdown document body — no preamble and no markdown code fences wrapping the entire document."""


def _class_table_layout_reminder(chunk_bundle: str) -> str:
    """Short ``02`` rules: index-first, no template examples, header-based mapping."""
    low = chunk_bundle.lower().replace("\\", "/")
    has_pdd = "pdd_idd_pdfplumber.md" in low
    has_pdr = "payment_date_report_pdfplumber.md" in low
    if has_pdd or has_pdr:
        names: list[str] = []
        if has_pdd:
            names.append("`_chunks_structured/pdd_idd_pdfplumber.md`")
        if has_pdr:
            names.append("`_chunks_structured/payment_date_report_pdfplumber.md`")
        files = " and ".join(names)
        structured = (
            f"- **Structured tables:** {files} in the bundle — prefer their **column headers** and row "
            "grouping when linear `_chunks/*.txt` order is wrong. Still quote `_chunks/*.txt` in "
            "**`## Source Text`** only.\n"
        )
        if has_pdd:
            structured += (
                "- **PDD/IDD (Computershare):** **Interest payment** from IDD **Sub Totals / class footer** "
                "**Interest Distribution** column for that **Note Class** — **not** **0.00** on the "
                "period-beginning-aligned subtotal line. **SUB:** **0.00000** coupon still has **Interest "
                "Distribution** cash on IDD (sum CUSIPs or footer). **Next Payment / Residual** = rate only. "
                "**Primary** = one row per **Note Class**; **listing** = one row per CUSIP. "
                "**-R** / **-RR** / **CR2**; **D** / **D-R** / **D-RR**, **CR** / **CRR** separate.\n"
                "- Do not treat a single letter glued after **Sub Totals** in linearized text as the class name — "
                "use the **Note Class** on the section header row.\n"
            )
    else:
        structured = (
            "- Rely on **printed headings** in the chunk (and page images if attached). "
            "**Notes** once when column order is ambiguous.\n"
        )
    return (
        "**Class table (`02`) — mandatory:**\n"
        "- Use the **index-driven page map** and **layout detection** blocks above — only those pages/chunks are in the bundle.\n"
        "- **Distribution in US$ / NVR $ table** (when present) = authoritative for **primary** balances and interest/principal **$**; "
        "factor / PDD **~1000** cells are **not** balances.\n"
        "- **Primary** = one row per **economic** class; **144A/Reg S/AI** slices → **listing** when **Multi-listing** = **Y**.\n"
        "- **`Class`** on **primary** = economic label (**SUB**, **A**, …) or trustee subtotal name; listing keeps **verbatim** slice labels.\n"
        "- **Do not** invent placeholder CUSIPs (12345ABC7, etc.) or filler **Distribution grid** / **Tranche by listing** "
        "sections unless the PDF has them.\n"
        "- **Distribution in US$ prior/current pair:** **Prior principal balance** → **Beginning balance**; "
        "**Current principal balance** → **Ending balance** (per-page chunk hints repeat this when the **$** grid is on that page).\n"
        "- **Interest paid** → **Interest payment**; **Principal paid** → **Principal payment** (period cash — not ending balance).\n"
        "- **Indenture NVR — Interest payable to [Class] Notes:** subsection **(2)** per-class "
        "**Interest payable to … Notes** **$** → **Interest payment** **and** **Interest payable** "
        "(same value; no separate paid column — not N/A on payment).\n"
        "- A **0%** or blank **coupon** does **not** mean **zero interest** if a **separate Interest Distribution Detail** column shows interest cash paid **by label**.\n"
        "- **SUB / Distribution Summary:** **Dividends 0.00** + **Ending principal < Beginning** → **`Principal payment`** = Beginning − Ending; "
        "**Interest payment** / **Interest payable** **0.00** (do not use Accrued Interest column when it equals the balance drop).\n"
        "- **Do not** fill only **Original balance** then zero the rest — map **Beginning** / **Ending** from **Prior** / **Current** on the **$** row; "
        "**Interest rate** from **Current Coupon** (often on **Distribution in US$**); "
        "**Deutsche Bank:** not **Index** + **Spread** from **Coupon Rates**.\n"
        "- **Interest Detail (Deutsche):** **Prior Cumulative** ≠ **Interest payment**; use **Interest Paid** only.\n"
        + structured
    )


def build_user_message(
    *,
    target: str,
    filename: str,
    repository_context: str,
    template_excerpt: str,
    prior_deliverables: str,
    chunk_bundle: str,
    current_draft: str,
    extra_instructions: str,
) -> str:
    parts: list[str] = [
        f"Deliverable file: **{filename}** (template section id `{target}`).\n",
    ]
    if repository_context.strip():
        parts += [
            "\n## Repository instructions (plain text; follow when they do not conflict "
            "with the file-specific excerpt)\n\n",
            repository_context.strip(),
        ]
    parts += [
        "\n\n## File-specific template excerpt (canonical structure for this deliverable)\n\n",
        template_excerpt.strip(),
    ]
    if prior_deliverables.strip():
        parts += [
            "\n\n## Prior deliverables already drafted in this folder "
            "(for 04 summary: synthesize **only** from 01–03 below; do not re-extract from PDF chunks)\n\n",
            prior_deliverables.strip()[:120_000],
        ]
    if target == "04":
        parts += [
            "\n\n## Target-specific reminder (`04`)\n\n"
            "**Extraction summary only:** compile counts, flags, cross-checks, and file status from "
            "**`01_report_metadata.md`**, **`02_tranche_class_balances.md`**, and "
            "`03_interest_principal_waterfall.md` already in this folder. **Do not** treat `_chunks/` "
            "as a primary source for new extraction. Optional brief page-range notes may reference "
            "what 01–03 quoted in **Source Text**.\n",
        ]
    if target == "02":
        parts += [
            "\n\n## File 02 — class table (read layout block in chunk bundle first)\n\n",
            _class_table_layout_reminder(chunk_bundle),
        ]
    if chunk_bundle.strip() or target != "04":
        index_note = ""
        if "index-driven page map" in chunk_bundle.lower():
            index_note = (
                "**Scope:** Chunk text below is limited to pages/chunks from `_page_index.md` "
                "(and waterfall index for `03` when applicable). Map fields only from these excerpts.\n\n"
            )
        parts += [
            "\n\n## PDF chunk text (index-selected segmentation output)\n\n",
            index_note,
            chunk_bundle.strip() or "(none — not used for this deliverable)",
        ]
    if current_draft.strip():
        parts += [
            "\n\n## Current editor draft\n\n"
            "Revise and complete this draft; preserve correct structure and improve tables/checklists.\n\n",
            current_draft.strip()[:120_000],
        ]
    if extra_instructions.strip():
        parts += [
            "\n\n## Additional user instructions\n\n",
            extra_instructions.strip()[:20_000],
        ]
    if target == "02":
        parts.append(
            "\n\n## Target-specific reminder (`02`)\n\n"
            "Map by **printed headers** on the pages in the layout index map (and page images if attached). "
            "**Interest paid** → **Interest payment**; **Principal paid** / **Principal Payments** → **Principal payment** "
            "(period cash — not ending balance, not distribution factor). On **Distribution in US$**, "
            "**Ending balance** = **Current principal balance** and **Beginning balance** = **Prior principal balance** "
            "(not **Original balance**). **Accrued Interest** is accrual unless the Distribution Report summary rule in the template applies. "
            "**Deferred interest** from a clearly labeled deferred / shortfall column when present. "
            "When **Principal Payments** is **0.00** and balances are flat, **Principal payment** stays **0.00**. "
            "**Ending zero paydown:** When **Principal payment** is 0/blank, **Beginning balance** > 0, and **Ending balance** "
            "= **0.00** from **Aggregate Outstanding Amount of Notes after giving effect to Principal Payments** (or equivalent "
            "outstanding column; `-` → **0.00**), fill **Principal payment** only when Section **11.1** / waterfall **class principal "
            "**Amount paid** matches **Beginning balance** for that class — use the waterfall **$**, **not** Beginning balance alone. "
            "Skip when **Ending balance** = **Beginning balance**. "
            "**SUB / subordinated — Distribution Summary / NVR (priority):** When **Dividends** are **0.00**, "
            "**coupon** is **0%**, and **Closing/Ending principal** < **Opening/Beginning**, set **`Principal payment`** "
            "= Beginning − Ending; **`Interest payment`** / **`Interest payable`** **0.00**; **`Dividend`** **0.00** — "
            "even if the trustee prints the **$** under **Accrued Interest** / **Current Payable**. "
            "**Computershare IDD — SUB / zero coupon (when separate IDD exists):** **Interest Distribution** column on "
            "IDD **Sub Totals / footer** = **`Interest payment`** only when **non-zero** and **not** overridden by the "
            "Distribution Summary principal rule above. **Do not** copy **0.00** from period-beginning subtotal lines. "
            "**Dividend with no interest paid:** non-zero **Dividend** with blank **Interest paid** → **`Interest payment`**; "
            "when **Dividends** are **0.00**, use principal rule instead. "
            "**Multi-listing + Distribution in US$:** set **`Multi-listing tranches?` = Y** when slices exist; "
            "**listing** = per-slice **$** from the **$** table; **primary** = one economic row per class from "
            "**subtotal/Total** on Distribution in US$ / NVR (or sum listing with **Notes**). "
            "**Program slices → one primary:** **A-R-144A** and **A-R-REGS** are the **same** tranche — primary "
            "**Class** = **A-R** (not **A-R-144A**); **SUB-144A** / **SUB-REGS** → primary **SUB**; "
            "**A-144A** / **A-REGS** → primary **A**. Put each **-144A** / **-REGS** / **-AI** line in "
            "**### Tranche by listing** only. "
            "**Preference Share / Preferred Shares:** When on the **class summary with note tranches**, **one primary row** "
            "(not **### Supplementary lines** only) — include in **Number of classes / tranches listed**. "
            "**DISTRIBUTION REPORT Section 10.5(b):** **(C) interest payable** secured → **Interest payable**; "
            "**(D) payments on Subordinated Notes** → **Interest payment** (required). "
            "**Applicable Periodic Rate** page → **Interest rate** — read page **(v)** chunk, not page 1 only. "
            "**Notes Information:** **Interest Paid** → **Interest payment**; **Deferred Interest Paid/Due** → **Deferred interest** only — "
            "map by **header titles** in the chunk, **never** by position after **All In Rate**; **0% All In Rate on SUB is normal**. "
            "**NOTE VALUATION REPORT — Periodic Interest Amount:** **Periodic Interest Amount on [Class]** with numeric **$** "
            "→ **Interest payment** (not **Interest payable** only). "
            "**NOTE VALUATION REPORT — Interest payable to [Class] Notes:** per-class "
            "**Interest payable to … Notes** **$** (subsection **(2)**; no separate paid column) → "
            "**Interest payment** **and** **Interest payable** (same **$**). "
            "**Deutsche Bank NVR:** **Interest rate** = **Current Coupon** on **Distribution in US$** "
            "(not **Index** + **Spread** from **Coupon Rates**). "
            "**Interest Detail:** **Prior Cumulative** ≠ **Interest payment**. "
            "Factor page: coupon reference only — not primary balances. "
            "**Anti-pattern:** non-zero **Original balance** with **all other** primary columns **0.00** while Source Text "
            "shows **Distribution in US$** / **Interest Detail** data for that class — re-read page 2 (US$) before shipping.\n"
        )
    if target == "03":
        parts.append(
            "\n\n## Target-specific reminder (`03`)\n\n"
            "**No `### Valuation-relevant fees` in this file** — fee roll-up is `05_valuation_relevant_fees.md` "
            "(run `map_valuation_fees.py` after extraction). **`map_valuation_fees.py` uses `### Waterfall table` "
            "when the grid has fee rows; otherwise `### Disbursement ladder` is primary** — do not leave both empty. "
            "**One numeric amount per cell** (never `54.42; 2,343.73` in one **Amount** / **Amount paid** field). "
            "**Grid layout:** fill **`### Waterfall table`** (Priority + payee + **Amount paid**). "
            "**Clause-only / no column headers** (Citibank Section 11.1, Computershare ladders): fill "
            "**`### Disbursement ladder`** with one payee and one amount per row; **omit** an empty "
            "**`### Waterfall table`** or set **Layout** = **Logical only** and **N/A** the grid in **Notes** — "
            "do not add a header-only waterfall table with no rows. "
            "When **both** grid and ladder exist, put each fee **once** — prefer **`### Waterfall table`** for "
            "fee **$**; in **`### Disbursement ladder`** use **Notes** `see waterfall table` for the same clause "
            "or omit duplicate fee rows (class cash may stay in the ladder). **`map_valuation_fees.py` dedupes** "
            "matching priority + amount across tables but do not rely on that — avoid repeating the same paid fee. "
            "**One payee per row** in **Waterfall table** and **Disbursement ladder** — e.g. **(A)(2)(i)** "
            "**Trustee** `54.42` and **Collateral Administrator** `2,343.73` as **separate** rows (same priority "
            "on each), **not** one row `Administrative Expenses: Trustee; Collateral Administrator` with a combined "
            "amount. Mirror the same split in **`### Continuations / sub-lines`** when you use that subsection. "
            "**Class interest/principal** already in **`02`:** keep them in the ladder for audit if needed, but in "
            "**`### Waterfall table`** use **Amount paid** `0.00` and **Notes** (Class cashflow — see 02) so fees are "
            "not rolled into `05`. "
            "Fill `### Waterfall table` / `### Disbursement ladder` / "
            "`### Logical / clause waterfall` with disbursed **Amount paid** on fee lines (waterfall-only). "
            "**`### Column mapping` (required for multi-column waterfalls):** quote **as-printed** headers for **this** "
            "trustee/deal and map each to **Amount payable**, **Amount paid**, **Amount available / running**, "
            "**Unpaid** / other — **column order is not fixed across trustees** (Due/Paid may be swapped, "
            "Payment may precede Amount Due, Citibank uses Distribution/Per Cap/Balance, some grids use two bare "
            "$$ with no headers). Match **heading → field** on every row; align with **sibling** clause lines when "
            "headers wrap. **Anti-pattern:** assuming **1st/2nd/3rd `$`** positions without reading labels. "
            "**Semantics:** due/payable ≠ paid; **Available** / **Running** / **Balance** (remaining pool) ≠ **Amount paid** — "
            "use the **Paid**/**Payment** header only for **Amount paid**, not the **Available** column even when it is the "
            "largest **$** on the row. When **Paid**/**Payment** is **0.00**, **Amount paid** = **0.00**. "
            "Example (headers `Due Paid Running Unpaid`): `$971.04 $0.00 … $971.04` → payable **971.04**, paid **0.00** — "
            "**not** paid **971.04** unless the **Paid** column shows **971.04**. "
            "Example (Payable | Paid | Running): map **middle** **Paid** to **Amount paid**, **Running** to **Amount available / running** — "
            "**not** by assuming 1st/2nd/3rd **$** position without reading labels. "
            "**Due | Paid | Running | Unpaid:** e.g. `$0.00 $42,006.90 $0.00` on clause **(i)** taxes = **Due** 0, **Running** 42,006.90, **Paid** 0 — "
            "**not** tax paid 42,006.90. Include **Senior** / **Subordinated Asset Management Fee** waterfall rows when the PDF prints non-zero **Paid**. "
            "**`### Administrative Expenses grid`:** include **only** when the PDF prints a separate admin / expense **table**; "
            "if there is no such grid, **omit** that subsection entirely (no empty table, no N/A placeholder). "
            "**Deutsche / NVR:** on **Administrative Cap and Expenses** pages, grid rows come from **Administrative Expenses** "
            "(trustee, bank, administrator, rating, counsel, reserve, …) — **not** from **Administrative Expenses Cap** "
            "(cap formula, aggregate principal, day count, computed cap total). "
            "Admin grid **Due** ≠ **Paid on the Distribution Date** — map grid payment column in **Column mapping**; "
            "do **not** use grid **Due** for waterfall **Amount paid** or `05`. "
            "**Mandatory page span:** When the chunk bundle lists a **contiguous** waterfall page range for `03`, read and quote "
            "**every** page in that range in **Source Text** — middle pages often hold fee rows even when `_page_index` previews "
            "look generic. **Interest vs Principal waterfall:** transcribe **both** ladders through the last mandatory page; "
            "**do not** zero **Principal** clause **(A)** when Source Text shows non-zero **Payment** / **Paid**. "
            "**Repeated** same clause + **different** paid ⇒ **separate** waterfall rows. "
            "**Subordinated management fees:** take **Amount paid** from the **interest** Priority line when the PDF prints "
            "**Subordinated Asset/Management Fee** with non-zero **Paid** — not from principal cross-reference text alone. "
            "**Subordinated Notes payments ≠ management fees:** **to the holders of the Subordinated Notes**, "
            "**payment on the Subordinated Notes**, **interest on the Subordinated Notes**, and similar noteholder "
            "distribution lines are **class cash** — put in **`### Other waterfall lines`** (or waterfall **Notes**: "
            "not a fee); **never** **`subordinate_management_fees`** unless the line explicitly says "
            "**Subordinated Management Fee** / **subordinate … management** / **collateral management** (junior tier). "
            "The word **subordinated** alone does **not** mean management.\n"
        )
    if target == "04":
        parts.append(
            "\n\n## Target-specific reminder (`04`)\n\n"
            "**Cross-check `02` vs `03` (review only — never edit `02` from waterfall in this file):**\n"
            "1. Sum **03** **class / noteholder** **Amount paid** (e.g. **(V)** + **(R)** Subordinated Notes, "
            "class interest/principal steps) — **exclude** fees/admin/management/tax rows.\n"
            "2. Compare to **`02`** **Interest payment** + **Principal payment** (or **Interest payable** when "
            "**Interest payment** is 0.00/blank).\n"
            "3. **When `02` Interest payment is 0.00/blank** and payable/waterfall totals align → **Y** with math "
            "and **Notes**: review **02** Distribution Summary / Total Payable rule (do **not** say "
            "'not comparable' without trying the sum).\n"
            "4. **When `02` Interest payment is already non-zero** → compare-only; **Y** if sums match, **N** with "
            "variance if not — **do not** recommend overwriting **`02`** from **`03`**.\n"
            "5. Never auto-merge waterfall into **`02`** in **`04`** — flag for human / **`02`** re-draft only.\n"
        )
    parts.append(
        "\n\n---\nWrite the FULL markdown file now, starting with the `#` title line from the template."
    )
    return "".join(parts)


def _chat_completions_post(
    payload: dict[str, Any],
    *,
    api_key: str,
    base: str,
    timeout: int,
) -> dict[str, Any]:
    url = f"{base.rstrip('/')}/chat/completions"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:8000]
        raise RuntimeError(f"LLM API HTTP {e.code}: {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM API connection error: {e!s}") from e


def _usage_log_line(
    body: dict[str, Any],
    *,
    model: str,
    base: str,
    draft_output_dir: Path | None,
    draft_target: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pt, ct, tt = _extract_usage_counts(body)
    cost_usd, pricing_note = _estimate_cost_usd(model, pt, ct)
    host = ""
    try:
        host = urlparse(base if "://" in base else f"https://{base}").netloc or base
    except Exception:
        host = base
    log_line: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "api_host": host,
        "prompt_tokens": pt,
        "completion_tokens": ct,
        "total_tokens": tt,
        "cost_usd": cost_usd,
        "pricing_note": pricing_note,
    }
    if draft_output_dir is not None:
        log_line["deal_folder"] = draft_output_dir.name
        if draft_target:
            log_line["draft_target"] = draft_target
    if extra:
        log_line.update(extra)
    _append_usage_log_line(log_line)
    return log_line


def openai_chat_completion(
    system: str,
    user: str,
    *,
    timeout: int = 300,
    draft_output_dir: Path | None = None,
    draft_target: str = "",
    draft_chunk_bundle: str = "",
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    api_key, base, model = draft_env()
    if not api_key:
        raise RuntimeError(
            "Missing API key: set NOTEVAL_DRAFT_API_KEY or OPENAI_API_KEY in the environment "
            "before starting the server."
        )
    _ = draft_chunk_bundle
    vision_meta: dict[str, Any] = {
        "vision_requested": False,
        "vision_pages": [],
        "vision_note": None,
        "vision_attached": False,
    }

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
    body = _chat_completions_post(payload, api_key=api_key, base=base, timeout=timeout)
    try:
        text = body["choices"][0]["message"]["content"]
        content = str(text).strip() if text is not None else ""
    except (KeyError, IndexError, TypeError) as e:
        snippet = str(body)[:800]
        raise RuntimeError(f"Unexpected LLM API response shape: {snippet}") from e

    log_line = _usage_log_line(
        body,
        model=model,
        base=base,
        draft_output_dir=draft_output_dir,
        draft_target=draft_target,
        extra={"mode": "completion"},
    )
    return content, vision_meta, log_line


def openai_chat_completion_with_tools(
    *,
    out_dir: Path,
    target: str,
    filename: str,
    template_excerpt: str,
    repository_context: str,
    prior_deliverables: str,
    extra_instructions: str,
    read_prior_fn: Any,
    timeout: int = 300,
    max_turns: int | None = None,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """
    Multi-turn Chat Completions with function tools (``noteval_llm_tools``).
    Returns final markdown, meta dict, aggregated usage log line.
    """
    import noteval_llm_tools as tools

    api_key, base, model = draft_env()
    if not api_key:
        raise RuntimeError(
            "Missing API key: set NOTEVAL_DRAFT_API_KEY or OPENAI_API_KEY in the environment "
            "before starting the server."
        )
    out_dir = out_dir.resolve()
    tid = target if target in ("01", "02", "03", "04") else "01"
    max_turns = max_turns if max_turns is not None else tools.draft_max_tool_turns()
    tool_list = tools.tool_definitions_for_target(tid)  # type: ignore[arg-type]

    user = tools.build_tools_user_message(
        target=tid,  # type: ignore[arg-type]
        filename=filename,
        repository_context=repository_context,
        extra_instructions=extra_instructions,
        out_dir=out_dir,
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": tools.SYSTEM_PROMPT_TOOLS},
        {"role": "user", "content": user},
    ]

    total_pt = total_ct = 0
    tool_calls_made: list[str] = []
    turns = 0
    final_content = ""

    while turns < max_turns:
        turns += 1
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tool_list,
            "tool_choice": "auto",
            "temperature": 0.2,
        }
        body = _chat_completions_post(payload, api_key=api_key, base=base, timeout=timeout)
        pt, ct, _ = _extract_usage_counts(body)
        if pt:
            total_pt += pt
        if ct:
            total_ct += ct

        try:
            msg = body["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected tool API response: {str(body)[:800]}") from e

        tool_calls = msg.get("tool_calls") or []
        content = msg.get("content")
        if content and str(content).strip() and not tool_calls:
            final_content = str(content).strip()
            break

        if not tool_calls:
            if content and str(content).strip():
                final_content = str(content).strip()
            break

        messages.append(msg)
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            args = str(fn.get("arguments") or "{}")
            tool_calls_made.append(name)
            result = tools.execute_tool(
                name,
                args,
                out_dir=out_dir,
                target=tid,  # type: ignore[arg-type]
                template_excerpt=template_excerpt,
                prior_deliverables=prior_deliverables,
                read_prior_fn=read_prior_fn,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id") or "",
                    "content": result,
                }
            )

    if not final_content:
        raise RuntimeError(
            f"Tool-calling draft for {target} ended without markdown after {turns} turn(s). "
            f"Tools used: {tool_calls_made[-12:]}. "
            "Try NOTEVAL_DRAFT_USE_TOOLS=0 or a model that supports function calling."
        )

    meta = {
        "mode": "tools",
        "tool_turns": turns,
        "tools_called": tool_calls_made,
        "vision_attached": False,
        "vision_requested": False,
        "vision_pages": [],
        "vision_note": "Tool mode does not attach page PNGs; use read_chunk_pages.",
    }
    agg_body = {
        "usage": {
            "prompt_tokens": total_pt,
            "completion_tokens": total_ct,
            "total_tokens": (total_pt + total_ct) if (total_pt or total_ct) else None,
        }
    }
    log_line = _usage_log_line(
        agg_body,
        model=model,
        base=base,
        draft_output_dir=out_dir,
        draft_target=target,
        extra={
            "mode": "tools",
            "tool_turns": turns,
            "tools_called_count": len(tool_calls_made),
            "vision_attached": False,
        },
    )
    return final_content, meta, log_line


def openai_chat_completion_text_only(
    system: str,
    user: str,
    *,
    timeout: int = 300,
) -> str:
    """Backward-compatible wrapper without page images."""
    text, _meta, _usage = openai_chat_completion(system, user, timeout=timeout)
    return text
