"""
map_valuation_fees.py — Build 05_valuation_relevant_fees.md from 03 waterfall / ladder rows.

Agents extract waterfall cash in ``03_interest_principal_waterfall.md`` only.
This script maps fee lines to Main category | Sub category | Amount paid (DB literals).

When ``03`` has fee disbursements, roll-up uses structured tables in this order:

1. **### Waterfall table** (multi-column grid) when it has mappable fee rows
2. Else **### Disbursement ladder** (Section 11.1 / clause-only layouts with no grid)
3. Plus **### Continuations / sub-lines** and selective **## Source Text** lines when
   not duplicates

**### Administrative Expenses grid** in ``03`` is **not** read for ``05`` — voucher
tie-out only. **## Source Text** four-number lines (Available|Optimal|Paid|Unpaid) correct
grid **Amount paid** when the trustee copied **Available** into **Paid**. Only **non-zero**
cash paid is emitted.

**Roll-up:** After mapping, rows with the same **Sub category** are merged in
``05_valuation_relevant_fees.md`` with **Amount paid** summed (line-level detail
remains in ``fee_mapping_report.md``).

**Coverage policy (downstream DB):** Include every non-zero fee row from the **primary**
structured table (waterfall **or** ladder) except class interest/principal and other
structural cash (``Notes`` / description guards). Map **Tax** → ``tax_gross_amounts``;
**Trustee** → ``trustee_expenses``; known hedge/management literals when text matches.
**All other included fee cash** rolls into **Administrative expense** /
``administrator_expenses`` (summed). **### Administrative Expenses grid** is not used for
``05``. Reconciliation totals are in ``fee_mapping_report.md``.

Usage:
    python map_valuation_fees.py <extraction_dir>
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Reuse table helpers from validate_noteval (same repo, no circular import).
from validate_noteval import (  # noqa: E402
    FEE_KEYWORDS,
    _header_join,
    column_index_amount_available_running,
    column_index_exact,
    find_waterfall_table,
    parse_md_tables,
    parse_number,
    row_description,
    valuation_fee_description_looks_non_fee,
    waterfall_data_rows,
)

# Source Text: Available Optimal Paid Unpaid (Deutsche Bank / similar).
_SOURCE_TEXT_FOUR_AMOUNTS = re.compile(
    r"(?P<avail>[\d,]+\.\d{2})\s+"
    r"(?P<opt>[\d,]+\.\d{2})\s+"
    r"(?P<paid>[\d,]+\.\d{2})\s+"
    r"(?P<unpaid>[\d,]+\.\d{2})\s*$"
)

# Payment Date Report: Due | Paid | Running Balance | Unpaid (Paid = 2nd $; 4 cols).
_SOURCE_TEXT_DUE_PAID_RUNNING_UNPAID = re.compile(
    r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$"
)

# Opening-pool lines: Due $0.00 Running $42,006.90 Unpaid $0.00 (Paid column omitted / zero).
_SOURCE_TEXT_DUE_RUNNING_UNPAID = re.compile(
    r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$"
)

OUT_FILE = "05_valuation_relevant_fees.md"
REPORT_FILE = "fee_mapping_report.md"
SRC_03 = "03_interest_principal_waterfall.md"

OTHER_FEE_LITERALS = ("other_fees_01", "other_fees_02", "other_fees_03")

# Vendor-only payee labels under Interest Waterfall (i) admin blocks (no "fee" in text).
_ADMIN_VENDOR_PAYEE = re.compile(
    r"\b("
    r"ernst\s*&?\s*young|"
    r"deloitte|"
    r"pwc|pricewaterhouse|"
    r"kpmg|"
    r"csc\b|"
    r"computershare|"
    r"maples|"
    r"corporate\s+services?\s+company|"
    r"independent\s+accountants?"
    r")\b",
    re.I,
)


@dataclass
class FeeCandidate:
    source: str
    description: str
    amount_paid: str
    priority: str = ""


def _amount_paid_col(header: list[str]) -> int | None:
    for name in ("Amount paid", "Amount", "Payment"):
        i = column_index_exact(header, name)
        if i is not None:
            return i
    h = _header_join(header)
    if "amount paid" in h:
        for i, cell in enumerate(header):
            if "paid" in cell.lower() and "payable" not in cell.lower():
                return i
    return None


def _priority_col(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        if "priority" in cell.lower() or "clause" in cell.lower():
            return i
    return None


def _format_amount(v: float | None) -> str:
    if v is None:
        return ""
    if abs(v) < 1e-9:
        return "0.00"
    return f"{v:,.2f}"


def _amount_payable_col(header: list[str]) -> int | None:
    return column_index_exact(header, "Amount payable")


def _normalize_fee_desc(desc: str) -> str:
    d = desc.lower().strip()
    d = re.sub(r"^payment of\s+(the\s+)?", "", d)
    d = re.sub(r"\s+", " ", d)
    return d


def _strip_priority_prefix(desc: str) -> str:
    d = desc.strip()
    d = re.sub(r"^\([A-Z]\)(?:\([0-9ivx]+\))*\s*", "", d, flags=re.I)
    d = re.sub(r"^\([0-9ivx]+\)\s*", "", d, flags=re.I)
    return d.strip()


def _store_source_text_paid(
    out: dict[str, float], desc: str, paid: float | None
) -> None:
    if paid is None:
        return
    desc = _strip_priority_prefix(desc)
    if not desc:
        return
    norm = _normalize_fee_desc(desc)
    keys = {
        norm,
        _normalize_fee_desc(re.sub(r"^payment of\s+(the\s+)?", "", desc, flags=re.I)),
    }
    for key in keys:
        prev = out.get(key)
        if prev is not None and prev > 1e-9 and abs(paid) < 1e-9:
            continue
        if prev is not None and abs(prev) < 1e-9 and paid > 1e-9:
            out[key] = paid
            continue
        if key not in out:
            out[key] = paid


def _paid_from_due_paid_running_tail(s: str) -> tuple[float | None, str]:
    """Parse Due/Paid/Running[/Unpaid] tail; return (paid, description prefix)."""
    m4 = _SOURCE_TEXT_DUE_PAID_RUNNING_UNPAID.search(s)
    if m4:
        due = parse_number(m4.group(1))
        paid = parse_number(m4.group(2))
        running = parse_number(m4.group(3))
        desc = s[: m4.start()].strip()
        if paid is not None:
            return paid, desc
        if (
            due is not None
            and running is not None
            and abs(due) < 1e-9
            and abs(running) > 1e-9
        ):
            return 0.0, desc
    m3 = _SOURCE_TEXT_DUE_RUNNING_UNPAID.search(s)
    if m3:
        due = parse_number(m3.group(1))
        mid = parse_number(m3.group(2))
        last = parse_number(m3.group(3))
        desc = s[: m3.start()].strip()
        if due is None or mid is None or last is None:
            return None, desc
        tol = max(0.01, 1e-8 * max(abs(mid), 1.0))
        if abs(due) < 1e-9 and abs(last) < 1e-9:
            return 0.0, desc
        if abs(due - mid) <= tol:
            return mid, desc
    return None, s


def _build_source_text_paid_lookup(text03: str) -> dict[str, float]:
    """
    Map normalized item text → **Paid** from Source Text.

    Supports Available/Optimal/Paid/Unpaid, Due/Paid/Running/Unpaid, and
    opening-pool lines ``$0.00 $42,006.90 $0.00`` (Due/Running/Unpaid — **Paid** = 0).
    """
    block = _source_text_block(text03)
    if not block:
        return {}
    out: dict[str, float] = {}
    for line in block.splitlines():
        s = line.strip()
        if not s or s.startswith("---"):
            continue
        s = re.sub(r"^>\s*", "", s).strip()
        paid: float | None = None
        desc = s
        m = _SOURCE_TEXT_FOUR_AMOUNTS.search(s)
        if m:
            paid = parse_number(m.group("paid"))
            desc = s[: m.start()].strip()
        else:
            paid, desc = _paid_from_due_paid_running_tail(s)
        if paid is None:
            continue
        _store_source_text_paid(out, desc, paid)
    return out


def _lookup_source_text_paid(desc: str, lookup: dict[str, float]) -> float | None:
    if not lookup:
        return None
    for key in (
        _normalize_fee_desc(desc),
        _normalize_fee_desc(_strip_priority_prefix(desc)),
    ):
        if key in lookup:
            return lookup[key]
    nd = _normalize_fee_desc(desc)
    for k, v in lookup.items():
        if nd in k or k in nd:
            return v
    return None


def _effective_waterfall_amount_paid(
    table: list[list[str]],
    row: list[str],
    *,
    source_paid: dict[str, float],
) -> float | None:
    """
    Return cash **paid** this period for a waterfall row.

    Uses the grid **Amount paid** column (trustee **Paid** / **Payment**), never
    **Amount available / running**. Corrects mis-maps when **Available** was copied
    into **Amount paid**, and uses **Source Text** only when the grid paid cell is
    blank or clearly wrong. Same fee label on interest vs principal ladders keeps
    each row's own grid **Paid** (e.g. 2,515.98 and 403.98 both map).
    """
    header = table[0]
    paid_i = _amount_paid_col(header)
    if paid_i is None or paid_i >= len(row):
        return None
    paid_raw = parse_number(row[paid_i].strip())
    payable_i = _amount_payable_col(header)
    avail_i = column_index_amount_available_running(header)
    payable = (
        parse_number(row[payable_i].strip())
        if payable_i is not None and payable_i < len(row)
        else None
    )
    avail = (
        parse_number(row[avail_i].strip())
        if avail_i is not None and avail_i < len(row)
        else None
    )
    desc = row_description(table, row).strip()

    src_paid = _lookup_source_text_paid(desc, source_paid)

    if paid_raw is None:
        if src_paid is not None and src_paid > 1e-9:
            return src_paid
        return None

    def _tol(a: float, b: float) -> float:
        return max(0.01, 1e-8 * max(abs(a), abs(b), 1.0))

    # Same fee label on interest vs principal ladders — Source Text often has one
    # line per description; do not replace this row's grid **Paid** with another step's $.
    if (
        src_paid is not None
        and src_paid > 1e-9
        and paid_raw > 1e-9
        and abs(paid_raw - src_paid) > _tol(paid_raw, src_paid)
    ):
        if (
            payable is not None
            and payable > 1e-9
            and _tol(paid_raw, payable) >= abs(paid_raw - payable)
        ):
            return paid_raw
        if (
            avail is not None
            and _tol(paid_raw, avail) >= abs(paid_raw - avail)
        ):
            return src_paid
        return paid_raw

    # **Amount paid** equals **Available** — do not treat the pool as cash paid.
    if (
        payable is not None
        and payable > 1e-9
        and avail is not None
        and _tol(payable, avail) >= abs(payable - avail)
        and _tol(paid_raw, payable) > abs(paid_raw - payable)
    ):
        return payable

    if (
        avail is not None
        and paid_raw > 1e-9
        and _tol(paid_raw, avail) >= abs(paid_raw - avail)
    ):
        if (
            payable is not None
            and payable > 1e-9
            and _tol(paid_raw, payable) >= abs(paid_raw - payable)
        ):
            return paid_raw
        if (
            src_paid is not None
            and src_paid > 1e-9
            and _tol(paid_raw, src_paid) >= abs(paid_raw - src_paid)
        ):
            return paid_raw
        return None

    # Source Text shows **Paid** = 0 but grid **Amount paid** is non-zero with no payable:
    # usually **Running Balance** copied into **Paid** (opening pool or post-step remainder).
    if (
        src_paid is not None
        and abs(src_paid) < 1e-9
        and paid_raw > 1e-9
        and (payable is None or abs(payable) < 1e-9)
    ):
        return None

    # No Source Text line and no payable/available: **Amount paid** is likely remaining pool.
    if (
        src_paid is None
        and paid_raw > 1e-9
        and (payable is None or abs(payable) < 1e-9)
        and (avail is None or abs(avail) < 1e-9)
    ):
        return None

    return paid_raw


def _admin_expenses_grid_present(tables: list[list[list[str]]]) -> bool:
    """True when 03 has a voucher grid (informational only — not mapped to 05)."""
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if "expense" in h and "fee type" in h and (
            "paid during" in h or "paid on the distribution" in h
        ):
            return True
    return False


def _looks_like_structural_waterfall(desc: str, priority: str = "") -> bool:
    """Class cash / pool movements — not valuation fee rows for ``05``."""
    d = (desc or "").lower()
    p = (priority or "").lower()
    if valuation_fee_description_looks_non_fee(desc):
        return True
    if re.search(
        r"\b(purchase\s+of\s+additional|reinvestment\s+period|collateral\s+obligations?|"
        r"eligible\s+investments?|remaining\s+(?:interest|principal)\s+proceeds|"
        r"interest\s+available\s+for\s+waterfall|principal\s+available\s+for\s+waterfall|"
        r"pro\s+rata\s+interest|interest\s+proceeds\s+residual|"
        r"preferred\s+shares?|preference\s+share|"
        r"coverage\s+test|overcollateralization|redemption\s+date|"
        r"holders?\s+of\s+(?:the\s+)?subordinated\s+notes?|"
        r"payment\s+on\s+(?:the\s+)?subordinated\s+notes?|"
        r"interest\s+on\s+(?:the\s+)?subordinated\s+notes?|"
        r"to\s+(?:the\s+)?payment\s+on\s+(?:the\s+)?subordinated\s+notes?|"
        r"incentive\s+management\s+fee\s+threshold|"
        r"distributed\s+to\s+note\s+classes?|note\s+classes?\s+and\s+subordinated)\b",
        d,
    ):
        return True
    if re.search(r"\bclass\s+[a-z][-\d\w]*\s*/\s*class\s+[a-z]", d):
        return True
    if re.search(r"\bprincipal\s+\(c\)\b|\binterest\s+\(w\)\b|\binterest\s+\(y\)\b", p):
        return True
    return False


def _notes_col_index(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        if "notes" in cell.strip().lower():
            return i
    return None


def _row_notes(table: list[list[str]], row: list[str]) -> str:
    ni = _notes_col_index(table[0])
    if ni is None or ni >= len(row):
        return ""
    return row[ni].strip()


def _waterfall_row_is_excluded(
    table: list[list[str]], row: list[str], desc: str, priority: str = ""
) -> bool:
    """
    Exclude class cash / structural lines from fee roll-up.

    Inclusive default: any other non-zero **Amount paid** in **### Waterfall table**
    is treated as fee economics for ``05``.
    """
    if not desc.strip():
        return True
    if _looks_like_ladder_aggregate(desc):
        return True
    notes = _row_notes(table, row).lower()
    if re.search(
        r"class\s+cash|class\s+cashflow|authoritative\s+in\s+02|\bsee\s+02\b",
        notes,
    ):
        return True
    if "structural" in notes and "fee" not in notes:
        return True
    if _looks_like_structural_waterfall(desc, priority):
        return True
    if valuation_fee_description_looks_non_fee(desc):
        return True
    return False


def _should_include_fee_row(desc: str, priority: str = "") -> bool:
    """Legacy ladder helper — still requires fee-like wording (ladder can be noisy)."""
    if not desc.strip():
        return False
    if _looks_like_structural_waterfall(desc, priority):
        return False
    if _looks_like_ladder_aggregate(desc):
        return False
    if _looks_like_fee(desc):
        return True
    p = (priority or "").lower()
    if re.search(
        r"\(a\)\(2\)|\(b\)\(1\)|\(s\)\(1\)|\(t\)\(1\)|"
        r"administrative\s+expense|management\s+fee|fee\s+line",
        p,
    ):
        return True
    if re.search(
        r"^to\s+the\s+|\bany\s+other\s+person\b|"
        r"\b(repack\s+fees?|rating\s+agenc|portfolio\s+manager\s+expense|"
        r"independent\s+accountants?|administrator|conflicts\s+review)\b",
        desc,
        re.I,
    ):
        return True
    if _is_accrued_unpaid_admin_up_to_cap(desc):
        return True
    return False


def _is_accrued_unpaid_admin_up_to_cap(desc: str) -> bool:
    """Real admin cash line — not a ladder subtotal/header to skip."""
    d = (desc or "").lower()
    return bool(
        re.search(
            r"\baccrued\s+and\s+unpaid\s+administrative\s+expenses?\b",
            d,
        )
        and re.search(
            r"\b(administrative\s+expense\s+cap|up\s+to\s+the\s+(?:administrative\s+expense\s+)?cap)\b",
            d,
        )
    )


def _looks_like_ladder_aggregate(desc: str) -> bool:
    """Disbursement ladder subtotals (not separate fee lines for ``05``)."""
    d = desc.lower().strip()
    if _is_accrued_unpaid_admin_up_to_cap(desc):
        return False
    if re.search(r"\badministrative\s+expenses?\s+block\b", d):
        return True
    if re.search(r"\btaxes?\s+and\s+administrative\s+expenses?\b", d):
        return True
    if re.search(r"\b(block|subtotal)\b", d) and re.search(r"\badministrative\s+expense", d):
        return True
    if re.search(
        r"\badministrative\s+expenses?\b.*\b(administrative\s+expense\s+cap|up\s+to\s+the\s+cap)\b",
        d,
    ):
        return True
    if re.search(
        r"^(first|second|third|fourth),?\s+.*\badministrative\s+expenses?\b", d
    ) and re.search(r"\b(cap|priority\s+stated)\b", d):
        return True
    if re.search(r"\bpro\s+rata\b", d) and re.search(r"\binterest\b", d):
        return True
    if re.search(r"\baccrued\s+and\s+unpaid\s+interest\b", d):
        return True
    return False


def _looks_like_fee(desc: str) -> bool:
    if not desc.strip():
        return False
    if valuation_fee_description_looks_non_fee(desc):
        return False
    if re.search(r"\b(independent\s+)?accountants?\b", desc, re.I) and re.search(
        r"\b(agents?\s+and\s+)?counsel\b", desc, re.I
    ):
        return True
    if re.search(r"\b(tax|taxes|governmental)\b", desc, re.I):
        return True
    if re.search(r"\brating\s+agenc", desc, re.I):
        return True
    if re.search(r"\bindependent\s+review", desc, re.I):
        return True
    if re.search(r"\bcollateral\s+manager\b", desc, re.I) and not re.search(
        r"\bmanagement\s+fee\b", desc, re.I
    ):
        return True
    # Computershare / CLO **Administrative Expenses** sixth(g) catch-all (no "fee" in label).
    if re.search(r"\bany\s+other\s+person\b", desc, re.I):
        return True
    if re.search(r"\bco[\s-]?issuer\s+admin\s+expenses?\b", desc, re.I):
        return True
    if _ADMIN_VENDOR_PAYEE.search(desc):
        return True
    if _desc_maps_to_expense_reserve_account(desc):
        return True
    return bool(FEE_KEYWORDS.search(desc))


def _desc_maps_to_expense_reserve_account(desc: str) -> bool:
    """Expense Reserve Account funding (admin not received / paid to reserve)."""
    d = (desc or "").lower()
    if re.search(r"\bexpense\s+reserve\s+account\b", d):
        return True
    if re.search(r"\bexpense\s+reimbursement\s+account\b", d):
        return False
    if re.search(r"\badministrative\s+expenses?\b", d) and re.search(
        r"\b(not\s+received|expense\s+reserve)\b", d
    ):
        return True
    if re.search(
        r"payment\s+of\s+administrative\s+expenses?.*\bto\s+the\s+expense\s+reserve\b",
        d,
    ):
        return True
    return False


def _desc_is_collateral_manager_admin_fee(desc: str) -> bool:
    """
    CLO waterfall lines paying the Collateral Manager base/admin fee.

    **Senior** / **Subordinated** / **Incentive** management tiers use their own
    literals (``senior_management_fees``, etc.). This helper is for collateral
    admin/management lines **without** those tier labels.
    """
    d = (desc or "").lower()
    if not re.search(r"\bcollateral\s+manager\b", d):
        return False
    if re.search(r"\bincentive\b", d):
        return False
    if re.search(r"\bsubordinat", d) and re.search(r"\bmanagement\s+fee\b", d):
        return False
    if re.search(r"\bsenior\b", d) and re.search(r"\bmanagement\s+fee\b", d):
        return False
    if re.search(r"\b(deferred|election of the collateral manager)\b", d):
        return False
    if re.search(
        r"\b(?:due and payable|payable|paid|payment)\b.*\bto\s+(?:the\s+)?collateral\s+manager\b",
        d,
    ):
        return True
    if re.search(
        r"\bto\s+(?:the\s+)?collateral\s+manager\b.*\b(?:as\s+the\s+)?(?:senior\s+)?management\s+fee\b",
        d,
    ):
        return True
    return False


def _desc_is_incentive_or_performance_management_fee(desc: str) -> bool:
    """
    Incentive / performance management tier — modeled as subordinate management.

    Includes **x% of remaining Interest/Principal Proceeds … Incentive Management
    Fee**, **subordinated incentive fee**, and **performance fee** to the manager.
    """
    d = (desc or "").lower()
    if re.search(r"\bdeferred\s+incentive\s+management", d):
        return True
    if re.search(r"\bsubordinated\s+incentive\s+fee\b", d):
        return True
    if re.search(r"\bperformance\s+fee\b", d) and re.search(
        r"\b(collateral\s+manager|management|manager)\b", d
    ):
        return True
    if re.search(r"\bincentive\s+management\s+fee\b", d):
        return True
    if re.search(r"\bincentive\b", d) and re.search(r"\bmanagement\s+fee\b", d):
        return True
    if re.search(
        r"\bremaining\s+(?:interest|principal)\s+proceeds\b.*\b"
        r"collateral\s+manager\b.*\bincentive\s+management\s+fee\b",
        d,
    ):
        return True
    if re.search(
        r"\bto\s+(?:the\s+)?collateral\s+manager\b.*\bas\s+the\s+incentive\s+management\s+fee\b",
        d,
    ):
        return True
    return False


def _desc_names_trustee_and_collateral_administrator(desc: str) -> bool:
    """Printed line names both trustee and collateral administrator/administration."""
    d = (desc or "").lower()
    if not re.search(r"\btrustee\b", d):
        return False
    return bool(
        re.search(
            r"\bcollateral\s+administrator\b"
            r"|\bcollateral\s+administration\b"
            r"|\bcollateral\s+administrative\b"
            r"|\bcollateral\s+admin\b",
            d,
        )
    )


def _classify(desc: str, other_count: int) -> tuple[str, str]:
    d = desc.lower()

    if re.search(r"\b(note|debt)\s+payment\s+sequence\b", d):
        idx = min(other_count, 2)
        return "Other", OTHER_FEE_LITERALS[idx]

    if re.search(r"\b(tax|taxes|governmental)\b", d) and (
        re.search(r"\b(issuer|co-?issuer|payment of)\b", d)
        or re.fullmatch(r"tax(es)?", d.strip())
        or (re.search(r"\b(tax|taxes)\b", d) and len(d.split()) <= 3)
    ):
        return "Tax", "tax_gross_amounts"

    if _desc_maps_to_expense_reserve_account(desc):
        return "Other", "expense_reserve_account"

    if _ADMIN_VENDOR_PAYEE.search(d):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\bhedge\b|\bswap\b", d) and re.search(
        r"\b(counterparty|agreement|transaction)\b", d
    ):
        return "Hedge", "fees_to_hedge_counterparty"

    # Standard CLO admin professionals line — not contractual Issuer / Co-Issuer fee.
    if re.search(r"\b(independent\s+)?accountants?\b", d) and re.search(
        r"\b(agents?\s+and\s+)?counsel\b", d
    ):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\bagents?\s+and\s+counsel\s+of\s+(the\s+)?issuer\b", d):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\bco[\s-]?issuer\s+admin\s+expenses?\b", d):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\bany\s+other\s+person\b", d):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\bco-?issuer\b", d) and re.search(r"\bfee", d):
        return "Administrative expense", "coissuer_fees"

    if re.search(r"\bissuer\b", d) and re.search(r"\bfee", d) and "tax" not in d:
        return "Administrative expense", "coissuer_fees"

    if _desc_names_trustee_and_collateral_administrator(desc):
        return "Administrative expense", "trustee_expenses"

    if re.search(r"\badditional\s+collateral\s+management\s+fee\b", d):
        return "Management fees", "subordinate_management_fees"

    if re.search(r"\bsubordinat", d) and re.search(
        r"\b(management|manager|collateral\s+management)\b", d
    ) and not re.search(
        r"\b(holders?\s+of\s+(?:the\s+)?subordinated\s+notes?|"
        r"payment\s+on\s+(?:the\s+)?subordinated\s+notes?|"
        r"interest\s+on\s+(?:the\s+)?subordinated\s+notes?)\b",
        d,
    ):
        return "Management fees", "subordinate_management_fees"

    if _desc_is_collateral_manager_admin_fee(desc):
        return "Administrative expense", "collateral_admin_fees"

    if _desc_is_incentive_or_performance_management_fee(desc):
        return "Management fees", "subordinate_management_fees"

    if re.search(
        r"\bunlabeled\s+clause\s+\(iv\)|\bclause\s+\(iv\)\s+row\b|"
        r"senior\s+(?:asset\s+)?management\s+fee",
        d,
    ):
        return "Management fees", "senior_management_fees"

    if re.search(r"\bsenior\b", d) and re.search(
        r"\b(management|manager|collateral\s+management)\b", d
    ):
        return "Management fees", "senior_management_fees"

    if re.search(r"\bcollateral\s+administrator\b", d) and not re.search(
        r"\bmanagement\s+fee\b", d
    ):
        return "Administrative expense", "administrator_expenses"

    if re.search(
        r"\bcollateral\b.*\b(management|manager|administrative|administration)\b",
        d,
    ) or re.search(
        r"\b(management|manager|administrative)\b.*\bcollateral\b",
        d,
    ):
        return "Administrative expense", "collateral_admin_fees"

    if re.search(r"\btrustee\b", d):
        return "Administrative expense", "trustee_expenses"

    # Short ### Disbursement ladder text often says only "To the Bank" (no
    # "Collateral Administrator"); must match ### Waterfall table so O(a)/B(a)
    # are not double-counted under administrator_expenses + collateral_admin_fees.
    if re.search(r"\badministrative\s+expense", d) and re.search(r"\bto\s+the\s+bank\b", d):
        return "Administrative expense", "collateral_admin_fees"

    if re.search(
        r"\b(administrative\s+expense|admin\s+expense|senior\s+expense|expenses?\s+cap)\b",
        d,
    ):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\b(management\s+fee|manager\s+fee|servicing\s+fee)\b", d):
        return "Management fees", "senior_management_fees"

    if re.search(r"\bfee", d) or re.search(r"\bexpense", d):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\brating\s+agenc", d):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\bindependent\s+review", d):
        return "Administrative expense", "administrator_expenses"

    if re.search(r"\bcollateral\s+manager\b", d) and "management fee" not in d:
        return "Administrative expense", "collateral_admin_fees"

    idx = min(other_count, 2)
    return "Other", OTHER_FEE_LITERALS[idx]


def _classify_for_downstream(desc: str, other_count: int = 0) -> tuple[str, str]:
    """
    Map to DB **Main category** / **Sub category**.

    Tax and trustee stay explicit; hedge/management literals when matched.
    Anything that would be **Other** / ``other_fees_*`` → **Administrative expense**
    / ``administrator_expenses`` (no data loss).
    """
    main, sub = _classify(desc, other_count)
    if main == "Other" or sub in OTHER_FEE_LITERALS:
        return "Administrative expense", "administrator_expenses"
    return main, sub


def _collect_from_waterfall(
    table: list[list[str]],
    *,
    source_paid: dict[str, float] | None = None,
) -> tuple[list[FeeCandidate], list[str]]:
    header = table[0]
    paid_i = _amount_paid_col(header)
    pri_i = _priority_col(header)
    if paid_i is None:
        return []
    lookup = source_paid or {}
    out: list[FeeCandidate] = []
    excluded: list[str] = []
    for row in waterfall_data_rows(table):
        desc = row_description(table, row).strip()
        pri = row[pri_i].strip() if pri_i is not None and pri_i < len(row) else ""
        if _waterfall_row_is_excluded(table, row, desc, pri):
            if desc:
                excluded.append(f"{desc[:80]} ({pri or '—'})")
            continue
        paid = _effective_waterfall_amount_paid(table, row, source_paid=lookup)
        if paid is None or abs(paid) < 1e-9:
            continue
        out.append(
            FeeCandidate(
                source="waterfall",
                description=desc,
                amount_paid=_format_amount(paid),
                priority=pri,
            )
        )
    return out, excluded


def _find_disbursement_ladder(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if ("clause" in h or "step" in h) and "amount" in h and "item" in h:
            return table
    return None


def _find_continuations_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if "continuation" in h and "parent" in h and "amount" in h:
            return table
    return None


def _collect_from_continuations(
    table: list[list[str]],
    *,
    source_paid: dict[str, float] | None = None,
) -> list[FeeCandidate]:
    """Itemized sub-lines (e.g. Trustee under (A)(2)(i)) when ladder rows use compound amounts."""
    header = table[0]
    amt_i = _amount_paid_col(header)
    if amt_i is None:
        for i, cell in enumerate(header):
            if cell.strip().lower() == "amount":
                amt_i = i
                break
    parent_i = _priority_col(header)
    if parent_i is None:
        for i, cell in enumerate(header):
            if "parent" in cell.lower():
                parent_i = i
                break
    text_i: int | None = None
    for i, cell in enumerate(header):
        cl = cell.lower()
        if "continuation" in cl or ("text" in cl and "parent" not in cl):
            text_i = i
            break
    if amt_i is None or text_i is None:
        return []
    lookup = source_paid or {}
    out: list[FeeCandidate] = []
    for row in table[1:]:
        if not row or not any(c.strip() for c in row):
            continue
        desc = row[text_i].strip() if text_i < len(row) else ""
        if not desc:
            continue
        parent = row[parent_i].strip() if parent_i is not None and parent_i < len(row) else ""
        if _looks_like_structural_waterfall(desc, parent):
            continue
        if not _should_include_fee_row(desc, parent):
            continue
        raw = row[amt_i].strip() if amt_i < len(row) else ""
        paid = parse_number(raw)
        sp = _lookup_source_text_paid(desc, lookup)
        if sp is not None:
            paid = sp
        if paid is None or abs(paid) < 1e-9:
            continue
        out.append(
            FeeCandidate(
                source="continuations",
                description=desc,
                amount_paid=_format_amount(paid) or raw,
                priority=parent,
            )
        )
    return out


def _collect_from_ladder(
    table: list[list[str]],
    *,
    source_paid: dict[str, float] | None = None,
) -> list[FeeCandidate]:
    header = table[0]
    amt_i = _amount_paid_col(header)
    if amt_i is None:
        for i, cell in enumerate(header):
            if cell.strip().lower() == "amount":
                amt_i = i
                break
    clause_i = _priority_col(header)
    if amt_i is None:
        return []
    lookup = source_paid or {}
    out: list[FeeCandidate] = []
    for row in table[1:]:
        if not row or not any(c.strip() for c in row):
            continue
        desc = row_description(table, row).strip()
        if not desc or desc.lower().startswith("clause"):
            continue
        clause = row[clause_i].strip() if clause_i is not None and clause_i < len(row) else ""
        if _looks_like_structural_waterfall(desc, clause):
            continue
        if not _should_include_fee_row(desc, clause):
            continue
        raw = row[amt_i].strip() if amt_i < len(row) else ""
        paid = parse_number(raw)
        sp = _lookup_source_text_paid(desc, lookup)
        if sp is not None:
            paid = sp
        elif (
            paid is not None
            and paid > 1e-9
            and re.search(r"\b(tax|taxes|governmental)\b", desc, re.I)
            and (sp is None or abs(sp) < 1e-9)
        ):
            paid = None
        if paid is None or abs(paid) < 1e-9:
            # Compound amounts (e.g. "54.42; 2,343.73") are not parseable — skip; use
            # ### Continuations / sub-lines or split ladder/waterfall rows instead.
            if raw and re.search(r"[\d,]+\.\d{2}\s*[;,]\s*[\d,]+\.\d{2}", raw):
                continue
            continue
        out.append(
            FeeCandidate(
                source="ladder",
                description=desc,
                amount_paid=_format_amount(paid) or raw,
                priority=clause,
            )
        )
    return out


@dataclass
class MappedRow:
    main_category: str
    sub_category: str
    amount_paid: str
    description: str
    source: str
    priority: str


def _classify_sub_category(desc: str) -> str:
    """Leaf sub_category only (for cross-source dedup)."""
    _main, sub = _classify_for_downstream(desc, 0)
    return sub


def _fee_descriptions_match(a: str, b: str) -> bool:
    na, nb = _normalize_fee_desc(a), _normalize_fee_desc(b)
    if na == nb:
        return True
    return na in nb or nb in na


def _clause_step_tokens(priority: str, description: str) -> set[str]:
    """Clause keys such as ``b(a)``, ``o(a)`` from priority + description."""
    blob = f"{priority} {description}".lower()
    return {f"{a}({b})" for a, b in re.findall(r"\b([a-z])\(([a-z0-9]+)\)", blob)}


def _normalize_priority_key(priority: str) -> str:
    """Stable clause key for cross-table dedup (waterfall vs ladder vs continuations)."""
    p = (priority or "").strip().lower()
    if not p or p in ("—", "-", "n/a"):
        return ""
    tokens = re.findall(r"\([^)]+\)", p)
    if tokens:
        return "".join(tokens)
    return re.sub(r"\s+", "", p)


def _priority_amount_dedup_key(c: FeeCandidate) -> tuple[str, str] | None:
    """(priority, amount) when both are present; else (sub_category, amount)."""
    amt = parse_number(c.amount_paid)
    if amt is None or abs(amt) < 1e-9:
        return None
    amt_s = _format_amount(amt)
    pri = _normalize_priority_key(c.priority)
    if pri:
        return (f"pri:{pri}", amt_s)
    sub = _classify_sub_category(c.description)
    return (f"sub:{sub}", amt_s)


def _is_duplicate_fee_payment(
    candidate: FeeCandidate, existing: list[FeeCandidate]
) -> bool:
    """
    True when a supplemental row repeats a fee already captured (same label family
    and amount, same priority + amount, or same amount + same mapped sub_category).
    """
    ca = parse_number(candidate.amount_paid)
    csub = _classify_sub_category(candidate.description)
    csteps = _clause_step_tokens(candidate.priority, candidate.description)
    c_pa = _priority_amount_dedup_key(candidate)
    for e in existing:
        if c_pa is not None:
            e_pa = _priority_amount_dedup_key(e)
            if e_pa is not None and e_pa == c_pa:
                return True
        if _fee_descriptions_match(candidate.description, e.description):
            ea = parse_number(e.amount_paid)
            if ca is None or ea is None:
                return True
            tol = max(0.01, 1e-8 * max(abs(ca), abs(ea), 1.0))
            if abs(ca - ea) <= tol:
                return True
        ea = parse_number(e.amount_paid)
        if ca is None or ea is None:
            continue
        tol = max(0.01, 1e-8 * max(abs(ca), abs(ea), 1.0))
        if abs(ca - ea) > tol:
            continue
        if csub == _classify_sub_category(e.description):
            return True
        # Waterfall already captured subordinate management — ignore supplemental pool mis-reads.
        if csub == "subordinate_management_fees" and _classify_sub_category(
            e.description
        ) == "subordinate_management_fees":
            return True
        # Same waterfall step ($) already in primary under a sibling admin sub_category.
        esteps = _clause_step_tokens(e.priority, e.description)
        if csteps and esteps and csteps & esteps:
            admin_subs = frozenset(
                {
                    "administrator_expenses",
                    "collateral_admin_fees",
                    "trustee_expenses",
                    "coissuer_fees",
                }
            )
            if (
                csub in admin_subs
                and _classify_sub_category(e.description) in admin_subs
            ):
                return True
    return False


def _source_text_block(text: str) -> str:
    m = re.search(r"^## Source Text\s*$", text, re.MULTILINE | re.IGNORECASE)
    if not m:
        return ""
    return text[m.end() :]


def _amounts_on_line(line: str) -> list[float]:
    vals: list[float] = []
    for raw in re.findall(r"\$?\s*[\d,]+\.\d{2}", line):
        v = parse_number(raw)
        if v is not None and abs(v) >= 1e-9:
            vals.append(v)
    return vals


_SOURCE_TEXT_MGMT_FEE = re.compile(
    r"\b("
    r"base\s+collateral\s+management\s+fee|"
    r"additional\s+collateral\s+management\s+fee|"
    r"base\s+management\s+fee|"
    r"subordinated\s+(?:asset\s+)?management\s+fee|"
    r"any\s+subordinated\s+(?:asset\s+)?management\s+fee|"
    r"senior\s+(?:asset\s+)?management\s+fee|"
    r"subordinated\s+investment\s+management\s+fee|"
    r"subordinated\s+management\s+fee|"
    r"payment\s+of\s+(?:the\s+)?(?:base|subordinated|senior)\s+.*?management\s+fee"
    r")\b",
    re.I,
)

# Principal / cross-reference ladder lines that mention a fee label but carry pool $ only.
_SOURCE_TEXT_SUPPLEMENTAL_MGMT_EXCLUDE = re.compile(
    r"\(xx\)\s+through\s+\(xxii\)|"
    r"interest\s+priority\s+\([a-z0-9]+\)|"
    r"priority\s+of\s+principal\s+payments|"
    r"amounts\s+referred\s+to\s+in\s+clause|"
    r"settle\s+date\s+principal\s+proceeds|"
    r"holders?\s+of\s+(?:the\s+)?subordinated\s+notes?|"
    r"remains?\s+due\s+and\s+unpaid\s+in\s+respect\s+of\s+any\s+prior\s+payment",
    re.I,
)

# Pasted ## Source Text from ### Administrative Expenses grid — not separate 05 rows.
_SOURCE_TEXT_ADMIN_VOUCHER = re.compile(
    r"\b("
    r"trustee\s+fee|"
    r"collateral\s+administration|"
    r"information\s+agent|"
    r"custody|"
    r"account\s+bank|"
    r"calculation\s+agent|"
    r"securitisation\s+transparency|"
    r"uk\s+securitisation\s+regulation|"
    r"fitch\s+ratings|"
    r"maples\s+group|"
    r"bny\s+csdr|"
    r"findox|"
    r"s\s+and\s+p\s+global|"
    r"rating\s+agenc"
    r")\b",
    re.I,
)


def _source_text_fee_eligible(
    desc: str,
    *,
    admin_grid_present: bool = False,
    line: str = "",
) -> bool:
    """Admin voucher detail lines (Annual Fee, Total Expenses, …) are not separate 05 rows."""
    blob = f"{desc} {line}".strip()
    if _SOURCE_TEXT_SUPPLEMENTAL_MGMT_EXCLUDE.search(blob):
        return False
    if re.search(r"\bminimum\s+annual\b", desc, re.I):
        return False
    if admin_grid_present and _SOURCE_TEXT_ADMIN_VOUCHER.search(desc):
        return False
    if not _looks_like_fee(desc):
        return False
    return bool(_SOURCE_TEXT_MGMT_FEE.search(desc))


def _all_amounts_on_line(line: str) -> list[float]:
    """Every ``$`` / decimal on the line, including **0.00** (position = paid vs running)."""
    vals: list[float] = []
    for raw in re.findall(r"\$?\s*[\d,]+\.\d{2}", line or ""):
        v = parse_number(raw)
        if v is not None:
            vals.append(v)
    return vals


def _source_text_paid_from_line(line: str) -> float | None:
    """
    Cash **paid** on a Source Text line — not running balance / pool remainder.

    Wells / indenture ladders often end ``$0.00 $1,145,147.23`` (paid, then running).
    Do **not** skip zero paid and take the pool **$** as fee cash.
    """
    s = re.sub(r"^>\s*", "", (line or "").strip())
    if not s:
        return None
    m4 = _SOURCE_TEXT_FOUR_AMOUNTS.search(s)
    if m4:
        return parse_number(m4.group("paid"))
    m2 = re.search(r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$", s)
    if m2:
        return parse_number(m2.group(1))
    m3 = re.search(
        r"\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$",
        s,
    )
    if m3:
        return parse_number(m3.group(1))
    amounts = _all_amounts_on_line(s)
    if not amounts:
        return None
    return amounts[0]


def _collect_from_source_text(
    text: str,
    *,
    admin_grid_present: bool = False,
) -> list[FeeCandidate]:
    """
    Admin voucher / pasted fee lines in ## Source Text (e.g. Base vs Subordinated
    management fees on the same page) when not present in ### Waterfall table.
    """
    block = _source_text_block(text)
    if not block:
        return []
    out: list[FeeCandidate] = []
    seen_norm: set[str] = set()
    for line in block.splitlines():
        s = line.strip()
        if not s or s.startswith("---"):
            continue
        desc: str | None = None
        paid: float | None = None
        mo = re.match(r"^(?P<desc>.+?)\s+USD\s+(.+)$", s, re.I)
        if mo:
            desc = mo.group("desc").strip()
            paid = _source_text_paid_from_line(s)
        else:
            mo2 = re.match(
                r"^(?P<desc>(?:Payment of\s+)?.+?(?:\bFee\b|\bExpenses?\b))"
                r"(?:\s+\$|\s+[\d,])",
                s,
                re.I,
            )
            if mo2:
                desc = mo2.group("desc").strip()
                paid = _source_text_paid_from_line(s)
            else:
                mo3 = re.match(
                    r"^(?P<desc>.+?\b(?:Asset\s+)?Management\s+Fee\b.*?)(?:\s+\$|\s+[\d,])",
                    s,
                    re.I,
                )
                if mo3:
                    desc = mo3.group("desc").strip()
                    paid = _source_text_paid_from_line(s)
        if desc:
            desc = re.sub(r"^>\s*", "", desc).strip()
        if not desc or paid is None or abs(paid) < 1e-9:
            continue
        if not _source_text_fee_eligible(
            desc, admin_grid_present=admin_grid_present, line=s
        ):
            continue
        norm = _normalize_fee_desc(desc)
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        out.append(
            FeeCandidate(
                source="source_text",
                description=desc,
                amount_paid=_format_amount(paid),
            )
        )
    return out


_PARENT_XXIII_LINE = re.compile(r"^\(xxiii\)\s*$", re.I)
_ORPHAN_CLAUSE_AB_DPR = re.compile(
    r"^\(([AB])\)\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s+\$([\d,]+\.\d{2})\s*$",
    re.I,
)


def _extraction_dir_chunk_text(extraction_dir: Path) -> str:
    chunk_dir = extraction_dir / "_chunks"
    if not chunk_dir.is_dir():
        return ""
    parts: list[str] = []
    for f in sorted(chunk_dir.glob("pages_*.txt")):
        parts.append(f.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def _extended_fee_lookup_text(text03: str, extraction_dir: Path) -> str:
    """``03`` Source Text plus ``_chunks/`` when page-7 ladder lines were omitted from ``03``."""
    return text03 + "\n" + _extraction_dir_chunk_text(extraction_dir)


def _collect_xxiii_sub_mgmt_orphans(text: str) -> list[FeeCandidate]:
    """
    (xxiii)(A) Subordinated Asset Management Fee when the PDF prints only
    ``(xxiii)`` then ``(A) $paid $paid $running $0`` without a fee label on the same line.
    """
    out: list[FeeCandidate] = []
    prev = ""
    for line in text.splitlines():
        s = re.sub(r"^>\s*", "", line.strip())
        if not s:
            continue
        if _PARENT_XXIII_LINE.match(s):
            prev = s
            continue
        m = _ORPHAN_CLAUSE_AB_DPR.match(s)
        if m and _PARENT_XXIII_LINE.match(prev):
            letter = m.group(1).upper()
            paid = parse_number(m.group(3))
            if letter == "A" and paid is not None and paid > 1e-9:
                out.append(
                    FeeCandidate(
                        source="source_text",
                        description="accrued and unpaid Subordinated Asset Management Fee",
                        amount_paid=_format_amount(paid),
                        priority="(a)(xxiii)(A)",
                    )
                )
            prev = ""
            continue
        if re.match(r"^\(xx", s, re.I):
            prev = s if _PARENT_XXIII_LINE.match(s) else ""
        elif not re.match(r"^\([A-Za-z0-9]+\)\s*$", s):
            prev = ""
    return out


def merge_fee_candidates(
    primary_rows: list[FeeCandidate],
    supplemental_rows: list[FeeCandidate],
) -> tuple[list[FeeCandidate], list[FeeCandidate]]:
    """
    Add supplemental rows only when they are not the same fee already in primary
    (label + amount, or amount + sub_category). Same amount with different fee types
    (e.g. two management fees) are kept.
    """
    if not primary_rows:
        return list(supplemental_rows), []
    if not supplemental_rows:
        return list(primary_rows), []

    kept: list[FeeCandidate] = []
    dropped: list[FeeCandidate] = []
    for row in supplemental_rows:
        if _is_duplicate_fee_payment(row, primary_rows):
            dropped.append(row)
        else:
            kept.append(row)
    return primary_rows + kept, dropped


def _merge_structured_03_fees(
    wf_fees: list[FeeCandidate],
    ladder_fees: list[FeeCandidate],
    continuation_fees: list[FeeCandidate],
    source_fees: list[FeeCandidate],
) -> tuple[list[FeeCandidate], list[FeeCandidate]]:
    """
    Combine waterfall, ladder, continuations, and source-text candidates.

    Uses **### Waterfall table** when it yields fee rows; otherwise **### Disbursement
    ladder** is primary (clause-only / logical layouts without a grid).
    """
    dropped: list[FeeCandidate] = []
    if wf_fees:
        primary, d = merge_fee_candidates(wf_fees, ladder_fees)
        dropped.extend(d)
    elif ladder_fees:
        primary = list(ladder_fees)
    else:
        primary = []

    primary, d = merge_fee_candidates(primary, continuation_fees)
    dropped.extend(d)
    primary, d = merge_fee_candidates(primary, source_fees)
    dropped.extend(d)
    return primary, dropped


def _dedupe_fee_candidates_final(
    candidates: list[FeeCandidate],
) -> tuple[list[FeeCandidate], list[FeeCandidate]]:
    """
    Last-pass dedup: one fee payment per (priority, amount) or (sub_category, amount).

    Prevents double-counting when **### Waterfall table** and **### Disbursement ladder**
    (or **### Continuations / sub-lines**) repeat the same clause cash.
    """
    kept: list[FeeCandidate] = []
    dropped: list[FeeCandidate] = []
    seen: set[tuple[str, str]] = set()
    for c in candidates:
        key = _priority_amount_dedup_key(c)
        if key is None:
            kept.append(c)
            continue
        if key in seen:
            dropped.append(c)
            continue
        seen.add(key)
        kept.append(c)
    return kept, dropped


def _mapped_row_specificity(r: MappedRow) -> int:
    """Higher = prefer this row when deduping same sub_category + amount."""
    d = r.description.lower()
    score = len(d)
    if re.search(r"\b(management\s+fee|portfolio\s+management|taxes?\s+and\s+governmental)\b", d):
        score += 40
    if re.search(r"\bunpaid\s+administrative\b", d):
        score -= 30
    if d.strip() in ("trustee", "administrator", "bank"):
        score -= 20
    return score


def _dedupe_mapped_rows(rows: list[MappedRow]) -> list[MappedRow]:
    """One row per (sub_category, amount_paid, priority); keep the most specific description."""
    best: dict[tuple[str, str, str], MappedRow] = {}
    for r in rows:
        key = (r.sub_category, r.amount_paid, (r.priority or "").strip())
        prev = best.get(key)
        if prev is None or _mapped_row_specificity(r) > _mapped_row_specificity(prev):
            best[key] = r
    return list(best.values())


def _aggregate_mapped_rows_by_sub_category(rows: list[MappedRow]) -> list[MappedRow]:
    """
    One row per ``sub_category``; sum ``Amount paid`` across waterfall steps.

    Line-level rows remain in ``fee_mapping_report.md``; ``05`` and XML use this roll-up.
    """
    if not rows:
        return []
    buckets: dict[str, list[MappedRow]] = {}
    for r in rows:
        buckets.setdefault(r.sub_category, []).append(r)

    out: list[MappedRow] = []
    for sub in sorted(buckets.keys()):
        group = buckets[sub]
        total = 0.0
        for r in group:
            v = parse_number(r.amount_paid)
            if v is not None:
                total += v
        best = max(group, key=_mapped_row_specificity)
        mains = {r.main_category for r in group}
        main = (
            best.main_category
            if len(mains) == 1
            else max(group, key=lambda r: parse_number(r.amount_paid) or 0.0).main_category
        )

        priorities: list[str] = []
        for r in group:
            p = (r.priority or "").strip()
            if p and p not in priorities:
                priorities.append(p)
        if len(group) == 1:
            priority = (group[0].priority or "").strip() or "—"
        elif len(priorities) == 1:
            priority = priorities[0]
        else:
            priority = "—"

        sources = {r.source for r in group}
        source = best.source if len(sources) == 1 else "waterfall"

        out.append(
            MappedRow(
                main_category=main,
                sub_category=sub,
                amount_paid=_format_amount(total),
                description=best.description,
                source=source,
                priority=priority,
            )
        )
    return out


def map_candidates(
    candidates: list[FeeCandidate],
) -> tuple[list[MappedRow], list[FeeCandidate], list[MappedRow]]:
    """
    Map waterfall candidates to DB rows.

    Returns (line_level_rows, skipped_zero_paid, catch_all_admin_line_rows) where
    catch_all rows were remapped from **Other** / unlabeled payees to
    ``administrator_expenses``.
    """
    mapped: list[MappedRow] = []
    skipped: list[FeeCandidate] = []
    catch_all: list[MappedRow] = []
    for c in candidates:
        paid_val = parse_number(c.amount_paid)
        if paid_val is None or abs(paid_val) < 1e-9:
            skipped.append(c)
            continue
        raw_main, raw_sub = _classify(c.description, 0)
        main, sub = _classify_for_downstream(c.description, 0)
        if raw_main == "Other" or raw_sub in OTHER_FEE_LITERALS:
            catch_all.append(
                MappedRow(
                    main_category=main,
                    sub_category=sub,
                    amount_paid=c.amount_paid,
                    description=c.description,
                    source=c.source,
                    priority=c.priority,
                )
            )
        mapped.append(
            MappedRow(
                main_category=main,
                sub_category=sub,
                amount_paid=c.amount_paid,
                description=c.description,
                source=c.source,
                priority=c.priority,
            )
        )
    mapped = _dedupe_mapped_rows(mapped)
    return mapped, skipped, catch_all


def _sum_amounts(amounts: list[str]) -> float:
    total = 0.0
    for s in amounts:
        v = parse_number(s)
        if v is not None:
            total += v
    return total


def _escape_cell(s: str) -> str:
    return (s or "").replace("|", "/").replace("\n", " ")


def write_05(
    out_dir: Path,
    rows: list[MappedRow],
    src_note: str,
    *,
    line_level_count: int | None = None,
) -> None:
    rollup_note = ""
    if line_level_count is not None and line_level_count > len(rows):
        rollup_note = (
            f" Roll-up: {line_level_count} waterfall line(s) → {len(rows)} row(s) "
            f"(same **Sub category** → summed **Amount paid**)."
        )
    lines = [
        "# Valuation-Relevant Fees",
        "",
        "## Extracted Data",
        "",
        "> Populated by `map_valuation_fees.py` from **`03` fee rows** in "
        f"`{SRC_03}` — **### Waterfall table** when present, else **### Disbursement ladder** "
        "(clause-only layouts). **Tax** → `tax_gross_amounts`; **Trustee** → "
        "`trustee_expenses`; unmapped payees → `administrator_expenses` (summed). "
        "Not from **### Administrative Expenses grid**. "
        f"Same **Sub category** rows are merged.{rollup_note} Re-run after editing `03`.",
        "",
        "### Valuation-relevant fees",
        "| Main category | Sub category | Priority | Amount paid |",
        "|---------------|-------------|----------|-------------|",
    ]
    if rows:
        for r in rows:
            pri = _escape_cell(r.priority) or "—"
            lines.append(
                f"| {r.main_category} | {r.sub_category} | {pri} | {r.amount_paid} |"
            )
    else:
        lines.append("| N/A | N/A | N/A | N/A |")
    lines.extend(
        [
            "",
            "### Mapping notes",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| Source | {src_note} |",
            f"| Row count | {len(rows)} |",
            "",
            "## Completeness Checklist",
            "- [ ] Re-run after waterfall edits",
            "- [ ] Review unmapped lines in `fee_mapping_report.md` if any",
            "",
            "## Source Text",
            "(See `03_interest_principal_waterfall.md` — fee lines are rolled up from the waterfall / ladder.)",
            "",
        ]
    )
    (out_dir / OUT_FILE).write_text("\n".join(lines), encoding="utf-8")


def write_report(
    out_dir: Path,
    mapped: list[MappedRow],
    skipped: list[FeeCandidate],
    unmapped: list[FeeCandidate],
    *,
    dropped_ladder_duplicates: list[FeeCandidate] | None = None,
    admin_grid_present: bool = False,
    waterfall_excluded: list[str] | None = None,
    catch_all_admin: list[MappedRow] | None = None,
    coverage: dict[str, float] | None = None,
) -> None:
    dropped_ladder_duplicates = dropped_ladder_duplicates or []
    waterfall_excluded = waterfall_excluded or []
    catch_all_admin = catch_all_admin or []
    lines = [
        "# Fee mapping report",
        "",
        "> Line-level waterfall mapping (before **Sub category** roll-up in `05`).",
        "",
        "**DB policy:** All non-zero fee rows from **### Waterfall table** and/or "
        "**### Disbursement ladder** → **Tax** / **trustee_expenses** / known literals / "
        "**`administrator_expenses`** (catch-all).",
        "",
        f"- **Mapped rows:** {len(mapped)}",
        f"- **Skipped (zero paid):** {len(skipped)}",
        f"- **Unmapped:** {len(unmapped)}",
        f"- **Waterfall rows excluded (class / structural):** {len(waterfall_excluded)}",
        f"- **Catch-all admin (`administrator_expenses`) line items:** {len(catch_all_admin)}",
        f"- **Supplemental / duplicate rows dropped (waterfall vs ladder / continuations):** "
        f"{len(dropped_ladder_duplicates)}",
        f"- **Administrative Expenses grid in 03:** "
        + ("present (not used for 05 — map from waterfall only)" if admin_grid_present else "not present"),
        "",
    ]
    if coverage:
        lines.extend(
            [
                "## Coverage reconciliation",
                "",
                f"- **Waterfall fee candidates (sum):** {_format_amount(coverage.get('candidates', 0))}",
                f"- **05 roll-up (sum):** {_format_amount(coverage.get('aggregated', 0))}",
                f"- **Delta:** {_format_amount(coverage.get('delta', 0))}",
                "",
            ]
        )
        if abs(coverage.get("delta", 0.0)) > 0.02:
            lines.append(
                "> Review: candidate total should match `05` after roll-up (dedupe may differ slightly)."
            )
            lines.append("")
    if catch_all_admin:
        lines.append("## Catch-all administrator_expenses (was Other / unlabeled)")
        for r in catch_all_admin[:40]:
            lines.append(
                f"- {_format_amount(parse_number(r.amount_paid))}: "
                f"{_escape_cell(r.description)[:100]}"
            )
        if len(catch_all_admin) > 40:
            lines.append(f"\n… and {len(catch_all_admin) - 40} more.")
        lines.append("")
    if waterfall_excluded:
        lines.append("## Excluded waterfall rows (class / structural)")
        for label in waterfall_excluded[:30]:
            lines.append(f"- {_escape_cell(label)}")
        if len(waterfall_excluded) > 30:
            lines.append(f"\n… and {len(waterfall_excluded) - 30} more.")
        lines.append("")
    if mapped:
        lines.append("## Mapped")
        lines.append("| Main | Sub | Amount paid | Source | Priority | Description |")
        lines.append("|------|-----|-------------|--------|----------|-------------|")
        for r in mapped[:80]:
            desc = _escape_cell(r.description)[:100]
            pri = _escape_cell(r.priority)[:40]
            lines.append(
                f"| {r.main_category} | {r.sub_category} | {r.amount_paid} | "
                f"{r.source} | {pri} | {desc} |"
            )
        if len(mapped) > 80:
            lines.append(f"\n… and {len(mapped) - 80} more mapped rows.")
        lines.append("")
    if skipped:
        lines.append("## Skipped (class cashflow / non-fee)")
        for c in skipped[:30]:
            lines.append(f"- `{c.source}`: {_escape_cell(c.description)[:100]}")
        lines.append("")
    if unmapped:
        lines.append("## Unmapped")
        for c in unmapped[:30]:
            lines.append(
                f"- `{c.source}` paid={c.amount_paid}: {_escape_cell(c.description)[:100]}"
            )
        lines.append("")
    if dropped_ladder_duplicates:
        lines.append(
            "## Supplemental skipped (same fee already in waterfall / ladder — label or amount + fee type)"
        )
        for c in dropped_ladder_duplicates[:40]:
            lines.append(
                f"- paid={c.amount_paid} `{_classify_sub_category(c.description)}`: "
                f"{_escape_cell(c.description)[:100]}"
            )
        if len(dropped_ladder_duplicates) > 40:
            lines.append(f"\n… and {len(dropped_ladder_duplicates) - 40} more.")
        lines.append("")
    (out_dir / REPORT_FILE).write_text("\n".join(lines), encoding="utf-8")


def run(extraction_dir: Path) -> dict[str, object]:
    p03 = extraction_dir / SRC_03
    if not p03.is_file():
        raise FileNotFoundError(f"Missing {SRC_03} under {extraction_dir}")

    text03 = p03.read_text(encoding="utf-8", errors="replace")
    tables = parse_md_tables(text03)

    wf = find_waterfall_table(tables)
    ladder = _find_disbursement_ladder(tables)
    continuations = _find_continuations_table(tables)
    admin_grid_present = _admin_expenses_grid_present(tables)
    lookup_text = _extended_fee_lookup_text(text03, extraction_dir)
    source_paid_lookup = _build_source_text_paid_lookup(lookup_text)

    wf_excluded: list[str] = []
    if wf:
        wf_fees, wf_excluded = _collect_from_waterfall(wf, source_paid=source_paid_lookup)
    else:
        wf_fees = []
    ladder_fees = (
        _collect_from_ladder(ladder, source_paid=source_paid_lookup) if ladder else []
    )
    continuation_fees = (
        _collect_from_continuations(continuations, source_paid=source_paid_lookup)
        if continuations
        else []
    )
    source_fees = _collect_from_source_text(text03, admin_grid_present=admin_grid_present)
    source_fees += _collect_xxiii_sub_mgmt_orphans(
        _source_text_block(text03) + "\n" + _extraction_dir_chunk_text(extraction_dir)
    )

    candidates, dropped_supplemental = _merge_structured_03_fees(
        wf_fees, ladder_fees, continuation_fees, source_fees
    )
    candidates, dropped_final = _dedupe_fee_candidates_final(candidates)
    dropped_supplemental = dropped_supplemental + dropped_final
    unique = candidates

    mapped_line, skipped, catch_all_admin = map_candidates(unique)
    aggregated = _aggregate_mapped_rows_by_sub_category(mapped_line)
    unmapped: list[FeeCandidate] = []

    cand_total = _sum_amounts([c.amount_paid for c in unique])
    agg_total = _sum_amounts([r.amount_paid for r in aggregated])
    coverage = {
        "candidates": cand_total,
        "aggregated": agg_total,
        "delta": cand_total - agg_total,
    }

    src = f"{SRC_03}"
    if wf_fees:
        src += " (### Waterfall table — primary; Source Text Paid when grid mis-maps)"
    elif ladder_fees:
        src += " (### Disbursement ladder — primary; no grid fee rows in ### Waterfall table)"
    if ladder_fees and wf_fees:
        src += " (### Disbursement ladder — supplemental when not duplicate)"
    if continuation_fees:
        src += " (### Continuations / sub-lines — supplemental when itemized)"
    if source_fees:
        src += " (## Source Text — supplemental management fees when not in waterfall)"
    if admin_grid_present:
        src += " (### Administrative Expenses grid present in 03 — not used for 05)"

    write_05(
        extraction_dir,
        aggregated,
        src,
        line_level_count=len(mapped_line),
    )
    write_report(
        extraction_dir,
        mapped_line,
        skipped,
        unmapped,
        dropped_ladder_duplicates=dropped_supplemental,
        admin_grid_present=admin_grid_present,
        waterfall_excluded=wf_excluded,
        catch_all_admin=catch_all_admin,
        coverage=coverage,
    )

    return {
        "output_file": str(extraction_dir / OUT_FILE),
        "report_file": str(extraction_dir / REPORT_FILE),
        "mapped_count": len(aggregated),
        "mapped_line_level_count": len(mapped_line),
        "skipped_count": len(skipped),
        "candidate_count": len(unique),
        "dropped_ladder_duplicate_count": len(dropped_supplemental),
        "source_text_fee_count": len(source_fees),
        "waterfall_excluded_count": len(wf_excluded),
        "catch_all_admin_count": len(catch_all_admin),
        "coverage_delta": coverage["delta"],
    }


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
    ap = argparse.ArgumentParser(description="Map waterfall fees to 05_valuation_relevant_fees.md")
    ap.add_argument("extraction_dir", type=Path)
    args = ap.parse_args()
    exdir = args.extraction_dir.resolve()
    if not exdir.is_dir():
        print(f"Not a directory: {exdir}", file=sys.stderr)
        return 1
    try:
        result = run(exdir)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(result["output_file"])
    print(f"Mapped {result['mapped_count']} fee row(s) from {result['candidate_count']} candidate(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
