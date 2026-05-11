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

Requires rows with a non-empty primary path column: ``pdf_path`` (preferred), or
``file_path``, or ``filepath`` (case-insensitive). If a ``status`` column exists, only
rows with ``status`` = ``ok`` are processed.

Optional column ``waterfall_path`` (e.g. Wells Fargo Waterfall Calculations
Report): when non-empty, that PDF is segmented into the **same** deal folder
after the note PDF. Standard outputs stay ``_chunks/``, ``_page_index.md``,
``_manifest.md`` (from ``pdf_path``). Waterfall outputs are moved to
``_chunks_waterfall/``, ``_page_index_waterfall.md``, ``_manifest_waterfall.md``.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
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


def path_cell_to_str(raw: object) -> str:
    """CSV/pandas-safe path string: NaN, float NaN, and literal 'nan' become empty."""
    if raw is None:
        return ""
    if isinstance(raw, float) and pd.isna(raw):
        return ""
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "<na>"):
        return ""
    return s


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


def _primary_path_column(cmap: dict[str, str], headers: list[str]) -> str:
    """First matching logical name (same role as ``get_file_path`` ``pdf_path``)."""
    for logical in ("pdf_path", "file_path", "filepath"):
        if logical in cmap:
            return cmap[logical]
    raise SystemExit(
        "deal_paths CSV needs one of: pdf_path, file_path, filepath (any case). "
        f"Found: {headers}"
    )


def load_rows(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    cmap = _colmap(df)
    pdf_col = _primary_path_column(cmap, list(df.columns))
    out = df[[pdf_col]].copy()
    out.rename(columns={pdf_col: "pdf_path"}, inplace=True)
    out["pdf_path"] = out["pdf_path"].map(path_cell_to_str)
    if "waterfall_path" in cmap:
        out["waterfall_path"] = df[cmap["waterfall_path"]].map(path_cell_to_str)
    else:
        out["waterfall_path"] = ""
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


def _run_pdf_workflow(
    *,
    script: Path,
    pdf: Path,
    output_dir: Path,
    chunk_size: int,
) -> int:
    cmd = [
        sys.executable,
        str(script),
        str(pdf.resolve()),
        str(output_dir),
        "--chunk-size",
        str(chunk_size),
    ]
    proc = subprocess.run(cmd, check=False)
    return int(proc.returncode)


def _replace_tree_or_file(dst: Path) -> None:
    if dst.exists():
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()


def _install_waterfall_artifacts(tmp_dir: Path, deal_dir: Path) -> None:
    """Move pdf_workflow segmentation outputs from ``tmp_dir`` into ``deal_dir`` with *_waterfall names."""
    moves = [
        (tmp_dir / "_chunks", deal_dir / "_chunks_waterfall"),
        (tmp_dir / "_page_index.md", deal_dir / "_page_index_waterfall.md"),
        (tmp_dir / "_manifest.md", deal_dir / "_manifest_waterfall.md"),
    ]
    for src, dst in moves:
        if not src.exists():
            continue
        _replace_tree_or_file(dst)
        shutil.move(str(src), str(dst))


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
            "CSV with a primary PDF column: pdf_path, file_path, or filepath. "
            "If omitted: use noteval_extractor/test/deal_paths.csv, else "
            "<parent-of-repo>/deal_paths.csv."
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
        help="Pages per chunk (passed to pdf_workflow).",
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

    for _, row in rows.iterrows():
        pdf_raw = path_cell_to_str(row.get("pdf_path", ""))
        st = row.get("_status", "")
        if st and str(st).strip().lower() != "ok":
            print(f"SKIP (status={st!r}): {pdf_raw!r}", file=sys.stderr, flush=True)
            skipped += 1
            continue
        if not pdf_raw:
            skipped += 1
            continue
        pdf = Path(pdf_raw)
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
        wf_raw = path_cell_to_str(row.get("waterfall_path", ""))
        wf_path = Path(wf_raw) if wf_raw else None
        wf_segment_ok = False

        if folder == stem and not noted_folder_fallback:
            noted_folder_fallback = True
            print(
                "NOTE: at least one row uses pdf stem as output folder; add deal_id + "
                "payment_date to CSV for stable deal_id_YYYYMMDD naming.",
                file=sys.stderr,
                flush=True,
            )
        print(f"{pdf} -> {output_dir}", flush=True)
        if wf_raw:
            if wf_path is None or not wf_path.is_file():
                print(
                    f"ERROR: waterfall_path is not a file: {wf_raw!r} (note PDF will still segment)",
                    file=sys.stderr,
                    flush=True,
                )
                failures += 1
            elif wf_path.resolve() == pdf.resolve():
                print(
                    f"SKIP waterfall (same file as pdf_path): {wf_path}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                wf_segment_ok = True
                print(f"{wf_path} -> {output_dir} (_chunks_waterfall, …)", flush=True)

        if args.dry_run:
            continue

        output_dir.mkdir(parents=True, exist_ok=True)
        rc = _run_pdf_workflow(
            script=script,
            pdf=pdf,
            output_dir=output_dir,
            chunk_size=args.chunk_size,
        )
        if rc != 0:
            print(f"ERROR: segmentation failed (exit {rc}): {pdf}", file=sys.stderr)
            failures += 1
            if not args.continue_on_error:
                raise SystemExit(rc)

        if wf_segment_ok:
            with tempfile.TemporaryDirectory(prefix="noteval_wf_seg_") as tmp:
                tmp_path = Path(tmp)
                rc2 = _run_pdf_workflow(
                    script=script,
                    pdf=wf_path,
                    output_dir=tmp_path,
                    chunk_size=args.chunk_size,
                )
                if rc2 != 0:
                    print(
                        f"ERROR: waterfall segmentation failed (exit {rc2}): {wf_path}",
                        file=sys.stderr,
                    )
                    failures += 1
                    if not args.continue_on_error:
                        raise SystemExit(rc2)
                else:
                    try:
                        _install_waterfall_artifacts(tmp_path, output_dir)
                    except OSError as e:
                        print(
                            f"ERROR: could not install waterfall artifacts: {e}",
                            file=sys.stderr,
                        )
                        failures += 1
                        if not args.continue_on_error:
                            raise SystemExit(1) from e

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
