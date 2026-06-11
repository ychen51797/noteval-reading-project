"""
compare_revised_report.py — Compare an original CLO/trustee extraction against a revised one.

Produces 06_revised_report_comparison.md in the revised folder with severity-tagged changes
across critical fields:
  - Note Valuation (PV / NVR) per class
  - IC / OC test ratios and Pass/Fail results
  - Interest Collection Account (ICA) balances
  - Principal Collection Account (PCA) balances
  - Class balances (02_tranche_class_balances.md)
  - Waterfall fees (05_valuation_relevant_fees.md or 03)
  - Key dates (01_report_metadata.md)

Usage:
    py -3 compare_revised_report.py <original-dir> <revised-dir>

Both directories must already contain 01_report_metadata.md and 02_tranche_class_balances.md
(extract first with the noteval-extractor-agent if needed).
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Shared helpers (mirrored from validate_noteval.py / map_valuation_fees.py)
# ---------------------------------------------------------------------------

def parse_md_tables(text: str) -> list[list[list[str]]]:
    """Parse markdown pipe tables; returns list of tables (header row + body rows)."""
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


def parse_number(s: str) -> Optional[float]:
    if not s or s.strip().upper() in ("N/A", "NA", "—", "-", ""):
        return None
    cleaned = s.replace("$", "").replace(",", "").replace("%", "").strip()
    if cleaned in ("", "—", "-"):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _header_join(row: list[str]) -> str:
    return " | ".join(h.lower().strip() for h in row)


def _col(header: list[str], *names: str) -> int:
    """Return index of first column header matching any of the given names (case-insensitive)."""
    for name in names:
        for i, h in enumerate(header):
            if name.lower() in h.lower():
                return i
    return -1


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _find_section(text: str, heading: str) -> str:
    """Extract text from a markdown heading until the next heading of same or higher level."""
    pattern = re.compile(
        r"^(#{1,4})\s+" + re.escape(heading) + r"[^\n]*\n",
        re.IGNORECASE | re.MULTILINE,
    )
    m = pattern.search(text)
    if not m:
        return ""
    level = len(m.group(1))
    end_pattern = re.compile(r"^#{1," + str(level) + r"}\s+", re.MULTILINE)
    next_m = end_pattern.search(text, m.end())
    if next_m:
        return text[m.start():next_m.start()]
    return text[m.start():]


# ---------------------------------------------------------------------------
# Severity
# ---------------------------------------------------------------------------

SEVERITY_CRITICAL = "CRITICAL"
SEVERITY_HIGH = "HIGH"
SEVERITY_LOW = "LOW"
SEVERITY_NO_CHANGE = "NO CHANGE"

ROUNDING_TOLERANCE = 0.01


def _numeric_severity(
    orig: Optional[float],
    rev: Optional[float],
    pct_threshold_high: float,
    pct_threshold_critical: Optional[float] = None,
) -> str:
    """Return severity based on percentage change."""
    if orig is None and rev is None:
        return SEVERITY_NO_CHANGE
    if orig is None or rev is None:
        # one side has value, other doesn't
        return SEVERITY_HIGH
    diff = abs(rev - orig)
    if diff <= ROUNDING_TOLERANCE:
        return SEVERITY_NO_CHANGE
    if orig == 0:
        pct = 100.0
    else:
        pct = diff / abs(orig) * 100.0
    if pct_threshold_critical is not None and pct > pct_threshold_critical:
        return SEVERITY_CRITICAL
    if pct > pct_threshold_high:
        return SEVERITY_HIGH
    return SEVERITY_LOW


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChangeRow:
    category: str
    label: str
    field: str
    original: str
    revised: str
    change_str: str
    change_pct: str
    severity: str
    page_ref: str = ""


@dataclass
class ComparisonResult:
    original_dir: Path
    revised_dir: Path
    original_deal_name: str = ""
    revised_deal_name: str = ""
    original_payment_date: str = ""
    revised_payment_date: str = ""
    original_deal_id: str = ""
    issues: list[str] = field(default_factory=list)
    changes: list[ChangeRow] = field(default_factory=list)

    @property
    def critical_count(self) -> int:
        return sum(1 for c in self.changes if c.severity == SEVERITY_CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for c in self.changes if c.severity == SEVERITY_HIGH)

    @property
    def low_count(self) -> int:
        return sum(1 for c in self.changes if c.severity == SEVERITY_LOW)

    @property
    def total_changed(self) -> int:
        return sum(1 for c in self.changes if c.severity != SEVERITY_NO_CHANGE)


# ---------------------------------------------------------------------------
# Step 1: Key dates from 01_report_metadata.md
# ---------------------------------------------------------------------------

def _extract_metadata(text: str) -> dict[str, str]:
    """Return dict of field->value from ### Key dates and ### Report identification tables."""
    result: dict[str, str] = {}
    for table in parse_md_tables(text):
        if not table or len(table[0]) < 2:
            continue
        h = _header_join(table[0])
        if "field" not in h or "value" not in h:
            continue
        for row in table[1:]:
            if len(row) >= 2:
                result[row[0].strip().lower()] = row[1].strip()
    return result


def compare_key_dates(result: ComparisonResult) -> None:
    orig_text = _read_text(result.original_dir / "01_report_metadata.md")
    rev_text = _read_text(result.revised_dir / "01_report_metadata.md")

    orig_meta = _extract_metadata(orig_text)
    rev_meta = _extract_metadata(rev_text)

    result.original_deal_name = orig_meta.get("deal / trust / series name", "")
    result.revised_deal_name = rev_meta.get("deal / trust / series name", "")
    result.original_payment_date = orig_meta.get("payment date", "")
    result.revised_payment_date = rev_meta.get("payment date", "")
    result.original_deal_id = orig_meta.get("other deal id / series code (if printed; not an isin/cusip)", "")

    # Check deal name
    if (
        result.original_deal_name
        and result.revised_deal_name
        and result.original_deal_name.lower() != result.revised_deal_name.lower()
    ):
        result.issues.append(
            f"Deal name mismatch: original='{result.original_deal_name}' "
            f"revised='{result.revised_deal_name}' — confirm same deal."
        )

    # Check payment date (CRITICAL if different)
    date_fields = ["determination date", "payment date", "distribution date"]
    for df in date_fields:
        ov = orig_meta.get(df, "N/A")
        rv = rev_meta.get(df, "N/A")
        is_changed = ov.lower() != rv.lower() and ov not in ("", "n/a") and rv not in ("", "n/a")
        severity = SEVERITY_CRITICAL if (is_changed and df == "payment date") else (
            SEVERITY_HIGH if is_changed else SEVERITY_NO_CHANGE
        )
        if is_changed:
            result.changes.append(ChangeRow(
                category="Key dates",
                label=df.title(),
                field=df,
                original=ov,
                revised=rv,
                change_str="Date changed",
                change_pct="—",
                severity=severity,
            ))


# ---------------------------------------------------------------------------
# Step 2: Class balances from 02_tranche_class_balances.md
# ---------------------------------------------------------------------------

def _extract_class_rows(text: str) -> dict[str, dict[str, str]]:
    """Parse ### Class balance table (primary) into dict[class_name -> {field: value}]."""
    section = _find_section(text, "Class balance table (primary)")
    if not section:
        # fallback: look for any table with Class + Beginning balance headers
        section = text

    tables = parse_md_tables(section)
    result: dict[str, dict[str, str]] = {}

    for table in tables:
        if not table:
            continue
        header = table[0]
        h = _header_join(header)
        if "class" not in h or "beginning balance" not in h:
            continue
        class_col = _col(header, "class")
        if class_col < 0:
            continue
        for row in table[1:]:
            if len(row) <= class_col:
                continue
            class_name = row[class_col].strip()
            if not class_name or class_name.lower() in ("class", ""):
                continue
            fields: dict[str, str] = {}
            for i, h_val in enumerate(header):
                if i < len(row):
                    fields[h_val.lower().strip()] = row[i].strip()
            result[class_name] = fields
    return result


_CLASS_NUMERIC_FIELDS = [
    ("beginning balance", 0.5, None),
    ("interest rate", 0.1, None),
    ("interest payment", 0.5, None),
    ("interest payable", 0.5, None),
    ("principal payment", 0.5, None),
    ("deferred interest", 0.5, None),
    ("ending balance", 0.5, None),
]


def compare_class_balances(result: ComparisonResult) -> None:
    orig_text = _read_text(result.original_dir / "02_tranche_class_balances.md")
    rev_text = _read_text(result.revised_dir / "02_tranche_class_balances.md")

    orig_classes = _extract_class_rows(orig_text)
    rev_classes = _extract_class_rows(rev_text)

    all_classes = sorted(set(orig_classes) | set(rev_classes))

    for cls in all_classes:
        if cls not in orig_classes:
            result.changes.append(ChangeRow(
                category="Class balances",
                label=cls,
                field="(class)",
                original="(not present)",
                revised="(added in revised)",
                change_str="New class",
                change_pct="—",
                severity=SEVERITY_CRITICAL,
            ))
            continue
        if cls not in rev_classes:
            result.changes.append(ChangeRow(
                category="Class balances",
                label=cls,
                field="(class)",
                original="(present)",
                revised="(removed in revised)",
                change_str="Class removed",
                change_pct="—",
                severity=SEVERITY_CRITICAL,
            ))
            continue

        orig_row = orig_classes[cls]
        rev_row = rev_classes[cls]

        for field_name, pct_high, pct_critical in _CLASS_NUMERIC_FIELDS:
            ov_str = orig_row.get(field_name, "")
            rv_str = rev_row.get(field_name, "")
            ov = parse_number(ov_str)
            rv = parse_number(rv_str)
            sev = _numeric_severity(ov, rv, pct_high, pct_critical)
            if sev == SEVERITY_NO_CHANGE:
                continue
            diff = (rv or 0) - (ov or 0)
            pct_change = ""
            if ov and ov != 0:
                pct_change = f"{diff / abs(ov) * 100:+.4f}%"
            result.changes.append(ChangeRow(
                category="Class balances",
                label=cls,
                field=field_name,
                original=ov_str or "N/A",
                revised=rv_str or "N/A",
                change_str=f"{diff:+,.2f}" if ov is not None or rv is not None else "—",
                change_pct=pct_change,
                severity=sev,
            ))


# ---------------------------------------------------------------------------
# Step 3: IC / OC tests from page index + chunks
# ---------------------------------------------------------------------------

_TEST_HEADING_PATTERN = re.compile(
    r"(coverage\s+test|ic\s+test|oc\s+test|overcollateral|interest\s+coverage|"
    r"quality\s+test|compliance\s+report|portfolio\s+quality)",
    re.IGNORECASE,
)

_PASS_FAIL_RE = re.compile(r"\b(pass|fail|passing|failing)\b", re.IGNORECASE)


def _extract_test_rows(text: str) -> dict[str, dict[str, str]]:
    """
    Extract IC/OC test rows from markdown text.
    Looks for tables containing 'test' / 'ratio' / 'pass' / 'fail' columns.
    Returns dict[test_name_normalized -> {field: value}].
    """
    rows: dict[str, dict[str, str]] = {}
    tables = parse_md_tables(text)
    for table in tables:
        if not table:
            continue
        header = table[0]
        h = _header_join(header)
        # Must have at least a name/test column and a ratio or pass/fail column
        has_test = any(w in h for w in ("test", "ratio", "result", "pass", "fail", "coverage"))
        if not has_test:
            continue
        name_col = _col(header, "test name", "test", "description", "item", "name")
        ratio_col = _col(header, "current ratio", "current", "ratio", "actual")
        threshold_col = _col(header, "threshold", "minimum", "min", "required", "trigger")
        prior_col = _col(header, "prior ratio", "prior", "previous")
        pf_col = _col(header, "pass", "result", "status", "p/f", "pass / fail", "pass/fail")
        num_col = _col(header, "numerator", "num")
        den_col = _col(header, "denominator", "den")

        if name_col < 0:
            continue

        for row in table[1:]:
            if len(row) <= name_col:
                continue
            name = row[name_col].strip()
            if not name or name.lower() in ("test name", "test", "description", ""):
                continue
            fields: dict[str, str] = {}
            if ratio_col >= 0 and ratio_col < len(row):
                fields["current ratio"] = row[ratio_col].strip()
            if threshold_col >= 0 and threshold_col < len(row):
                fields["threshold"] = row[threshold_col].strip()
            if prior_col >= 0 and prior_col < len(row):
                fields["prior ratio"] = row[prior_col].strip()
            if pf_col >= 0 and pf_col < len(row):
                fields["pass/fail"] = row[pf_col].strip()
            if num_col >= 0 and num_col < len(row):
                fields["numerator"] = row[num_col].strip()
            if den_col >= 0 and den_col < len(row):
                fields["denominator"] = row[den_col].strip()
            # Full row for audit
            fields["_raw"] = " | ".join(row)
            key = re.sub(r"\s+", " ", name.lower().strip())
            rows[key] = fields
    return rows


def compare_coverage_tests(result: ComparisonResult) -> None:
    """
    Compare IC/OC tests between original and revised.
    Looks in the _chunks/ text for coverage test pages referenced by _page_index.md,
    and also checks any markdown files that might contain extracted test tables.
    """
    # Try to find extracted test data in markdown outputs first
    for fname in ["03_interest_principal_waterfall.md", "04_extraction_summary.md",
                  "01_report_metadata.md"]:
        orig_text = _read_text(result.original_dir / fname)
        rev_text = _read_text(result.revised_dir / fname)
        orig_tests = _extract_test_rows(orig_text)
        rev_tests = _extract_test_rows(rev_text)
        if orig_tests or rev_tests:
            _emit_test_changes(result, orig_tests, rev_tests, fname)
            return

    # If no test tables found in standard files, scan chunks for test pages
    orig_tests = _scan_chunks_for_tests(result.original_dir)
    rev_tests = _scan_chunks_for_tests(result.revised_dir)
    if orig_tests or rev_tests:
        _emit_test_changes(result, orig_tests, rev_tests, "chunks")


def _scan_chunks_for_tests(output_dir: Path) -> dict[str, dict[str, str]]:
    """Scan _chunks/*.txt for coverage test tables."""
    page_index = _read_text(output_dir / "_page_index.md")
    test_pages: list[str] = []
    for line in page_index.splitlines():
        if _TEST_HEADING_PATTERN.search(line):
            m = re.search(r"pages?[_\-](\d+(?:[_\-]\d+)?)", line, re.IGNORECASE)
            if m:
                test_pages.append(m.group(0))

    chunks_dir = output_dir / "_chunks"
    all_tests: dict[str, dict[str, str]] = {}
    if chunks_dir.is_dir():
        for chunk_file in sorted(chunks_dir.glob("pages_*.txt")):
            chunk_text = _read_text(chunk_file)
            if _TEST_HEADING_PATTERN.search(chunk_text):
                chunk_tests = _extract_test_rows(chunk_text)
                all_tests.update(chunk_tests)
    return all_tests


def _emit_test_changes(
    result: ComparisonResult,
    orig_tests: dict[str, dict[str, str]],
    rev_tests: dict[str, dict[str, str]],
    source: str,
) -> None:
    all_tests = sorted(set(orig_tests) | set(rev_tests))
    for test_key in all_tests:
        if test_key not in orig_tests:
            result.changes.append(ChangeRow(
                category="IC/OC Tests",
                label=test_key,
                field="(test)",
                original="(not in original)",
                revised=rev_tests[test_key].get("_raw", ""),
                change_str="New test in revised",
                change_pct="—",
                severity=SEVERITY_HIGH,
            ))
            continue
        if test_key not in rev_tests:
            result.changes.append(ChangeRow(
                category="IC/OC Tests",
                label=test_key,
                field="(test)",
                original=orig_tests[test_key].get("_raw", ""),
                revised="(not in revised)",
                change_str="Test removed from revised",
                change_pct="—",
                severity=SEVERITY_HIGH,
            ))
            continue

        orig_row = orig_tests[test_key]
        rev_row = rev_tests[test_key]

        # Pass/Fail flip — CRITICAL
        orig_pf = orig_row.get("pass/fail", "").lower()
        rev_pf = rev_row.get("pass/fail", "").lower()
        if orig_pf and rev_pf and orig_pf != rev_pf:
            result.changes.append(ChangeRow(
                category="IC/OC Tests",
                label=test_key,
                field="pass/fail",
                original=orig_row.get("pass/fail", ""),
                revised=rev_row.get("pass/fail", ""),
                change_str=f"{orig_row.get('pass/fail','')} → {rev_row.get('pass/fail','')}",
                change_pct="—",
                severity=SEVERITY_CRITICAL,
            ))

        # Ratio change
        ov = parse_number(orig_row.get("current ratio", ""))
        rv = parse_number(rev_row.get("current ratio", ""))
        if ov is not None or rv is not None:
            diff = (rv or 0) - (ov or 0)
            abs_pp_change = abs(diff)
            sev = SEVERITY_NO_CHANGE
            if abs_pp_change > ROUNDING_TOLERANCE:
                sev = SEVERITY_HIGH if abs_pp_change > 0.5 else SEVERITY_LOW
            if sev != SEVERITY_NO_CHANGE:
                result.changes.append(ChangeRow(
                    category="IC/OC Tests",
                    label=test_key,
                    field="current ratio",
                    original=orig_row.get("current ratio", "N/A"),
                    revised=rev_row.get("current ratio", "N/A"),
                    change_str=f"{diff:+.4f}",
                    change_pct=f"{diff:+.4f} pp",
                    severity=sev,
                ))

        # Numerator / denominator
        for fn in ("numerator", "denominator"):
            ov = parse_number(orig_row.get(fn, ""))
            rv = parse_number(rev_row.get(fn, ""))
            sev = _numeric_severity(ov, rv, 0.1, None)
            if sev != SEVERITY_NO_CHANGE:
                diff = (rv or 0) - (ov or 0)
                pct_change = ""
                if ov and ov != 0:
                    pct_change = f"{diff / abs(ov) * 100:+.4f}%"
                result.changes.append(ChangeRow(
                    category="IC/OC Tests",
                    label=test_key,
                    field=fn,
                    original=orig_row.get(fn, "N/A"),
                    revised=rev_row.get(fn, "N/A"),
                    change_str=f"{diff:+,.2f}",
                    change_pct=pct_change,
                    severity=sev,
                ))


# ---------------------------------------------------------------------------
# Step 4: Account balances (ICA / PCA) from chunks
# ---------------------------------------------------------------------------

_ICA_PATTERNS = re.compile(
    r"interest\s+collection\s+account|ica\b|interest\s+account",
    re.IGNORECASE,
)
_PCA_PATTERNS = re.compile(
    r"principal\s+collection\s+account|pca\b|principal\s+account",
    re.IGNORECASE,
)

_ACCOUNT_FIELD_MAP = [
    ("opening balance", ["opening", "beginning", "prior", "start", "balance at beginning"]),
    ("total deposits", ["deposit", "collection", "received", "inflow", "proceeds received"]),
    ("total disbursements", ["disbursement", "payment", "outflow", "paid", "distributed"]),
    ("closing balance", ["closing", "ending", "remaining", "balance at end", "final"]),
]


def _extract_account_balances(text: str, account_pattern: re.Pattern) -> dict[str, float]:
    """Extract opening/deposits/disbursements/closing from account statement text."""
    # Find relevant section
    sections = []
    for line in text.splitlines():
        if account_pattern.search(line):
            sections.append(line)

    if not sections:
        return {}

    result: dict[str, float] = {}

    # Try to find a table in the text matching account fields
    tables = parse_md_tables(text)
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if not account_pattern.search(h):
            continue
        # Look for field + amount columns
        field_col = _col(table[0], "field", "description", "item", "account")
        val_col = _col(table[0], "amount", "balance", "value", "revised", "original")
        if field_col < 0 or val_col < 0:
            continue
        for row in table[1:]:
            if len(row) <= max(field_col, val_col):
                continue
            field_name = row[field_col].lower().strip()
            val = parse_number(row[val_col])
            if val is not None:
                result[field_name] = val

    # Fallback: scan raw text for labeled amounts
    if not result:
        amount_re = re.compile(
            r"(opening|beginning|prior|closing|ending|total\s+deposit|total\s+disbursement|"
            r"total\s+paid|collection|received)\s*[:\-]?\s*([\d,]+\.\d{2})",
            re.IGNORECASE,
        )
        for m in amount_re.finditer(text):
            label = m.group(1).lower().strip()
            val = parse_number(m.group(2))
            if val is not None:
                result[label] = val

    return result


def _get_account_data_from_dir(output_dir: Path, account_pattern: re.Pattern) -> dict[str, float]:
    """Search markdown outputs and chunks for account balance data."""
    for fname in ["03_interest_principal_waterfall.md", "04_extraction_summary.md"]:
        text = _read_text(output_dir / fname)
        if account_pattern.search(text):
            data = _extract_account_balances(text, account_pattern)
            if data:
                return data

    # Scan chunks
    chunks_dir = output_dir / "_chunks"
    if chunks_dir.is_dir():
        for chunk_file in sorted(chunks_dir.glob("pages_*.txt")):
            chunk_text = _read_text(chunk_file)
            if account_pattern.search(chunk_text):
                data = _extract_account_balances(chunk_text, account_pattern)
                if data:
                    return data
    return {}


def _compare_account(
    result: ComparisonResult,
    category: str,
    orig_data: dict[str, float],
    rev_data: dict[str, float],
) -> None:
    if not orig_data and not rev_data:
        result.issues.append(f"{category}: not found in either extraction (N/A — may not be printed in this report type).")
        return

    all_keys = sorted(set(orig_data) | set(rev_data))
    for key in all_keys:
        ov = orig_data.get(key)
        rv = rev_data.get(key)
        sev = _numeric_severity(ov, rv, 1.0, None)
        if sev == SEVERITY_NO_CHANGE:
            continue
        diff = (rv or 0) - (ov or 0)
        pct_change = ""
        if ov and ov != 0:
            pct_change = f"{diff / abs(ov) * 100:+.4f}%"
        result.changes.append(ChangeRow(
            category=category,
            label=key.title(),
            field=key,
            original=f"{ov:,.2f}" if ov is not None else "N/A",
            revised=f"{rv:,.2f}" if rv is not None else "N/A",
            change_str=f"{diff:+,.2f}",
            change_pct=pct_change,
            severity=sev,
        ))


def compare_account_balances(result: ComparisonResult) -> None:
    for label, pattern in [
        ("ICA (Interest Collection Account)", _ICA_PATTERNS),
        ("PCA (Principal Collection Account)", _PCA_PATTERNS),
    ]:
        orig_data = _get_account_data_from_dir(result.original_dir, pattern)
        rev_data = _get_account_data_from_dir(result.revised_dir, pattern)
        _compare_account(result, label, orig_data, rev_data)


# ---------------------------------------------------------------------------
# Step 5: Note Valuation (PV / NVR)
# ---------------------------------------------------------------------------

_NVR_HEADING_PATTERN = re.compile(
    r"note\s+valuation|nvr|present\s+value|calculated\s+value|note\s+value",
    re.IGNORECASE,
)

_NVR_ROW_RE = re.compile(
    r"^(?P<cls>[A-Za-z0-9\-\.]+\s*(?:Notes?|Class|Tranche)?)\s+"
    r"(?P<val>[\d,]+\.\d{2})",
    re.IGNORECASE,
)


def _extract_nvr_values(text: str) -> dict[str, float]:
    """Extract per-class NVR/PV values. Returns {class_name: pv_value}."""
    result: dict[str, float] = {}
    tables = parse_md_tables(text)
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if not any(w in h for w in ("note value", "pv", "present value", "calculated value", "nvr", "valuation")):
            continue
        class_col = _col(table[0], "class", "notes", "tranche", "name")
        val_col = _col(table[0], "note value", "pv", "present value", "calculated value", "value")
        if class_col < 0 or val_col < 0:
            continue
        for row in table[1:]:
            if len(row) <= max(class_col, val_col):
                continue
            cls = row[class_col].strip()
            val = parse_number(row[val_col])
            if cls and val is not None:
                result[cls] = val

    # Fallback: look for NVR section in raw text
    if not result:
        nvr_section = ""
        for line in text.splitlines():
            if _NVR_HEADING_PATTERN.search(line):
                nvr_section = line
                break
        if nvr_section:
            for m in _NVR_ROW_RE.finditer(text):
                val = parse_number(m.group("val"))
                if val is not None:
                    result[m.group("cls").strip()] = val

    return result


def _get_nvr_from_dir(output_dir: Path) -> dict[str, float]:
    """Search markdown outputs and chunks for NVR/PV data."""
    for fname in ["03_interest_principal_waterfall.md", "01_report_metadata.md",
                  "02_tranche_class_balances.md", "04_extraction_summary.md"]:
        text = _read_text(output_dir / fname)
        if _NVR_HEADING_PATTERN.search(text):
            data = _extract_nvr_values(text)
            if data:
                return data

    chunks_dir = output_dir / "_chunks"
    if chunks_dir.is_dir():
        for chunk_file in sorted(chunks_dir.glob("pages_*.txt")):
            chunk_text = _read_text(chunk_file)
            if _NVR_HEADING_PATTERN.search(chunk_text):
                data = _extract_nvr_values(chunk_text)
                if data:
                    return data
    return {}


def compare_nvr(result: ComparisonResult) -> None:
    orig_nvr = _get_nvr_from_dir(result.original_dir)
    rev_nvr = _get_nvr_from_dir(result.revised_dir)

    if not orig_nvr and not rev_nvr:
        result.issues.append(
            "Note Valuation (PV/NVR): not found in either extraction — "
            "may not be printed in this report type, or agent did not extract it yet."
        )
        return

    all_classes = sorted(set(orig_nvr) | set(rev_nvr))
    for cls in all_classes:
        ov = orig_nvr.get(cls)
        rv = rev_nvr.get(cls)
        sev = _numeric_severity(ov, rv, 0.1, 0.1)
        if sev == SEVERITY_NO_CHANGE:
            continue
        diff = (rv or 0) - (ov or 0)
        pct_change = ""
        if ov and ov != 0:
            pct_change = f"{diff / abs(ov) * 100:+.4f}%"
        result.changes.append(ChangeRow(
            category="Note Valuation (PV)",
            label=cls,
            field="note value / PV",
            original=f"{ov:,.2f}" if ov is not None else "N/A",
            revised=f"{rv:,.2f}" if rv is not None else "N/A",
            change_str=f"{diff:+,.2f}",
            change_pct=pct_change,
            severity=sev,
        ))


# ---------------------------------------------------------------------------
# Step 6: Fee amounts from 05 or 03
# ---------------------------------------------------------------------------

def _extract_fee_rows(text: str) -> dict[str, float]:
    """Parse 05_valuation_relevant_fees.md or 03 ### Valuation-relevant fees into {sub_category: amount}."""
    result: dict[str, float] = {}
    tables = parse_md_tables(text)
    for table in tables:
        if not table:
            continue
        h = _header_join(table[0])
        if "amount paid" not in h and "sub category" not in h and "fee" not in h:
            continue
        sub_col = _col(table[0], "sub category", "fee_type", "fee type", "sub")
        amt_col = _col(table[0], "amount paid", "amount")
        desc_col = _col(table[0], "description", "main category", "category")
        if amt_col < 0:
            continue
        for row in table[1:]:
            if len(row) <= amt_col:
                continue
            key = ""
            if sub_col >= 0 and sub_col < len(row):
                key = row[sub_col].strip()
            elif desc_col >= 0 and desc_col < len(row):
                key = row[desc_col].strip()
            if not key:
                continue
            val = parse_number(row[amt_col])
            if val is not None and val != 0:
                result[key] = result.get(key, 0.0) + val
    return result


def compare_fees(result: ComparisonResult) -> None:
    def load_fees(output_dir: Path) -> dict[str, float]:
        for fname in ["05_valuation_relevant_fees.md", "03_interest_principal_waterfall.md"]:
            text = _read_text(output_dir / fname)
            fees = _extract_fee_rows(text)
            if fees:
                return fees
        return {}

    orig_fees = load_fees(result.original_dir)
    rev_fees = load_fees(result.revised_dir)

    if not orig_fees and not rev_fees:
        result.issues.append(
            "Fees: 05_valuation_relevant_fees.md not available in either folder — "
            "run map_valuation_fees.py after 03 is complete."
        )
        return

    all_fee_types = sorted(set(orig_fees) | set(rev_fees))
    for fee_type in all_fee_types:
        ov = orig_fees.get(fee_type)
        rv = rev_fees.get(fee_type)
        diff = (rv or 0) - (ov or 0)
        if abs(diff) <= ROUNDING_TOLERANCE:
            continue
        abs_diff = abs(diff)
        sev = SEVERITY_HIGH if abs_diff > 1000 else SEVERITY_LOW
        pct_change = ""
        if ov and ov != 0:
            pct_change = f"{diff / abs(ov) * 100:+.4f}%"
        result.changes.append(ChangeRow(
            category="Fee changes",
            label=fee_type,
            field="amount paid",
            original=f"{ov:,.2f}" if ov is not None else "N/A",
            revised=f"{rv:,.2f}" if rv is not None else "N/A",
            change_str=f"{diff:+,.2f}",
            change_pct=pct_change,
            severity=sev,
        ))


# ---------------------------------------------------------------------------
# Output rendering
# ---------------------------------------------------------------------------

def _changes_by_category(result: ComparisonResult, category: str) -> list[ChangeRow]:
    return [c for c in result.changes if c.category == category and c.severity != SEVERITY_NO_CHANGE]


def _build_report(result: ComparisonResult) -> str:
    lines: list[str] = []
    run_date = datetime.date.today().isoformat()

    # Derive deal info
    deal_name = result.original_deal_name or result.revised_deal_name or "N/A"
    payment_date = result.original_payment_date or "N/A"
    orig_folder = result.original_dir.name
    rev_folder = result.revised_dir.name

    # Summary narrative
    critical_changes = [c for c in result.changes if c.severity == SEVERITY_CRITICAL]
    narrative_parts = []
    if result.critical_count == 0 and result.high_count == 0:
        narrative_parts.append("No material changes found between the original and revised report.")
    else:
        pf_flips = [c for c in critical_changes if c.field == "pass/fail"]
        if pf_flips:
            tests = ", ".join(c.label for c in pf_flips[:3])
            narrative_parts.append(f"CRITICAL: IC/OC test Pass/Fail flipped for: {tests}.")
        class_changes = [c for c in critical_changes if c.category == "Class balances"]
        if class_changes:
            cls_labels = ", ".join(f"{c.label} {c.field}" for c in class_changes[:3])
            narrative_parts.append(f"CRITICAL class changes: {cls_labels}.")
        high_items = [c for c in result.changes if c.severity == SEVERITY_HIGH]
        if high_items:
            narrative_parts.append(
                f"{len(high_items)} HIGH-severity field(s) changed, including "
                f"{high_items[0].category} / {high_items[0].label} {high_items[0].field}."
            )
    narrative = " ".join(narrative_parts) if narrative_parts else "Review changes below."

    lines += [
        "# Revised Report Comparison",
        "",
        "## Summary",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Deal / trust name | {deal_name} |",
        f"| Deal ID (Moody's) | {result.original_deal_id or 'N/A'} |",
        f"| Payment date covered | {payment_date} |",
        f"| Original report folder | `{orig_folder}` |",
        f"| Revised report folder | `{rev_folder}` |",
        f"| Comparison run date | {run_date} |",
        f"| CRITICAL changes | {result.critical_count} |",
        f"| HIGH changes | {result.high_count} |",
        f"| LOW changes | {result.low_count} |",
        f"| Total changed fields | {result.total_changed} |",
        "",
        f"**Summary narrative:** {narrative}",
        "",
        "---",
        "",
    ]

    # Issues
    if result.issues:
        lines += ["## Issues", ""]
        for issue in result.issues:
            lines.append(f"- {issue}")
        lines += ["", "---", ""]

    # Helper to emit a table of changes
    def emit_category(category: str, table_header: list[str], row_fn) -> None:
        cat_changes = _changes_by_category(result, category)
        lines.append(f"## {category}")
        lines.append("")
        if not cat_changes:
            lines.append("_No changes detected (or data not available in this report type)._")
            lines.append("")
            return
        lines.append("| " + " | ".join(table_header) + " |")
        lines.append("| " + " | ".join("---" for _ in table_header) + " |")
        for c in cat_changes:
            lines.append("| " + " | ".join(row_fn(c)) + " |")
        lines.append("")

    # Note Valuation
    emit_category(
        "Note Valuation (PV)",
        ["Class", "Original PV", "Revised PV", "Change", "Change %", "Severity"],
        lambda c: [c.label, c.original, c.revised, c.change_str, c.change_pct, c.severity],
    )
    lines.append("---")
    lines.append("")

    # IC/OC Tests
    emit_category(
        "IC/OC Tests",
        ["Test name", "Field", "Original", "Revised", "Change", "Severity"],
        lambda c: [c.label, c.field, c.original, c.revised, c.change_str, c.severity],
    )
    lines.append("---")
    lines.append("")

    # ICA
    emit_category(
        "ICA (Interest Collection Account)",
        ["Field", "Original", "Revised", "Change", "Change %", "Severity"],
        lambda c: [c.label, c.original, c.revised, c.change_str, c.change_pct, c.severity],
    )
    lines.append("---")
    lines.append("")

    # PCA
    emit_category(
        "PCA (Principal Collection Account)",
        ["Field", "Original", "Revised", "Change", "Change %", "Severity"],
        lambda c: [c.label, c.original, c.revised, c.change_str, c.change_pct, c.severity],
    )
    lines.append("---")
    lines.append("")

    # Class balances
    emit_category(
        "Class balances",
        ["Class", "Field", "Original", "Revised", "Change", "Change %", "Severity"],
        lambda c: [c.label, c.field, c.original, c.revised, c.change_str, c.change_pct, c.severity],
    )
    lines.append("---")
    lines.append("")

    # Fees
    emit_category(
        "Fee changes",
        ["Fee type", "Original amount paid", "Revised amount paid", "Change", "Change %", "Severity"],
        lambda c: [c.label, c.original, c.revised, c.change_str, c.change_pct, c.severity],
    )
    lines.append("---")
    lines.append("")

    # Key dates
    emit_category(
        "Key dates",
        ["Field", "Original", "Revised", "Change", "Severity"],
        lambda c: [c.field.title(), c.original, c.revised, c.change_str, c.severity],
    )
    lines.append("---")
    lines.append("")

    # Completeness checklist
    class_changes_exist = bool(_changes_by_category(result, "Class balances"))
    nvr_issues = any("Note Valuation" in i for i in result.issues)
    test_issues = any("test" in i.lower() for i in result.issues)
    ica_issues = any("ICA" in i for i in result.issues)
    pca_issues = any("PCA" in i for i in result.issues)
    fee_issues = any("Fee" in i for i in result.issues)

    def ck(done: bool) -> str:
        return "[x]" if done else "[ ]"

    lines += [
        "## Completeness Checklist",
        f"- {ck(True)} Class balances compared for all classes in original and revised",
        f"- {ck(not nvr_issues)} Note Valuation (PV) compared (or N/A if not printed in either report)",
        f"- {ck(not test_issues)} IC/OC tests compared (or N/A if not printed in either report)",
        f"- {ck(not ica_issues)} ICA balance compared (or N/A if not printed)",
        f"- {ck(not pca_issues)} PCA balance compared (or N/A if not printed)",
        f"- {ck(not fee_issues)} Fee amounts compared (or N/A if 05 / 03 not available)",
        f"- {ck(True)} Key dates confirmed identical (or CRITICAL flag raised)",
        f"- {ck(True)} CRITICAL changes count reported in Summary",
        f"- {ck(True)} Summary narrative written",
        "",
        "---",
        "",
        "## Source Text",
        "",
        "_Paste key changed lines from revised `_chunks/` with **Page N** labels for audit._",
        "",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare original vs revised CLO trustee report extractions."
    )
    parser.add_argument("original_dir", help="Path to the original extraction folder")
    parser.add_argument("revised_dir", help="Path to the revised extraction folder")
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: <revised-dir>/06_revised_report_comparison.md)",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Exit 1 if any CRITICAL or HIGH changes are found",
    )
    args = parser.parse_args()

    original_dir = Path(args.original_dir)
    revised_dir = Path(args.revised_dir)

    if not original_dir.is_dir():
        print(f"ERROR: original-dir not found: {original_dir}", file=sys.stderr)
        return 1
    if not revised_dir.is_dir():
        print(f"ERROR: revised-dir not found: {revised_dir}", file=sys.stderr)
        return 1

    # Check required files
    for fname in ["01_report_metadata.md", "02_tranche_class_balances.md"]:
        if not (original_dir / fname).exists():
            print(f"WARNING: {fname} missing in original-dir — extract with noteval-extractor-agent first.", file=sys.stderr)
        if not (revised_dir / fname).exists():
            print(f"WARNING: {fname} missing in revised-dir — extract with noteval-extractor-agent first.", file=sys.stderr)

    result = ComparisonResult(original_dir=original_dir, revised_dir=revised_dir)

    print("Comparing key dates...", flush=True)
    compare_key_dates(result)

    print("Comparing class balances (02)...", flush=True)
    compare_class_balances(result)

    print("Comparing coverage tests (IC/OC)...", flush=True)
    compare_coverage_tests(result)

    print("Comparing account balances (ICA/PCA)...", flush=True)
    compare_account_balances(result)

    print("Comparing note valuation (PV/NVR)...", flush=True)
    compare_nvr(result)

    print("Comparing fees (05/03)...", flush=True)
    compare_fees(result)

    report_text = _build_report(result)

    out_path = Path(args.output) if args.output else revised_dir / "06_revised_report_comparison.md"
    out_path.write_text(report_text, encoding="utf-8")

    print(f"\nComparison report written to: {out_path}", flush=True)
    print(
        f"  CRITICAL: {result.critical_count}  "
        f"HIGH: {result.high_count}  "
        f"LOW: {result.low_count}  "
        f"Total changed: {result.total_changed}",
        flush=True,
    )

    if result.issues:
        print("\nIssues noted:")
        for issue in result.issues:
            print(f"  - {issue}")

    if args.strict and (result.critical_count > 0 or result.high_count > 0):
        print("\nExit 1: CRITICAL or HIGH changes found (--strict).", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
