"""
``noteval_llm.py`` — OpenAI-compatible chat completions for the noteval UI extraction agent.

Uses stdlib only (urllib). Configure with environment variables:

- NOTEVAL_DRAFT_API_KEY — preferred
- OPENAI_API_KEY — fallback
- NOTEVAL_DRAFT_BASE_URL — optional (default https://api.openai.com/v1)
- NOTEVAL_DRAFT_MODEL — optional (default gpt-4o-mini)
- NOTEVAL_DRAFT_USAGE_LOG — optional path to append JSONL usage lines (default:
  ``<repo_root>/logs/noteval_draft_api_usage.log``). Set to ``0`` or ``off`` to disable.
- NOTEVAL_DRAFT_PRICE_INPUT_PER_1M — optional USD per 1M **input** tokens (overrides built-in table)
- NOTEVAL_DRAFT_PRICE_OUTPUT_PER_1M — optional USD per 1M **output** tokens (overrides built-in table)

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
from urllib.parse import urlparse

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_BASE = "https://api.openai.com/v1"

_LOG_LOCK = threading.Lock()

# Approximate list-style USD per 1M tokens (input, output). Override with env for billing accuracy.
_MODEL_PRICE_USD_PER_1M: list[tuple[str, float, float]] = [
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
    return {
        "configured": bool(key),
        "model": model,
        "base_url": None if base == DEFAULT_BASE else base,
        "usage_log_path": str(log_p) if log_p else None,
        "usage_log_enabled": bool(log_p),
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


SYSTEM_PROMPT = """You are a structured extraction assistant for U.S. CLO / RMBS trustee and note valuation PDFs.
You output ONE markdown file: the user's target deliverable (01–04).
Follow the template excerpt: use the same top-level `#` title, section names, and table column headers where the template shows them.
Use these sections in order when the template expects them: ## Extracted Data, ## Completeness Checklist, ## Source Text.
In ## Source Text, quote CHUNK EXCERPTS verbatim when possible. When a chunk line shows a page marker like "--- Page N of ... ---", keep or add a **Page N** label near the quoted lines.
Do not invent currency amounts, dates, or CUSIPs not supported by the chunks. Use N/A or empty cells and a short explanation in Notes when data is missing.
For fee / waterfall rows, prefer amounts the trustee labels as paid, settled, or payment over discretionary "remaining" columns when ambiguous; state the mapping once in Notes if needed.
Output ONLY the markdown document body — no preamble like "Here is the file" and no markdown code fences wrapping the entire document."""


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
            "(for 04 summary: synthesize; do not contradict; cite Source Text from chunks where needed)\n\n",
            prior_deliverables.strip()[:120_000],
        ]
    parts += [
        "\n\n## PDF chunk text (segmentation output)\n\n",
        chunk_bundle.strip(),
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
    parts.append(
        "\n\n---\nWrite the FULL markdown file now, starting with the `#` title line from the template."
    )
    return "".join(parts)


def openai_chat_completion(
    system: str,
    user: str,
    *,
    timeout: int = 300,
) -> str:
    api_key, base, model = draft_env()
    if not api_key:
        raise RuntimeError(
            "Missing API key: set NOTEVAL_DRAFT_API_KEY or OPENAI_API_KEY in the environment "
            "before starting the server."
        )
    url = f"{base}/chat/completions"
    payload: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
    }
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
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:8000]
        raise RuntimeError(f"LLM API HTTP {e.code}: {err}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"LLM API connection error: {e!s}") from e
    try:
        text = body["choices"][0]["message"]["content"]
        content = str(text).strip()
    except (KeyError, IndexError, TypeError) as e:
        snippet = str(body)[:800]
        raise RuntimeError(f"Unexpected LLM API response shape: {snippet}") from e

    pt, ct, tt = _extract_usage_counts(body)
    cost_usd, pricing_note = _estimate_cost_usd(model, pt, ct)
    host = ""
    try:
        host = urlparse(base if "://" in base else f"https://{base}").netloc or base
    except Exception:
        host = base

    _append_usage_log_line(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "api_host": host,
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "total_tokens": tt,
            "cost_usd": cost_usd,
            "pricing_note": pricing_note,
        }
    )
    return content
