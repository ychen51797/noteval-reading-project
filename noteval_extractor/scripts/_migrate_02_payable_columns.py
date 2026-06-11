"""Add Interest payable + Principal payable columns to legacy 02_tranche_class_balances.md.

Re-run only on files that still use the old 11-column primary header. Section state for
**### Tranche by listing** must not treat the section title line as a reset (do not match
``optional`` alone on the H3 title).
"""
from __future__ import annotations

from pathlib import Path


PRIMARY_OLD_HDR = (
    "| Class | ISIN | CUSIP | Original balance | Beginning balance | "
    "Interest payment | Principal payment | Deferred interest | Dividend | "
    "Ending balance | Notes |"
)
PRIMARY_NEW_HDR = (
    "| Class | ISIN | CUSIP | Original balance | Beginning balance | "
    "Interest payment | Interest payable | Principal payment | Principal payable | "
    "Deferred interest | Dividend | Ending balance | Notes |"
)
PRIMARY_OLD_SEP = (
    "|-------|------|-------|------------------|-------------------|"
    "------------------|-------------------|-------------------|----------|"
    "----------------|-------|"
)
PRIMARY_NEW_SEP = (
    "|-------|------|-------|------------------|-------------------|"
    "------------------|------------------|-------------------|-------------------|"
    "-------------------|----------|----------------|-------|"
)

TRANCHE_OLD_HDR = (
    "| Economic class | Listing / program | ISIN | CUSIP | Original balance | "
    "Beginning balance | Interest payment | Principal payment | Deferred interest | "
    "Dividend | Ending balance | Notes |"
)
TRANCHE_NEW_HDR = (
    "| Economic class | Listing / program | ISIN | CUSIP | Original balance | "
    "Beginning balance | Interest payment | Interest payable | Principal payment | "
    "Principal payable | Deferred interest | Dividend | Ending balance | Notes |"
)
TRANCHE_OLD_SEP = (
    "|----------------|-------------------|------|-------|------------------|"
    "-------------------|------------------|-------------------|-------------------|"
    "----------|----------------|-------|"
)
TRANCHE_NEW_SEP = (
    "|----------------|-------------------|------|-------|------------------|"
    "-------------------|------------------|------------------|-------------------|"
    "-------------------|-------------------|----------|----------------|-------|"
)

DIST_OLD_HDR = (
    "| Class | ISIN | CUSIP | Prior principal balance | Current principal balance | "
    "Principal paid | Interest paid | Other columns (name + value) | Notes |"
)
DIST_NEW_HDR = (
    "| Class | ISIN | CUSIP | Prior principal balance | Current principal balance | "
    "Principal paid | Principal payable | Interest paid | Interest payable | "
    "Other columns (name + value) | Notes |"
)
DIST_OLD_SEP = (
    "|-------|------|-------|------------------------|---------------------------|"
    "----------------|----------------|------------------------------|-------|"
)
DIST_NEW_SEP = (
    "|-------|------|-------|------------------------|---------------------------|"
    "----------------|-------------------|----------------|------------------|"
    "------------------------------|-------|"
)


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().split("|")[1:-1]]


def _join_cells(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def expand_primary_row(line: str) -> str:
    c = _cells(line)
    if len(c) == 13:
        return line
    if len(c) != 11:
        return line
    new_c = c[:6] + [c[5], c[6], c[6]] + c[7:]
    return _join_cells(new_c)


def expand_tranche_row(line: str) -> str:
    c = _cells(line)
    if len(c) == 14:
        return line
    if len(c) != 12:
        return line
    new_c = c[:7] + [c[6], c[7], c[7]] + c[8:]
    return _join_cells(new_c)


def expand_dist_row(line: str) -> str:
    c = _cells(line)
    if len(c) == 11:
        return line
    if len(c) != 9:
        return line
    new_c = c[:6] + [c[5], c[6], c[6]] + c[7:]
    return _join_cells(new_c)


def migrate_file(path: Path) -> bool:
    raw = path.read_text(encoding="utf-8", errors="replace")
    if PRIMARY_OLD_HDR not in raw:
        return False
    t = raw.replace(PRIMARY_OLD_HDR, PRIMARY_NEW_HDR).replace(PRIMARY_OLD_SEP, PRIMARY_NEW_SEP)
    t = t.replace(TRANCHE_OLD_HDR, TRANCHE_NEW_HDR).replace(TRANCHE_OLD_SEP, TRANCHE_NEW_SEP)
    t = t.replace(DIST_OLD_HDR, DIST_NEW_HDR).replace(DIST_OLD_SEP, DIST_NEW_SEP)

    lines = t.splitlines()
    out: list[str] = []
    section: str | None = None
    for line in lines:
        s = line.strip()
        if s.startswith("### "):
            if "Class balance table (primary)" in s:
                section = "primary"
            elif section == "primary" and s.startswith("### "):
                section = None
            elif s.startswith("### Tranche by listing"):
                section = "tranche"
            elif section == "tranche" and s.startswith("### "):
                section = None
            elif "Distribution grid" in s:
                section = "dist"
            elif section == "dist" and s.startswith("### "):
                section = None
            out.append(line)
            continue

        if section in ("primary", "tranche", "dist") and s.startswith("|"):
            if set(s.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
                out.append(line)
                continue
            if section == "primary":
                out.append(expand_primary_row(line))
            elif section == "tranche":
                out.append(expand_tranche_row(line))
            else:
                out.append(expand_dist_row(line))
            continue

        out.append(line)

    path.write_text("\n".join(out) + ("\n" if raw.endswith("\n") else ""), encoding="utf-8")
    return True


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "output"
    for p in sorted(root.glob("*/02_tranche_class_balances.md")):
        if migrate_file(p):
            print("migrated", p)


if __name__ == "__main__":
    main()
