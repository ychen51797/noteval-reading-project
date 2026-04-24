"""
validate_noteval.py — Lightweight checks on noteval_extractor markdown outputs.

Rules (initial):
  1. FAIL if there is no tranche/class data (no populated class rows in 02).
  2. WARN if a waterfall/proceeds table exists but no fee-like rows are detected.
  3. WARN if **all** tranches (class rows) have **Interest payment**, **Interest
     payable**, and **Dividend** each zero or blank — i.e. no row has a nonzero in
     payment **or** payable **or** dividend (possible extraction gap). Subordinated
     notes often use **Dividend**; payable-only layouts use **Interest payable**.
  4. WARN if **all** tranches have **Original balance**, **Beginning balance**, and
     **Ending balance** each zero or blank (possible extraction gap). Deals with
     only **subordinated notes** left and seniors at zero are **normal** — such a
     deal passes as long as the sub row has a nonzero balance in any of those columns.
  5. WARN if **Ending balance** ≠ **Beginning balance** + **Deferred interest**
     − **Principal payment** (within tolerance) on class rows where **Principal
     payable** is blank/zero (rows with nonzero **Principal payable** are skipped
     — voucher-style layouts).

Usage:
    python validate_noteval.py <extraction_dir>
    python validate_noteval.py <extraction_dir> --strict   # exit 1 on warnings too

Writes validation_report.md into <extraction_dir>.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REQUIRED_FILES = (
    "01_report_metadata.md",
    "02_tranche_class_balances.md",
    "07_extraction_summary.md",
)


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


# Principal roll-forward: ending ≈ beginning + deferred_interest − principal_payment
PRINCIPAL_ROLLFORWARD_ABS_TOL = 0.02


def principal_rollforward_row_stats(
    header: list[str],
    data_rows: list[list[str]],
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

    for row in data_rows:
        cls = row[0].strip() if row else "?"
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


FEE_KEYWORDS = re.compile(
    r"\b(fee|fees|servicing|master serv|trustee|"
    r"administration|administrator|custodian|"
    r"expense|expenses|issuer|guarantor|swap|"
    r"indemn|reimburse|pfa|payment facilitation)\b",
    re.I,
)


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

    if data_rows and cb:
        n_pr, n_bad, pr_msgs = principal_rollforward_row_stats(cb[0], data_rows)
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
            checks.append(
                Check(
                    "balances",
                    "Principal roll-forward (ending ≈ beg + deferred − principal pmt)",
                    False,
                    detail.strip(),
                    "warn",
                )
            )

    p04 = out_dir / "04_interest_principal_waterfall.md"
    if p04.is_file():
        text04 = p04.read_text(encoding="utf-8", errors="replace")
        if file_section_absent(text04):
            checks.append(
                Check(
                    "waterfall",
                    "Fee-like rows in waterfall",
                    True,
                    "Waterfall section marked not present - fee check skipped.",
                    "info",
                )
            )
        else:
            tables04 = parse_md_tables(text04)
            wf = find_waterfall_table(tables04)
            if not wf:
                checks.append(
                    Check(
                        "waterfall",
                        "Waterfall table found",
                        False,
                        "04 has no recognizable waterfall/proceeds table "
                        "(expected Priority + Item/payee + Amount paid).",
                        "warn",
                    )
                )
            else:
                wrows = waterfall_data_rows(wf)
                if not wrows:
                    checks.append(
                        Check(
                            "waterfall",
                            "Waterfall has data rows",
                            False,
                            "Waterfall table has no data rows.",
                            "warn",
                        )
                    )
                else:
                    fee_hits = sum(
                        1 for r in wrows if FEE_KEYWORDS.search(row_description(wf, r))
                    )
                    if fee_hits == 0:
                        checks.append(
                            Check(
                                "waterfall",
                                "Fee-like rows in waterfall",
                                False,
                                f"{len(wrows)} waterfall row(s), none matched fee/servicing/"
                                f"trustee keywords - verify fees were extracted.",
                                "warn",
                            )
                        )
                    else:
                        checks.append(
                            Check(
                                "waterfall",
                                "Fee-like rows in waterfall",
                                True,
                                f"{fee_hits} row(s) matched fee-like pattern.",
                                "info",
                            )
                        )

            # Optional fee mirror table
            for table in tables04:
                if not table or len(table[0]) < 2:
                    continue
                h = _header_join(table[0])
                if "fee name" in h and "paid" in h:
                    fee_rows = [r for r in table[1:] if any(c.strip() for c in r)]
                    if fee_rows:
                        checks.append(
                            Check(
                                "waterfall",
                                "Optional fee mirror table populated",
                                True,
                                f"{len(fee_rows)} fee mirror row(s).",
                                "info",
                            )
                        )
                    break
    else:
        checks.append(
            Check(
                "waterfall",
                "File 04 present for waterfall/fee checks",
                False,
                "04_interest_principal_waterfall.md missing - add if PDF has waterfall.",
                "warn",
            )
        )

    return checks


def write_report(out_dir: Path, checks: list[Check]) -> None:
    errors = sum(1 for c in checks if not c.ok and c.severity == "error")
    warns = sum(1 for c in checks if not c.ok and c.severity == "warn")
    oks = sum(1 for c in checks if c.ok)

    lines = [
        "# Noteval extraction validation report",
        "",
        f"- **Checks OK:** {oks}",
        f"- **Errors:** {errors}",
        f"- **Warnings:** {warns}",
        "",
    ]
    if errors == 0 and warns == 0:
        lines.append("**STATUS: PASS** (no errors or warnings)")
    elif errors == 0:
        lines.append("**STATUS: PASS WITH WARNINGS** - review warnings below")
    else:
        lines.append("**STATUS: FAIL** - fix errors before relying on extraction")

    lines.extend(["", "## Results", "", "| Category | Check | Severity | Status | Detail |"])
    lines.append("|----------|-------|----------|--------|--------|")
    for c in checks:
        status = "OK" if c.ok else ("FAIL" if c.severity == "error" else "WARN")
        sev = c.severity.upper()
        detail = (c.detail or "").replace("|", "/")
        lines.append(
            f"| {c.category} | {c.name} | {sev} | {status} | {detail} |"
        )

    if errors or warns:
        lines.extend(["", "## Items needing attention", ""])
        for c in checks:
            if not c.ok:
                lines.append(f"- **{c.category} / {c.name}** ({c.severity}): {c.detail}")

    (out_dir / "validation_report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate noteval_extractor markdown outputs.")
    parser.add_argument("extraction_dir", type=Path, help="Directory with 01_*.md … 07_*.md")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any warnings (not only errors).",
    )
    args = parser.parse_args()
    out_dir: Path = args.extraction_dir

    if not out_dir.is_dir():
        print(f"ERROR: Not a directory: {out_dir}", file=sys.stderr)
        return 1

    checks = validate_dir(out_dir)
    write_report(out_dir, checks)

    errors = [c for c in checks if not c.ok and c.severity == "error"]
    warns = [c for c in checks if not c.ok and c.severity == "warn"]

    report_path = out_dir / "validation_report.md"
    print(f"Wrote {report_path}")
    print(f"  errors: {len(errors)}  warnings: {len(warns)}")

    if errors:
        for c in errors:
            print(f"  FAIL: [{c.category}] {c.name}: {c.detail}", file=sys.stderr)
        return 1
    if warns and args.strict:
        for c in warns:
            print(f"  WARN: [{c.category}] {c.name}: {c.detail}", file=sys.stderr)
        return 1
    if warns:
        for c in warns:
            print(f"  WARN: [{c.category}] {c.name}: {c.detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
