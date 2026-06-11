"""
Index-driven chunk selection for LLM extraction drafts.

Reads ``_page_index.md`` (and ``_page_index_waterfall.md`` when present) plus
``_manifest.md`` chunk page ranges, scores pages per deliverable (01–04), and
returns only the ``_chunks/*.txt`` / ``_chunks_waterfall/*.txt`` files that cover
those pages — similar to the SDK / noteval-extractor-agent workflow.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# --- Page index -----------------------------------------------------------------

_PAGE_INDEX_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*(.+?)\s*\|$")
_TOTAL_PAGES_RE = re.compile(r"Total pages:\s*(\d+)", re.I)

# --- Manifest -------------------------------------------------------------------

_MANIFEST_CHUNK_ROW = re.compile(
    r"^\|\s*`(_chunks(?:_waterfall)?/pages_\d+_\d+\.txt)`\s*\|\s*(\d+)-(\d+)\s*\|",
    re.I,
)
_CHUNK_FILENAME_PAGES = re.compile(r"pages_(\d+)_(\d+)\.txt$", re.I)
_PAGE_MARKER = re.compile(r"^--- Page (\d+) of \d+ ---\s*$", re.MULTILINE)


@dataclass(frozen=True)
class PagePreview:
    page: int
    preview: str


@dataclass(frozen=True)
class ChunkSpan:
    rel: str  # e.g. _chunks/pages_001_012.txt
    start: int
    end: int


@dataclass(frozen=True)
class ChunkSelectionResult:
    rel_paths: list[str]
    pages: list[int]
    note: str | None = None


def index_driven_enabled() -> bool:
    raw = os.environ.get("NOTEVAL_DRAFT_INDEX_CHUNKS", "1").strip().lower()
    return raw not in ("0", "false", "off", "no")


def parse_page_index(path: Path) -> tuple[list[PagePreview], int | None]:
    if not path.is_file():
        return [], None
    text = path.read_text(encoding="utf-8", errors="replace")
    total: int | None = None
    m = _TOTAL_PAGES_RE.search(text)
    if m:
        try:
            total = int(m.group(1))
        except ValueError:
            total = None
    rows: list[PagePreview] = []
    for line in text.splitlines():
        mrow = _PAGE_INDEX_ROW.match(line.strip())
        if not mrow:
            continue
        try:
            page = int(mrow.group(1))
        except ValueError:
            continue
        rows.append(PagePreview(page=page, preview=mrow.group(2).strip()))
    return rows, total


def parse_manifest_chunks(path: Path, *, prefix: str) -> list[ChunkSpan]:
    """Parse ``| `_chunks/...` | start-end |`` rows; ``prefix`` is ``_chunks`` or ``_chunks_waterfall``."""
    if not path.is_file():
        return []
    spans: list[ChunkSpan] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = _MANIFEST_CHUNK_ROW.match(line.strip())
        if not m:
            continue
        rel = m.group(1).replace("\\", "/")
        if not rel.startswith(prefix + "/"):
            continue
        try:
            spans.append(
                ChunkSpan(rel=rel, start=int(m.group(2)), end=int(m.group(3)))
            )
        except ValueError:
            continue
    return spans


def discover_chunks_from_dir(chunk_dir: Path, rel_prefix: str) -> list[ChunkSpan]:
    if not chunk_dir.is_dir():
        return []
    spans: list[ChunkSpan] = []
    for f in sorted(chunk_dir.glob("pages_*.txt")):
        m = _CHUNK_FILENAME_PAGES.search(f.name)
        if not m:
            continue
        spans.append(
            ChunkSpan(
                rel=f"{rel_prefix}/{f.name}",
                start=int(m.group(1)),
                end=int(m.group(2)),
            )
        )
    return spans


_DIST_US_PAGE_HINT = (
    "> **Distribution in US$ / Distribution Summary — balance mapping (this page):** "
    "**Prior / Opening principal** → **`Beginning balance`**; "
    "**Current / Closing principal** → **`Ending balance`** (same **Class** row). "
    "**Do not** use **Original balance** or **Factor per 1000** cells for beginning/ending. "
    "**SUB / subordinated:** when **Dividends** are **0.00**, **coupon** is **0%**, and **Ending < Beginning**, "
    "**`Principal payment`** = Beginning − Ending; **`Interest payment`** / **`Interest payable`** **0.00** "
    "(do not map **Accrued Interest** / **Current Payable** to interest when that **$** equals the balance drop).\n\n"
)

_DEUTSCHE_DIST_US_RATE_HINT = (
    "> **Deutsche Bank NVR — Interest rate (this page when present):** "
    "Map **`Interest rate`** from the **`Current Coupon`** column on **Distribution in US$** "
    "(or **Percent of Current** / **Coupon** when that is the printed period accrual label). "
    "**Do not** build **`Interest rate`** as **Index % + Spread %** from the **Coupon Rates** / "
    "**Factor Information per 1000** page when **Current Coupon** is on this row.\n\n"
)

_DEUTSCHE_FACTOR_PAGE_HINT = (
    "> **Deutsche Bank — Factor / Coupon Rates page:** "
    "**Skip** for balances and interest **$**. For **`Interest rate`**, use **Current Coupon** "
    "when that column is printed on this page or on **Distribution in US$**. "
    "**Do not** concatenate separate **Index** and **Spread** cells into **`Interest rate`** "
    "(those are components, not the period **Current Coupon**). "
    "**Prior Cumulative** amounts on **Interest Detail** are **not** **`Interest payment`**.\n\n"
)

_DEUTSCHE_INTEREST_DETAIL_HINT = (
    "> **Deutsche Bank — Interest Detail:** "
    "**Interest Paid** → **`Interest payment`** only. Leading **$** on **SUB** lines labeled "
    "**Prior Cumulative** / deferred are **not** period cash — keep **`Interest payment`** **0.00** "
    "when **Interest Paid** is **0.00**.\n\n"
)

_NVR_INTEREST_PAYABLE_TO_HINT = (
    "> **Indenture NVR — Interest payable to [Class] Notes (subsection (2)):** "
    "Per-class **Interest payable to Class … Notes** **$** is the **period interest cash** — map to "
    "**`Interest payment`** **and** **`Interest payable`** (same **$**). "
    "**Do not** leave **`Interest payment`** **N/A** when only payable is filled.\n\n"
)


def _page_body_looks_like_nvr_interest_payable_to(body: str) -> bool:
    low = (body or "").lower()
    return "interest payable to" in low and ("notes" in low or "subordinated" in low)


def _preview_looks_like_distribution_us(preview: str) -> bool:
    b = (preview or "").lower()
    if "distribution in us$" in b or "distribution in us" in b:
        return True
    compact = b.replace(" ", "")
    return any(k in compact for k in ("facevaluefacevaluebalance", "facevaluebalanceinterest"))


def _page_body_looks_like_distribution_us(body: str) -> bool:
    low = (body or "").lower()
    if "distribution in us$" in low or "distribution in us" in low:
        return True
    if "prior principal balance" in low and "current principal balance" in low:
        return True
    if "prior principal" in low and "current principal" in low:
        return True
    compact = re.sub(r"\s+", "", low)
    if "priorprincipalbalance" in compact and "currentprincipalbalance" in compact:
        return True
    return False


def _page_needs_distribution_us_hint(
    page_num: int,
    page_body: str,
    previews_by_page: dict[int, str],
) -> bool:
    if _page_body_looks_like_distribution_us(page_body):
        return True
    prev = previews_by_page.get(page_num, "")
    return _preview_looks_like_distribution_us(prev)


def _chunk_text_looks_deutsche_bank(text: str) -> bool:
    low = (text or "").lower()
    return "deutsche bank" in low and (
        "distribution in us$" in low
        or "interest detail" in low
        or "factor information per 1000" in low
        or "distribution of interest proceeds" in low
    )


def _page_body_looks_like_factor_coupon_page(body: str) -> bool:
    low = (body or "").lower()
    return "factor information per 1000" in low or (
        "coupon rates" in low and "class cusip" in low
    )


def _page_body_looks_like_interest_detail(body: str) -> bool:
    low = (body or "").lower()
    compact = re.sub(r"\s+", "", low)
    return "interestdetail" in compact and "interestpaid" in compact


def _hints_for_02_page(
    page_body: str,
    *,
    deutsche: bool,
    dist_us: bool,
) -> str:
    parts: list[str] = []
    if _page_body_looks_like_nvr_interest_payable_to(page_body):
        parts.append(_NVR_INTEREST_PAYABLE_TO_HINT)
    if dist_us:
        parts.append(_DIST_US_PAGE_HINT)
        if deutsche:
            parts.append(_DEUTSCHE_DIST_US_RATE_HINT)
    elif deutsche and _page_body_looks_like_factor_coupon_page(page_body):
        parts.append(_DEUTSCHE_FACTOR_PAGE_HINT)
    elif deutsche and _page_body_looks_like_interest_detail(page_body):
        parts.append(_DEUTSCHE_INTEREST_DETAIL_HINT)
    return "".join(parts)


def annotate_02_chunk_pages(
    text: str,
    *,
    previews: list[PagePreview] | None = None,
) -> str:
    """
    When drafting ``02``, insert a short hint after each page marker for
    **Distribution in US$** / prior-current principal grids.
    """
    previews_by_page: dict[int, str] = {}
    if previews:
        previews_by_page = {p.page: p.preview for p in previews}

    deutsche = _chunk_text_looks_deutsche_bank(text)

    matches = list(_PAGE_MARKER.finditer(text))
    if not matches:
        hint = _hints_for_02_page(
            text,
            deutsche=deutsche,
            dist_us=_page_body_looks_like_distribution_us(text),
        )
        return hint + text if hint else text

    out_parts: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]
        try:
            pg = int(m.group(1))
        except ValueError:
            out_parts.append(section)
            continue
        body = section[m.end() - start :]
        dist_us = _page_needs_distribution_us_hint(pg, body, previews_by_page)
        hint = _hints_for_02_page(body, deutsche=deutsche, dist_us=dist_us)
        if hint:
            marker_line = section[: m.end() - start].rstrip()
            rest = body.lstrip("\n")
            out_parts.append(marker_line + "\n\n" + hint + rest)
        else:
            out_parts.append(section)
    return "\n\n".join(out_parts)


def filter_chunk_text_to_pages(text: str, pages: set[int]) -> str:
    """Keep only ``--- Page N of T ---`` sections whose ``N`` is in ``pages``."""
    if not pages:
        return text
    matches = list(_PAGE_MARKER.finditer(text))
    if not matches:
        return text
    parts: list[str] = []
    for i, m in enumerate(matches):
        try:
            pg = int(m.group(1))
        except ValueError:
            continue
        if pg not in pages:
            continue
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        parts.append(text[start:end].rstrip())
    if not parts:
        return text
    header = "[Index filter: selected pages only]\n\n"
    return header + "\n\n".join(parts) + "\n"


def chunks_covering_pages(spans: list[ChunkSpan], pages: set[int]) -> list[str]:
    if not pages or not spans:
        return []
    out: list[str] = []
    for sp in spans:
        if any(sp.start <= p <= sp.end for p in pages):
            out.append(sp.rel)
    return out


# --- Per-target page scoring ----------------------------------------------------

def _preview_blob(p: PagePreview) -> str:
    return p.preview.lower()


def _any_kw(blob: str, keywords: tuple[str, ...]) -> bool:
    return any(k in blob for k in keywords)


def _score_page(target: str, p: PagePreview) -> float:
    b = _preview_blob(p)
    score = 0.0

    if target == "01":
        kws = (
            "payment date",
            "determination date",
            "collection period",
            "record date",
            "note valuation",
            "valuation report",
            "compiled in accordance",
            "schedule g",
            "trustee report",
            "distribution date",
            "closing date",
            "report covers",
        )
        if _any_kw(b, kws):
            score += 3.0
        if p.page <= 3:
            score += 2.0
        return score

    if target == "02":
        if "distribution in us$" in b or "distribution in us" in b:
            score += 6.0
        if "interest detail" in b:
            score += 3.0
        if "factor per 1000" in b or "factor information per 1000" in b:
            score -= 2.0
        compact = b.replace(" ", "")
        if "facevaluefacevaluebalance" in compact or "facevaluebalanceinterest" in compact:
            score += 4.0
        kws = (
            "distribution in us",
            "principal distribution",
            "interest distribution",
            "principal distribution detail",
            "interest distribution detail",
            "notes information",
            "payment date factor",
            "payment date report",
            "class balance",
            "class original principal",
            "beginning principal",
            "ending principal",
            "all in rate",
            "interest due",
            "interest paid",
            "cusip",
            "isin",
            "accrued interest",
            "accrued dividends",
            "subordinated note",
            "reinvesting holder",
            "reinvesting",
            "holder note",
            "income note",
            "income notes",
            "m note",
            "m notes",
            "preferred return",
            "principal balance",
            "coupon",
            "note interest",
            "distribution grid",
            "per unit",
            "orig prin",
            "trustee report to note",
            "trustee report",
            "compiled in accordance",
        )
        if _any_kw(b, kws):
            score += 3.0
        if p.page <= 5:
            score += 1.0
        if "administrative expenses" in b and "section 11.1" not in b:
            score += 0.5
        return score

    if target == "03":
        compact = re.sub(r"\s+", " ", b)
        if "administrative cap and expenses" in compact:
            score += 5.0
        elif "administrative expenses cap" in compact and "administrative expenses" in compact:
            if "distribution of interest proceeds" not in compact:
                score += 3.0
        kws = (
            "section 11.1",
            "disbursement",
            "interest proceeds",
            "principal proceeds",
            "waterfall",
            "due paid",
            "running balance",
            "schedule of payments",
            "priority of interest",
            "priority of principal",
            "application of interest",
            "application of principal",
            "administrative expenses",
            "payment account",
            "proceeds available",
            "wf distro",
            "settle date principal",
        )
        if _any_kw(b, kws):
            score += 3.0
        if "interest proceeds $" in b or "principal proceeds" in b:
            score += 4.0
        if _interest_03_anchor(b) or _principal_03_anchor(b):
            score += 3.0
        return score

    if target == "04":
        if p.page <= 2:
            return 2.0
        return 0.0

    return 0.0


def _expand_02_tranche_pages(previews: list[PagePreview], selected: set[int]) -> set[int]:
    hits = [p.page for p in previews if _score_page("02", p) >= 2.0]
    if not hits:
        return selected
    start = min(min(hits), 2)
    end = max(hits)
    if end >= 4:
        start = min(start, 2)
    return selected | set(range(start, end + 1))


def _interest_03_anchor(blob: str) -> bool:
    b = re.sub(r"\s+", " ", (blob or "").lower())
    return any(
        k in b
        for k in (
            "interest proceeds",
            "proceeds available",
            "wf distro",
            "priority of interest",
            "distribution of interest proceeds",
            "application of interest",
        )
    )


def _principal_03_anchor(blob: str) -> bool:
    b = re.sub(r"\s+", " ", (blob or "").lower())
    return any(
        k in b
        for k in (
            "principal proceeds",
            "settle date principal",
            "priority of principal",
            "distribution of principal proceeds",
            "application of principal",
        )
    )


def _weak_03_waterfall_anchor(blob: str) -> bool:
    b = re.sub(r"\s+", " ", (blob or "").lower())
    return (
        _interest_03_anchor(b)
        or _principal_03_anchor(b)
        or any(
            k in b
            for k in (
                "section 11.1",
                "schedule of payments",
                "running balance",
                "disbursement",
                "waterfall",
                "due paid",
                "payment account",
            )
        )
    )


def _expand_03_waterfall_pages(
    previews: list[PagePreview],
    selected: set[int],
    *,
    total_pages: int | None,
) -> set[int]:
    """
    Contiguous interest + principal waterfall span (not fee-keyword cherry-pick).

    Payment Date Reports often print generic index lines on middle pages (e.g. 5–7)
    while fees live in the interest ladder; principal may start pages later. When both
    interest- and principal-phase anchors exist, fill every page between them (and a
    short tail after the last principal anchor).
    """
    interest_anchors: list[int] = []
    principal_anchors: list[int] = []
    other_anchors: list[int] = []
    for p in previews:
        b = _preview_blob(p)
        if _interest_03_anchor(b):
            interest_anchors.append(p.page)
        if _principal_03_anchor(b):
            principal_anchors.append(p.page)
        if _score_page("03", p) >= 2.0 or _weak_03_waterfall_anchor(b):
            other_anchors.append(p.page)

    if interest_anchors and principal_anchors:
        start = min(min(interest_anchors), min(principal_anchors))
        end = max(max(interest_anchors), max(principal_anchors))
        if total_pages and end < total_pages:
            tail = total_pages - end
            if tail <= 4:
                end = total_pages
        return selected | set(range(start, end + 1))

    anchors = sorted(set(interest_anchors + principal_anchors + other_anchors))
    if not anchors:
        return selected
    start = min(anchors)
    end = max(anchors)
    if total_pages and len(anchors) == 1 and start <= 5:
        end = total_pages
    elif total_pages and principal_anchors and end < total_pages:
        tail = total_pages - end
        if tail <= 4:
            end = total_pages
    return selected | set(range(start, end + 1))


def resolve_03_mandatory_waterfall_pages(
    out: Path,
    *,
    chunk_tree: str = "both",
    use_index: bool | None = None,
) -> list[int]:
    """
    1-based pages that must be read for ``03`` (contiguous waterfall span).

    Uses the same index + expansion rules as ``resolve_chunk_relpaths`` for ``03``.
    Returns ``[]`` when index-driven selection is off or no waterfall pages resolve.
    """
    if use_index is None:
        use_index = index_driven_enabled()
    if not use_index:
        return []
    sel = resolve_chunk_relpaths(
        out,
        for_deliverable="03",
        chunk_tree=chunk_tree,
        use_index=use_index,
    )
    if sel is None or not sel.pages:
        return []
    return sorted(sel.pages)


def format_03_mandatory_waterfall_brief(
    pages: list[int],
    *,
    primary_previews: list[PagePreview] | None = None,
    wf_previews: list[PagePreview] | None = None,
    out_dir: Path | None = None,
) -> str:
    """LLM-facing block: full contiguous waterfall page span (mandatory for tool ``03``)."""
    if not pages and out_dir is None:
        return ""
    preview_by_page: dict[int, str] = {}
    if primary_previews:
        preview_by_page.update({p.page: p.preview for p in primary_previews})
    if wf_previews:
        for p in wf_previews:
            preview_by_page.setdefault(p.page, p.preview)

    wf_pages: list[int] = []
    primary_admin_pages: list[int] = []
    if out_dir is not None and (out_dir / "_page_index_waterfall.md").is_file() and wf_previews:
        wf_sel = resolve_chunk_relpaths(
            out_dir, for_deliverable="03", chunk_tree="waterfall", use_index=True
        )
        wf_pages = sorted(wf_sel.pages) if wf_sel and wf_sel.pages else []
        prim_sel = resolve_chunk_relpaths(
            out_dir, for_deliverable="03", chunk_tree="primary", use_index=True
        )
        primary_admin_pages = sorted(prim_sel.pages) if prim_sel and prim_sel.pages else []
    elif pages:
        wf_pages = pages

    if not wf_pages and not primary_admin_pages and not pages:
        return ""

    lines = [
        "## File 03 — mandatory waterfall page span (read all pages below)",
        "",
    ]
    if wf_previews and wf_pages:
        lines += [
            "**Dual PDF (Wells Fargo / split waterfall):** Section **11.1** ladders are in "
            "**`_chunks_waterfall/`** — **not** in the note-valuation **`_chunks/`** PDF. "
            "**Never** mark Section 11.1 **N/A** when **`_page_index_waterfall.md`** exists.",
            "",
            "**Required tool calls:**",
            f"1. **`read_chunk_pages`** with `tree` = **`waterfall`**, `pages` = `{wf_pages}` — "
            "full interest + principal ladders (fee **Amount paid** for **`map_valuation_fees.py`**).",
        ]
        if primary_admin_pages:
            lines.append(
                f"2. **`read_chunk_pages`** with `tree` = **`primary`**, `pages` = `{primary_admin_pages}` — "
                "**Administrative Expenses grid** (audit / voucher only; **do not** use grid **$** for fee roll-up)."
            )
        lines += [
            "",
            "Using `tree` = **`primary`** for waterfall page numbers **1–7** reads the **wrong PDF** "
            "(PDD/IDD/Current Balance — **not** Section 11.1).",
            "",
            "### Waterfall PDF pages (`tree=waterfall`)",
            "",
            "| Page | `_page_index_waterfall` preview |",
            "|------|----------------------------------|",
        ]
        for pg in wf_pages:
            prev = (preview_by_page.get(pg) or "—").replace("|", "/")
            if len(prev) > 160:
                prev = prev[:159].rstrip() + "…"
            lines.append(f"| {pg} | {prev} |")
        if primary_admin_pages:
            lines += [
                "",
                "### Note-valuation PDF — admin grid only (`tree=primary`)",
                "",
                "| Page | `_page_index` preview |",
                "|------|------------------------|",
            ]
            for pg in primary_admin_pages:
                prev = (preview_by_page.get(pg) or "—").replace("|", "/")
                if len(prev) > 160:
                    prev = prev[:159].rstrip() + "…"
                lines.append(f"| {pg} | {prev} |")
        lines.append("")
        return "\n".join(lines)

    lines += [
        "The server resolved a **contiguous** interest + principal waterfall block from "
        "`_page_index.md` (not fee-keyword cherry-pick). Middle pages often have **generic** "
        "index previews but still contain clause steps and fees — **do not skip** pages in this list.",
        "",
        "**Required:** After `read_page_index`, call **`read_chunk_pages`** once with "
        f"`pages` = `{pages}` and the correct `tree` (`primary` or `waterfall` per index). "
        "Transcribe the **full** interest ladder **and** principal ladder. Quote **every** page "
        "in **`## Source Text`**.",
        "",
        "| Page | `_page_index` preview |",
        "|------|------------------------|",
    ]
    display_pages = wf_pages or pages
    for pg in display_pages:
        prev = (preview_by_page.get(pg) or "—").replace("|", "/")
        if len(prev) > 160:
            prev = prev[:159].rstrip() + "…"
        lines.append(f"| {pg} | {prev} |")
    lines.append("")
    return "\n".join(lines)


def select_pages_for_target(
    target: str,
    previews: list[PagePreview],
    *,
    min_score: float = 2.0,
    always_pages: tuple[int, ...] = (),
    total_pages: int | None = None,
) -> set[int]:
    selected: set[int] = set(always_pages)
    for p in previews:
        if _score_page(target, p) >= min_score:
            selected.add(p.page)
    if target == "02":
        try:
            import noteval_layout_detect as _layout

            layout = _layout.detect_02_layout_from_index(previews)
            layout_pages = _layout.select_02_pages_by_layout(
                previews, layout, always_pages=always_pages
            )
            if layout_pages is not None:
                selected = layout_pages
            else:
                selected = _expand_02_tranche_pages(previews, selected)
        except ImportError:
            selected = _expand_02_tranche_pages(previews, selected)
    if target == "03":
        selected = _expand_03_waterfall_pages(previews, selected, total_pages=total_pages)
    if target in ("01", "02") and not selected:
        for p in previews:
            if p.page <= min(5, len(previews)):
                selected.add(p.page)
    return selected


_ADMIN_GRID_PAGE_HINT = (
    "> **Administrative Expenses grid (this page):** Populate **`### Administrative Expenses grid`** "
    "from the **Administrative Expenses** block only — itemized lines **(i) Trustee**, "
    "**(ii) Bank**, **(iii) Administrator**, **(iv) Rating Agencies**, **(v)** counsel, "
    "**(viii)** reserve, **(ix)** other fees, and **Total** when printed. "
    "**Do not** add rows from **Administrative Expenses Cap** (cap formula, **Aggregate Principal**, "
    "**per annum**, **Day Count**, **( A + B ) * ( C / 360 )**, computed cap **$**). "
    "Cap may be noted in **Notes** for waterfall tie-out — not in the grid table.\n\n"
)


def _page_body_has_admin_voucher_grid(body: str) -> bool:
    low = (body or "").lower()
    if "distribution of interest proceeds" in low or "available optimal paid" in low:
        return False
    if "administrative cap and expenses" in low:
        return True
    if "administrative expenses cap" in low and re.search(
        r"\(i\)\s+trustee",
        low,
        re.I,
    ):
        return True
    if re.search(r"\badministrative\s+expenses\b", low) and re.search(
        r"\(i\)\s+trustee",
        low,
        re.I,
    ):
        return True
    return False


def annotate_03_chunk_pages(text: str) -> str:
    """Insert admin-grid scope hints after page markers on Cap and Expenses pages."""
    matches = list(_PAGE_MARKER.finditer(text))
    if not matches:
        if _page_body_has_admin_voucher_grid(text):
            return _ADMIN_GRID_PAGE_HINT + text
        return text

    out_parts: list[str] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section = text[start:end]
        body = section[m.end() - start :]
        if _page_body_has_admin_voucher_grid(body):
            marker_line = section[: m.end() - start].rstrip()
            rest = body.lstrip("\n")
            out_parts.append(marker_line + "\n\n" + _ADMIN_GRID_PAGE_HINT + rest)
        else:
            out_parts.append(section)
    return "\n\n".join(out_parts)


def _merge_admin_pages_for_03(
    primary_previews: list[PagePreview], selected: set[int]
) -> set[int]:
    """Attach note-val admin voucher grid pages (not waterfall-only admin clauses)."""
    extra = set(selected)
    for p in primary_previews:
        b = _preview_blob(p)
        compact = re.sub(r"\s+", " ", b)
        if "administrative cap and expenses" in compact:
            extra.add(p.page)
            continue
        if "administrative expenses cap" in compact and "administrative expenses" in compact:
            if "section 11.1" not in compact and "distribution of interest proceeds" not in compact:
                extra.add(p.page)
            continue
        if "administrative expenses" in b and "section 11.1" not in b:
            if "distribution of interest proceeds" not in b and "available optimal paid" not in b:
                extra.add(p.page)
        if "schedule g" in b and p.page <= 4:
            extra.add(p.page)
    return extra


def index_driven_pages(
    out: Path,
    target: str,
    *,
    chunk_tree: str = "primary",
    use_index: bool | None = None,
) -> list[int] | None:
    """
    1-based page numbers selected for a deliverable via ``_page_index.md`` scoring.

    Returns ``None`` when index-driven selection is off or could not resolve pages.
    Used by layout detection and chunk-bundle gathering for ``02``.
    """
    if use_index is None:
        use_index = index_driven_enabled()
    if not use_index:
        return None
    sel = resolve_chunk_relpaths(
        out,
        for_deliverable=target,
        chunk_tree=chunk_tree,
        use_index=use_index,
    )
    if sel is None or not sel.pages:
        return None
    return sorted(set(sel.pages))


def resolve_chunk_relpaths(
    out: Path,
    *,
    for_deliverable: str | None,
    chunk_tree: str = "primary",
    explicit_paths: list[str] | None = None,
    use_index: bool | None = None,
) -> ChunkSelectionResult | None:
    """
    Return chunk relative paths for a deliverable, or ``None`` to use legacy
    “load all chunks” behavior (caller should fall back).
    """
    if explicit_paths:
        return None
    if use_index is None:
        use_index = index_driven_enabled()
    if not use_index or not for_deliverable:
        return None

    target = for_deliverable
    if target == "04":
        return ChunkSelectionResult(
            rel_paths=[],
            pages=[],
            note="Index-driven: target 04 uses prior 01-03 deliverables on disk (no chunk bundle).",
        )
    primary_index = out / "_page_index.md"
    wf_index = out / "_page_index_waterfall.md"
    primary_previews, primary_total = parse_page_index(primary_index)
    wf_previews, wf_total = parse_page_index(wf_index)
    total_pages = primary_total or wf_total

    if not primary_previews and not wf_previews:
        return None

    always = (1,) if target in ("01", "02", "04") else ()
    pages: set[int] = set()

    if target == "03" and chunk_tree in ("waterfall", "both") and wf_previews:
        pages |= select_pages_for_target(
            "03", wf_previews, always_pages=always, total_pages=wf_total
        )
    if target == "03" and chunk_tree in ("primary", "both"):
        primary_pages = select_pages_for_target(
            "03", primary_previews, always_pages=always, total_pages=primary_total
        )
        pages |= _merge_admin_pages_for_03(primary_previews, primary_pages)
    elif target != "03" or chunk_tree == "primary" or not wf_previews:
        src = primary_previews if primary_previews else wf_previews
        tot = primary_total if primary_previews else wf_total
        pages |= select_pages_for_target(
            target, src, always_pages=always, total_pages=tot
        )

    primary_spans = parse_manifest_chunks(out / "_manifest.md", prefix="_chunks")
    if not primary_spans:
        primary_spans = discover_chunks_from_dir(out / "_chunks", "_chunks")

    wf_spans: list[ChunkSpan] = []
    if target == "03" and chunk_tree in ("waterfall", "both"):
        wf_spans = parse_manifest_chunks(out / "_manifest_waterfall.md", prefix="_chunks_waterfall")
        if not wf_spans:
            wf_spans = discover_chunks_from_dir(out / "_chunks_waterfall", "_chunks_waterfall")

    rels: list[str] = []
    if target == "03" and chunk_tree in ("waterfall", "both") and wf_spans and wf_previews:
        wf_pages = select_pages_for_target(
            "03", wf_previews, total_pages=wf_total
        )
        rels.extend(chunks_covering_pages(wf_spans, wf_pages))

    primary_pages = pages
    if target == "03" and chunk_tree == "both" and wf_previews:
        primary_pages = _merge_admin_pages_for_03(
            primary_previews,
            select_pages_for_target(
                "03", primary_previews, always_pages=always, total_pages=primary_total
            ),
        )
    rels.extend(chunks_covering_pages(primary_spans, primary_pages))

    seen: set[str] = set()
    deduped: list[str] = []
    for r in rels:
        if r not in seen:
            seen.add(r)
            deduped.append(r)

    page_list = sorted(pages)
    if not deduped:
        if pages:
            return ChunkSelectionResult(
                rel_paths=[],
                pages=page_list,
                note=(
                    f"Index-mapped pages {page_list} for {target} but no "
                    f"`_chunks/` / `_chunks_waterfall/` span covers them — check `_manifest.md`."
                ),
            )
        return None

    note = f"Index-driven chunks for {target}: pages {page_list} -> {len(deduped)} file(s)"
    return ChunkSelectionResult(rel_paths=deduped, pages=page_list, note=note)


def format_index_map_brief(
    target: str,
    *,
    pages: list[int],
    rel_paths: list[str],
    primary_previews: list[PagePreview],
    wf_previews: list[PagePreview] | None = None,
) -> str:
    """
    LLM-facing page map: which index rows and chunk files were selected (SDK-style scope).
    """
    preview_by_page: dict[int, str] = {p.page: p.preview for p in primary_previews}
    if wf_previews:
        for p in wf_previews:
            preview_by_page.setdefault(p.page, p.preview)

    lines = [
        f"## File {target} — index-driven page map (mandatory)",
        "",
        "The server mapped **`_page_index.md`** (and **`_page_index_waterfall.md`** for `03` when "
        "present) to **only** the chunk files and page sections below. Treat this as the full PDF "
        "scope for this deliverable — **do not** invent rows from pages not listed.",
    ]
    if target == "03" and pages and len(pages) >= 2:
        lines.append(
            "For **`03`**, selected pages are a **contiguous** interest + principal waterfall span — "
            "read and quote **every** page in the table (middle pages may have generic index previews "
            "but still contain clause steps and fees)."
        )
    lines.append("")
    if pages:
        lines.extend(
            [
                "### Selected pages",
                "",
                "| Page | `_page_index` preview |",
                "|------|------------------------|",
            ]
        )
        for pg in pages:
            prev = (preview_by_page.get(pg) or "—").replace("|", "/")
            if len(prev) > 160:
                prev = prev[:159].rstrip() + "…"
            lines.append(f"| {pg} | {prev} |")
        lines.append("")
    if rel_paths:
        lines.extend(
            [
                "### Chunk files in this bundle (read only these)",
                "",
                *[f"- `{r}`" for r in rel_paths],
                "",
            ]
        )
    else:
        lines.append("*No chunk files matched the selected pages.*")
        lines.append("")
    return "\n".join(lines)
