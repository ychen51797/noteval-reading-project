"""
validate_noteval.py — Lightweight checks on noteval_extractor markdown outputs.

Rules (initial):
  1. FAIL if there is no tranche/class data (no populated class rows in 02).
  2. WARN if a waterfall/proceeds table exists but no fee-like rows are detected.
  3. WARN if every class row has interest payment zero or blank (possible extraction gap).

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
    """Table whose header includes Class + Beginning balance + Interest payment."""
    for table in tables:
        if not table or len(table[0]) < 3:
            continue
        h = _header_join(table[0])
        if "class" in h and "beginning balance" in h and "interest payment" in h:
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
    tl = text.lower()
    if "section not present" in tl:
        return True
    for table in parse_md_tables(text):
        for row in table[1:]:
            if len(row) < 2:
                continue
            k, v = row[0].strip().lower(), row[1].strip().lower()
            if "section present" in k and v in ("n", "no"):
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
                "No table with headers Class + Beginning balance + Interest payment.",
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

    int_col = column_index_interest_payment(cb[0])
    if int_col is not None and data_rows:
        values: list[float | None] = []
        for row in data_rows:
            v = parse_number(row[int_col]) if int_col < len(row) else None
            values.append(v)
        numeric = [v for v in values if v is not None]
        # Warn when every class row has interest 0 or blank (no nonzero amount).
        all_zero_or_blank = bool(values) and not any(
            v is not None and abs(v) > 1e-9 for v in values
        )

        if all_zero_or_blank and data_rows:
            checks.append(
                Check(
                    "interest",
                    "Interest payment column not all zero/blank",
                    False,
                    "Every class row has interest payment 0, blank, or N/A - "
                    "confirm this matches the PDF or re-extract.",
                    "warn",
                )
            )
        else:
            checks.append(
                Check(
                    "interest",
                    "Interest payment column not all zero/blank",
                    True,
                    f"{len(numeric)} numeric interest cell(s), at least one nonzero.",
                    "info",
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
