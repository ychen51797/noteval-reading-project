"""
validate_noteval.py — Lightweight checks on noteval_extractor markdown outputs.

Rules (initial):
  1. FAIL if there is no tranche/class data (no populated class rows in 02).
  2. WARN if **all** tranches (class rows) have **Interest payment**, **Interest
     payable**, and **Dividend** each zero or blank — i.e. no row has a nonzero in
     payment **or** payable **or** dividend (possible extraction gap). Subordinated
     notes often use **Dividend**; payable-only layouts use **Interest payable**.
  2b. WARN when **Interest Distribution Detail** shows **Interest Distribution** cash
     for a class (especially **SUB** / **0% coupon**) but **primary** **Interest payment**
     is **0.00** — use the class **Sub Totals / footer** row, not the period-balance line.
  4. WARN if **all** tranches have **Original balance**, **Beginning balance**, and
     **Ending balance** each zero or blank (possible extraction gap). Deals with
     only **subordinated notes** left and seniors at zero are **normal** — such a
     deal passes as long as the sub row has a nonzero balance in any of those columns.
  5. WARN if **Ending balance** ≠ **Beginning balance** + **Deferred interest**
     − **Principal payment** (within tolerance) on class rows where **Principal
     payable** is blank/zero (rows with nonzero **Principal payable** are skipped
     — voucher-style layouts).
  5b. WARN if **Principal payment** matches **Beginning** / **Ending** balance while
     those balances are **unchanged** (flat pool) — typical **PDD** column mis-map
     (notional / balance treated as period **paid** principal); or if **Principal
     payment** looks like a **distribution factor** (~1000) with large flat balances.
  5c. WARN on **`### Distribution grid`** when **Principal paid** sums to ~sum of
     **current principal** (balance column mis-map), or **Principal paid** equals
     **Interest paid** on a row (IDD interest copied into principal-paid column).
  5d. WARN when **Distribution in US$** / **`### Distribution grid`** is present and
     primary **Beginning balance** ≠ **Prior principal balance** or **Ending balance**
     ≠ **Current principal balance** (prior → beginning, current → ending on the **$** table).
  6b. WARN if **03** **Amount paid** equals **Amount available / running** on a row (often
     **Available** copied into **Amount paid** — map **Paid**/**Payment** by header).
  6c. WARN if **03** **`### Column mapping`** maps **Available**/**Running** → **Amount paid**.
  6d. WARN if **02** **primary** rows show non-zero **Original balance** but **Beginning**, **Ending**,
     **Interest payment**, and **Interest rate** all **0.00** while Source Text includes
     **Distribution in US$** (typical “Original-only” LLM gap — re-map full US$ row + Coupon page).
  6e. WARN if **02** **primary** **Class** uses program-slice labels (**A-R-144A**, **SUB-REGS**, …) instead
     of rolling up to economic class (**A-R**, **SUB**, …) with slices in **`### Tranche by listing`** only.
  6. WARN if any **parsed money-style** cell in **02** (class balance primary) or
     **03** (main waterfall table) is **strictly negative**
     (after stripping $ , %). Legitimate negatives are rare (e.g. some adjustments);
     negatives usually signal wrong column, OCR, or sign error — review flagged cells.
  7. WARN if **`### Distribution grid`** has populated **Interest rate** cells but
     **every** primary class row has **Interest rate** blank — usually means dual-exhibit
     merge omitted the rate in **`### Class balance table (primary)`** (see File 02
     **Dual exhibits**).
  9. WARN when **`03`** has fee-like waterfall rows but **`05_valuation_relevant_fees.md`** is missing
     or has no non-zero **Amount paid** rows (run **`map_valuation_fees.py`**).
  (Legacy **`03` ### Valuation-relevant fees** table checks removed; fee literals not validated here.)
  8. WARN (gated) when **`02` Interest payment** is **0.00** / blank but **`03`** waterfall/ladder
     **class / noteholder** **Amount paid** sums tie to **`02` Interest payable** — suggests reviewing
     **02** Distribution Summary / Total Payable rules; **never** auto-writes **`02`** from **`03`**.
  8b. WARN (compare-only) when **`02` Interest payment** is **already populated** but differs from
     **`03`** class-cash sum — **`02`** stays authoritative.

Usage:
    python validate_noteval.py <extraction_dir>
    python validate_noteval.py <extraction_dir> --strict   # exit 1 on warnings too
    python validate_noteval.py <extraction_dir> --verbose  # include passing INFO rows in report

By default, **validation_report.md** omits passing **INFO** checks (warnings/errors always shown).
Use **--verbose** for the full Results table including roll-forward OK lines, negative-amount OK, etc.

Writes **validation_report.md** into ``<extraction_dir>`` with: **At a glance** (compact
index of warnings/errors), **Results** table (**Detail** cells truncated for width),
then **Full detail** (one heading per failed check with the complete message).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_FILES = (
    "01_report_metadata.md",
    "02_tranche_class_balances.md",
    "04_extraction_summary.md",
)

# Max bullets in consolidated **02 class coverage vs Source Text** WARN (item 3).
_CLASS_COVERAGE_MAX_WARNINGS = 4

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_PAGE_RE = re.compile(
    r"\*\*Page\s+(\d+)\*\*|---\s*Page\s+(\d+)\s+of\s+\d+\s*---",
    re.I,
)


def _import_noteval_chunk_select():
    try:
        import noteval_chunk_select as cs

        return cs
    except ImportError:
        root = str(_REPO_ROOT)
        if root not in sys.path:
            sys.path.insert(0, root)
        import noteval_chunk_select as cs

        return cs


def collect_03_waterfall_source_page_warnings(out_dir: Path, text03: str) -> list[str]:
    """WARN when ``## Source Text`` omits pages in the index-mandatory waterfall span."""
    cs = _import_noteval_chunk_select()
    mandatory = cs.resolve_03_mandatory_waterfall_pages(out_dir)
    if len(mandatory) < 2:
        return []
    m = re.search(r"^##\s+Source Text\s*$", text03, re.M | re.I)
    if not m:
        return []
    src = text03[m.end() :]
    cited: set[int] = set()
    for hit in _SOURCE_PAGE_RE.finditer(src):
        for g in hit.groups():
            if g:
                cited.add(int(g))
    missing = [p for p in mandatory if p not in cited]
    if not missing:
        return []
    return [
        f"Mandatory waterfall pages {mandatory} — Source Text missing page(s) {missing} "
        f"(cited: {sorted(cited) or 'none'}). Re-read the full interest + principal ladder."
    ]


def parse_md_tables(text: str) -> list[list[list[str]]]:
    """Parse markdown pipe tables; returns list of tables (each: header + body rows)."""
    tables: list[list[list[str]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines):
            sep_line = lines[i + 1].strip()
            if re.match(r"^\|[\s\-:|]+\|$", sep_line):
                table: list[list[str]] = []
                header = [c.strip() for c in line.split("|")[1:-1]]
                table.append(header)
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith("|"):
                    row = [c.strip() for c in lines[j].strip().split("|")[1:-1]]
                    table.append(row)
                    j += 1
                tables.append(table)
                i = j
                continue
        i += 1
    return tables


def parse_number(s: str) -> float | None:
    if not s or s.upper() == "N/A":
        return None
    cleaned = s.replace("$", "").replace(",", "").replace("%", "").strip()
    if cleaned in ("", "—", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _header_join(row: list[str]) -> str:
    return " | ".join(h.lower() for h in row)


def find_class_balance_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    """Table whose header includes Class + Beginning balance + interest payment or payable."""
    for table in tables:
        if not table or len(table[0]) < 3:
            continue
        h = _header_join(table[0])
        if "class" not in h or "beginning balance" not in h:
            continue
        if "interest payment" in h or "interest payable" in h:
            return table
    return None


def find_distribution_grid_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    """Optional File 02 Distribution grid (prior/current principal + Interest rate)."""
    for table in tables:
        if not table or len(table[0]) < 5:
            continue
        h = _header_join(table[0])
        if "prior principal" in h and "current principal" in h and "interest rate" in h:
            return table
    return None


_INTEREST_TYPE_LABEL_ONLY = re.compile(
    r"^(floating|variable|fixed|float|var|fixed\s+rate|floating\s+rate|variable\s+rate)$",
    re.I,
)


def interest_rate_looks_like_type_label(s: str) -> bool:
    """True when the cell is only an interest-type classification (not a numeric accrual)."""
    t = (s or "").strip()
    if not t or t.upper() == "N/A":
        return False
    if _INTEREST_TYPE_LABEL_ONLY.match(t):
        return True
    if re.search(r"\b(floating|variable|fixed)\b", t, re.I) and not re.search(r"\d", t):
        return True
    return False


def _unpaid_amount_from_other_column(cell: str) -> float | None:
    """Parse trailing Unpaid from ``Other amount columns`` (e.g. ``Unpaid 971.04``)."""
    t = (cell or "").strip()
    if not t:
        return None
    m = re.search(r"unpaid\s+([\d,]+\.?\d*)", t, re.I)
    if m:
        return parse_number(m.group(1))
    return None


_TEMPLATE_PLACEHOLDER_CUSIPS = frozenset(
    {"12345abc7", "12345abd5", "12345abe3"},
)

_SOURCE_TEXT_SECTION = re.compile(r"^##\s+Source Text\s*$", re.I | re.M)
_EXTRACTED_DATA_SECTION = re.compile(r"^##\s+Extracted Data\s*$", re.I | re.M)
_COMPLETENESS_CHECKLIST_SECTION = re.compile(
    r"^##\s+Completeness Checklist\s*$", re.I | re.M
)


def _split_02_source_text(text02: str) -> tuple[str, str]:
    """Return (extracted body, source text) from a File 02 markdown document."""
    parts = _SOURCE_TEXT_SECTION.split(text02, maxsplit=1)
    if len(parts) < 2:
        return text02, ""
    return parts[0], parts[1]


def _extracted_data_body(text02: str) -> str:
    """
    ``## Extracted Data`` through the next major ``02`` section (excludes
    **Completeness Checklist** boilerplate that mentions PDD/IDD by name).
    """
    m = _EXTRACTED_DATA_SECTION.search(text02)
    if not m:
        extracted, _ = _split_02_source_text(text02)
        return extracted
    start = m.end()
    end = len(text02)
    for boundary in (_COMPLETENESS_CHECKLIST_SECTION, _SOURCE_TEXT_SECTION):
        b = boundary.search(text02, start)
        if b:
            end = min(end, b.start())
    return text02[start:end]


def collect_02_layout_claim_warnings(text02: str) -> list[str]:
    """Flag when ``02`` claims PDD+IDD or omits seniors vs Source Text / template bleed."""
    msgs: list[str] = []
    extracted, source = _split_02_source_text(text02)
    data_body = _extracted_data_body(text02)
    el = data_body.lower()
    sl = source.lower()

    claims_pdd = "principal distribution detail" in el
    claims_idd = "interest distribution detail" in el
    if claims_pdd and claims_idd:
        if "principal distribution detail" not in sl and "interest distribution detail" not in sl:
            msgs.append(
                "Summary cites **Principal** + **Interest Distribution Detail** but "
                "**Source Text** has neither title — likely template/hallucination; use "
                "**Notes Information** or actual chunk pages from `_page_index.md`."
            )

    if claims_pdd and claims_idd and "notes information" in sl and "principal distribution detail" not in sl:
        msgs.append(
            "**Source Text** is **Notes Information** (consolidated grid) while extracted "
            "tables reference PDD/IDD — set **Table name(s)** to **Notes Information** and "
            "one row per printed class (A-R, B-R, …, Subordinated Notes)."
        )

    # Template example CUSIPs (scan tables / summary only, not checklist)
    for ph in _TEMPLATE_PLACEHOLDER_CUSIPS:
        if ph in sl.replace("-", "") or ph in el:
            if ph in el:
                msgs.append(
                    f"Placeholder CUSIP **{ph.upper()}** in extracted tables — matches "
                    "`extraction-templates.md` worked example, not the PDF."
                )
                break

    if "class a-r" in sl or "senior secured" in sl or "class b-r" in sl:
        primary_only_sub = bool(
            re.search(
                r"\|\s*SUB\s*\|",
                extracted,
                re.I,
            )
        ) and not re.search(
            r"\|\s*Class\s+[A-E]",
            extracted,
            re.I,
        )
        if primary_only_sub:
            msgs.append(
                "**Source Text** includes senior classes (e.g. Class A-R) but "
                "**Class balance table (primary)** only lists **SUB** — extract every "
                "printed class from the trustee grid."
            )

    if re.search(r"reinvesting\s+holder", sl, re.I) and not re.search(
        r"reinvesting\s+holder", extracted, re.I
    ):
        msgs.append(
            "**Source Text** includes **Reinvesting Holder** but "
            "**Class balance table (primary)** has no matching row — add a primary row "
            "for each printed tranche label."
        )

    msgs.extend(collect_prefix_sibling_class_warnings(text02))
    msgs.extend(collect_refinance_twice_alias_warnings(text02))

    return msgs


def _dedupe_warning_msgs(msgs: list[str], max_msgs: int) -> list[str]:
    """Drop near-duplicate bullets; cap count."""
    seen: set[str] = set()
    out: list[str] = []
    for m in msgs:
        key = re.sub(r"\s+", " ", (m or "").lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(m.strip())
        if len(out) >= max_msgs:
            break
    return out


def collect_02_class_coverage_warnings(
    text02: str,
    data_rows: list[list[str]],
    header: list[str],
    *,
    chunk_text: str = "",
    max_msgs: int = _CLASS_COVERAGE_MAX_WARNINGS,
) -> list[str]:
    """
    One WARN family for **02** class/table coverage vs **Source Text** (layout, missing
    classes, prefix-sibling / refinance aliases, amount tied to wrong class).
    """
    parts: list[str] = []
    parts.extend(collect_02_layout_claim_warnings(text02))
    parts.extend(collect_missing_primary_class_warnings(text02, data_rows))
    parts.extend(collect_idd_footer_stack_missing_class_warnings(text02, data_rows, chunk_text=chunk_text))
    parts.extend(collect_primary_amount_source_class_warnings(text02, data_rows, header))
    parts.extend(
        collect_idd_footer_stack_primary_warnings(
            text02, data_rows, header, chunk_text=chunk_text
        )
    )
    return _dedupe_warning_msgs(parts, max_msgs)


def _source_has_numeric_coupon_reference(text02: str) -> bool:
    """True when Source Text shows a numeric coupon / rate the model could map to **Interest rate**."""
    body = _source_text_body(text02)
    if not body:
        return False
    if re.search(
        r"\b(coupon|current\s+coupon|interest\s+rate|spread|sofr|libor|euribor)\b",
        body,
        re.I,
    ) and re.search(r"\d+\.?\d*\s*%|\d+\.\d{2,}", body):
        return True
    if re.search(r"\b\d+\.\d{4,8}\s*%", body):
        return True
    return False


def collect_interest_rate_type_label_warnings(
    text02: str,
    data_rows: list[list[str]],
    header: list[str],
) -> list[str]:
    """
    WARN only when Source Text has numeric coupon/rate language but **Interest rate** holds
    a type label (**Floating** / **Fixed**) with no digits.
    """
    if not _source_has_numeric_coupon_reference(text02):
        return []
    ir_i = column_index_exact(header, "Interest rate")
    if ir_i is None:
        return []
    type_label_rows: list[str] = []
    for r in data_rows:
        if ir_i >= len(r):
            continue
        cell = (r[ir_i] or "").strip()
        if interest_rate_looks_like_type_label(cell):
            cls = (r[0] if r else "").strip() or "?"
            type_label_rows.append(f"{cls}={cell!r}")
    if not type_label_rows:
        return []
    sample = ", ".join(type_label_rows[:6])
    if len(type_label_rows) > 6:
        sample += f", … (+{len(type_label_rows) - 6})"
    return [
        "**Interest rate** should be a **numeric accrual** when **Source Text** shows coupon / "
        f"% / spread with digits — not type-only **Floating** / **Fixed**. Rows: {sample}."
    ]


def collect_due_paid_swap_warnings(
    wf: list[list[str]],
    *,
    max_msgs: int = 8,
) -> list[str]:
    """
    Flag rows where Amount paid equals Amount payable but Unpaid remains — often
    means Due was copied into Amount paid (Schedule G Due|Paid|Running|Unpaid).
    """
    if not wf or len(wf) < 2:
        return []
    paid_i = column_index_exact(wf[0], "Amount paid")
    payable_i = column_index_exact(wf[0], "Amount payable")
    other_i = column_index_exact(wf[0], "Other amount columns")
    if paid_i is None or payable_i is None:
        return []
    msgs: list[str] = []
    for r in waterfall_data_rows(wf):
        if paid_i >= len(r) or payable_i >= len(r):
            continue
        paid = parse_number(r[paid_i])
        payable = parse_number(r[payable_i])
        if paid is None or payable is None or paid <= 0:
            continue
        if abs(paid - payable) > 0.01:
            continue
        unpaid_amt = None
        if other_i is not None and other_i < len(r):
            unpaid_amt = _unpaid_amount_from_other_column(r[other_i])
        if unpaid_amt is None or unpaid_amt <= 0.01:
            continue
        desc = row_description(wf, r)[:60]
        msgs.append(f"{desc!r}: paid=payable={paid:,.2f} but Unpaid={unpaid_amt:,.2f}")
        if len(msgs) >= max_msgs:
            break
    return msgs


def interest_rate_cell_nonempty(s: str) -> bool:
    """True if Interest rate cell looks populated (coupon / % / spread text with digits)."""
    t = (s or "").strip()
    if not t or t.upper() == "N/A":
        return False
    if t in ("—", "-", "–"):
        return False
    if interest_rate_looks_like_type_label(t):
        return False
    return bool(re.search(r"[\d%.]", t))


def find_waterfall_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if "priority" in h and "item" in h and "payee" in h:
            return table
        if "item" in h and "payee" in h and "amount paid" in h:
            return table
    return None


def find_disbursement_ladder(tables: list[list[list[str]]]) -> list[list[str]] | None:
    """Section 11.1 / clause-only proceeds ladder (no multi-column grid)."""
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if ("clause" in h or "step" in h) and "amount" in h and "item" in h:
            return table
    return None


def is_total_row(class_cell: str) -> bool:
    t = class_cell.lower()
    return any(
        k in t
        for k in (
            "total",
            "aggregate",
            "subtotal",
            "sum",
            "combined",
            "all classes",
        )
    )


def class_balance_data_rows(table: list[list[str]]) -> list[list[str]]:
    """Body rows that look like class lines (skip empty and obvious totals)."""
    if len(table) < 2:
        return []
    out: list[list[str]] = []
    for row in table[1:]:
        if not row:
            continue
        cls = row[0].strip() if row else ""
        if not cls:
            continue
        if is_total_row(cls):
            continue
        out.append(row)
    return out


def column_index_interest_payment(header: list[str]) -> int | None:
    for i, h in enumerate(header):
        hl = h.lower()
        if "interest" in hl and "payment" in hl:
            return i
    return None


def column_index_exact(header: list[str], name: str) -> int | None:
    nl = name.lower()
    for i, h in enumerate(header):
        if h.strip().lower() == nl:
            return i
    return None


def column_index_amount_available_running(header: list[str]) -> int | None:
    """``Amount available / running`` or header containing both available and running."""
    for i, h in enumerate(header):
        hl = h.strip().lower()
        if "amount available" in hl:
            return i
        if "available" in hl and "running" in hl:
            return i
    return None


def collect_paid_equals_available_warnings(
    wf: list[list[str]],
    *,
    max_msgs: int = 6,
) -> list[str]:
    """Flag rows where Amount paid equals Amount available / running (non-zero)."""
    if not wf or len(wf) < 2:
        return []
    paid_i = column_index_exact(wf[0], "Amount paid")
    avail_i = column_index_amount_available_running(wf[0])
    if paid_i is None or avail_i is None:
        return []
    msgs: list[str] = []
    for r in waterfall_data_rows(wf):
        if paid_i >= len(r) or avail_i >= len(r):
            continue
        paid = parse_number(r[paid_i])
        avail = parse_number(r[avail_i])
        if paid is None or avail is None or paid <= 0:
            continue
        if abs(paid - avail) > 0.01:
            continue
        desc = row_description(wf, r)[:60]
        msgs.append(
            f"{desc!r}: **Amount paid** = **Amount available / running** = {paid:,.2f} "
            "— check **Paid**/**Payment** column (not **Available**/**Running**)."
        )
        if len(msgs) >= max_msgs:
            break
    return msgs


def collect_03_column_mapping_header_warnings(text03: str) -> list[str]:
    """Warn when ``### Column mapping`` maps Available/Running into Amount paid."""
    msgs: list[str] = []
    parts = re.split(r"(?i)^###\s+Column mapping\s*$", text03, maxsplit=1)
    if len(parts) < 2:
        return msgs
    block = parts[1][:4000].lower()
    if re.search(
        r"(available|running\s+balance|available\s+for\s+disbursements).{0,80}"
        r"(?:→|->|maps?\s+to).{0,40}amount\s+paid",
        block,
        re.I | re.S,
    ):
        msgs.append(
            "**### Column mapping** maps **Available** / **Running** to **Amount paid** — "
            "use **Paid** / **Payment** for **Amount paid**; **Available** → "
            "**Amount available / running**."
        )
    return msgs


def row_has_nonzero_interest_payment_payable_or_dividend(
    row: list[str],
    pay_i: int | None,
    payable_i: int | None,
    dividend_i: int | None,
) -> bool:
    """True if this tranche has a nonzero **Interest payment**, **Interest payable**, or **Dividend**.

    **Dividend:** **DIVIDEND PAYABLE** on **Subordinated Notes** is treated as
    interest-like economics for this sanity check.
    """
    for i in (pay_i, payable_i, dividend_i):
        if i is None or i >= len(row):
            continue
        v = parse_number(row[i])
        if v is not None and abs(v) > 1e-9:
            return True
    return False


def all_tranches_zero_interest_payment_payable_and_dividend(
    data_rows: list[list[str]],
    pay_i: int | None,
    payable_i: int | None,
    dividend_i: int | None,
) -> bool:
    """True if every class row lacks a nonzero in payment, payable, and dividend."""
    if not data_rows:
        return False
    return all(
        not row_has_nonzero_interest_payment_payable_or_dividend(
            row, pay_i, payable_i, dividend_i
        )
        for row in data_rows
    )


def row_has_nonzero_original_beginning_or_ending(
    row: list[str],
    orig_i: int | None,
    beg_i: int | None,
    end_i: int | None,
) -> bool:
    """True if Original, Beginning, or Ending balance parses nonzero for this row."""
    for i in (orig_i, beg_i, end_i):
        if i is None or i >= len(row):
            continue
        v = parse_number(row[i])
        if v is not None and abs(v) > 1e-9:
            return True
    return False


def all_tranches_zero_original_beginning_and_ending(
    data_rows: list[list[str]],
    orig_i: int | None,
    beg_i: int | None,
    end_i: int | None,
) -> bool:
    """True if every class row has no nonzero in original, beginning, or ending balance."""
    if not data_rows:
        return False
    if orig_i is None and beg_i is None and end_i is None:
        return False
    return all(
        not row_has_nonzero_original_beginning_or_ending(row, orig_i, beg_i, end_i)
        for row in data_rows
    )


def _cell_nonzero(row: list[str], col_i: int | None) -> bool:
    if col_i is None or col_i >= len(row):
        return False
    v = parse_number(row[col_i])
    return v is not None and abs(v) > 1e-9


def _source_text_body(text02: str) -> str:
    parts = re.split(
        r"(?im)^##\s+Source Text\s*$",
        text02,
        maxsplit=1,
    )
    return parts[1] if len(parts) >= 2 else ""


# Footer / block labels quoted without digits (Computershare PDD/IDD — e.g. ``> D-R``).
_STANDALONE_CLASS_SKIP = frozenset(
    {
        "NOTE",
        "CLASS",
        "TOTALS",
        "IDENTIFIER",
        "CUSIP",
        "ENDING",
        "BALANCE",
        "ORIGINAL",
        "FACE",
        "PERIOD",
        "COUPON",
        "RATE",
        "RECORD",
        "PAYMENT",
        "PAGE",
    }
)
# Line-tail tokens that are CUSIP bodies, not Note Class names (Computershare PDD/IDD).
_CUSIP_TAIL_TOKEN = re.compile(r"^[A-Z0-9]{4,9}$")
_STANDALONE_CLASS_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*$")
_PROGRAM_SLICE_SUFFIX = re.compile(r"-(?:144A|REGS|AI)$", re.I)
# Trustee variants for “refinanced twice” (same generation — do not merge into base class).
_REFI_TWICE_EQUIV_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"CRR", "CR2"}),
    frozenset({"C-RR", "C-R2"}),
)


def _class_labels_in_02_source(text02: str) -> set[str]:
    """Rough set of trustee class tokens at end of numeric lines in ## Source Text."""
    body = _source_text_body(text02)
    if not body:
        return set()
    labels: set[str] = set()
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("```") or s.startswith("**Page"):
            continue
        # Common NVR / Distribution in US$ tail: ... 0.00II-SUB-144A
        m = re.search(
            r"([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*(?:-144A|-REGS|-AI)?)\s*$",
            s,
        )
        if not m or not any(ch.isdigit() for ch in s):
            continue
        token = m.group(1)
        tu = token.upper()
        if tu in _STANDALONE_CLASS_SKIP:
            continue
        if _CUSIP_TAIL_TOKEN.fullmatch(tu) and "-" not in tu:
            if tu in ("SUB", "CR", "CRR", "CR2", "D", "DR", "RH", "AI"):
                labels.add(token)
                continue
            if (
                re.search(r"\bcusip\b", s, re.I)
                or re.match(r"^[A-Z0-9]{5,12}\b", s)
                or "0.00000" in s
                or (len(tu) <= 5 and re.search(r"\d{4,}", s))
            ):
                continue
        labels.add(token)
    return labels


def _class_labels_standalone_in_source(text02: str) -> set[str]:
    """
    Computershare-style **Note Class** footers often appear as blockquote-only lines
    (``> D-R``) with no digits on the same line — easy for the model to quote but skip in primary.
    """
    body = _source_text_body(text02)
    if not body:
        return set()
    labels: set[str] = set()
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith(">"):
            continue
        inner = s.lstrip(">").strip()
        if not inner or inner.upper() in _STANDALONE_CLASS_SKIP:
            continue
        if _STANDALONE_CLASS_RE.fullmatch(inner):
            labels.add(inner)
    return labels


def _is_program_slice_label(label: str) -> bool:
    return bool(_PROGRAM_SLICE_SUFFIX.search(label.strip()))


def _prefix_sibling_pairs(labels: set[str]) -> list[tuple[str, str]]:
    """
    Pairs (short, long) where the trustee prints two classes and the shorter
    name is a strict prefix of the longer (e.g. **CR** / **CRR**, **D** / **D-R**).
    Common CLO pattern: **-R** / **-RR** = refinance generation; the longer label
    is usually the latest tranche carrying payment. Skips 144A/REGS/AI program slices.
    """
    clean = sorted(
        {x.strip() for x in labels if x.strip() and not _is_program_slice_label(x)},
        key=len,
    )
    pairs: list[tuple[str, str]] = []
    for i, short in enumerate(clean):
        su = short.upper()
        for long in clean[i + 1 :]:
            if _is_program_slice_label(long):
                continue
            lu = long.upper()
            if lu.startswith(su) and len(lu) > len(su):
                pairs.append((short, long))
    return pairs


def collect_refinance_twice_alias_warnings(text02: str) -> list[str]:
    """
    Some deals print **CR2** instead of **CRR** (both = refinanced twice).
    Warn when Source uses one variant but primary uses another equivalent name.
    """
    src_labels = _class_labels_in_02_source(text02) | _class_labels_standalone_in_source(
        text02
    )
    if not src_labels:
        return []
    extracted, _ = _split_02_source_text(text02)
    tables = parse_md_tables(extracted)
    cb = find_class_balance_table(tables)
    if not cb:
        return []
    primary = {row[0].strip() for row in class_balance_data_rows(cb) if row and row[0].strip()}
    msgs: list[str] = []
    for group in _REFI_TWICE_EQUIV_GROUPS:
        upper_group = {g.upper() for g in group}
        in_src = {x for x in src_labels if x.upper() in upper_group}
        if not in_src:
            continue
        in_pri = {x for x in primary if x.upper() in upper_group}
        for printed in sorted(in_src, key=len):
            if printed in primary:
                continue
            wrong_pri = {p for p in in_pri if p.upper() != printed.upper()}
            if wrong_pri:
                other = sorted(wrong_pri)[0]
                msgs.append(
                    f"**Source Text** prints **{printed}** (twice refinanced; same generation as "
                    f"**CRR** / **-RR**) but primary **Class** is **{other}** — use verbatim "
                    f"**{printed}** on the primary row."
                )
    return msgs[:3]


def collect_prefix_sibling_class_warnings(text02: str) -> list[str]:
    """Warn when Source has both **CR** and **CRR** (etc.) but primary omits the longer class."""
    src_labels = _class_labels_in_02_source(text02) | _class_labels_standalone_in_source(
        text02
    )
    if len(src_labels) < 2:
        return []
    extracted, _ = _split_02_source_text(text02)
    tables = parse_md_tables(extracted)
    cb = find_class_balance_table(tables)
    if not cb:
        return []
    primary = {row[0].strip() for row in class_balance_data_rows(cb) if row and row[0].strip()}
    msgs: list[str] = []
    for short, long in _prefix_sibling_pairs(src_labels):
        if long in primary:
            continue
        if short not in primary:
            continue
        msgs.append(
            f"**Source Text** includes **{long}** and **{short}**; primary has **{short}** "
            f"but not **{long}** — **{long}** amounts (e.g. **Sub Totals** for that section) "
            f"must not be rolled into **{short}** "
            f"(**-R**/**-RR** or **CR2**: longer/latest name carries payment; **CR2** = twice refinanced like **CRR**)."
        )
        if len(msgs) >= 4:
            break
    return msgs


def _amount_tokens(v: float) -> set[str]:
    """Search variants for a parsed dollar amount in Source Text lines."""
    if v is None or abs(v) < 1e-6:
        return set()
    whole = int(round(abs(v)))
    frac = abs(v) - whole
    tokens = {f"{whole:,}", f"{whole:,}.00", f"{whole:.2f}"}
    if frac < 1e-9:
        tokens.add(f"{whole:,}.00")
    return tokens


def _labels_near_source_lines(body: str, line_idx: int, labels: set[str]) -> set[str]:
    lines = body.splitlines()
    found: set[str] = set()
    for j in range(max(0, line_idx - 3), min(len(lines), line_idx + 2)):
        s = lines[j].strip()
        if s.startswith(">"):
            inner = s.lstrip(">").strip()
            if inner in labels:
                found.add(inner)
        for lab in labels:
            if re.search(rf"\b{re.escape(lab)}\b", s, re.I):
                found.add(lab)
    return found


def collect_primary_amount_source_class_warnings(
    text02: str,
    data_rows: list[list[str]],
    header: list[str],
) -> list[str]:
    """
    When a primary balance matches a Source line, warn if that line sits under a
    different **Note Class** (e.g. **58,050,000** under **CRR** but mapped to **CR**).
    """
    body = _source_text_body(text02)
    if not body or not data_rows:
        return []
    src_labels = _class_labels_in_02_source(text02) | _class_labels_standalone_in_source(
        text02
    )
    pairs = _prefix_sibling_pairs(src_labels)
    if not pairs:
        return []
    short_to_long = {s: lg for s, lg in pairs}
    lines = body.splitlines()
    orig_i = column_index_exact(header, "Original balance")
    beg_i = column_index_exact(header, "Beginning balance")
    end_i = column_index_exact(header, "Ending balance")
    msgs: list[str] = []
    for row in data_rows:
        cls = row[0].strip() if row else ""
        long_cls = short_to_long.get(cls)
        if not long_cls:
            continue
        for col_i in (orig_i, beg_i, end_i):
            if col_i is None or col_i >= len(row):
                continue
            val = parse_number(row[col_i])
            if val is None or abs(val) < 1e-6:
                continue
            tokens = _amount_tokens(val)
            if not tokens:
                continue
            for i, line in enumerate(lines):
                if not any(t in line for t in tokens):
                    continue
                near = _labels_near_source_lines(body, i, src_labels)
                if long_cls in near and cls not in near:
                    msgs.append(
                        f"**{cls}** primary uses **{val:,.2f}** but **Source Text** (page excerpt) "
                        f"ties that amount to **{long_cls}**, not **{cls}** — move balances/cash to "
                        f"**{long_cls}** (**-R**/**-RR**: **{long_cls}** is usually the active refinanced line)."
                    )
                    break
            if len(msgs) >= 5:
                return msgs
    return msgs


def _source_line_inner(line: str) -> str:
    return line.strip().lstrip(">").strip()


_IDD_FOOTER_ROW_RE = re.compile(
    r"^([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s+"
    r"([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$"
)


def _idd_cusip_interest_from_zero_coupon_line(s: str) -> float | None:
    """Interest Distribution $ on a **0.00000** coupon CUSIP line (not face / factor)."""
    nums = [parse_number(m.group(0)) for m in re.finditer(r"[\d,]+\.\d{2,8}", s)]
    nums = [n for n in nums if n is not None]
    if len(nums) < 3:
        return None
    face = nums[1] if len(nums) > 1 else None
    for n in nums[2:]:
        if 1_000.0 <= n < 50_000_000.0 and (face is None or abs(n - face) > 1_000.0):
            return n
    return None


def _idd_sum_zero_coupon_before_label_stack(lines: list[str], label_start: int) -> float | None:
    """Sum **Interest Distribution** on **0.00000** CUSIPs immediately above a label stack."""
    total = 0.0
    n = 0
    for j in range(label_start - 1, max(label_start - 40, -1), -1):
        s = _source_line_inner(lines[j])
        if not s or s in ("...",):
            continue
        if "principal distribution" in s.lower() or "interest distribution detail" in s.lower():
            break
        if _STANDALONE_CLASS_RE.fullmatch(s):
            break
        if "0.00000" in s:
            v = _idd_cusip_interest_from_zero_coupon_line(s)
            if v is not None:
                total += v
                n += 1
        elif re.match(r"^[A-Z0-9]{5,12}\b", s):
            break
    return total if n else None


def _idd_footer_interest_amount(row: tuple[float | None, ...]) -> float | None:
    """Second footer column on IDD = interest distribution; skip PDD balance pairs (col1 ≈ col2)."""
    if len(row) < 2:
        return None
    principal, interest = row[0], row[1]
    if interest is None or interest < 1_000.0:
        return None
    if principal is not None and principal >= 1_000_000.0:
        if abs(principal - interest) < 1_000.0:
            return None
        if interest > principal * 0.95:
            return None
    return interest


def _idd_best_footer_stack(
    body: str,
) -> tuple[list[str], list[tuple[float | None, ...]], float | None]:
    """
    Best Computershare IDD **Note Class** label stack + aligned **Sub Totals** footer rows.

    Returns ``(labels, footer_rows, sub_cusip_interest_sum)``; empty labels when not found.
    """
    if "interest distribution detail" not in body.lower():
        return [], [], None
    lines = body.splitlines()
    idd_starts = [
        i
        for i, line in enumerate(lines)
        if "interest distribution detail" in line.lower()
    ]
    if not idd_starts:
        return [], [], None

    best_labels: list[str] = []
    best_start = -1
    best_score = -1

    for idd_start in idd_starts:
        i = idd_start
        while i < min(idd_start + 120, len(lines)):
            inner = _source_line_inner(lines[i])
            if not _STANDALONE_CLASS_RE.fullmatch(inner or ""):
                i += 1
                continue
            labels: list[str] = []
            j = i
            while j < len(lines):
                lab = _source_line_inner(lines[j])
                if not lab or lab.startswith("**") or lab.startswith("("):
                    break
                if _STANDALONE_CLASS_RE.fullmatch(lab):
                    labels.append(lab)
                    j += 1
                else:
                    break
            if len(labels) < 3:
                i = j if j > i else i + 1
                continue
            footers: list[tuple[float | None, ...]] = []
            k = j
            while k < len(lines) and len(footers) < len(labels) + 2:
                s = _source_line_inner(lines[k])
                m = _IDD_FOOTER_ROW_RE.match(s)
                if m:
                    footers.append(
                        tuple(parse_number(m.group(g)) for g in range(1, 6))
                    )
                    k += 1
                elif not s or s == "...":
                    k += 1
                else:
                    break
            if len(footers) < min(3, len(labels)):
                i = j if j > i else i + 1
                continue
            score = sum(1 for f in footers if _idd_footer_interest_amount(f))
            sub_cusip = _idd_sum_zero_coupon_before_label_stack(lines, i)
            if "SUB" in {x.upper() for x in labels} and sub_cusip and sub_cusip >= 1_000.0:
                score += 3
            if score > best_score:
                best_score = score
                best_labels = labels
                best_start = i
            i = j if j > i else i + 1
    if len(best_labels) < 3 or best_start < 0:
        return [], [], None

    footers: list[tuple[float | None, ...]] = []
    k = best_start + len(best_labels)
    while k < len(lines) and len(footers) < len(best_labels) + 2:
        s = _source_line_inner(lines[k])
        m = _IDD_FOOTER_ROW_RE.match(s)
        if m:
            footers.append(tuple(parse_number(m.group(g)) for g in range(1, 6)))
            k += 1
        elif not s or s == "...":
            k += 1
        else:
            break

    sub_cusip_sum = _idd_sum_zero_coupon_before_label_stack(lines, best_start)
    return best_labels, footers, sub_cusip_sum


def _idd_label_footer_interest_map(body: str) -> dict[str, float]:
    """
    Computershare IDD often stacks **Note Class** labels then aligned **Sub Totals** rows.

    Prefer the stack on **Interest Distribution Detail** (not Principal Distribution Detail).
    Footer columns: principal | interest distribution | … — use the **second** field when it is
    not a duplicate balance. When that field is **0.00** for **SUB**, sum **0.00000** coupon CUSIPs
    above the stack.
    """
    labels, footers, sub_cusip_sum = _idd_best_footer_stack(body)
    if not labels:
        return {}
    out: dict[str, float] = {}
    for idx, lab in enumerate(labels):
        if idx >= len(footers):
            break
        interest = _idd_footer_interest_amount(footers[idx])
        if interest is not None:
            out[lab.upper()] = interest
        elif (
            lab.upper() == "SUB"
            and sub_cusip_sum is not None
            and sub_cusip_sum >= 1_000.0
        ):
            out["SUB"] = sub_cusip_sum
    return out


def _idd_label_footer_primary_map(body: str) -> dict[str, tuple[float | None, float | None]]:
    """Map **Note Class** footer label → (Sub Totals principal, interest distribution)."""
    labels, footers, sub_cusip_sum = _idd_best_footer_stack(body)
    if not labels:
        return {}
    out: dict[str, tuple[float | None, float | None]] = {}
    for idx, lab in enumerate(labels):
        if idx >= len(footers):
            break
        row = footers[idx]
        principal = row[0] if row else None
        interest = _idd_footer_interest_amount(row)
        if lab.upper() == "SUB" and (interest is None or interest < 1_000.0):
            if sub_cusip_sum is not None and sub_cusip_sum >= 1_000.0:
                interest = sub_cusip_sum
        if principal is not None or interest is not None:
            out[lab.upper()] = (principal, interest)
    return out


def _load_idd_chunk_text(out_dir: Path) -> str:
    """Concat chunk files that contain **Interest Distribution Detail** (for footer-stack checks)."""
    chunks_dir = out_dir / "_chunks"
    if not chunks_dir.is_dir():
        return ""
    parts: list[str] = []
    for p in sorted(chunks_dir.glob("pages_*.txt")):
        try:
            t = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "interest distribution detail" in t.lower():
            parts.append(t)
    return "\n".join(parts)


def collect_idd_footer_stack_missing_class_warnings(
    text02: str,
    data_rows: list[list[str]],
    *,
    chunk_text: str = "",
) -> list[str]:
    """Warn when IDD **Note Class** footer stack lists a class absent from primary."""
    body = chunk_text.strip() or _source_text_body(text02)
    labels, _, _ = _idd_best_footer_stack(body)
    if len(labels) < 3:
        return []
    primary = {row[0].strip() for row in data_rows if row and row[0].strip()}
    missing = sorted(lab for lab in labels if lab not in primary)
    if not missing:
        return []
    sample = ", ".join(missing[:10])
    if len(missing) > 10:
        sample += f", … (+{len(missing) - 10})"
    return [
        f"IDD **Note Class** footer stack includes **{sample}** but **02** primary has no "
        f"matching row — add each printed class (paid-down → **0.00** from page 8); map "
        f"**nth** label → **nth** Sub Totals block (**extraction-templates.md** "
        f"**Computershare IDD — Note Class footer stack**)."
    ]


def collect_idd_footer_stack_primary_warnings(
    text02: str,
    data_rows: list[list[str]],
    header: list[str],
    *,
    chunk_text: str = "",
    max_msgs: int = 6,
) -> list[str]:
    """
    Cross-check Computershare IDD **Note Class** footer stack vs **02** primary.

    High-confidence cases only: footer economics for class **O** appear on a different
    primary row (e.g. **C2-R3** holding **C1-R3**'s 22M / 329,107.67), or **O** is
    missing from primary while another row carries **O**'s Sub Totals **$**.
    """
    body = chunk_text.strip() or _source_text_body(text02)
    if not body or "interest distribution detail" not in body.lower():
        return []
    fmap = _idd_label_footer_primary_map(body)
    if not fmap:
        return []

    beg_i = column_index_exact(header, "Beginning balance")
    int_pay_i = column_index_interest_payment(header)
    primary: dict[str, list[str]] = {}
    for row in data_rows:
        if not row or not row[0].strip():
            continue
        primary[row[0].strip().upper()] = row

    msgs: list[str] = []

    def _tol(a: float, b: float) -> float:
        return max(0.02, 1e-6 * max(abs(a), abs(b), 1.0))

    def _row_beg_pay(row: list[str]) -> tuple[float | None, float | None]:
        beg = (
            parse_number(row[beg_i])
            if beg_i is not None and beg_i < len(row)
            else None
        )
        pay = (
            parse_number(row[int_pay_i])
            if int_pay_i is not None and int_pay_i < len(row)
            else None
        )
        return beg, pay

    def _matches_footer(
        beg: float | None, pay: float | None, prin: float | None, fi: float | None
    ) -> bool:
        if fi is None or fi < 1_000.0:
            return False
        if pay is None or abs(pay - fi) > _tol(pay, fi):
            return False
        if prin is not None and prin >= 1_000_000.0:
            if beg is None or abs(beg - prin) > _tol(beg, prin):
                return False
        return True

    for owner_u, (prin, fi) in fmap.items():
        if fi is None or fi < 1_000.0:
            continue
        if owner_u in primary:
            continue
        for cls_u, row in primary.items():
            if cls_u == owner_u:
                continue
            beg, pay = _row_beg_pay(row)
            if not _matches_footer(beg, pay, prin, fi):
                continue
            prin_s = f"{prin:,.2f}" if prin is not None else "N/A"
            msgs.append(
                f"**{cls_u}** carries IDD footer economics for **{owner_u}** "
                f"(Sub Totals **{prin_s}**, interest **{fi:,.2f}**) — add **{owner_u}** "
                f"to primary and map **Note Class** footer stack **by position** "
                f"(ignore pdfplumber/CUSIP tail labels)."
            )
            break
        if len(msgs) >= max_msgs:
            break
    return msgs


def _idd_block_after_label(
    lines: list[str], start: int, cls_u: str
) -> float | None:
    """Parse interest $ in the window after one standalone **Note Class** line."""
    cusip_parts: list[float] = []
    footer_val: float | None = None
    for j in range(start + 1, min(start + 40, len(lines))):
        s = _source_line_inner(lines[j])
        if not s:
            continue
        if _STANDALONE_CLASS_RE.fullmatch(s) and s.upper() != cls_u:
            break
        m2 = re.match(r"^([\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$", s)
        if m2:
            v1 = parse_number(m2.group(1))
            if v1 is not None and v1 >= 100.0:
                footer_val = v1
            continue
        fm = _IDD_FOOTER_ROW_RE.match(s)
        if fm:
            v_int = parse_number(fm.group(2))
            if v_int is not None and v_int >= 1_000.0:
                footer_val = v_int
            continue
        if "0.00000" in s:
            v = _idd_cusip_interest_from_zero_coupon_line(s)
            if v is not None:
                cusip_parts.append(v)
    if footer_val is not None:
        return footer_val
    if cusip_parts:
        return sum(cusip_parts)
    return None


def _idd_interest_distribution_for_class(body: str, class_name: str) -> float | None:
    """
    Estimate period **Interest Distribution** $ for a **Note Class** on Computershare IDD.

    Uses the stacked label/footer block (common on page 3+), every standalone label
    occurrence, and **0.00000** CUSIP sums for **SUB** when the footer interest column is **0.00**.
    """
    cls_u = class_name.strip().upper()
    estimates: list[float] = []

    for lab, val in _idd_label_footer_interest_map(body).items():
        if lab == cls_u:
            estimates.append(val)

    lines = body.splitlines()
    for i, line in enumerate(lines):
        if _source_line_inner(line).upper() != cls_u:
            continue
        block = _idd_block_after_label(lines, i, cls_u)
        if block is not None:
            estimates.append(block)

    for i, line in enumerate(lines):
        inner = _source_line_inner(line)
        if cls_u not in inner.upper() or "sub total" not in inner.lower():
            continue
        for j in range(i + 1, min(i + 5, len(lines))):
            m2 = re.match(
                r"^([\d,]+\.\d{2})\s+([\d,]+\.\d{2})",
                _source_line_inner(lines[j]),
            )
            if not m2:
                continue
            v1 = parse_number(m2.group(1))
            if v1 is not None and v1 >= 1_000.0:
                estimates.append(v1)
                break

    if not estimates:
        return None
    return max(estimates)


def collect_idd_subtotal_interest_mismatch_warnings(
    text02: str,
    data_rows: list[list[str]],
    header: list[str],
) -> list[str]:
    """Warn when IDD shows Interest Distribution $ but primary Interest payment is zero."""
    body = _source_text_body(text02)
    if not body or "interest distribution detail" not in body.lower():
        return []
    int_pay_i = column_index_interest_payment(header)
    if int_pay_i is None:
        return []
    msgs: list[str] = []
    for row in data_rows:
        if not row:
            continue
        cls = row[0].strip()
        if not cls:
            continue
        pay = (
            parse_number(row[int_pay_i])
            if int_pay_i < len(row)
            else None
        )
        if pay is not None and abs(pay) > 1e-6:
            continue
        est = _idd_interest_distribution_for_class(body, cls)
        if est is None or est < 1_000.0:
            continue
        msgs.append(
            f"**{cls}**: **Interest payment** is **0.00** but **Source Text** (Interest "
            f"Distribution Detail) shows **Interest Distribution** **{est:,.2f}** on the "
            f"class **Sub Totals / footer** or CUSIP lines — map that **$** to **Interest "
            f"payment** (common on **SUB** with **0% coupon**)."
        )
        if len(msgs) >= 6:
            break
    return msgs


def collect_missing_primary_class_warnings(
    text02: str,
    data_rows: list[list[str]],
) -> list[str]:
    """Warn when Source Text lists printed class lines absent from primary."""
    src_labels = _class_labels_in_02_source(text02) | _class_labels_standalone_in_source(
        text02
    )
    if not src_labels:
        return []
    primary = {row[0].strip() for row in data_rows if row and row[0].strip()}
    missing = sorted(l for l in src_labels if l not in primary)
    if not missing:
        return []
    sample = ", ".join(missing[:12])
    if len(missing) > 12:
        sample += f", … (+{len(missing) - 12})"
    return [
        "Source Text lists printed class name(s) missing from **### Class balance table (primary)**: "
        f"{sample}. "
        "On Computershare **Interest / Principal Distribution Detail**, use the **Note Class** on "
        "the **top** row of each section — **CRR** / **CR2** ≠ **CR**, **D-RR** ≠ **D** (**-R**/**-RR** or "
        "**2** = refinance generation). See **extraction-templates.md** **Refinance -R / -RR**."
    ]


def _distribution_grid_class_rows(table: list[list[str]]) -> list[list[str]]:
    """Body rows from optional **### Distribution grid**."""
    if len(table) < 2:
        return []
    out: list[list[str]] = []
    for row in table[1:]:
        if not row or not any(c.strip() for c in row):
            continue
        cls = row[0].strip() if row else ""
        if not cls or is_total_row(cls):
            continue
        out.append(row)
    return out


def collect_distribution_grid_principal_balance_pair_warnings(
    cb_header: list[str],
    data_rows: list[list[str]],
    dg_table: list[list[str]] | None,
    text02: str,
    *,
    max_msgs: int = 10,
) -> list[str]:
    """
    When Distribution in US$ / ### Distribution grid exists, primary balances should
    mirror the trustee prior/current principal pair: **Prior principal balance** →
    **Beginning balance**, **Current principal balance** → **Ending balance**.
    """
    if not dg_table or len(dg_table) < 2:
        return []
    if "distribution in us$" not in text02.casefold() and "distribution grid" not in text02.casefold():
        return []
    beg_i = column_index_exact(cb_header, "Beginning balance")
    end_i = column_index_exact(cb_header, "Ending balance")
    prior_i = column_index_exact(dg_table[0], "Prior principal balance")
    curr_i = column_index_exact(dg_table[0], "Current principal balance")
    if prior_i is None and curr_i is None:
        return []

    prior_by_class: dict[str, float] = {}
    curr_by_class: dict[str, float] = {}
    for row in _distribution_grid_class_rows(dg_table):
        cls = row[0].strip().casefold()
        if not cls:
            continue
        if prior_i is not None and prior_i < len(row):
            p = parse_number(row[prior_i])
            if p is not None:
                prior_by_class[cls] = p
        if curr_i is not None and curr_i < len(row):
            c = parse_number(row[curr_i])
            if c is not None:
                curr_by_class[cls] = c

    if not prior_by_class and not curr_by_class:
        return []

    msgs: list[str] = []
    for row in data_rows:
        cls = row[0].strip() if row else ""
        if not cls:
            continue
        key = cls.casefold()

        if beg_i is not None and prior_i is not None and key in prior_by_class:
            if beg_i < len(row):
                beg = parse_number(row[beg_i])
                prior = prior_by_class[key]
                if beg is not None:
                    tol = max(0.02, 1e-8 * max(abs(beg), abs(prior), 1.0))
                    if abs(beg - prior) > tol:
                        msgs.append(
                            f"{cls}: **Beginning balance** {beg:,.2f} ≠ **Prior principal balance** "
                            f"{prior:,.2f} — use **Prior** → **Beginning** on **Distribution in US$**."
                        )

        if end_i is not None and curr_i is not None and key in curr_by_class:
            if end_i < len(row):
                end = parse_number(row[end_i])
                curr = curr_by_class[key]
                if end is not None:
                    tol = max(0.02, 1e-8 * max(abs(end), abs(curr), 1.0))
                    if abs(end - curr) > tol:
                        msgs.append(
                            f"{cls}: **Ending balance** {end:,.2f} ≠ **Current principal balance** "
                            f"{curr:,.2f} — use **Current** → **Ending** on **Distribution in US$**."
                        )

        if len(msgs) >= max_msgs:
            break
    return msgs


_PROGRAM_SLICE_SUFFIXES = ("144A", "REGS", "REGA", "AI")


def economic_class_from_program_slice_label(name: str) -> str | None:
    """If ``name`` ends with -144A / -REGS / -REGA / -AI, return the economic class prefix."""
    s = name.strip()
    if not s:
        return None
    upper = s.upper()
    for suf in _PROGRAM_SLICE_SUFFIXES:
        for sep in ("-", " "):
            tail = f"{sep}{suf}"
            if upper.endswith(tail) and len(s) > len(tail):
                econ = s[: -len(tail)].rstrip("- ").strip()
                if econ and econ.upper() != upper:
                    return econ
    return None


def collect_primary_program_slice_warnings(
    data_rows: list[list[str]],
    *,
    max_msgs: int = 6,
) -> list[str]:
    """Warn when primary uses slice labels (A-R-144A) instead of economic rollup (A-R)."""
    groups: dict[str, list[str]] = {}
    for row in data_rows:
        cls = row[0].strip() if row else ""
        if not cls:
            continue
        econ = economic_class_from_program_slice_label(cls)
        if econ is None or econ.casefold() == cls.casefold():
            continue
        groups.setdefault(econ, []).append(cls)
    if not groups:
        return []
    msgs: list[str] = []
    for econ in sorted(groups.keys(), key=str.casefold):
        labels = groups[econ]
        labels_s = ", ".join(labels[:4]) + ("…" if len(labels) > 4 else "")
        msgs.append(
            f"Program-slice name(s) in **primary** ({labels_s}) → one row **{econ}** in "
            f"**### Class balance table (primary)**; keep slices in **### Tranche by listing** "
            f"(**A-R-144A** + **A-R-REGS** = same tranche **A-R**)."
        )
        if len(msgs) >= max_msgs:
            break
    return msgs


def collect_primary_original_only_warnings(
    text02: str,
    data_rows: list[list[str]],
    header: list[str],
) -> list[str]:
    """
  Warn when primary rows look like only **Original balance** was mapped (common LLM gap
  on **Distribution in US$** + factor layouts).
    """
    if "distribution in us$" not in text02.casefold():
        return []
    orig_i = column_index_exact(header, "Original balance")
    if orig_i is None:
        return []
    beg_i = column_index_exact(header, "Beginning balance")
    end_i = column_index_exact(header, "Ending balance")
    rate_i = column_index_exact(header, "Interest rate")
    pay_i = column_index_interest_payment(header)
    pbl_i = column_index_exact(header, "Interest payable")

    sparse: list[str] = []
    for row in data_rows:
        if not row or not _cell_nonzero(row, orig_i):
            continue
        if _cell_nonzero(row, beg_i) or _cell_nonzero(row, end_i):
            continue
        if _cell_nonzero(row, pay_i) or _cell_nonzero(row, pbl_i):
            continue
        if _cell_nonzero(row, rate_i):
            continue
        cls = row[0].strip() if row else "?"
        sparse.append(cls)

    if len(sparse) < 2:
        return []
    sample = ", ".join(sparse[:6])
    if len(sparse) > 6:
        sample += "…"
    return [
        f"{len(sparse)} primary row(s) ({sample}) have non-zero **Original balance** but "
        "**Beginning balance**, **Ending balance**, **Interest payment**, and **Interest rate** "
        "are all **0.00** — re-read **Distribution in US$** (full row, not first column only) and "
        "merge **Coupon** / **Interest Detail**; see template *Distribution in US$ — primary authority*."
    ]


# Principal roll-forward: ending ≈ beginning + deferred_interest − principal_payment
PRINCIPAL_ROLLFORWARD_ABS_TOL = 0.02


def _class_names_from_warning_msgs(msgs: list[str]) -> set[str]:
    """Parse leading ``Class:`` from validator detail strings."""
    out: set[str] = set()
    for m in msgs:
        hit = re.match(r"^([^:]+):", m or "")
        if hit:
            out.add(hit.group(1).strip())
    return out


def _filter_msgs_by_class(msgs: list[str], skip: set[str]) -> list[str]:
    if not skip:
        return msgs
    kept: list[str] = []
    for m in msgs:
        hit = re.match(r"^([^:]+):", m or "")
        if hit and hit.group(1).strip() in skip:
            continue
        kept.append(m)
    return kept


def principal_rollforward_row_stats(
    header: list[str],
    data_rows: list[list[str]],
    *,
    skip_classes: frozenset[str] | None = None,
) -> tuple[int, int, list[str]]:
    """How many class rows pass ending ≈ beg + deferred − principal_payment.

    Skips a row when **Principal payable** parses nonzero — common voucher layouts
    where **Ending balance** is not the same roll-forward object as beginning − payment.

    Returns ``(n_checked, n_mismatch, sample_messages)``.
    """
    beg_i = column_index_exact(header, "Beginning balance")
    end_i = column_index_exact(header, "Ending balance")
    prin_i = column_index_exact(header, "Principal payment")
    def_i = column_index_exact(header, "Deferred interest")
    prin_pbl_i = column_index_exact(header, "Principal payable")

    if beg_i is None or end_i is None or prin_i is None:
        return 0, 0, []

    n_checked = 0
    n_mismatch = 0
    msgs: list[str] = []

    skip = skip_classes or frozenset()

    for row in data_rows:
        cls = row[0].strip() if row else "?"
        if cls in skip:
            continue
        if prin_pbl_i is not None and prin_pbl_i < len(row):
            pbl = parse_number(row[prin_pbl_i])
            if pbl is not None and abs(pbl) > PRINCIPAL_ROLLFORWARD_ABS_TOL:
                continue

        if beg_i >= len(row) or end_i >= len(row):
            continue
        beg = parse_number(row[beg_i])
        end = parse_number(row[end_i])
        if beg is None or end is None:
            continue

        prin = parse_number(row[prin_i]) if prin_i < len(row) else None
        if prin is None:
            prin = 0.0

        def_val = 0.0
        if def_i is not None and def_i < len(row):
            d = parse_number(row[def_i])
            if d is not None:
                def_val = d

        expected = beg + def_val - prin
        tol = max(
            PRINCIPAL_ROLLFORWARD_ABS_TOL,
            1e-9 * max(abs(beg), abs(end), abs(expected), 1.0),
        )
        n_checked += 1
        if abs(end - expected) > tol:
            n_mismatch += 1
            if len(msgs) < 5:
                msgs.append(
                    f"{cls}: ending {end:,.2f} vs expected {expected:,.2f} "
                    f"(beg {beg:,.2f} + def {def_val:,.2f} − prin {prin:,.2f}); "
                    f"delta {end - expected:,.2f}"
                )

    return n_checked, n_mismatch, msgs


def _tol_balance_unchanged(beg: float, end: float) -> float:
    return max(
        PRINCIPAL_ROLLFORWARD_ABS_TOL,
        1e-9 * max(abs(beg), abs(end), 1.0),
    )


def _tol_prin_equals_balance(prin: float, bal: float) -> float:
    return max(1.0, 1e-8 * max(abs(bal), abs(prin), 1.0))


def collect_principal_payment_balance_confusion_warnings(
    header: list[str],
    data_rows: list[list[str]],
    max_msgs: int = 8,
) -> list[str]:
    """Flag PDD-style mis-map: period **Principal payment** equals notional while ending ≈ beginning."""
    beg_i = column_index_exact(header, "Beginning balance")
    end_i = column_index_exact(header, "Ending balance")
    prin_i = column_index_exact(header, "Principal payment")
    if beg_i is None or end_i is None or prin_i is None:
        return []
    msgs: list[str] = []
    for row in data_rows:
        if beg_i >= len(row) or end_i >= len(row) or prin_i >= len(row):
            continue
        cls = row[0].strip() if row else "?"
        beg = parse_number(row[beg_i])
        end = parse_number(row[end_i])
        prin = parse_number(row[prin_i])
        if beg is None or end is None or prin is None:
            continue
        if abs(prin) <= PRINCIPAL_ROLLFORWARD_ABS_TOL:
            continue
        tb = _tol_balance_unchanged(beg, end)
        if abs(end - beg) > tb:
            continue
        if abs(prin - beg) <= _tol_prin_equals_balance(prin, beg) or abs(prin - end) <= _tol_prin_equals_balance(
            prin, end
        ):
            msgs.append(
                f"{cls}: **Principal payment** {prin:,.2f} matches beginning/ending while balances are flat "
                "(ending ≈ beginning) — likely **Principal Distribution Detail** **balance / notional** "
                "mapped to **Principal payment**; use the column for **period principal distributed / paid** "
                "(often **0.00**). See **extraction-templates.md** (**PDD balance ≠ principal paid**)."
            )
        elif 100.0 <= abs(prin) <= 5000.0 and max(abs(beg), abs(end)) >= 1e6:
            msgs.append(
                f"{cls}: **Principal payment** {prin:,.6g} looks like a **distribution factor** "
                f"(not dollars) while balances are large and flat — do not map **Principal Distribution Factor** "
                f"into **Principal payment**."
            )
        if len(msgs) >= max_msgs:
            break
    return msgs


def column_index_distribution_principal_paid_only(header: list[str]) -> int | None:
    for i, h in enumerate(header):
        ls = h.strip().lower()
        if ls == "principal paid":
            return i
    for i, h in enumerate(header):
        ls = h.strip().lower()
        if "principal" in ls and "paid" in ls and "payable" not in ls:
            return i
    return None


def column_index_distribution_interest_paid_only(header: list[str]) -> int | None:
    for i, h in enumerate(header):
        ls = h.strip().lower()
        if ls == "interest paid":
            return i
    for i, h in enumerate(header):
        ls = h.strip().lower()
        if "interest" in ls and "paid" in ls and "payable" not in ls:
            return i
    return None


def collect_distribution_grid_principal_paid_warnings(
    dg: list[list[str]],
    max_msgs: int = 10,
) -> list[str]:
    """Heuristic warnings for mis-mapped **Principal paid** in ``### Distribution grid``.

    Context: In **dual PDD + IDD** deals, the grid often merges **prior/current principal**
    (balances) with **Principal paid** (from PDD — often **0.00** when no amortization) and
    **Interest paid** (from IDD). Common mistakes:

    1. **Column swap (interest → principal paid):** For a class, **Principal paid** and
       **Interest paid** parse to the **same** dollar amount. That usually means the
       interest cash column was copied into **Principal paid** instead of taking period
       principal from **PDD** (often **0.00** when balances are flat).

    2. **Balance → principal paid:** **Principal paid** ≈ **Current principal balance**
       while **Prior** ≈ **Current** (no meaningful principal change this period). That
       suggests the **outstanding** column was mistaken for **Principal paid**.

    3. **Aggregate slip:** After scanning rows, if the **sum** of **Principal paid** is
       about equal to the **sum** of **Current principal balance** across classes (large
       pool), the extractor may have been summing **balances** in the markdown cross-check
       or every row’s **Principal paid** is effectively a balance — the warning nudges
       you to align **Sum of principal paid** with true **paid** principal from PDD.

    Returns short markdown-ready strings (``max_msgs`` cap). Uses tolerances scaled to
    the amounts; false positives are possible on exotic layouts — read the flagged row
    against **Source Text**.
    """
    if not dg or len(dg) < 2:
        return []
    header = dg[0]
    prior_i = column_index_exact(header, "Prior principal balance")
    curr_i = column_index_exact(header, "Current principal balance")
    pp_i = column_index_distribution_principal_paid_only(header)
    ip_i = column_index_distribution_interest_paid_only(header)
    if pp_i is None:
        return []
    body = class_balance_data_rows(dg)
    if not body:
        return []
    msgs: list[str] = []
    sum_pp = 0.0
    sum_curr = 0.0
    n_pp = 0
    n_curr = 0
    for row in body:
        cls = row[0].strip() if row else "?"
        pp = parse_number(row[pp_i]) if pp_i < len(row) else None
        ip = parse_number(row[ip_i]) if ip_i is not None and ip_i < len(row) else None
        cur = parse_number(row[curr_i]) if curr_i is not None and curr_i < len(row) else None

        if pp is not None and abs(pp) > PRINCIPAL_ROLLFORWARD_ABS_TOL and ip is not None and abs(ip) > 1e-9:
            tol_eq = max(0.02, 1e-9 * max(abs(pp), abs(ip), 1.0))
            if abs(pp - ip) <= tol_eq:
                msgs.append(
                    f"{cls}: **Principal paid** equals **Interest paid** (~{pp:,.2f}) — likely **IDD** interest "
                    "mapped into **Principal paid**; **Principal paid** should come from **PDD** period principal "
                    "(often **0.00** when balances are flat)."
                )

        if (
            pp is not None
            and cur is not None
            and prior_i is not None
            and prior_i < len(row)
            and abs(pp) > PRINCIPAL_ROLLFORWARD_ABS_TOL
        ):
            tol_pc = max(1.0, 1e-8 * max(abs(pp), abs(cur), 1.0))
            if abs(pp - cur) <= tol_pc:
                pri = parse_number(row[prior_i])
                if pri is not None:
                    tb = _tol_balance_unchanged(pri, cur)
                    if abs(pri - cur) <= tb:
                        msgs.append(
                            f"{cls}: **Principal paid** {pp:,.2f} matches **Current principal balance** while "
                            "prior ≈ current — likely **balance** column mis-mapped as **Principal paid**."
                        )

        if pp is not None and abs(pp) > PRINCIPAL_ROLLFORWARD_ABS_TOL:
            sum_pp += pp
            n_pp += 1
        if cur is not None and abs(cur) > 1e-9:
            sum_curr += cur
            n_curr += 1

        if len(msgs) >= max_msgs:
            break

    if len(msgs) < max_msgs and n_pp > 0 and n_curr > 0 and sum_curr > 1e6:
        tol_sum = max(100.0, 1e-6 * max(sum_pp, sum_curr, 1.0))
        if abs(sum_pp - sum_curr) <= tol_sum:
            msgs.append(
                "Sum of **Principal paid** across grid (~"
                f"{sum_pp:,.2f}) ≈ sum of **Current principal balance** (~{sum_curr:,.2f}) — "
                "likely summing **outstanding** balances instead of **period principal paid**; "
                "fix **`### Cross-checks (distribution grid)`** **Sum of principal paid** to sum **paid** "
                "principal only."
            )

    return msgs[:max_msgs]


_NEG_AMOUNT_HEADER = re.compile(
    r"(balance|payment|payable|paid|dividend|deferred|amount\s+due|"
    r"distribution|admin|trustee|issuer|fee|available|running)\b",
    re.I,
)
_NEG_HEADER_EXCLUDE = re.compile(
    r"(\brate\b|\bcoupon\b|wal|warf|line\s+id|cusip|isin|page|count|priority|"
    r"description|item|payee|type|standard\s+fee)",
    re.I,
)


def _header_is_neg_check_amount_column(h: str) -> bool:
    """True for columns that normally represent currency amounts (not rates/ids)."""
    hl = h.strip()
    if not hl or _NEG_HEADER_EXCLUDE.search(hl):
        return False
    return bool(_NEG_AMOUNT_HEADER.search(hl))


def _waterfall_amount_column_indices(header: list[str]) -> list[int]:
    """Column indices in 03 grid likely to hold currency (skip item/payee/priority)."""
    out: list[int] = []
    for i, h in enumerate(header):
        hl = h.strip().lower()
        if not hl or _NEG_HEADER_EXCLUDE.search(h):
            continue
        if any(
            k in hl
            for k in (
                "paid",
                "payable",
                "available",
                "running",
                "due",
                "amount",
                "distribution",
                "balance",
            )
        ):
            if re.search(r"\brate\b|\bcoupon\b", hl):
                continue
            out.append(i)
    return out


def collect_negative_amount_warnings_02(
    cb: list[list[str]],
    data_rows: list[list[str]],
    max_msgs: int = 12,
) -> list[str]:
    msgs: list[str] = []
    if not cb:
        return msgs
    header = cb[0]
    for ci, h in enumerate(header):
        if not _header_is_neg_check_amount_column(h):
            continue
        for row in data_rows:
            if ci >= len(row):
                continue
            v = parse_number(row[ci])
            if v is not None and v < -1e-6:
                cls = row[0].strip() if row else "?"
                msgs.append(f"02 `{cls}` / **{h.strip()}** → {v:,.6g}")
                if len(msgs) >= max_msgs:
                    return msgs
    return msgs


def collect_negative_amount_warnings_waterfall(
    wf: list[list[str]],
    max_msgs: int = 12,
    existing: list[str] | None = None,
) -> list[str]:
    if existing is None:
        msgs: list[str] = []
    else:
        msgs = existing
    if not wf or len(wf) < 2:
        return msgs
    header = wf[0]
    idxs = _waterfall_amount_column_indices(header)
    if not idxs:
        return msgs
    for row in waterfall_data_rows(wf):
        desc = row_description(wf, row).strip() or "?"
        for ci in idxs:
            if ci >= len(row):
                continue
            v = parse_number(row[ci])
            if v is not None and v < -1e-6:
                hi = header[ci] if ci < len(header) else "?"
                msgs.append(f"03 waterfall `{desc[:80]}` / **{hi.strip()}** → {v:,.6g}")
                if len(msgs) >= max_msgs:
                    return msgs
    return msgs


FEE_KEYWORDS = re.compile(
    r"\b(fee|fees|servicing|master serv|trustee|"
    r"administration|administrator|custodian|"
    r"expense|expenses|issuer|guarantor|swap|"
    r"indemn|reimburse|pfa|payment facilitation)\b",
    re.I,
)

_CLASS_CASH_WATERFALL = re.compile(
    r"\b("
    r"holders?\s+of\s+(?:the\s+)?subordinated\s+notes?|"
    r"payment\s+on\s+(?:the\s+)?subordinated\s+notes?|"
    r"to\s+(?:the\s+)?holders?\s+of\s+(?:the\s+)?(?:class|notes?)|"
    r"periodic\s+interest\s+amount\s+on\s+(?:the\s+)?class|"
    r"cumulative\s+interest\s+amount\s+on\s+(?:the\s+)?class|"
    r"interest\s+on\s+(?:the\s+)?class\s+[a-z0-9-]+|"
    r"principal\s+on\s+(?:the\s+)?class|"
    r"defaulted\s+interest\s+on\s+(?:the\s+)?class"
    r")\b",
    re.I,
)


def _column_index_amount_paid(header: list[str]) -> int | None:
    i = column_index_exact(header, "Amount paid")
    if i is not None:
        return i
    for i, cell in enumerate(header):
        hl = cell.strip().lower()
        if hl in ("amount", "payment amount"):
            return i
    for i, cell in enumerate(header):
        hl = cell.strip().lower()
        if "paid" in hl and "payable" not in hl and "unpaid" not in hl:
            return i
    return None


def _waterfall_row_looks_like_class_cash(desc: str, priority: str = "") -> bool:
    """Note / class distributions — not admin, management, or tax fee lines."""
    d = (desc or "").strip()
    if not d:
        return False
    dl = d.lower()
    if re.search(
        r"\b(administrative\s+expense|management\s+fee|collateral\s+management\s+fee|"
        r"trustee\s+fee|taxes?\s+and\s+governmental|hedge\s+counterparty|"
        r"expense\s+cap|incentive\s+collateral\s+management\s+fee)\b",
        dl,
    ):
        if not re.search(r"\bholders?\s+of\s+(?:the\s+)?subordinated\s+notes?\b", dl):
            return False
    if _CLASS_CASH_WATERFALL.search(d):
        return True
    if re.search(r"\bclass\s+[a-z0-9-]+\s+notes?\b", d, re.I) and re.search(
        r"\b(interest|principal|periodic|cumulative|defaulted)\b", d, re.I
    ):
        return True
    if re.search(r"\bincentive\s+.*threshold\b", dl) and "subordinated" in dl:
        return True
    return False


def _collect_03_class_cash_paid_rows(
    tables03: list[list[list[str]]],
) -> tuple[float, list[str]]:
    """Sum **Amount paid** on class / noteholder rows in ``03`` (not fees)."""
    total = 0.0
    lines: list[str] = []
    seen_keys: set[tuple[str, str]] = set()

    def _norm_desc_key(desc: str) -> str:
        d = re.sub(r"\s+", " ", (desc or "").lower())[:60]
        return d

    def _add_row(priority: str, desc: str, paid_raw: str) -> None:
        nonlocal total
        paid = parse_number(paid_raw)
        if paid is None or abs(paid) < 1e-9:
            return
        if not _waterfall_row_looks_like_class_cash(desc, priority):
            return
        pri = (priority or "").strip()
        amt_key = f"{paid:.2f}"
        desc_key = _norm_desc_key(desc)
        for key in ((pri.lower(), amt_key), (desc_key, amt_key)):
            if key in seen_keys:
                return
        seen_keys.add((pri.lower(), amt_key))
        seen_keys.add((desc_key, amt_key))
        total += paid
        label = f"{pri + ' ' if pri else ''}{desc[:48]}".strip()
        lines.append(f"{label}={paid:,.2f}")

    wf = find_waterfall_table(tables03)
    if wf:
        paid_i = _column_index_amount_paid(wf[0])
        pri_i = column_index_exact(wf[0], "Priority")
        if paid_i is not None:
            for row in waterfall_data_rows(wf):
                desc = row_description(wf, row).strip()
                pri = row[pri_i].strip() if pri_i is not None and pri_i < len(row) else ""
                raw = row[paid_i].strip() if paid_i < len(row) else ""
                _add_row(pri, desc, raw)

    ladder = find_disbursement_ladder(tables03)
    if ladder:
        paid_i = _column_index_amount_paid(ladder[0])
        pri_i = None
        for i, cell in enumerate(ladder[0]):
            if "clause" in cell.lower() or "step" in cell.lower():
                pri_i = i
                break
        if paid_i is not None:
            for row in waterfall_data_rows(ladder):
                desc = row_description(ladder, row).strip()
                pri = row[pri_i].strip() if pri_i is not None and pri_i < len(row) else ""
                raw = row[paid_i].strip() if paid_i < len(row) else ""
                _add_row(pri, desc, raw)

    return total, lines


def collect_02_03_class_cash_crosscheck_warnings(
    cb: list[list[str]],
    data_rows: list[list[str]],
    tables03: list[list[list[str]]],
) -> list[str]:
    """
    Cross-check **02** class cash vs **03** noteholder / class waterfall paid.

    **Gated suggestion:** only when **Interest payment** is blank/0.00 and payable/waterfall align.
    **Compare-only:** when **Interest payment** is already set but differs from **03** sum.
    Never modifies **02** — review messages only.
    """
    wf_total, wf_lines = _collect_03_class_cash_paid_rows(tables03)
    if wf_total < 1e-9 or not wf_lines:
        return []

    int_pay_i = column_index_interest_payment(cb[0])
    int_pbl_i = column_index_exact(cb[0], "Interest payable")
    princ_pay_i = column_index_exact(cb[0], "Principal payment")
    msgs: list[str] = []
    sample = "; ".join(wf_lines[:4]) + ("…" if len(wf_lines) > 4 else "")

    for row in data_rows:
        cls = (row[0] if row else "").strip() or "?"
        int_pay = (
            parse_number(row[int_pay_i].strip())
            if int_pay_i is not None and int_pay_i < len(row)
            else None
        )
        int_pbl = (
            parse_number(row[int_pbl_i].strip())
            if int_pbl_i is not None and int_pbl_i < len(row)
            else None
        )
        princ_pay = (
            parse_number(row[princ_pay_i].strip())
            if princ_pay_i is not None and princ_pay_i < len(row)
            else None
        )
        pay_blank = int_pay is None or abs(int_pay) < 1e-9
        o2_cash = (int_pay or 0.0) + (princ_pay or 0.0)
        o2_payable = int_pbl or 0.0
        tol = max(0.02, 1e-8 * max(wf_total, o2_cash, o2_payable, 1.0))

        if pay_blank:
            if o2_payable > 1e-9 and abs(wf_total - o2_payable) <= tol:
                msgs.append(
                    f"{cls}: **Interest payment** is 0.00/blank but **Interest payable** "
                    f"{o2_payable:,.2f} matches **03** class/noteholder paid sum {wf_total:,.2f} "
                    f"({sample}) — review **02** Distribution Summary / Total Payable → "
                    "**Interest payment** rule in **02** (do **not** auto-copy from waterfall)."
                )
            elif o2_payable > 1e-9 and abs(wf_total - o2_payable) > tol:
                msgs.append(
                    f"{cls}: **Interest payment** is 0.00/blank; **03** class-cash sum "
                    f"{wf_total:,.2f} ({sample}) ≠ **Interest payable** {o2_payable:,.2f} — "
                    "review **02** and **03** (no auto-merge)."
                )
        elif wf_total > 1e-9 and abs(wf_total - o2_cash) > tol:
            msgs.append(
                f"{cls}: **02** **Interest payment**+**Principal payment**={o2_cash:,.2f} "
                f"≠ **03** class/noteholder paid sum {wf_total:,.2f} ({sample}) — "
                "compare-only; **02** stays authoritative unless you re-read the PDF."
            )
    return msgs


# Shared with map_valuation_fees.py — class cashflow lines must not roll into 05.
_VALUATION_FEE_DESC_LOOKS_NON_FEE = re.compile(
    r"(accrued\s+and\s+unpaid\s+interest\s+on\s+the\s+class|"
    r"accrued\s+interest\s+on\s+the\s+class|"
    r"payment\s+of\s+accrued.*interest.*class\s+[a-z][-\d\w]*|"
    r"unpaid\s+interest\s+on\s+the\s+class|"
    r"to\s+pay\s+periodic\s+interest\s+on\s+the\s+class|"
    r"periodic\s+interest\s+on\s+the\s+class|"
    r"pro\s+rata\s+interest|interest\s+.*\s+pro\s+rata\b|"
    r"class\s+[a-z][-\d\w]*\s*/\s*class\s+[a-z]|"
    r"class\s+[a-z][-\d\w]*\s+notes?\b|"
    r"class\s+[a-z][-\d\w]*\s+note\s+interest|"
    r"class\s+[a-z][-\d\w]*\s+note\s+principal|"
    r"\b(?:current|deferred)\s+interest\s+amount\b|"
    r"\bprincipal\s+repayment\b|"
    r"preferred\s+shares?|preference\s+share|"
    r"interest\s+proceeds\s+residual|remaining\s+interest\s+proceeds|"
    r"remaining\s+principal\s+proceeds|"
    r"interest\s+available\s+for\s+waterfall|principal\s+available\s+for\s+waterfall|"
    r"coverage\s+test|overcollateralization|"
    r"redemption\s+date|reinvest\s+period|"
    r"remaining\s+interest\s+proceeds\s+to\s+be\s+paid.*issuer|"
    r"holders\s+of\s+(?:the\s+)?subordinated\s+notes?|"
    r"payment\s+on\s+(?:the\s+)?subordinated\s+notes?|"
    r"interest\s+on\s+(?:the\s+)?subordinated\s+notes?|"
    r"to\s+(?:the\s+)?payment\s+on\s+(?:the\s+)?subordinated\s+notes?|"
    r"\bdebt\s+payment\s+sequence\b|"
    r"\bnote\s+payment\s+sequence\b|"
    r"\bnote\s+principal\b)",
    re.I,
)


def valuation_fee_description_looks_non_fee(description: str) -> bool:
    """True when text is clearly class cashflow / structural, not a trustee fee line."""
    d = (description or "").strip()
    if not d:
        return False
    return bool(_VALUATION_FEE_DESC_LOOKS_NON_FEE.search(d))


def find_05_valuation_fees_table(
    tables: list[list[list[str]]],
) -> list[list[str]] | None:
    for table in tables:
        if not table or len(table[0]) < 2:
            continue
        h = _header_join(table[0])
        if (
            "main category" in h
            and "amount paid" in h
            and ("sub category" in h or "fee_type" in h or "standard fee type" in h)
        ):
            return table
    return None


def _05_fee_table_body_rows(table: list[list[str]]) -> list[list[str]]:
    if len(table) < 2:
        return []
    out: list[list[str]] = []
    for row in table[1:]:
        if row and any(c.strip() for c in row):
            out.append(row)
    return out


def count_03_waterfall_fee_keyword_rows(
    wf: list[list[str]] | None,
    wrows: list[list[str]],
) -> int:
    if not wf or not wrows:
        return 0
    return sum(1 for r in wrows if FEE_KEYWORDS.search(row_description(wf, r)))


def collect_05_fee_rollup_warnings(
    out_dir: Path,
    *,
    fee_hits: int,
) -> list[str]:
    """
    WARN when ``03`` looks fee-bearing but ``05`` is missing or empty after mapping.
    """
    if fee_hits <= 0:
        return []
    p05 = out_dir / "05_valuation_relevant_fees.md"
    if not p05.is_file():
        return [
            f"**03** has {fee_hits} fee-like waterfall row(s) but "
            "**05_valuation_relevant_fees.md** is missing — run **map_valuation_fees.py**."
        ]
    text05 = p05.read_text(encoding="utf-8", errors="replace")
    if "not present" in text05.lower() and "valuation-relevant fees" in text05.lower():
        return [
            f"**03** has {fee_hits} fee-like row(s) but **05** marks valuation fees not present."
        ]
    tables05 = parse_md_tables(text05)
    fee_table = find_05_valuation_fees_table(tables05)
    if fee_table is None:
        return [
            f"**05_valuation_relevant_fees.md** exists but has no **Main category** / "
            "**Amount paid** table — re-run **map_valuation_fees.py** after editing **03**."
        ]
    paid_i = column_index_exact(fee_table[0], "Amount paid")
    if paid_i is None:
        return [
            "**05** fee table has no **Amount paid** column — check **map_valuation_fees.py** output."
        ]
    n_paid = 0
    total = 0.0
    for row in _05_fee_table_body_rows(fee_table):
        if paid_i >= len(row):
            continue
        v = parse_number(row[paid_i])
        if v is not None and abs(v) > 1e-9:
            n_paid += 1
            total += v
    if n_paid == 0:
        return [
            f"**03** has {fee_hits} fee-like waterfall row(s) but **05** has no non-zero "
            "**Amount paid** rows — run or re-run **map_valuation_fees.py**."
        ]
    return []


def waterfall_data_rows(table: list[list[str]]) -> list[list[str]]:
    if len(table) < 2:
        return []
    rows = []
    for row in table[1:]:
        if not row or not any(c.strip() for c in row):
            continue
        desc_idx = 1 if len(row) > 1 else 0
        desc = row[desc_idx].strip() if desc_idx < len(row) else ""
        if not desc or desc.lower() in ("item / payee description",):
            continue
        rows.append(row)
    return rows


def row_description(table: list[list[str]], row: list[str]) -> str:
    header = table[0]
    # Prefer column named like item/payee
    for i, h in enumerate(header):
        if "item" in h.lower() or "payee" in h.lower() or "description" in h.lower():
            if i < len(row):
                return row[i]
    if len(row) > 1:
        return row[1]
    return row[0] if row else ""


def file_section_absent(text: str) -> bool:
    """True only for explicit prose that the waterfall/proceeds section is absent.

    Do **not** scan generic key/value tables: optional **`04`** tables such as
    **Logical / clause waterfall** use ``Section present (Y/N) | N`` when the
    *clause ladder* is absent while a **grid** waterfall still exists — that must
    not skip fee validation on the grid.
    """
    tl = text.lower()
    if "section not present" in tl:
        return True
    return False


class Check:
    def __init__(
        self,
        category: str,
        name: str,
        ok: bool,
        detail: str = "",
        severity: str = "error",
    ):
        self.category = category
        self.name = name
        self.ok = ok
        self.detail = detail
        self.severity = severity  # "error" | "warn" | "info"


def validate_dir(out_dir: Path) -> list[Check]:
    checks: list[Check] = []

    for name in REQUIRED_FILES:
        p = out_dir / name
        checks.append(
            Check(
                "files",
                f"Required file {name}",
                p.is_file(),
                f"Missing: {p}" if not p.is_file() else str(p),
                "error" if not p.is_file() else "info",
            )
        )

    p02 = out_dir / "02_tranche_class_balances.md"
    if not p02.is_file():
        checks.append(
            Check(
                "tranches",
                "Class / tranche rows present",
                False,
                "Cannot validate tranches without 02 file.",
                "error",
            )
        )
        return checks

    text02 = p02.read_text(encoding="utf-8", errors="replace")
    tables02 = parse_md_tables(text02)
    cb = find_class_balance_table(tables02)
    if not cb:
        checks.append(
            Check(
                "tranches",
                "Class balance table found",
                False,
                "No table with headers Class + Beginning balance + "
                "Interest payment (and/or Interest payable).",
                "error",
            )
        )
        return checks

    data_rows = class_balance_data_rows(cb)
    has_tranches = len(data_rows) > 0
    checks.append(
        Check(
            "tranches",
            "At least one class row (non-total)",
            has_tranches,
            f"Found {len(data_rows)} data row(s)."
            + (" Populate 02 class balance table." if not has_tranches else ""),
            "error" if not has_tranches else "info",
        )
    )

    int_pay_i = column_index_interest_payment(cb[0])
    int_pbl_i = column_index_exact(cb[0], "Interest payable")
    div_i = column_index_exact(cb[0], "Dividend")
    if (int_pay_i is not None or int_pbl_i is not None or div_i is not None) and data_rows:
        all_blank = all_tranches_zero_interest_payment_payable_and_dividend(
            data_rows, int_pay_i, int_pbl_i, div_i
        )

        if all_blank:
            checks.append(
                Check(
                    "interest",
                    "All tranches zero on interest payment, payable, and dividend",
                    False,
                    f"All {len(data_rows)} class row(s) have Interest payment, "
                    "Interest payable, and Dividend each 0, blank, or N/A — "
                    "confirm the PDF, or fill **Interest payable** / **Dividend** "
                    "(sub notes) per trustee layout.",
                    "warn",
                )
            )
        else:
            n_pay = sum(
                1
                for row in data_rows
                if int_pay_i is not None
                and int_pay_i < len(row)
                and parse_number(row[int_pay_i]) is not None
            )
            n_pbl = sum(
                1
                for row in data_rows
                if int_pbl_i is not None
                and int_pbl_i < len(row)
                and parse_number(row[int_pbl_i]) is not None
            )
            n_div = sum(
                1
                for row in data_rows
                if div_i is not None
                and div_i < len(row)
                and parse_number(row[div_i]) is not None
            )
            n_tranches_with_signal = sum(
                1
                for row in data_rows
                if row_has_nonzero_interest_payment_payable_or_dividend(
                    row, int_pay_i, int_pbl_i, div_i
                )
            )
            checks.append(
                Check(
                    "interest",
                    "Not all tranches blank on interest payment / payable / dividend",
                    True,
                    f"{n_tranches_with_signal}/{len(data_rows)} tranche(s) have a "
                    f"nonzero interest payment, payable, or dividend; numeric cells: "
                    f"{n_pay} payment, {n_pbl} payable, {n_div} dividend.",
                    "info",
                )
            )

    orig_i = column_index_exact(cb[0], "Original balance")
    beg_i = column_index_exact(cb[0], "Beginning balance")
    end_i = column_index_exact(cb[0], "Ending balance")
    if data_rows and (orig_i is not None or beg_i is not None or end_i is not None):
        all_bal_zero = all_tranches_zero_original_beginning_and_ending(
            data_rows, orig_i, beg_i, end_i
        )
        if all_bal_zero:
            checks.append(
                Check(
                    "balances",
                    "All tranches zero on original, beginning, and ending balance",
                    False,
                    f"All {len(data_rows)} class row(s) have Original balance, "
                    "Beginning balance, and Ending balance each 0, blank, or N/A — "
                    "likely extraction gap. (If the deal is **sub-only** with seniors "
                    "at zero, the subordinated row should still show nonzero balances.)",
                    "warn",
                )
            )
        else:
            n_with_bal = sum(
                1
                for row in data_rows
                if row_has_nonzero_original_beginning_or_ending(
                    row, orig_i, beg_i, end_i
                )
            )
            checks.append(
                Check(
                    "balances",
                    "Not all tranches blank on original / beginning / ending balance",
                    True,
                    f"{n_with_bal}/{len(data_rows)} tranche(s) have a nonzero "
                    f"original, beginning, or ending balance.",
                    "info",
                )
            )

    idd_int_msgs = collect_idd_subtotal_interest_mismatch_warnings(
        text02, data_rows, cb[0]
    )
    if idd_int_msgs:
        checks.append(
            Check(
                "interest",
                "IDD Sub Totals Interest Distribution vs primary (zero coupon)",
                False,
                " | ".join(idd_int_msgs),
                "warn",
            )
        )

    coverage_msgs = collect_02_class_coverage_warnings(
        text02, data_rows, cb[0], chunk_text=_load_idd_chunk_text(out_dir)
    )
    if coverage_msgs:
        checks.append(
            Check(
                "tranches",
                "02 class coverage vs Source Text",
                False,
                " | ".join(coverage_msgs),
                "warn",
            )
        )

    orig_only_msgs = collect_primary_original_only_warnings(text02, data_rows, cb[0])
    if orig_only_msgs:
        checks.append(
            Check(
                "tranches",
                "Primary “Original balance only” (Distribution in US$)",
                False,
                " | ".join(orig_only_msgs),
                "warn",
            )
        )

    slice_msgs = collect_primary_program_slice_warnings(data_rows)
    if slice_msgs:
        checks.append(
            Check(
                "tranches",
                "Program-slice labels in primary (rollup to economic class)",
                False,
                " | ".join(slice_msgs),
                "warn",
            )
        )

    dg_table = find_distribution_grid_table(tables02)

    pbal_msgs: list[str] = []
    if cb and data_rows:
        pbal_msgs = collect_principal_payment_balance_confusion_warnings(cb[0], data_rows)
    pbal_classes = frozenset(_class_names_from_warning_msgs(pbal_msgs))

    if data_rows and cb:
        n_pr, n_bad, pr_msgs = principal_rollforward_row_stats(
            cb[0], data_rows, skip_classes=pbal_classes
        )
        pr_msgs = _filter_msgs_by_class(pr_msgs, set(pbal_classes))
        if n_pr == 0:
            checks.append(
                Check(
                    "balances",
                    "Principal roll-forward (ending ≈ beg + deferred − principal pmt)",
                    True,
                    "No class rows checked: missing Beginning/Ending/Principal payment "
                    "columns, non-numeric beginning/ending, or all rows skipped "
                    "(nonzero **Principal payable** — voucher-style layout).",
                    "info",
                )
            )
        elif n_bad == 0:
            checks.append(
                Check(
                    "balances",
                    "Principal roll-forward (ending ≈ beg + deferred − principal pmt)",
                    True,
                    f"{n_pr} class row(s) within tolerance "
                    f"(ending ≈ beginning + deferred interest − principal payment).",
                    "info",
                )
            )
        else:
            detail = f"{n_bad}/{n_pr} row(s) mismatch. " + (
                " Examples: " + " | ".join(pr_msgs) if pr_msgs else ""
            )
            detail += (
                " Common causes: (1) **Principal payment** taken from **PDD balance / notional** (or **factor**) "
                "instead of **period principal distributed / paid** while **Ending balance** still matches the PDF "
                "— see **Principal payment vs flat balance (PDD column map)** and **extraction-templates.md** "
                "**PDD balance ≠ principal paid**; (2) **Interest** **$** mis-mapped into **Principal payment** — "
                "fix columns from **Source Text** headings; do not recompute **Ending balance** from a wrong "
                "**Principal payment**."
            )
            checks.append(
                Check(
                    "balances",
                    "Principal roll-forward (ending ≈ beg + deferred − principal pmt)",
                    False,
                    detail.strip(),
                    "warn",
                )
            )

    if pbal_msgs:
        checks.append(
            Check(
                "balances",
                "Principal payment vs flat balance (PDD column map)",
                False,
                " | ".join(pbal_msgs),
                "warn",
            )
        )

    if dg_table and len(dg_table) > 1:
        dg_pr_msgs = collect_distribution_grid_principal_paid_warnings(dg_table)
        dg_pr_msgs = _filter_msgs_by_class(dg_pr_msgs, set(pbal_classes))
        if dg_pr_msgs:
            checks.append(
                Check(
                    "balances",
                    "Distribution grid Principal paid sanity",
                    False,
                    " | ".join(dg_pr_msgs),
                    "warn",
                )
            )

    if cb and data_rows and dg_table:
        pair_msgs = collect_distribution_grid_principal_balance_pair_warnings(
            cb[0], data_rows, dg_table, text02
        )
        if pair_msgs:
            detail_ec = " | ".join(pair_msgs)
            if len(pair_msgs) >= 6:
                detail_ec += " …"
            checks.append(
                Check(
                    "balances",
                    "Prior/current principal vs Beginning/Ending (Distribution in US$)",
                    False,
                    detail_ec,
                    "warn",
                )
            )

    if cb and data_rows:
        neg02 = collect_negative_amount_warnings_02(cb, data_rows)
        if neg02:
            detail = "Negative values (review sign/OCR/column): " + " | ".join(neg02)
            if len(neg02) >= 12:
                detail += " …"
            checks.append(
                Check(
                    "amounts",
                    "Non-negative money-style cells (02)",
                    False,
                    detail,
                    "warn",
                )
            )
        else:
            checks.append(
                Check(
                    "amounts",
                    "Non-negative money-style cells (02)",
                    True,
                    "No strictly negative parsed values in 02 amount columns.",
                    "info",
                )
            )

    # Distribution grid has Interest rate but primary column entirely blank (merge gap).
    ir_pri_i = column_index_exact(cb[0], "Interest rate")
    if data_rows and ir_pri_i is not None and dg_table is not None and len(dg_table) > 1:
        ir_dg_i = column_index_exact(dg_table[0], "Interest rate")
        if ir_dg_i is not None:
            dg_body = class_balance_data_rows(dg_table)
            any_dg_rate = any(
                ir_dg_i < len(r) and interest_rate_cell_nonempty(r[ir_dg_i])
                for r in dg_body
            )
            all_primary_rate_blank = all(
                ir_pri_i >= len(r) or not interest_rate_cell_nonempty(r[ir_pri_i])
                for r in data_rows
            )
            if dg_body and any_dg_rate and all_primary_rate_blank:
                checks.append(
                    Check(
                        "interest_rate",
                        "Primary Interest rate vs Distribution grid",
                        False,
                        "`### Distribution grid` has populated **Interest rate** values, "
                        "but every **`### Class balance table (primary)`** row has blank "
                        "**Interest rate** — copy merged coupon / interest-exhibit rate "
                        "into **primary** per `extraction-templates.md` **Dual exhibits**.",
                        "warn",
                    )
                )

    rate_type_msgs = collect_interest_rate_type_label_warnings(text02, data_rows, cb[0])
    if rate_type_msgs:
        checks.append(
            Check(
                "interest_rate",
                "Interest rate vs Interest type label",
                False,
                " | ".join(rate_type_msgs),
                "warn",
            )
        )

    p03 = out_dir / "03_interest_principal_waterfall.md"
    fee_hits_03 = 0
    if p03.is_file():
        text04 = p03.read_text(encoding="utf-8", errors="replace")
        if file_section_absent(text04):
            pass
        else:
            tables04 = parse_md_tables(text04)
            map_hdr_msgs = collect_03_column_mapping_header_warnings(text04)
            if map_hdr_msgs:
                checks.append(
                    Check(
                        "waterfall",
                        "03 Column mapping (Paid vs Available)",
                        False,
                        " | ".join(map_hdr_msgs),
                        "warn",
                    )
                )

            src_page_msgs = collect_03_waterfall_source_page_warnings(out_dir, text04)
            if src_page_msgs:
                checks.append(
                    Check(
                        "waterfall",
                        "03 Source Text covers mandatory waterfall pages",
                        False,
                        " | ".join(src_page_msgs),
                        "warn",
                    )
                )

            wf = find_waterfall_table(tables04)
            ladder = find_disbursement_ladder(tables04)
            ladder_rows = waterfall_data_rows(ladder) if ladder else []
            if not wf:
                if ladder_rows:
                    checks.append(
                        Check(
                            "waterfall",
                            "Waterfall table found",
                            True,
                            "Logical/clause layout — no ### Waterfall table grid; "
                            f"{len(ladder_rows)} row(s) in ### Disbursement ladder "
                            "(map_valuation_fees.py uses ladder as primary).",
                            "info",
                        )
                    )
                else:
                    checks.append(
                        Check(
                            "waterfall",
                            "Waterfall table found",
                            False,
                            "03 has no recognizable waterfall grid (Priority + Item/payee + "
                            "Amount paid) and no ### Disbursement ladder rows.",
                            "warn",
                        )
                    )
            else:
                wrows = waterfall_data_rows(wf)
                if not wrows:
                    if ladder_rows:
                        checks.append(
                            Check(
                                "waterfall",
                                "Waterfall has data rows",
                                True,
                                "Waterfall table has no data rows; "
                                f"{len(ladder_rows)} row(s) in ### Disbursement ladder "
                                "(map_valuation_fees.py uses ladder when grid is empty).",
                                "info",
                            )
                        )
                    else:
                        checks.append(
                            Check(
                                "waterfall",
                                "Waterfall has data rows",
                                False,
                                "Waterfall table has no data rows and no disbursement ladder.",
                                "warn",
                            )
                        )
                else:
                    fee_hits_03 = count_03_waterfall_fee_keyword_rows(wf, wrows)
                    due_paid_msgs = collect_due_paid_swap_warnings(wf)
                    if due_paid_msgs:
                        detail_dp = (
                            "Possible **due/payable** copied into **Amount paid** (check **### Column mapping** "
                            "and **Paid**/**Payment** column for this trustee — order is not fixed). Rows: "
                            + " | ".join(due_paid_msgs)
                        )
                        if len(due_paid_msgs) >= 8:
                            detail_dp += " …"
                        checks.append(
                            Check(
                                "waterfall",
                                "Amount paid vs Amount payable (Due/Paid)",
                                False,
                                detail_dp,
                                "warn",
                            )
                        )
                    paid_avail_msgs = collect_paid_equals_available_warnings(wf)
                    if paid_avail_msgs:
                        detail_pa = (
                            "Possible **Available**/**Running** copied into **Amount paid** "
                            "(map **Paid**/**Payment** by header — not column position). Rows: "
                            + " | ".join(paid_avail_msgs)
                        )
                        if len(paid_avail_msgs) >= 6:
                            detail_pa += " …"
                        checks.append(
                            Check(
                                "waterfall",
                                "Amount paid vs Amount available (Paid/Available)",
                                False,
                                detail_pa,
                                "warn",
                            )
                        )

            neg03: list[str] = []
            if wf:
                collect_negative_amount_warnings_waterfall(wf, max_msgs=12, existing=neg03)
            if neg03:
                detail03 = "Negative values (review sign/OCR/column): " + " | ".join(neg03)
                if len(neg03) >= 12:
                    detail03 += " …"
                checks.append(
                    Check(
                        "amounts",
                        "Non-negative money-style cells (03)",
                        False,
                        detail03,
                        "warn",
                    )
                )
            elif wf is not None:
                checks.append(
                    Check(
                        "amounts",
                        "Non-negative money-style cells (03)",
                        True,
                        "No strictly negative parsed values in 03 waterfall grid.",
                        "info",
                    )
                )
    else:
        checks.append(
            Check(
                "waterfall",
                "File 03 present for waterfall/fee checks",
                False,
                "03_interest_principal_waterfall.md missing - add if PDF has waterfall.",
                "warn",
            )
        )

    fee05_msgs = collect_05_fee_rollup_warnings(out_dir, fee_hits=fee_hits_03)
    if fee05_msgs:
        checks.append(
            Check(
                "fees",
                "05 fee roll-up vs 03 waterfall",
                False,
                " | ".join(fee05_msgs),
                "warn",
            )
        )

    if p02.is_file() and p03.is_file() and cb and data_rows:
        tables03_xc = parse_md_tables(
            p03.read_text(encoding="utf-8", errors="replace")
        )
        xc_msgs = collect_02_03_class_cash_crosscheck_warnings(
            cb, data_rows, tables03_xc
        )
        if xc_msgs:
            checks.append(
                Check(
                    "crosscheck",
                    "02 class cash vs 03 waterfall (review only)",
                    False,
                    " | ".join(xc_msgs),
                    "warn",
                )
            )

    return checks


def _sanitize_table_cell(s: str) -> str:
    """Single-line cell safe for pipe tables."""
    return (s or "").replace("|", "/").replace("\n", " ").strip()


def _truncate_table_detail(s: str, max_len: int = 140) -> str:
    t = _sanitize_table_cell(s)
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _short_console_message(s: str | None, max_len: int = 220) -> str:
    t = (s or "").replace("\n", " ").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _filter_checks_for_output(checks: list[Check], verbose: bool) -> list[Check]:
    """Drop passing INFO rows from reports unless ``verbose`` (warnings/errors always kept)."""
    if verbose:
        return checks
    return [c for c in checks if c.severity != "info"]


def write_report(out_dir: Path, checks: list[Check], *, verbose: bool = False) -> None:
    displayed = _filter_checks_for_output(checks, verbose)
    info_omitted = 0 if verbose else sum(1 for c in checks if c.severity == "info")
    errors = sum(1 for c in displayed if not c.ok and c.severity == "error")
    warns = sum(1 for c in displayed if not c.ok and c.severity == "warn")
    oks = sum(1 for c in displayed if c.ok)
    bad = [c for c in displayed if not c.ok]

    lines = [
        "# Noteval extraction validation report",
        "",
        f"- **Checks OK:** {oks}",
        f"- **Errors:** {errors}",
        f"- **Warnings:** {warns}",
        "",
    ]
    if info_omitted:
        lines.append(
            f"- **Info checks omitted:** {info_omitted} (re-run with `--verbose` to list passing sanity rows)"
        )
        lines.append("")
    if errors == 0 and warns == 0:
        lines.append("**STATUS: PASS** (no errors or warnings)")
    elif errors == 0:
        lines.append("**STATUS: PASS WITH WARNINGS** - review warnings below")
    else:
        lines.append("**STATUS: FAIL** - fix errors before relying on extraction")

    if bad:
        lines.extend(
            [
                "",
                "## At a glance (warnings & errors)",
                "",
                "Scan this table first; full text is under **[Full detail](#full-detail)** so long messages are not buried in one wide row.",
                "",
                "| # | Category | Check | Severity |",
                "|---|----------|-------|----------|",
            ]
        )
        for i, c in enumerate(bad, start=1):
            sev = "ERROR" if c.severity == "error" else c.severity.upper()
            lines.append(f"| {i} | {c.category} | {c.name} | {sev} |")
        lines.append("")

    lines.extend(["", "## Results", "", "| Category | Check | Severity | Status | Detail (truncated) |"])
    lines.append("|----------|-------|----------|--------|-------------------|")
    for c in displayed:
        status = "OK" if c.ok else ("FAIL" if c.severity == "error" else "WARN")
        sev = c.severity.upper()
        detail = _truncate_table_detail(c.detail)
        lines.append(f"| {c.category} | {c.name} | {sev} | {status} | {detail} |")

    if bad:
        lines.extend(
            [
                "",
                "## Full detail",
                "",
                "One subsection per failed check (same order as **At a glance**).",
                "",
            ]
        )
        for i, c in enumerate(bad, start=1):
            sev = c.severity.upper()
            lines.append(f"### {i}. {c.category} — {c.name} ({sev})")
            lines.append("")
            lines.append((c.detail or "(no detail)").strip() or "(no detail)")
            lines.append("")

    (out_dir / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")


def _configure_stdio_utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconf = getattr(stream, "reconfigure", None)
        if callable(reconf):
            try:
                reconf(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def main() -> int:
    _configure_stdio_utf8()
    parser = argparse.ArgumentParser(description="Validate noteval_extractor markdown outputs.")
    parser.add_argument("extraction_dir", type=Path, help="Directory with 01_ … 04_ extraction markdown")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any warnings (not only errors).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include passing INFO checks in validation_report.md (default: omit).",
    )
    args = parser.parse_args()
    out_dir: Path = args.extraction_dir

    if not out_dir.is_dir():
        print(f"ERROR: Not a directory: {out_dir}", file=sys.stderr)
        return 1

    checks = validate_dir(out_dir)
    write_report(out_dir, checks, verbose=args.verbose)

    errors = [c for c in checks if not c.ok and c.severity == "error"]
    warns = [c for c in checks if not c.ok and c.severity == "warn"]
    info_omitted = 0 if args.verbose else sum(1 for c in checks if c.severity == "info")

    report_path = out_dir / "validation_report.md"
    print(f"Wrote {report_path}")
    print(f"  errors: {len(errors)}  warnings: {len(warns)}", end="")
    if info_omitted:
        print(f"  (info rows omitted: {info_omitted}; use --verbose)", end="")
    print()

    if errors:
        for c in errors:
            print(
                f"  FAIL: [{c.category}] {c.name}: {_short_console_message(c.detail)}",
                file=sys.stderr,
            )
        return 1
    if warns and args.strict:
        for c in warns:
            print(
                f"  WARN: [{c.category}] {c.name}: {_short_console_message(c.detail)}",
                file=sys.stderr,
            )
        return 1
    if warns:
        for c in warns:
            print(f"  WARN: [{c.category}] {c.name}: {_short_console_message(c.detail)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
