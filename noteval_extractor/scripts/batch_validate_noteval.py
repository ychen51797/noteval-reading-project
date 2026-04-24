#!/usr/bin/env python3
"""
Run validate_noteval on many extraction folders under an output root.

Discovers subdirectories that contain ``01_report_metadata.md`` (same layout as
``batch_segment.py`` / ``pdf_workflow`` outputs), sorts by name, validates each,
writes ``validation_report.md`` per deal, and a roll-up ``batch_validation_summary.md``
under the output root.

  py -3 noteval_extractor/scripts/batch_validate_noteval.py
  py -3 noteval_extractor/scripts/batch_validate_noteval.py --max-deals 10 --strict

Exit code: 1 if any deal has validation errors (or warnings when ``--strict``).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import validate_noteval as vn


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def default_output_root() -> Path:
    return _repo_root() / "noteval_extractor" / "output"


def discover_deal_dirs(output_root: Path) -> list[Path]:
    """Child dirs that look like noteval extractions (have 01_report_metadata.md)."""
    marker = "01_report_metadata.md"
    if not output_root.is_dir():
        return []
    out: list[Path] = []
    for p in output_root.iterdir():
        if p.is_dir() and (p / marker).is_file():
            out.append(p)
    return sorted(out, key=lambda x: x.name.lower())


def _counts(checks: list[vn.Check]) -> tuple[int, int]:
    errors = sum(1 for c in checks if not c.ok and c.severity == "error")
    warns = sum(1 for c in checks if not c.ok and c.severity == "warn")
    return errors, warns


def _deal_failed(checks: list[vn.Check], strict: bool) -> bool:
    errors, warns = _counts(checks)
    if errors:
        return True
    if strict and warns:
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-run validate_noteval on deal folders.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Parent of per-deal folders (default: noteval_extractor/output).",
    )
    parser.add_argument(
        "--max-deals",
        type=int,
        default=10,
        help="Maximum number of deal folders to validate (after sort). Default: 10.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings like errors for exit code (same as validate_noteval.py --strict).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List deal folders that would be validated; do not write reports.",
    )
    args = parser.parse_args()

    out_root = args.output_root
    if out_root is None:
        out_root = default_output_root()
    out_root = out_root.resolve()

    dirs = discover_deal_dirs(out_root)
    if args.max_deals is not None and args.max_deals > 0:
        dirs = dirs[: args.max_deals]

    if not dirs:
        print(f"No extraction folders found under {out_root} (need */01_report_metadata.md).", file=sys.stderr)
        return 1

    print(f"output_root={out_root}", file=sys.stderr, flush=True)
    print(f"Validating {len(dirs)} deal folder(s).", file=sys.stderr, flush=True)

    if args.dry_run:
        for d in dirs:
            print(d, flush=True)
        return 0

    summary_rows: list[tuple[str, int, int, str]] = []
    any_fail = False

    for d in dirs:
        checks = vn.validate_dir(d)
        vn.write_report(d, checks)
        errors, warns = _counts(checks)
        failed = _deal_failed(checks, args.strict)
        if failed:
            any_fail = True
        status = "FAIL" if failed else ("WARN" if warns else "OK")
        summary_rows.append((d.name, errors, warns, status))
        rp = d / "validation_report.md"
        print(f"{d.name}: errors={errors} warnings={warns} -> {rp}", flush=True)
        if errors:
            for c in checks:
                if not c.ok and c.severity == "error":
                    print(f"  FAIL: [{c.category}] {c.name}: {c.detail}", file=sys.stderr)
        if warns:
            stream = sys.stderr if (args.strict or errors) else sys.stdout
            for c in checks:
                if not c.ok and c.severity == "warn":
                    print(f"  WARN: [{c.category}] {c.name}: {c.detail}", file=stream)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Batch noteval validation summary",
        "",
        f"- **Output root:** `{out_root}`",
        f"- **Deals run:** {len(summary_rows)}",
        f"- **Strict:** {'yes' if args.strict else 'no'}",
        f"- **Generated:** {ts}",
        "",
        "| Deal | Errors | Warnings | Status |",
        "|------|--------|----------|--------|",
    ]
    for name, err, war, st in summary_rows:
        lines.append(f"| {name} | {err} | {war} | {st} |")

    total_err = sum(r[1] for r in summary_rows)
    total_war = sum(r[2] for r in summary_rows)
    lines.extend(
        [
            "",
            f"**Total errors:** {total_err}  **Total warnings:** {total_war}",
        ]
    )
    if any_fail:
        lines.append("")
        lines.append("**Batch STATUS: FAIL** (see per-deal `validation_report.md`).")
    else:
        lines.append("")
        lines.append("**Batch STATUS: PASS** (no failing deals under current strictness).")

    summary_path = out_root / "batch_validation_summary.md"
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {summary_path}", flush=True)

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
