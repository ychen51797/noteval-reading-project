"""
Extract trustee-style grids with pdfplumber and write Markdown tables under
``_chunks_structured/``:

- ``pdd_idd_pdfplumber.md`` — Principal / Interest Distribution Detail (PDD/IDD).
- ``payment_date_report_pdfplumber.md`` — Payment Date Report / consolidated
  per-class principal & interest grids (detected by **content fingerprints** on
  pypdf page text, not by number position in linearized chunks).

Requires ``pdfplumber`` (``py -3 -m pip install pdfplumber``). When the import
fails, callers should skip silently.

Used after pypdf segmentation so ``page_texts`` can select candidate pages without
re-parsing layout text for detection.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def pages_matching_pdd_idd(page_texts: list[str]) -> list[int]:
    """1-based page numbers whose body text looks like PDD / IDD (same cues as page index)."""
    keys = (
        "principal distribution detail",
        "interest distribution detail",
        "principal and interest distribution",
    )
    # CUSIP-style identifiers (US) usually start with a digit; avoids matching words like STATEMENT.
    cusip_like = re.compile(r"\b[0-9][A-Z0-9]{8}\b")
    out: list[int] = []
    for i, raw in enumerate(page_texts):
        low = (raw or "").lower()
        if not any(k in low for k in keys):
            continue
        if "table of contents" in low and "principal distribution detail" in low:
            i_toc = low.find("table of contents")
            i_pdd = low.find("principal distribution detail")
            if i_toc >= 0 and i_pdd >= 0 and i_toc < i_pdd and not cusip_like.search(raw or ""):
                continue
        out.append(i + 1)
    return sorted(set(out))


def pages_matching_payment_date_report(page_texts: list[str]) -> list[int]:
    """
    1-based page numbers whose pypdf text matches a **Payment Date Report** or
    similar consolidated class economics grid (fingerprints — no PDD/IDD title
    required). Excludes obvious TOC-only hits when the real section appears later
    without data cues.
    """
    cusip_like = re.compile(r"\b[0-9][A-Z0-9]{8}\b")
    out: list[int] = []
    for i, raw in enumerate(page_texts):
        low = (raw or "").lower()
        has_pdr = "payment date report" in low
        has_orig = "original principal amount" in low
        has_ending = "ending principal amount" in low
        has_prin_begin = "principal amount beginning" in low
        has_int_paid = "interest paid" in low
        has_int_due = "interest due" in low
        has_def = "deferred interest" in low
        has_prin_pay_col = (
            "principal payments" in low
            or "principal payments on related payment date" in low
            or ("principal payment" in low and "related payment" in low)
        )

        # Strong: titled section
        titled = has_pdr and (
            has_orig
            or has_ending
            or has_prin_begin
            or has_int_paid
            or has_int_due
            or has_prin_pay_col
        )
        # Strong: classic column bundle without requiring the report title on-page
        bundle_a = has_orig and has_ending and (has_int_paid or has_int_due)
        bundle_b = (
            has_prin_begin
            and has_ending
            and has_int_paid
            and (has_prin_pay_col or has_def)
        )

        if not (titled or bundle_a or bundle_b):
            continue

        # TOC guard: TOC appears before the first fingerprint hit and no CUSIP-like row
        if "table of contents" in low:
            i_toc = low.find("table of contents")
            hits: list[int] = []
            for needle in (
                "payment date report",
                "original principal amount",
                "ending principal amount",
                "principal amount beginning",
                "interest paid",
            ):
                j = low.find(needle)
                if j >= 0:
                    hits.append(j)
            i_hit = min(hits) if hits else -1
            if (
                i_toc >= 0
                and i_hit >= 0
                and i_toc < i_hit
                and not cusip_like.search(raw or "")
            ):
                continue

        out.append(i + 1)
    return sorted(set(out))


def _clean_cell(x: object) -> str:
    if x is None:
        return ""
    s = str(x).replace("\n", " ").strip()
    s = s.replace("|", "\\|")
    return s


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    if not rows:
        return ""
    ncol = max((len(r) for r in rows), default=0)
    if ncol == 0:
        return ""
    norm: list[list[str | None]] = []
    for r in rows:
        row = list(r) if r else []
        if len(row) < ncol:
            row = row + [None] * (ncol - len(row))
        else:
            row = row[:ncol]
        norm.append(row)
    header = norm[0]
    sep = ["---"] * ncol
    lines = [
        "| " + " | ".join(_clean_cell(c) for c in header) + " |",
        "| " + " | ".join(sep) + " |",
    ]
    for r in norm[1:]:
        lines.append("| " + " | ".join(_clean_cell(c) for c in r) + " |")
    return "\n".join(lines) + "\n"


def _page_section_label(page_text: str) -> str:
    low = (page_text or "").lower()
    if "principal distribution detail" in low:
        return "Principal Distribution Detail"
    if "interest distribution detail" in low:
        return "Interest Distribution Detail"
    return "Distribution-related page"


def _page_section_label_payment_date_report(page_text: str) -> str:
    low = (page_text or "").lower()
    if "payment date report" in low:
        return "Payment Date Report"
    if "original principal amount" in low and "ending principal amount" in low:
        return "Consolidated class economics (principal / interest grid)"
    return "Payment-date / class economics page"


def _extract_tables_for_page(page: object) -> list[list[list[str | None]]]:
    """Return non-empty tables (list of rows) using line-first then text strategy."""
    strategies: tuple[dict[str, str], ...] = (
        {"vertical_strategy": "lines", "horizontal_strategy": "lines"},
        {"vertical_strategy": "text", "horizontal_strategy": "text"},
    )
    out: list[list[list[str | None]]] = []
    for ts in strategies:
        try:
            raw_tabs = page.extract_tables(table_settings=ts) or []
        except Exception:
            continue
        for tab in raw_tabs:
            if not tab or len(tab) < 2:
                continue
            ncol = max(len(r or []) for r in tab)
            ncells = sum(len(r or []) for r in tab)
            if ncol < 2 or ncells < 8:
                continue
            out.append(tab)
        if out:
            break
    return out


def write_structured_pdd_idd_markdown(
    pdf_path: Path,
    output_dir: Path,
    page_texts: list[str],
) -> Path | None:
    """
    Write ``_chunks_structured/pdd_idd_pdfplumber.md`` when pdfplumber is available
    and at least one table is extracted. Otherwise return ``None``.
    """
    try:
        import pdfplumber
    except ImportError:
        return None

    pdf_path = pdf_path.resolve()
    output_dir = output_dir.resolve()
    if not pdf_path.is_file():
        return None

    pages = pages_matching_pdd_idd(page_texts)
    if not pages:
        return None

    chunks: list[str] = [
        "# PDD / IDD tables (pdfplumber → Markdown)",
        "",
        "These tables are machine-extracted from PDF vector geometry. Use **together** with "
        "``_chunks/*.txt`` (pypdf). **Prefer this file for column alignment and row grouping** "
        "when the linearized chunk text disagrees with the printed grid (e.g. Computershare "
        "CUSIP blocks vs Note Class lines). **Tail-label rule (critical):** Any token — whether "
        "a single letter or a full class name like ``AL3-R2`` — glued after ``Sub Totals`` in "
        "the first column is the **next** section's class name, **not** the class for the current "
        "row. The current CUSIP row belongs to the class whose name appeared as the tail of the "
        "**preceding** row. Do not assign a CUSIP to the tail label on its own row — that label "
        "names the section that follows. Example: ``BCC3N3Y39 ... Sub Totals: ... AL3-R2`` means "
        "BCC3N3Y39 belongs to **AL2-R2** (the tail of the preceding row), and AL3-R2 is the "
        "header of the *next* section.",
        "",
    ]

    n_tables = 0
    with pdfplumber.open(str(pdf_path)) as pdf:
        n_doc = len(pdf.pages)
        for pnum in pages:
            if pnum < 1 or pnum > n_doc:
                continue
            page = pdf.pages[pnum - 1]
            pt = page_texts[pnum - 1] if pnum <= len(page_texts) else ""
            label = _page_section_label(pt)
            chunks.append(f"## Page {pnum} — {label}")
            chunks.append("")
            tables = _extract_tables_for_page(page)
            if not tables:
                chunks.append(
                    "_pdfplumber found no table on this page (layout may be non-grid); "
                    "rely on ``_chunks/`` text._"
                )
                chunks.append("")
                continue
            for ti, tab in enumerate(tables, start=1):
                chunks.append(f"### Table {ti}")
                chunks.append("")
                chunks.append(_table_to_markdown(tab))
                chunks.append("")
                n_tables += 1

    if n_tables == 0:
        return None

    out_dir = output_dir / "_chunks_structured"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "pdd_idd_pdfplumber.md"
    out_path.write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8", newline="\n")
    return out_path


def write_structured_payment_date_report_markdown(
    pdf_path: Path,
    output_dir: Path,
    page_texts: list[str],
) -> Path | None:
    """
    Write ``_chunks_structured/payment_date_report_pdfplumber.md`` when pdfplumber
    is available and at least one fingerprint-matched page yields a table.
    Pages are chosen from **pypdf text fingerprints** (not column position in
    ``_chunks/*.txt``). Overlap with PDD/IDD pages is allowed — grids differ.
    """
    try:
        import pdfplumber
    except ImportError:
        return None

    pdf_path = pdf_path.resolve()
    output_dir = output_dir.resolve()
    if not pdf_path.is_file():
        return None

    pages = pages_matching_payment_date_report(page_texts)
    if not pages:
        return None

    chunks: list[str] = [
        "# Payment Date Report / consolidated class economics (pdfplumber → Markdown)",
        "",
        "These tables are machine-extracted from PDF vector geometry. **Prefer this file** "
        "over inferring dollar columns from **positional order** in ``_chunks/*.txt`` when "
        "the linearized text wraps headers (e.g. **Principal Payments** vs **Ending Principal "
        "Amount**). Use **printed column headers** in the Markdown tables below. Still quote "
        "**verbatim** ``_chunks/*.txt`` lines in **`## Source Text`** per template.",
        "",
    ]

    n_tables = 0
    with pdfplumber.open(str(pdf_path)) as pdf:
        n_doc = len(pdf.pages)
        for pnum in pages:
            if pnum < 1 or pnum > n_doc:
                continue
            page = pdf.pages[pnum - 1]
            pt = page_texts[pnum - 1] if pnum <= len(page_texts) else ""
            label = _page_section_label_payment_date_report(pt)
            chunks.append(f"## Page {pnum} — {label}")
            chunks.append("")
            tables = _extract_tables_for_page(page)
            if not tables:
                chunks.append(
                    "_pdfplumber found no table on this page (layout may be non-grid); "
                    "rely on ``_chunks/`` text._"
                )
                chunks.append("")
                continue
            for ti, tab in enumerate(tables, start=1):
                chunks.append(f"### Table {ti}")
                chunks.append("")
                chunks.append(_table_to_markdown(tab))
                chunks.append("")
                n_tables += 1

    if n_tables == 0:
        return None

    out_dir = output_dir / "_chunks_structured"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "payment_date_report_pdfplumber.md"
    out_path.write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8", newline="\n")
    return out_path


def parse_pdfplumber_cusip_class(structured_md: str) -> dict[str, str]:
    """
    Parse ``_chunks_structured/pdd_idd_pdfplumber.md`` and return a dict mapping
    each CUSIP / Identifier → Note Class label (e.g. ``{"97988QBJ2": "E-RR", ...}``).

    The pdfplumber table groups each CUSIP under the Note Class label that appears in
    the first column of its group.  This is the authoritative CUSIP→class assignment
    for Computershare PDD/IDD — preferred over nth-label ↔ nth-Sub-Totals-band
    matching on pypdf linearized text.

    Rules applied when parsing:
    - Rows where col-0 looks like a Note Class header (non-empty, not an identifier,
      not "Sub Totals:", not a pure number) set the current_class.
    - Rows where col-1 looks like a real identifier (9-char alphanumeric CUSIP or
      ISSUER\\d+ / ISSUER\\w+ placeholder) are emitted as {identifier: current_class}.
    - "Sub Totals:" rows are skipped.
    - current_class resets between tables / pages but carries forward within a table.
    """
    _cusip_re = re.compile(r"^[0-9A-Z]{9}$")
    _issuer_re = re.compile(r"^ISSUER\w+$", re.I)
    _number_re = re.compile(r"^-?[\d,]+(\.\d+)?$")

    result: dict[str, str] = {}
    current_class: str | None = None

    for line in structured_md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            # Section heading or blank — reset class so next table starts fresh
            current_class = None
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not cells:
            continue
        # Skip separator rows
        if all(re.fullmatch(r"[-: ]+", c) for c in cells if c):
            continue

        col0 = cells[0] if cells else ""
        col1 = cells[1] if len(cells) > 1 else ""

        # Detect Note Class header row: col0 non-empty, col1 empty, col0 not a
        # number or Sub Totals, not obviously a CUSIP
        if col0 and not col1:
            col0_up = col0.upper()
            if (
                not col0_up.startswith("SUB TOTALS")
                and not _number_re.match(col0)
                and not _cusip_re.match(col0_up)
                and not _issuer_re.match(col0_up)
                and "totals" not in col0.lower()
                and "|" not in col0
            ):
                current_class = col0
                continue

        # Detect identifier row: col1 is the first identifier in this pdfplumber row.
        # Use setdefault so that a CUSIP already assigned from col0 pre-Sub-Totals scan
        # (on the same glued row) is not overwritten by a later continuation row.
        if col1 and current_class:
            col1_up = col1.upper()
            if _cusip_re.match(col1_up) or _issuer_re.match(col1_up):
                result.setdefault(col1_up, current_class)

        # The glued col0 may contain additional identifiers AND the next class label.
        # Extract any CUSIP/ISSUER tokens from col0 that appear BEFORE "Sub Totals:"
        # (they all belong to current_class), then advance current_class from the tail.
        if col0 and current_class:
            before_st = col0.split("Sub Totals")[0] if "Sub Totals" in col0 else col0
            for token in before_st.split():
                t_up = token.upper()
                if _cusip_re.match(t_up) or _issuer_re.match(t_up):
                    result.setdefault(t_up, current_class)
            # Advance current_class from the tail after Sub Totals
            if "Sub Totals" in col0:
                tail = re.split(r"Sub Totals:?\s*[\d,. ]+", col0, maxsplit=1)
                if len(tail) > 1:
                    candidate = tail[-1].strip()
                    if (
                        candidate
                        and not _number_re.match(candidate)
                        and not _cusip_re.match(candidate.upper())
                        and not _issuer_re.match(candidate.upper())
                        and "totals" not in candidate.lower()
                    ):
                        current_class = candidate

    return result


def parse_pdfplumber_pdd_rows(structured_md: str) -> list[dict[str, str]]:
    """
    Parse ``_chunks_structured/pdd_idd_pdfplumber.md`` and return one dict per
    CUSIP / Identifier row from the **first** PDD table encountered, reading
    values directly from the vector-geometry column cells (cols 1–9).

    Each dict contains:
        cusip            – identifier string (e.g. "97988QBC7", "ISSUER172")
        economic_class   – Note Class label from the current section header
        original_face    – col 2 value
        beginning_balance – col 3 value (Period Beginning Balance)
        principal_distribution – col 5 value
        deferred_interest – col 6 value
        ending_balance   – col 7 value

    Only the first PDD table (before IDD / Payment Date Report sections) is
    parsed.  Values come directly from pdfplumber's column-aligned extraction,
    so they are immune to the nth-label ↔ nth-band positional ambiguity in
    linearized pypdf text.

    Sub Totals rows are skipped.  The Note Class header rows (col0 non-empty,
    col1 empty) advance ``current_class`` exactly as in
    ``parse_pdfplumber_cusip_class``.
    """
    _cusip_re = re.compile(r"^[0-9A-Z]{9}$")
    _issuer_re = re.compile(r"^ISSUER\w+$", re.I)
    _number_re = re.compile(r"^-?[\d,]+(\.\d+)?$")

    # Expected PDD column headers at fixed indices (0-based, Computershare standard).
    # col0=Note Class, col1=Identifier, col2=Original Face,
    # col3=Period Beginning Balance, col4=Period Beginning Balance Factor,
    # col5=Principal Distribution, col6=Deferred Interest,
    # col7=Ending Balance, col8=Principal Distribution Factor,
    # col9=Ending Balance Factor
    _PDD_EXPECTED: dict[int, str] = {
        1: "Identifier",
        2: "Original Face",
        3: "Period Beginning Balance",
        5: "Principal Distribution",
        6: "Deferred Interest",
        7: "Ending Balance",
    }

    rows: list[dict[str, str]] = []
    current_class: str | None = None
    in_pdd = False
    pdd_header_validated = False
    # Maps CUSIP → class extracted from glued col0 pre-Sub-Totals tokens.
    # Used to correctly assign continuation rows whose current_class may have already
    # been advanced to the next section by the Sub Totals tail.
    pre_assigned: dict[str, str] = {}

    for line in structured_md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            low = line.lower()
            if "interest distribution" in low or "payment date report" in low:
                break
            if "principal distribution" in low:
                in_pdd = True
            current_class = None
            continue
        if not in_pdd:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not cells:
            continue
        if all(re.fullmatch(r"[-: ]+", c) for c in cells if c):
            continue

        col0 = cells[0] if len(cells) > 0 else ""
        col1 = cells[1] if len(cells) > 1 else ""

        # Header row validation — fires once on the column-name row
        if not pdd_header_validated and col1 == "Identifier":
            pdd_header_validated = True
            mismatches = []
            for idx, expected in _PDD_EXPECTED.items():
                actual = cells[idx] if len(cells) > idx else "(missing)"
                if actual.lower() != expected.lower():
                    mismatches.append(f"col{idx}: expected '{expected}', got '{actual}'")
            if mismatches:
                import sys
                print(
                    f"WARNING parse_pdfplumber_pdd_rows: Computershare PDD column layout "
                    f"mismatch — fixed indices may be wrong. Differences: "
                    + "; ".join(mismatches),
                    file=sys.stderr,
                )
            continue

        # Note Class header row
        if col0 and not col1:
            col0_up = col0.upper()
            if (
                not col0_up.startswith("SUB TOTALS")
                and not _number_re.match(col0)
                and not _cusip_re.match(col0_up)
                and not _issuer_re.match(col0_up)
                and "totals" not in col0.lower()
            ):
                current_class = col0
                continue

        if col1.lower().startswith("sub totals"):
            continue

        # Pre-scan col0 for any additional CUSIP tokens before "Sub Totals:" —
        # they belong to current_class even after the tail advances it.
        if col0 and current_class:
            before_st = col0.split("Sub Totals")[0] if "Sub Totals" in col0 else col0
            for token in before_st.split():
                t_up = token.upper()
                if (_cusip_re.match(t_up) or _issuer_re.match(t_up)) and t_up not in pre_assigned:
                    pre_assigned[t_up] = current_class

        # col1 is the identifier; use pre_assigned class if available (accounts for
        # continuation rows where current_class has already been advanced)
        if col1 and current_class is not None:
            col1_up = col1.upper()
            if _cusip_re.match(col1_up) or _issuer_re.match(col1_up):
                ec = pre_assigned.get(col1_up, current_class)
                rows.append({
                    "cusip": col1_up,
                    "economic_class": ec,
                    "original_face": cells[2] if len(cells) > 2 else "",
                    "beginning_balance": cells[3] if len(cells) > 3 else "",
                    "principal_distribution": cells[5] if len(cells) > 5 else "",
                    "deferred_interest": cells[6] if len(cells) > 6 else "",
                    "ending_balance": cells[7] if len(cells) > 7 else "",
                })

        # Advance current_class from glued col0 Sub Totals tail
        if col0 and "Sub Totals" in col0 and current_class:
            tail = re.split(r"Sub Totals:?\s*[\d,. ]+", col0, maxsplit=1)
            if len(tail) > 1:
                candidate = tail[-1].strip()
                if (
                    candidate
                    and not _number_re.match(candidate)
                    and not _cusip_re.match(candidate.upper())
                    and not _issuer_re.match(candidate.upper())
                    and "totals" not in candidate.lower()
                ):
                    current_class = candidate

    return rows


def parse_pdfplumber_idd_rows(structured_md: str) -> list[dict[str, str]]:
    """
    Parse ``_chunks_structured/pdd_idd_pdfplumber.md`` and return one dict per
    CUSIP / Identifier row from the **first** IDD table encountered.

    Each dict contains:
        cusip              – identifier string
        economic_class     – Note Class label from the current section header
        beginning_balance  – col 2 value (Period Beginning Balance)
        coupon_rate        – col 3 value (Coupon Rate)
        interest_distribution – col 6 value (Interest Distribution / paid column)

    Column indices follow the IDD header:
        col0 Note Class | col1 Identifier | col2 Period Beginning Balance |
        col3 Coupon Rate | col4 Accrued Interest | col5 Payment of Previous
        Interest Shortfall | col6 Current Interest Shortfall |
        col7 Interest Distribution | col8 Interest Distribution Factor | ...

    Computershare IDD column order (0-based, matching printed headers):
        col0  Note Class
        col1  Identifier
        col2  Period Beginning Balance          → beginning_balance
        col3  Coupon Rate                       → coupon_rate
        col4  Accrued Interest
        col5  Payment of Previous Interest Shortfall
        col6  Current Interest Shortfall
        col7  Interest Distribution             → interest_distribution (paid)
        col8  Interest Distribution Factor
        col9  Remaining Unpaid Interest Shortfall
        col10 Cumulative Interest Distribution
    """
    _cusip_re = re.compile(r"^[0-9A-Z]{9}$")
    _issuer_re = re.compile(r"^ISSUER\w+$", re.I)
    _number_re = re.compile(r"^-?[\d,]+(\.\d+)?$")

    # Expected IDD column headers at fixed indices (0-based, Computershare standard).
    # col0=Note Class, col1=Identifier, col2=Period Beginning Balance,
    # col3=Coupon Rate, col4=Accrued Interest,
    # col5=Payment of Previous Interest Shortfall,
    # col6=Current Interest Shortfall, col7=Interest Distribution,
    # col8=Interest Distribution Factor,
    # col9=Remaining Unpaid Interest Shortfall,
    # col10=Cumulative Interest Distribution
    _IDD_EXPECTED: dict[int, str] = {
        1: "Identifier",
        2: "Period Beginning Balance",
        3: "Coupon Rate",
        4: "Accrued Interest",
        5: "Payment of Previous Interest Shortfall",
        6: "Current Interest Shortfall",
        7: "Interest Distribution",
    }

    rows: list[dict[str, str]] = []
    current_class: str | None = None
    in_idd = False
    idd_header_validated = False
    pre_assigned: dict[str, str] = {}

    for line in structured_md.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            low = line.lower()
            if "interest distribution" in low:
                in_idd = True
                current_class = None
            elif "principal distribution" in low and in_idd:
                break
            else:
                current_class = None
            continue
        if not in_idd:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if not cells:
            continue
        if all(re.fullmatch(r"[-: ]+", c) for c in cells if c):
            continue

        col0 = cells[0] if len(cells) > 0 else ""
        col1 = cells[1] if len(cells) > 1 else ""

        # Header row validation — fires once on the column-name row
        if not idd_header_validated and col1 == "Identifier":
            idd_header_validated = True
            mismatches = []
            for idx, expected in _IDD_EXPECTED.items():
                actual = cells[idx] if len(cells) > idx else "(missing)"
                if actual.lower() != expected.lower():
                    mismatches.append(f"col{idx}: expected '{expected}', got '{actual}'")
            if mismatches:
                import sys
                print(
                    f"WARNING parse_pdfplumber_idd_rows: Computershare IDD column layout "
                    f"mismatch — fixed indices may be wrong. Differences: "
                    + "; ".join(mismatches),
                    file=sys.stderr,
                )
            continue

        if col0 and not col1:
            col0_up = col0.upper()
            if (
                not col0_up.startswith("SUB TOTALS")
                and not _number_re.match(col0)
                and not _cusip_re.match(col0_up)
                and not _issuer_re.match(col0_up)
                and "totals" not in col0.lower()
            ):
                current_class = col0
                continue

        if col1.lower().startswith("sub totals"):
            continue

        # Pre-scan col0 for additional CUSIPs before "Sub Totals:" — same class
        if col0 and current_class:
            before_st = col0.split("Sub Totals")[0] if "Sub Totals" in col0 else col0
            for token in before_st.split():
                t_up = token.upper()
                if (_cusip_re.match(t_up) or _issuer_re.match(t_up)) and t_up not in pre_assigned:
                    pre_assigned[t_up] = current_class

        if col1 and current_class is not None:
            col1_up = col1.upper()
            if _cusip_re.match(col1_up) or _issuer_re.match(col1_up):
                ec = pre_assigned.get(col1_up, current_class)
                rows.append({
                    "cusip": col1_up,
                    "economic_class": ec,
                    "beginning_balance": cells[2] if len(cells) > 2 else "",
                    "coupon_rate": cells[3] if len(cells) > 3 else "",
                    "interest_distribution": cells[7] if len(cells) > 7 else "",
                })

        if col0 and "Sub Totals" in col0 and current_class:
            tail = re.split(r"Sub Totals:?\s*[\d,. ]+", col0, maxsplit=1)
            if len(tail) > 1:
                candidate = tail[-1].strip()
                if (
                    candidate
                    and not _number_re.match(candidate)
                    and not _cusip_re.match(candidate.upper())
                    and not _issuer_re.match(candidate.upper())
                    and "totals" not in candidate.lower()
                ):
                    current_class = candidate

    return rows


def _pypdf_page_texts(pdf_path: Path) -> list[str]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    texts: list[str] = []
    for i in range(len(reader.pages)):
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception:
            t = ""
        texts.append(t)
    return texts


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Regenerate structured pdfplumber Markdown under _chunks_structured/ for an "
            "already-segmented output folder: pdd_idd_pdfplumber.md (PDD/IDD) and "
            "payment_date_report_pdfplumber.md (Payment Date Report fingerprints). "
            "Reads Source PDF from _manifest.md unless pdf_path is passed."
        )
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Deal output directory (contains _manifest.md or sibling PDF)",
    )
    parser.add_argument(
        "pdf_path",
        type=Path,
        nargs="?",
        default=None,
        help="Optional PDF path; default: parse from _manifest.md Source PDF line",
    )
    args = parser.parse_args()
    out = args.output_dir.resolve()
    pdf: Path | None = args.pdf_path
    if pdf is not None:
        pdf = pdf.resolve()
    else:
        man = out / "_manifest.md"
        if not man.is_file():
            print(f"ERROR: {man} missing and no pdf_path argument.", file=sys.stderr)
            raise SystemExit(2)
        text = man.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            s = line.strip()
            if s.lower().startswith("- **source pdf:**"):
                rest = s.split(":", 1)[-1].strip().strip("`").strip()
                if rest:
                    pdf = Path(rest)
                break
    if pdf is None or not pdf.is_file():
        print("ERROR: could not resolve PDF path.", file=sys.stderr)
        raise SystemExit(2)

    page_texts = _pypdf_page_texts(pdf)
    paths: list[Path] = []
    p1 = write_structured_pdd_idd_markdown(pdf, out, page_texts)
    if p1 is not None:
        paths.append(p1)
    p2 = write_structured_payment_date_report_markdown(pdf, out, page_texts)
    if p2 is not None:
        paths.append(p2)
    if not paths:
        print(
            "No structured file written (install pdfplumber, or no matching pages / no tables).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    for p in paths:
        print(f"Wrote {p}")


if __name__ == "__main__":
    main()
