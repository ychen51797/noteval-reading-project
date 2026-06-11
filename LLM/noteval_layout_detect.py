"""
Detect trustee **02** (class / tranche) layout from ``_page_index.md`` previews and
drive index-driven chunk page selection + LLM briefings.

Layout families:
  - ``dual_pdd_idd`` — separate Principal + Interest Distribution Detail exhibits
  - ``consolidated`` — single Notes Information / Payment Date Report class grid
  - ``distribution_report`` — Distribution Report summary blocks (pages 2–3 style)
  - ``unknown`` — fall back to generic keyword scoring in ``noteval_chunk_select``
"""

from __future__ import annotations

from dataclasses import dataclass

from noteval_chunk_select import PagePreview

# --- Preview keywords (index first-line text, lowercased) -----------------------

_PDD_PREVIEW = (
    "principal distribution detail",
    "principal and interest distribution",  # combined title on one page
)
_IDD_PREVIEW = (
    "interest distribution detail",
)
_CONSOLIDATED_PREVIEW = (
    "notes information",
    "note valuation report",  # weak alone — paired with class columns in preview
    "class original principal",
    "beginning principal",
    "all in rate",
    "interest due",
    "ending principal",
)
_DIST_REPORT_PREVIEW = (
    "distribution report",
    "redemption report",
)
_FACTORS_PREVIEW = (
    "payment date factor",
    "payment date factors",
    "factor information per 1000",
    "factor per 1000",
    "coupon only — not balances",
    "coupon only",
)
_DIST_US_PREVIEW = (
    "distribution in us$",
)
# Deutsche NVR: US$ table title may appear below the first index lines.
_DIST_US_WEAK_PREVIEW = (
    "facevaluefacevaluebalance",
    "facevaluebalanceinterest",
)
_INTEREST_DETAIL_PREVIEW = (
    "interest detail",
)


@dataclass(frozen=True)
class TrancheLayout02:
    """Detected class-table layout for File ``02``."""

    family: str  # dual_pdd_idd | consolidated | distribution_report | unknown
    confidence: str  # high | medium | low
    evidence: tuple[str, ...]
    pdd_pages: tuple[int, ...]
    idd_pages: tuple[int, ...]
    consolidated_pages: tuple[int, ...]
    distribution_report_pages: tuple[int, ...]
    factors_pages: tuple[int, ...]
    distribution_us_pages: tuple[int, ...]
    interest_detail_pages: tuple[int, ...]
    primary_pages: tuple[int, ...]  # pages the LLM should read for class rows


def _blob(p: PagePreview) -> str:
    return p.preview.lower()


def _pages_matching(previews: list[PagePreview], keywords: tuple[str, ...]) -> list[int]:
    out: list[int] = []
    for p in previews:
        b = _blob(p)
        if any(k in b for k in keywords):
            out.append(p.page)
    return sorted(set(out))


def _is_dist_us_preview(blob: str) -> bool:
    if any(k in blob for k in _DIST_US_PREVIEW):
        return True
    compact = blob.replace(" ", "")
    return any(k in compact for k in _DIST_US_WEAK_PREVIEW)


def _distribution_us_pages(previews: list[PagePreview]) -> list[int]:
    out: list[int] = []
    for p in previews:
        if _is_dist_us_preview(_blob(p)):
            out.append(p.page)
    return sorted(set(out))


def _factors_pages(previews: list[PagePreview], dist_us_pages: list[int]) -> list[int]:
    out = _pages_matching(previews, _FACTORS_PREVIEW)
    if not dist_us_pages:
        return out
    anchor = min(dist_us_pages)
    for p in previews:
        if p.page in out or p.page <= anchor:
            continue
        b = _blob(p)
        if "note valuation report" in b and (
            "class cusip" in b or "factor per 1000" in b.replace(" ", "")
        ):
            out.append(p.page)
    return sorted(set(out))


def _primary_02_pages(
    *,
    dist_us_pages: list[int],
    interest_detail_pages: list[int],
    consolidated_pages: list[int],
    factors_pages: list[int],
    pdd_pages: list[int] | None = None,
    idd_pages: list[int] | None = None,
) -> list[int]:
    """Class-row **$** mapping pages: US$ + interest detail; exclude factor-only grids."""
    core: list[int] = []
    core.extend(dist_us_pages)
    core.extend(interest_detail_pages)
    if pdd_pages:
        core.extend(pdd_pages)
    if idd_pages:
        core.extend(idd_pages)
    for p in consolidated_pages:
        if p not in factors_pages and p not in core:
            core.append(p)
    return sorted(set(core))


def detect_02_layout_from_index(previews: list[PagePreview]) -> TrancheLayout02:
    """Classify ``02`` layout from ``_page_index.md`` row previews only."""
    empty = TrancheLayout02(
        family="unknown",
        confidence="low",
        evidence=("empty page index",),
        pdd_pages=(),
        idd_pages=(),
        consolidated_pages=(),
        distribution_report_pages=(),
        factors_pages=(),
        distribution_us_pages=(),
        interest_detail_pages=(),
        primary_pages=(),
    )
    if not previews:
        return empty

    pdd_pages = _pages_matching(previews, _PDD_PREVIEW)
    idd_pages = _pages_matching(previews, _IDD_PREVIEW)
    # "Notes Information" without requiring PDD/IDD titles
    consolidated_pages = _pages_matching(previews, _CONSOLIDATED_PREVIEW)
    # Drop cover-only NVR hits: page 1 often says "note valuation report" in preview
    consolidated_pages = [
        p
        for p in consolidated_pages
        if p > 1
        or any(
            k in next((x.preview.lower() for x in previews if x.page == p), "")
            for k in ("notes information", "class", "principal", "cusip")
        )
    ]
    dist_pages = _pages_matching(previews, _DIST_REPORT_PREVIEW)
    dist_us_pages = _distribution_us_pages(previews)
    factors_pages = _factors_pages(previews, dist_us_pages)
    interest_detail_pages = _pages_matching(previews, _INTEREST_DETAIL_PREVIEW)

    evidence: list[str] = []
    has_pdd = bool(pdd_pages)
    has_idd = bool(idd_pages)

    def _factor_evidence() -> None:
        if factors_pages:
            evidence.append(
                f"index: Factor page(s) {factors_pages} — "
                "**skip for balances**; **Current Coupon** → **Interest rate** when printed "
                "(Deutsche: **do not** concatenate **Index** + **Spread** from **Coupon Rates**; "
                "never map **~1000** factor cells to **Beginning** / **Ending** / **Interest payment**)"
            )

    if has_pdd and has_idd:
        primary = _primary_02_pages(
            dist_us_pages=dist_us_pages,
            interest_detail_pages=interest_detail_pages,
            consolidated_pages=[],
            factors_pages=factors_pages,
            pdd_pages=pdd_pages,
            idd_pages=idd_pages,
        )
        evidence.append(
            f"index: principal exhibit page(s) {pdd_pages}; interest exhibit page(s) {idd_pages}"
        )
        if dist_us_pages:
            evidence.append(
                f"index: Distribution in US$ page(s) {dist_us_pages} — "
                "**authoritative $** for balances / interest paid"
            )
        _factor_evidence()
        return TrancheLayout02(
            family="dual_pdd_idd",
            confidence="high",
            evidence=tuple(evidence),
            pdd_pages=tuple(pdd_pages),
            idd_pages=tuple(idd_pages),
            consolidated_pages=tuple(consolidated_pages),
            distribution_report_pages=tuple(dist_pages),
            factors_pages=tuple(factors_pages),
            distribution_us_pages=tuple(dist_us_pages),
            interest_detail_pages=tuple(interest_detail_pages),
            primary_pages=tuple(primary),
        )

    if consolidated_pages and not (has_pdd and has_idd):
        primary = _primary_02_pages(
            dist_us_pages=dist_us_pages,
            interest_detail_pages=interest_detail_pages,
            consolidated_pages=consolidated_pages,
            factors_pages=factors_pages,
        )
        if dist_us_pages:
            evidence.append(
                f"index: Distribution in US$ page(s) {dist_us_pages} — **primary $** "
                "(balances, interest paid; map full row — not Original column only)"
            )
        if interest_detail_pages:
            evidence.append(
                f"index: Interest Detail page(s) {interest_detail_pages} — merge cash interest / balances"
            )
        non_factor = [p for p in consolidated_pages if p not in factors_pages]
        evidence.append(f"index: Note Valuation / class grid page(s) {non_factor}")
        if has_pdd or has_idd:
            evidence.append(
                "index: partial dual-exhibit mention without both — treating as consolidated"
            )
        _factor_evidence()
        return TrancheLayout02(
            family="consolidated",
            confidence="high"
            if dist_us_pages
            or any("notes information" in _blob(p) for p in previews if p.page in primary)
            else "medium",
            evidence=tuple(evidence),
            pdd_pages=tuple(pdd_pages),
            idd_pages=tuple(idd_pages),
            consolidated_pages=tuple(consolidated_pages),
            distribution_report_pages=tuple(dist_pages),
            factors_pages=tuple(factors_pages),
            distribution_us_pages=tuple(dist_us_pages),
            interest_detail_pages=tuple(interest_detail_pages),
            primary_pages=tuple(primary),
        )

    if dist_pages and not has_pdd and not has_idd:
        primary = sorted(set(dist_pages + dist_us_pages))
        evidence.append(f"index: Distribution Report page(s) {primary}")
        _factor_evidence()
        return TrancheLayout02(
            family="distribution_report",
            confidence="medium",
            evidence=tuple(evidence),
            pdd_pages=tuple(pdd_pages),
            idd_pages=tuple(idd_pages),
            consolidated_pages=tuple(consolidated_pages),
            distribution_report_pages=tuple(dist_pages),
            factors_pages=tuple(factors_pages),
            distribution_us_pages=tuple(dist_us_pages),
            interest_detail_pages=tuple(interest_detail_pages),
            primary_pages=tuple(primary),
        )

    if has_pdd or has_idd:
        primary = _primary_02_pages(
            dist_us_pages=dist_us_pages,
            interest_detail_pages=interest_detail_pages,
            consolidated_pages=[],
            factors_pages=factors_pages,
            pdd_pages=pdd_pages,
            idd_pages=idd_pages,
        )
        evidence.append(f"index: only one dual exhibit found — pages {primary}")
        _factor_evidence()
        return TrancheLayout02(
            family="dual_pdd_idd",
            confidence="medium",
            evidence=tuple(evidence),
            pdd_pages=tuple(pdd_pages),
            idd_pages=tuple(idd_pages),
            consolidated_pages=tuple(consolidated_pages),
            distribution_report_pages=tuple(dist_pages),
            factors_pages=tuple(factors_pages),
            distribution_us_pages=tuple(dist_us_pages),
            interest_detail_pages=tuple(interest_detail_pages),
            primary_pages=tuple(primary),
        )

    return TrancheLayout02(
        family="unknown",
        confidence="low",
        evidence=("no dual exhibits, Notes Information, or Distribution Report hit in index",),
        pdd_pages=tuple(pdd_pages),
        idd_pages=tuple(idd_pages),
        consolidated_pages=tuple(consolidated_pages),
        distribution_report_pages=tuple(dist_pages),
        factors_pages=tuple(factors_pages),
        distribution_us_pages=tuple(dist_us_pages),
        interest_detail_pages=tuple(interest_detail_pages),
        primary_pages=(),
    )


def select_02_pages_by_layout(
    previews: list[PagePreview],
    layout: TrancheLayout02,
    *,
    always_pages: tuple[int, ...] = (),
) -> set[int] | None:
    """
  Return explicit page set for ``02``, or ``None`` to use generic index scoring.
    """
    selected: set[int] = set(always_pages)

    if layout.family == "dual_pdd_idd":
        for p in previews:
            b = _blob(p)
            if any(k in b for k in _PDD_PREVIEW):
                selected.add(p.page)
            if any(k in b for k in _IDD_PREVIEW):
                selected.add(p.page)
            if _is_dist_us_preview(b):
                selected.add(p.page)
        selected.update(layout.distribution_us_pages)
        selected.update(layout.interest_detail_pages)
        # Factor pages: optional context for Coupon % only (not required for chunk scope)
        if not selected and layout.primary_pages:
            selected.update(layout.primary_pages)
        if selected:
            lo = max(1, min(selected) - 1)
            hi = max(selected)
            selected |= set(range(lo, hi + 1))
        return selected

    if layout.family == "consolidated":
        selected.update(layout.distribution_us_pages)
        selected.update(layout.interest_detail_pages)
        if layout.primary_pages:
            selected.update(layout.primary_pages)
        else:
            for p in previews:
                b = _blob(p)
                if any(k in b for k in _CONSOLIDATED_PREVIEW) and p.page not in layout.factors_pages:
                    selected.add(p.page)
        # Neighbor context for wrapped headers (±1 page); include factor page only as neighbor
        if selected:
            expanded: set[int] = set()
            for pg in selected:
                expanded.add(pg)
                if pg > 1:
                    expanded.add(pg - 1)
                expanded.add(pg + 1)
            selected = expanded
        return selected if selected else None

    if layout.family == "distribution_report":
        selected.update(layout.distribution_report_pages)
        selected.update(layout.distribution_us_pages)
        if selected:
            lo = max(1, min(selected) - 1)
            hi = max(selected)
            selected |= set(range(lo, hi + 1))
        return selected if selected else None

    return None


def refine_02_layout_from_chunks(layout: TrancheLayout02, chunk_text: str) -> TrancheLayout02:
    """Upgrade/downgrade layout when chunk text contradicts index-only detection."""
    low = (chunk_text or "").lower()[:400_000]
    if not low:
        return layout

    has_pdd = "principal distribution detail" in low
    has_idd = "interest distribution detail" in low
    has_dist_us = "distribution in us$" in low
    has_interest_detail = "interest detail" in low and "interest paid" in low
    has_factor = "factor information per 1000" in low
    has_notes = "notes information" in low and (
        "beginning principal" in low or "all in rate" in low or "interest due" in low
    )

    evidence = list(layout.evidence)
    dist_us = list(layout.distribution_us_pages)
    interest_detail = list(layout.interest_detail_pages)
    factors = list(layout.factors_pages)
    consolidated = list(layout.consolidated_pages)

    if has_dist_us and not dist_us:
        evidence.append("chunks: Distribution in US$ title present — prioritize for primary $")
        # Typical Deutsche NVR: US$ table is page 2 when bundle starts at page 1
        if 2 not in dist_us:
            dist_us.append(2)
    if has_interest_detail and not interest_detail:
        evidence.append("chunks: Interest Detail exhibit present")
        if 3 not in interest_detail:
            interest_detail.append(3)
    if has_factor and not factors:
        evidence.append("chunks: Factor per 1000 grid present — coupon/rate only")
        if 4 not in factors:
            factors.append(4)

    if dist_us or interest_detail or factors:
        primary = _primary_02_pages(
            dist_us_pages=dist_us,
            interest_detail_pages=interest_detail,
            consolidated_pages=consolidated,
            factors_pages=factors,
            pdd_pages=list(layout.pdd_pages),
            idd_pages=list(layout.idd_pages),
        )
        if layout.family in ("consolidated", "unknown") and (has_dist_us or dist_us):
            evidence.append(
                "chunks: using Distribution in US$ + Interest Detail for class **$**; "
                "skipping Factor per 1000 for balances"
            )
            return TrancheLayout02(
                family="consolidated",
                confidence="high",
                evidence=tuple(evidence),
                pdd_pages=layout.pdd_pages,
                idd_pages=layout.idd_pages,
                consolidated_pages=layout.consolidated_pages,
                distribution_report_pages=layout.distribution_report_pages,
                factors_pages=tuple(sorted(set(factors))),
                distribution_us_pages=tuple(sorted(set(dist_us))),
                interest_detail_pages=tuple(sorted(set(interest_detail))),
                primary_pages=tuple(primary),
            )

    if has_pdd and has_idd and layout.family != "dual_pdd_idd":
        evidence.append("chunks: both Principal and Interest Distribution Detail titles present")
        primary = _primary_02_pages(
            dist_us_pages=dist_us,
            interest_detail_pages=interest_detail,
            consolidated_pages=[],
            factors_pages=factors,
            pdd_pages=list(layout.pdd_pages),
            idd_pages=list(layout.idd_pages),
        )
        return TrancheLayout02(
            family="dual_pdd_idd",
            confidence="high",
            evidence=tuple(evidence),
            pdd_pages=layout.pdd_pages,
            idd_pages=layout.idd_pages,
            consolidated_pages=layout.consolidated_pages,
            distribution_report_pages=layout.distribution_report_pages,
            factors_pages=tuple(sorted(set(factors))),
            distribution_us_pages=tuple(sorted(set(dist_us))),
            interest_detail_pages=tuple(sorted(set(interest_detail))),
            primary_pages=tuple(primary) if primary else layout.pdd_pages + layout.idd_pages,
        )

    if has_notes and not (has_pdd and has_idd) and layout.family == "unknown":
        evidence.append("chunks: Notes Information consolidated grid")
        primary = _primary_02_pages(
            dist_us_pages=dist_us,
            interest_detail_pages=interest_detail,
            consolidated_pages=consolidated,
            factors_pages=factors,
        )
        return TrancheLayout02(
            family="consolidated",
            confidence="high",
            evidence=tuple(evidence),
            pdd_pages=layout.pdd_pages,
            idd_pages=layout.idd_pages,
            consolidated_pages=layout.consolidated_pages,
            distribution_report_pages=layout.distribution_report_pages,
            factors_pages=tuple(sorted(set(factors))),
            distribution_us_pages=tuple(sorted(set(dist_us))),
            interest_detail_pages=tuple(sorted(set(interest_detail))),
            primary_pages=tuple(primary) if primary else layout.consolidated_pages,
        )

    return layout


def format_index_brief_for_02(
    previews: list[PagePreview],
    layout: TrancheLayout02,
    selected_pages: set[int],
) -> str:
    """Markdown block prepended to the LLM chunk bundle for deliverable ``02``."""
    _family_label = {
        "dual_pdd_idd": "dual_exhibits",
        "consolidated": "consolidated",
        "distribution_report": "distribution_report",
        "unknown": "unknown",
    }.get(layout.family, layout.family)
    lines = [
        "## File 02 — layout detection (read before chunk text)",
        "",
        f"**Detected layout:** `{_family_label}` (confidence: {layout.confidence})",
        "",
    ]
    if layout.evidence:
        lines.append("**Evidence:** " + "; ".join(layout.evidence))
        lines.append("")

    lines.extend(
        [
            "**Index map (_page_index.md → use matching `_chunks/` pages):**",
            "",
            "| Page | Index preview | Role for 02 |",
            "|------|---------------|-------------|",
        ]
    )

    sel = selected_pages or set(layout.primary_pages)
    primary_set = set(layout.primary_pages)

    def _role_for_page(pg: int) -> str:
        if pg in layout.factors_pages:
            return (
                "**SKIP balances** — Factor per 1000 / **Coupon Rates**; "
                "**Current Coupon** → **Interest rate** (not **Index** + **Spread** concat)"
            )
        if pg in layout.distribution_us_pages:
            return (
                "**Primary $** — Distribution in US$; **Prior principal balance** → "
                "**Beginning balance**; **Current principal balance** → **Ending balance** "
                "(map full row — not Original / factor ~1000)"
            )
        if pg in layout.interest_detail_pages:
            return (
                "**Primary $** — Interest Detail (**Interest Paid** → payment; "
                "**Prior Cumulative** ≠ period cash)"
            )
        if layout.family == "dual_pdd_idd":
            if pg in layout.pdd_pages:
                return "**Principal exhibit** — balances / principal paid"
            if pg in layout.idd_pages:
                return "**Interest exhibit** — interest paid / payable / coupon"
        if pg in primary_set:
            if layout.family == "distribution_report" and pg in layout.distribution_report_pages:
                return "**Primary** — Distribution Report class summary"
            if layout.family == "consolidated" and pg in layout.consolidated_pages:
                return "**Primary** — Note Valuation class grid (supporting US$ / interest)"
            return "**Primary** — class rows"
        if pg in sel:
            return "context / neighbor"
        return "—"

    for p in previews:
        role = _role_for_page(p.page)
        if p.page in sel and role == "—":
            role = "context / neighbor"
        preview = (p.preview or "").replace("|", "/")[:120]
        lines.append(f"| {p.page} | {preview} | {role} |")

    lines.append("")
    if layout.family == "dual_pdd_idd":
        dist_us_in_sel = any(
            "distribution in us$" in _blob(p) for p in previews if p.page in sel
        )
        dual_rules = [
            "**Dual-exhibit rules:**",
            "- Map **principal** fields from **principal exhibit** pages; **interest** paid/payable/rate from **interest exhibit** pages.",
            "- One **primary** row per **economic class** (printed Note Class / subtotal), not per CUSIP line.",
            "- Extra CUSIPs under the same class → **`### Tranche by listing`** only when the PDF prints multiple listings.",
            "- Use the **index table above** to open the right chunk pages — do not assume fixed page numbers.",
        ]
        if dist_us_in_sel:
            dual_rules.extend(
                [
                    "- **Distribution in US$** (when in index map): **Prior principal balance** → **Beginning balance**; "
                    "**Current principal balance** → **Ending balance**; also **Interest payment** / **Principal payment** "
                    "from the **$** row — map **every** column, **not** only **Original face**.",
                    "- **Interest rate** from **Current Coupon** on **Distribution in US$** when printed; "
                    "**Deutsche Bank:** **do not** use **Index** + **Spread** from **Coupon Rates** unless "
                    "**Current Coupon** is absent and **Notes** document index+margin.",
                    "- **SUB** / subordinated lines with **non-zero** balances on **Distribution in US$** must appear in **primary** "
                    "(rollup **I-SUB** / **II-SUB** or trustee subtotal) — **never** only in a side grid with **~1000** factor balances.",
                ]
            )
        dual_rules.append("")
        lines.extend(dual_rules)
    elif layout.family == "consolidated":
        cons_rules = [
            "**Deutsche / consolidated NVR rules (read index roles above):**",
            "- **Distribution in US$** pages: **Prior principal balance** → **Beginning balance**; "
            "**Current principal balance** → **Ending balance**; **Interest payment** / **Principal payment** "
            "from the same row — map **every** column, **not** only **Original face**.",
            "- **Interest Detail** pages: merge cash interest / balances when US$ row is sparse.",
            "- **Factor Information per 1000 / Coupon Rates** pages: **SKIP** for balances and interest **$**; "
            "**Interest rate** = **Current Coupon** when printed (on US$ or factor page) — "
            "**do not** fill **Interest rate** as **Index % + Spread %** from separate factor columns.",
            "- **Interest Detail:** **Interest Paid** → **Interest payment**; **Prior Cumulative** leading **$** "
            "is deferred balance, **not** period interest cash.",
            "- One **primary** row per **economic class**; program slices (**SUB-144A**, **I-SUB-REGS**, …) → "
            "**`### Tranche by listing`** when multiple CUSIPs print.",
            "- **Subordinated** rows may show **0% coupon** but **non-zero** cash interest on US$ / Interest Detail.",
        ]
        if layout.distribution_us_pages:
            cons_rules.append(
                f"- **Pages with Distribution in US$:** {list(layout.distribution_us_pages)}."
            )
        if layout.factors_pages:
            cons_rules.append(
                f"- **Pages to skip for $ mapping (coupon only):** {list(layout.factors_pages)}."
            )
        cons_rules.append("")
        lines.extend(cons_rules)
    elif layout.family == "distribution_report":
        lines.extend(
            [
                "**Distribution Report summary rules:**",
                "- Map class balances from summary blocks per `extraction-templates.md` (ii)(a)/(ii)(b)/(iii).",
                "- Use Payment Date Factors pages for cross-check / listing only unless template says otherwise.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "**Layout unclear:** Read index previews and chunk text; identify whether the deal uses "
                "**separate principal + interest exhibits**, a **single consolidated** class table, or a **Distribution Report** summary before filling `02`.",
                "",
            ]
        )

    if selected_pages:
        lines.append(f"**Pages selected for this draft:** {sorted(selected_pages)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)
