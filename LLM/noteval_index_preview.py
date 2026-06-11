"""
LLM-enriched ``_page_index.md`` previews for index-driven chunk selection.

After segmentation (rule-based previews from ``pdf_workflow.py``), this module
calls an OpenAI-compatible chat API to rewrite each page's preview line so
``noteval_chunk_select`` can route ``01`` / ``02`` / ``03`` more reliably.

Environment (same API key as ``noteval_llm.py``):

- ``NOTEVAL_INDEX_PREVIEW_ENRICH`` — default ``1``; set ``0`` / ``off`` to disable
- ``NOTEVAL_INDEX_PREVIEW_MODEL`` — optional model override (else ``NOTEVAL_DRAFT_MODEL``)
- ``NOTEVAL_INDEX_PREVIEW_BATCH_PAGES`` — pages per API call (default ``10``, max ``20``)
- ``NOTEVAL_INDEX_PREVIEW_EXCERPT_CHARS`` — page text sent per page (default ``1400``)
- ``NOTEVAL_INDEX_PREVIEW_FORCE`` — set ``1`` to re-enrich even if already marked

CLI::

    py -3 noteval_index_preview.py <output-dir>
    py -3 noteval_index_preview.py <output-dir> --waterfall-only
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import noteval_chunk_select as _chunk_select
import noteval_llm as _draft

_PAGE_MARKER = re.compile(r"^--- Page (\d+) of \d+ ---\s*$", re.MULTILINE)
_LLM_ENRICHED_MARKER = "LLM-enriched previews"
_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.I)

SYSTEM_PROMPT = """You enrich trustee / CLO note valuation PDF page-index rows.
Downstream code matches previews with keyword rules — use these exact phrases when the page contains that content:

For 01 (metadata): payment date, determination date, note valuation report, table of contents
For 02 (class / balances): Distribution in US$, Note Valuation Report, Principal Distribution Detail,
Interest Distribution Detail, Interest Detail, Factor per 1000, Payment Date Report, Notes Information,
class balance, coupon, CUSIP, ISIN
For 03 (waterfall / fees): Section 11.1, Distribution of Interest Proceeds, Distribution of Principal Proceeds,
Administrative Cap and Expenses, administrative expenses, waterfall, interest proceeds, principal proceeds,
disbursement, payment account

Output rules:
- One preview per page, max 200 characters, no pipe | character
- Format: **Section tag** / brief hint [also: secondary1, secondary2] when multiple exhibits share a page
- Section tag first when identifiable; otherwise start with the most specific heading on the page
- Do not invent dollar amounts, dates, or class names not visible in the excerpt
- TOC / cover / blank → short label like "Table of contents" or "Cover / boilerplate"

Respond with ONLY valid JSON:
{"pages": [{"page": <int>, "preview": "<string>"}, ...]}
Include every page number from the user message."""


@dataclass(frozen=True)
class EnrichResult:
    index_path: Path
    pages_enriched: int
    batches: int
    skipped: bool
    note: str | None = None


def index_preview_enrich_enabled() -> bool:
    raw = os.environ.get("NOTEVAL_INDEX_PREVIEW_ENRICH", "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def _preview_model() -> str:
    return (
        os.environ.get("NOTEVAL_INDEX_PREVIEW_MODEL", "").strip()
        or _draft.draft_env()[2]
    )


def _batch_size() -> int:
    try:
        n = int((os.environ.get("NOTEVAL_INDEX_PREVIEW_BATCH_PAGES") or "10").strip())
    except ValueError:
        n = 10
    return max(1, min(n, 20))


def _excerpt_chars() -> int:
    try:
        n = int((os.environ.get("NOTEVAL_INDEX_PREVIEW_EXCERPT_CHARS") or "1400").strip())
    except ValueError:
        n = 1400
    return max(400, min(n, 4000))


def _force_reenrich() -> bool:
    raw = os.environ.get("NOTEVAL_INDEX_PREVIEW_FORCE", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _sanitize_preview(text: str, *, max_len: int = 200) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    s = s.replace("|", "¦")
    if len(s) > max_len:
        s = s[: max_len - 1].rstrip() + "…"
    return s or "(no text)"


def _load_page_texts_from_chunks(chunks_dir: Path) -> dict[int, str]:
    """Merge ``--- Page N ---`` sections from all ``pages_*.txt`` in order."""
    if not chunks_dir.is_dir():
        return {}
    by_page: dict[int, str] = {}
    for path in sorted(chunks_dir.glob("pages_*.txt")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        matches = list(_PAGE_MARKER.finditer(text))
        if not matches:
            continue
        for i, m in enumerate(matches):
            try:
                pg = int(m.group(1))
            except ValueError:
                continue
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            body = text[start:end].strip()
            if body:
                by_page[pg] = body
    return by_page


def _index_already_enriched(path: Path) -> bool:
    if not path.is_file():
        return False
    head = path.read_text(encoding="utf-8", errors="replace")[:800]
    return _LLM_ENRICHED_MARKER in head


def _backup_rule_index(index_path: Path) -> None:
    backup = index_path.with_name("_page_index_rules.md")
    if backup.is_file() or not index_path.is_file():
        return
    backup.write_text(
        index_path.read_text(encoding="utf-8", errors="replace"),
        encoding="utf-8",
        newline="\n",
    )


def _parse_llm_pages_payload(raw: str) -> dict[int, str]:
    text = raw.strip()
    fence = _JSON_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("LLM response is not JSON") from None
        obj = json.loads(text[start : end + 1])
    pages = obj.get("pages") if isinstance(obj, dict) else None
    if not isinstance(pages, list):
        raise ValueError("JSON missing 'pages' array")
    out: dict[int, str] = {}
    for item in pages:
        if not isinstance(item, dict):
            continue
        try:
            pg = int(item.get("page"))
        except (TypeError, ValueError):
            continue
        prev = item.get("preview")
        if isinstance(prev, str) and prev.strip():
            out[pg] = _sanitize_preview(prev)
    return out


def _build_batch_user_message(
    batch: list[tuple[int, str, str]],
    *,
    tree_label: str,
) -> str:
    lines = [
        f"Enrich page-index previews for **{tree_label}**.",
        "Each item: page number, current rule-based preview, excerpt of page text.",
        "",
    ]
    cap = _excerpt_chars()
    for pg, rule_prev, body in batch:
        excerpt = body if len(body) <= cap else body[: cap - 1] + "…"
        lines.append(f"### Page {pg}")
        lines.append(f"- **Rule preview:** {rule_prev}")
        lines.append(f"- **Excerpt:**\n{excerpt}")
        lines.append("")
    return "\n".join(lines)


def _write_page_index(
    path: Path,
    *,
    previews: dict[int, str],
    total_pages: int | None,
    enriched: bool,
) -> None:
    total = total_pages or (max(previews) if previews else 0)
    lines = [
        "# Page Index",
        "",
    ]
    if enriched:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"- **{_LLM_ENRICHED_MARKER}** ({ts}; model `{_preview_model()}`)")
        lines.append("")
    if total:
        lines.append(f"Total pages: {total}")
        lines.append("")
    lines.extend(
        [
            "Use this index to identify which pages contain the sections you need.",
            "Previews lead with section tags when found (e.g. **Distribution in US$**), then context.",
            "Then read the corresponding chunk file from `_chunks/` for full text.",
            "",
            "| Page | First Lines |",
            "|------|-------------|",
        ]
    )
    for p in range(1, total + 1):
        prev = previews.get(p, "(no text)")
        lines.append(f"| {p} | {prev} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def enrich_page_index_file(
    out_dir: Path,
    *,
    index_name: str = "_page_index.md",
    chunks_subdir: str = "_chunks",
    tree_label: str = "note valuation PDF",
    force: bool = False,
) -> EnrichResult:
    """
    LLM-rewrite previews in ``index_name`` using text from ``chunks_subdir``.
    Backs up the first rule-based index to ``_page_index_rules.md`` (primary only).
    """
    out_dir = out_dir.resolve()
    index_path = out_dir / index_name
    chunks_dir = out_dir / chunks_subdir

    if not index_path.is_file():
        return EnrichResult(
            index_path=index_path,
            pages_enriched=0,
            batches=0,
            skipped=True,
            note=f"Missing {index_name}",
        )
    if not force and not _force_reenrich() and _index_already_enriched(index_path):
        return EnrichResult(
            index_path=index_path,
            pages_enriched=0,
            batches=0,
            skipped=True,
            note="Already LLM-enriched (set NOTEVAL_INDEX_PREVIEW_FORCE=1 to redo)",
        )

    previews_list, total = _chunk_select.parse_page_index(index_path)
    if not previews_list:
        return EnrichResult(
            index_path=index_path,
            pages_enriched=0,
            batches=0,
            skipped=True,
            note="No rows in page index",
        )

    if index_name == "_page_index.md":
        _backup_rule_index(index_path)

    page_texts = _load_page_texts_from_chunks(chunks_dir)
    rule_by_page = {p.page: p.preview for p in previews_list}

    items: list[tuple[int, str, str]] = []
    for pg in sorted(rule_by_page):
        items.append(
            (
                pg,
                rule_by_page[pg],
                page_texts.get(pg, ""),
            )
        )

    merged: dict[int, str] = dict(rule_by_page)
    batches = 0
    any_llm_ok = False
    bs = _batch_size()
    for i in range(0, len(items), bs):
        batch = items[i : i + bs]
        user_msg = _build_batch_user_message(batch, tree_label=tree_label)
        md, _usage, _vision = _draft.openai_chat_completion(
            SYSTEM_PROMPT,
            user_msg,
            timeout=180,
        )
        batches += 1
        try:
            llm_pages = _parse_llm_pages_payload(md)
        except ValueError:
            continue
        any_llm_ok = True
        for pg, prev in llm_pages.items():
            if pg in rule_by_page:
                merged[pg] = prev

    if not any_llm_ok:
        return EnrichResult(
            index_path=index_path,
            pages_enriched=0,
            batches=batches,
            skipped=True,
            note="LLM returned no parseable JSON batches",
        )

    _write_page_index(
        index_path,
        previews=merged,
        total_pages=total,
        enriched=True,
    )
    changed = sum(1 for pg in rule_by_page if merged.get(pg) != rule_by_page.get(pg))
    return EnrichResult(
        index_path=index_path,
        pages_enriched=len(merged),
        batches=batches,
        skipped=False,
        note=f"Updated {changed}/{len(rule_by_page)} preview row(s) in {batches} batch(es)",
    )


def enrich_output_dir(
    out_dir: Path,
    *,
    include_waterfall: bool = True,
    force: bool = False,
) -> list[EnrichResult]:
    """Enrich primary index; optionally ``_page_index_waterfall.md`` when present."""
    if not index_preview_enrich_enabled():
        return [
            EnrichResult(
                index_path=out_dir / "_page_index.md",
                pages_enriched=0,
                batches=0,
                skipped=True,
                note="NOTEVAL_INDEX_PREVIEW_ENRICH is off",
            )
        ]
    api_key, _, _ = _draft.draft_env()
    if not api_key:
        return [
            EnrichResult(
                index_path=out_dir / "_page_index.md",
                pages_enriched=0,
                batches=0,
                skipped=True,
                note="LLM API key not configured",
            )
        ]

    results: list[EnrichResult] = []
    results.append(
        enrich_page_index_file(
            out_dir,
            index_name="_page_index.md",
            chunks_subdir="_chunks",
            tree_label="note valuation PDF",
            force=force,
        )
    )
    wf_index = out_dir / "_page_index_waterfall.md"
    if include_waterfall and wf_index.is_file():
        results.append(
            enrich_page_index_file(
                out_dir,
                index_name="_page_index_waterfall.md",
                chunks_subdir="_chunks_waterfall",
                tree_label="waterfall calculations PDF",
                force=force,
            )
        )
    return results


def enrich_public_config() -> dict[str, object]:
    key, base, draft_model = _draft.draft_env()
    return {
        "enabled": index_preview_enrich_enabled(),
        "configured": bool(key),
        "model": _preview_model() if key else None,
        "batch_pages": _batch_size(),
        "excerpt_chars": _excerpt_chars(),
        "base_url": None if base == _draft.DEFAULT_BASE else base,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("output_dir", type=Path, help="Segmented deal folder")
    ap.add_argument(
        "--waterfall-only",
        action="store_true",
        help="Only enrich _page_index_waterfall.md",
    )
    ap.add_argument(
        "--no-waterfall",
        action="store_true",
        help="Skip waterfall index even if present",
    )
    ap.add_argument("--force", action="store_true", help="Re-run even if already enriched")
    args = ap.parse_args()
    out = args.output_dir.resolve()
    if args.waterfall_only:
        r = enrich_page_index_file(
            out,
            index_name="_page_index_waterfall.md",
            chunks_subdir="_chunks_waterfall",
            tree_label="waterfall calculations PDF",
            force=args.force,
        )
        results = [r]
    else:
        results = enrich_output_dir(
            out,
            include_waterfall=not args.no_waterfall,
            force=args.force,
        )
    for r in results:
        status = "SKIP" if r.skipped else "OK"
        print(f"[{status}] {r.index_path.name}: {r.note or r.pages_enriched}")
    if any(not x.skipped and x.batches == 0 and x.pages_enriched == 0 for x in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
