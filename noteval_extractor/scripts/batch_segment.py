#!/usr/bin/env python3
"""
Run ``pdf_workflow.py`` for each PDF listed in ``deal_paths.csv``.

Each run writes to ``<output-root>/<folder>/``. Default folder name is
``{deal_id}_{YYYYMMDD}`` when the CSV includes **deal_id** and **payment_date**
(same columns as ``get_file_path.py``). If either is missing or the date cannot
be parsed, falls back to **pdf** stem (e.g. ``180118_175.pdf`` →
``…/output/180118_175/``).

  py -3 noteval_extractor/scripts/batch_segment.py
  py -3 noteval_extractor/scripts/batch_segment.py --deal-paths C:/Users/you/.cursor/projects/deal_paths.csv

Default CSV search: (1) ``noteval_extractor/test/deal_paths.csv`` if present;
(2) ``deal_paths.csv`` in the **parent** of the repo (e.g. ``…/projects/deal_paths.csv`` when the repo is ``…/projects/noteval-reading-project``).

Requires rows with a non-empty ``pdf_path``. If a ``status`` column exists, only
rows with ``status`` = ``ok`` are processed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd


def _repo_root() -> Path:
    """``noteval-reading-project`` (parent of ``noteval_extractor``)."""
    return Path(__file__).resolve().parent.parent.parent


def default_deal_paths_csv() -> Path:
    return Path(__file__).resolve().parent.parent / "test" / "deal_paths.csv"


def sibling_parent_deal_paths_csv() -> Path:
    """``deal_paths.csv`` next to the repo folder (sibling of ``noteval-reading-project``)."""
    return _repo_root().parent / "deal_paths.csv"


def resolve_deal_paths_csv(explicit: Path | None) -> Path:
    if explicit is not None:
        p = explicit.expanduser().resolve()
        if not p.is_file():
            raise SystemExit(f"deal_paths CSV not found: {p}")
        return p
    for candidate in (default_deal_paths_csv(), sibling_parent_deal_paths_csv()):
        if candidate.is_file():
            print(f"Using deal_paths: {candidate}", file=sys.stderr, flush=True)
            return candidate
    raise SystemExit(
        "Pass --deal-paths to your deal_paths.csv, or create one of:\n"
        f"  - {default_deal_paths_csv()}\n"
        f"  - {sibling_parent_deal_paths_csv()}"
    )


def default_output_root() -> Path:
    return _repo_root() / "noteval_extractor" / "output"


def _colmap(df: pd.DataFrame) -> dict[str, str]:
    return {str(c).strip().lower(): str(c) for c in df.columns}


def _pdf_workflow_script() -> Path:
    return Path(__file__).resolve().parent / "pdf_workflow.py"


def normalize_deal_id(raw: object) -> str:
    """Strip whitespace; turn ``867840715.0`` (CSV float) into ``867840715``."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return ""
    if re.fullmatch(r"\d+\.0", s):
        return s[:-2]
    return s


def payment_date_to_yyyymmdd(payment_date_raw: str) -> str | None:
    """Parse common payment-date strings; return ``YYYYMMDD`` or None."""
    s = str(payment_date_raw).strip()
    if not s or s.lower() == "nan":
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            if fmt == "%Y-%m-%d" and len(s) >= 10 and s[4] == "-":
                d = datetime.strptime(s[:10], "%Y-%m-%d").date()
            else:
                d = datetime.strptime(s, fmt).date()
            return d.strftime("%Y%m%d")
        except ValueError:
            continue
    return None


def output_folder_name(deal_id: str, payment_date: str, pdf_stem: str) -> str:
    """Prefer ``{deal_id}_{YYYYMMDD}``; else ``pdf_stem``."""
    did = normalize_deal_id(deal_id)
    ymd = payment_date_to_yyyymmdd(payment_date) if payment_date else None
    if did and ymd:
        return f"{did}_{ymd}"
    return pdf_stem


def load_rows(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    cmap = _colmap(df)
    if "pdf_path" not in cmap:
        raise SystemExit(f"{path}: missing required column pdf_path. Found: {list(df.columns)}")
    pdf_col = cmap["pdf_path"]
    out = df[[pdf_col]].copy()
    out.rename(columns={pdf_col: "pdf_path"}, inplace=True)
    out["pdf_path"] = out["pdf_path"].astype(str).str.strip()
    if "status" in cmap:
        out["_status"] = df[cmap["status"]].astype(str).str.strip()
    else:
        out["_status"] = ""
    if "deal_id" in cmap:
        out["_deal_id"] = df[cmap["deal_id"]].map(normalize_deal_id)
    else:
        out["_deal_id"] = ""
    if "payment_date" in cmap:
        out["_payment_date"] = df[cmap["payment_date"]].astype(str).str.strip()
    else:
        out["_payment_date"] = ""
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Segment each PDF in deal_paths.csv into output/{deal_id}_{YYYYMMDD}/ "
        "when those columns exist, else output/<pdf-stem>/."
    )
    parser.add_argument(
        "--deal-paths",
        type=Path,
        default=None,
        help=(
            "CSV from get_file_path.py (needs pdf_path). If omitted: use "
            "noteval_extractor/test/deal_paths.csv, else <parent-of-repo>/deal_paths.csv."
        ),
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Parent directory for per-deal folders (default: noteval_extractor/output under repo root).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=30,
        help="Pages per chunk (passed to segment_pdf via pdf_workflow).",
    )
    parser.add_argument(
        "--segment-script",
        type=Path,
        default=None,
        help="Path to segment_pdf.py (same as pdf_workflow --segment-script).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned pdf → output_dir only; do not run segmentation.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Run all rows even if one fails; exit 1 if any failure.",
    )
    args = parser.parse_args()

    deal_paths = resolve_deal_paths_csv(args.deal_paths)

    out_root = args.output_root
    if out_root is None:
        out_root = default_output_root()
    out_root = out_root.resolve()
    deal_paths = deal_paths.resolve()

    rows = load_rows(deal_paths)
    script = _pdf_workflow_script()
    if not script.is_file():
        raise SystemExit(f"pdf_workflow.py not found: {script}")

    failures = 0
    skipped = 0
    noted_folder_fallback = False
    for i, row in rows.iterrows():
        pdf = Path(row["pdf_path"])
        st = row.get("_status", "")
        if st and str(st).strip().lower() != "ok":
            print(f"SKIP (status={st!r}): {pdf}", file=sys.stderr, flush=True)
            skipped += 1
            continue
        if not row["pdf_path"]:
            skipped += 1
            continue
        if not pdf.is_file():
            print(f"SKIP (not a file): {pdf}", file=sys.stderr, flush=True)
            failures += 1
            continue

        stem = pdf.stem
        folder = output_folder_name(
            str(row.get("_deal_id", "")),
            str(row.get("_payment_date", "")),
            stem,
        )
        output_dir = out_root / folder
        if folder == stem and not noted_folder_fallback:
            noted_folder_fallback = True
            print(
                "NOTE: at least one row uses pdf stem as output folder; add deal_id + "
                "payment_date to CSV for stable deal_id_YYYYMMDD naming.",
                file=sys.stderr,
                flush=True,
            )
        print(f"{pdf} -> {output_dir}", flush=True)

        if args.dry_run:
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            sys.executable,
            str(script),
            str(pdf.resolve()),
            str(output_dir),
            "--chunk-size",
            str(args.chunk_size),
        ]
        if args.segment_script:
            cmd.extend(["--segment-script", str(args.segment_script.resolve())])

        proc = subprocess.run(cmd, check=False)
        if proc.returncode != 0:
            print(f"ERROR: segmentation failed (exit {proc.returncode}): {pdf}", file=sys.stderr)
            failures += 1
            if not args.continue_on_error:
                raise SystemExit(proc.returncode)

    if args.dry_run:
        print("(dry-run; no segmentation run)", file=sys.stderr)
        return

    print(
        f"Done. output_root={out_root} failures={failures} skipped={skipped}",
        file=sys.stderr,
        flush=True,
    )
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
