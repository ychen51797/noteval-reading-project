#!/usr/bin/env python3
"""
Quick side-by-side summary of LLM vs SDK extraction folders (same deal, two output dirs).

  py -3 noteval_extractor/scripts/compare_llm_sdk_outputs.py \\
      noteval_extractor/output/195084_249 \\
      noteval_extractor/output/195084_249_sdk
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

_FILES = (
    "01_report_metadata.md",
    "02_tranche_class_balances.md",
    "03_interest_principal_waterfall.md",
    "04_extraction_summary.md",
)


def _read(p: Path) -> list[str]:
    if not p.is_file():
        return []
    return p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("llm_dir", type=Path, help="Folder with noteval_llm / UI pipeline output")
    ap.add_argument("sdk_dir", type=Path, help="Folder with Cursor SDK agent output")
    ap.add_argument("--diff", action="store_true", help="Print unified diff per file")
    args = ap.parse_args()
    llm = args.llm_dir.resolve()
    sdk = args.sdk_dir.resolve()
    if not llm.is_dir() or not sdk.is_dir():
        raise SystemExit("Both arguments must be existing directories")

    print(f"LLM: {llm}")
    print(f"SDK: {sdk}\n")
    for name in _FILES:
        pl, ps = llm / name, sdk / name
        el, es = pl.is_file(), ps.is_file()
        print(f"=== {name} ===")
        print(f"  LLM: {'yes' if el else 'MISSING'}  SDK: {'yes' if es else 'MISSING'}")
        if el and es:
            ll = len(_read(pl))
            sl = len(_read(ps))
            print(f"  lines: LLM={ll} SDK={sl}")
            if args.diff and pl.read_bytes() != ps.read_bytes():
                diff = difflib.unified_diff(
                    _read(pl),
                    _read(ps),
                    fromfile=f"llm/{name}",
                    tofile=f"sdk/{name}",
                    lineterm="",
                )
                print("".join(f"{line}\n" for line in diff))
        print()


if __name__ == "__main__":
    main()
