#!/usr/bin/env python3
"""
Batch pipeline: SQL (per deal) → resolved PDF paths → segmentation → ready for agent extraction.

Chains the same logic as ``get_file_path.py`` + ``batch_segment.py`` **without** writing or
reading ``requests.csv`` / ``deal_paths.csv``. Pass deal/payment pairs on the command line.

Steps:
  1. For each ``--pair deal_id payment_date``, query ARD (same query/env as ``get_file_path.py``).
  2. Resolve ``pdf_path`` / optional ``waterfall_path`` (UNC) like ``build_deal_path_row``.
  3. Run ``pdf_workflow.run_segment_pdf`` into ``noteval_extractor/output/<deal_id>_YYYYMMDD/``.
  4. You (or the Noteval Extractor agent) open each output folder and draft ``01_``–``04_`` from ``_chunks/``.

Examples (repo root)::

  py -3 noteval_extractor/scripts/batch_deal_pipeline.py \\
      --pair 825275100 3/16/2026 --pair 825275101 3/16/2026

  py -3 noteval_extractor/scripts/batch_deal_pipeline.py --dry-run --pair 123 2026-01-15

Requires: ``.env`` with DB_* (see ``get_file_path.py``), ``pypdf``, network access to ARD and UNC PDFs.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import batch_segment as bs
import get_file_path as gfp
from pdf_workflow import run_segment_pdf


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query ARD per deal/payment date, segment PDFs; no requests/deal_paths CSV."
    )
    parser.add_argument(
        "--pair",
        nargs=2,
        metavar=("DEAL_ID", "PAYMENT_DATE"),
        action="append",
        default=None,
        help="Deal id and payment date (repeat for multiple deals). E.g. --pair 825275100 3/16/2026",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Parent for per-deal folders (default: noteval_extractor/output under repo root).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=30,
        help="Pages per chunk (default: 30).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Query DB and print paths only; no segmentation.",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Process remaining pairs after an error; exit 1 if any failure.",
    )
    args = parser.parse_args()

    pairs = args.pair
    if not pairs:
        parser.error("Provide at least one --pair DEAL_ID PAYMENT_DATE")

    out_root = args.output_root
    if out_root is None:
        out_root = bs.default_output_root()
    out_root = out_root.resolve()

    failures = 0
    skipped = 0
    ok_dirs: list[Path] = []
    noted_folder_fallback = False

    for deal_id, payment_date in pairs:
        did = str(deal_id).strip()
        pdt = str(payment_date).strip()
        print(f"--- deal_id={did!r} payment_date={pdt!r} ---", flush=True)

        df = gfp.fetch_deal_report_rows(did, pdt)
        row = gfp.build_deal_path_row(df, did, pdt)
        status = row.get("status", "")
        pdf_raw = bs.path_cell_to_str(row.get("pdf_path", ""))
        wf_raw = bs.path_cell_to_str(row.get("waterfall_path", ""))

        if status != "ok" or not pdf_raw:
            print(
                f"SKIP status={status!r} pdf_path={pdf_raw!r}",
                file=sys.stderr,
                flush=True,
            )
            skipped += 1
            continue

        pdf = Path(pdf_raw)
        if not pdf.is_file():
            print(f"SKIP (not a file): {pdf}", file=sys.stderr, flush=True)
            failures += 1
            skipped += 1
            if not args.continue_on_error:
                raise SystemExit(1)
            continue

        stem = pdf.stem
        folder = bs.output_folder_name(
            row.get("deal_id", did),
            row.get("payment_date", pdt),
            stem,
        )
        if folder == stem and not noted_folder_fallback:
            noted_folder_fallback = True
            print(
                "NOTE: using pdf stem as folder name; ensure deal_id/payment_date in DB row for stable naming.",
                file=sys.stderr,
                flush=True,
            )
        output_dir = out_root / folder

        wf_path: Path | None = None
        wf_segment_ok = False
        if wf_raw:
            wfp = Path(wf_raw)
            if not wfp.is_file():
                print(
                    f"ERROR: waterfall_path is not a file: {wf_raw!r} (note PDF will still segment)",
                    file=sys.stderr,
                    flush=True,
                )
                failures += 1
            elif wfp.resolve() == pdf.resolve():
                print(
                    f"SKIP waterfall (same file as pdf_path): {wfp}",
                    file=sys.stderr,
                    flush=True,
                )
            else:
                wf_path = wfp
                wf_segment_ok = True

        print(f"{pdf} -> {output_dir}", flush=True)
        if wf_segment_ok and wf_path:
            print(f"{wf_path} -> {output_dir} (_chunks_waterfall, …)", flush=True)

        if args.dry_run:
            continue

        fail_before = failures
        output_dir.mkdir(parents=True, exist_ok=True)
        try:
            run_segment_pdf(pdf, output_dir, chunk_size=args.chunk_size)
        except (FileNotFoundError, ValueError, OSError) as e:
            print(f"ERROR: segmentation failed: {pdf}: {e}", file=sys.stderr, flush=True)
            failures += 1
            if not args.continue_on_error:
                raise SystemExit(1) from e
            continue

        if wf_segment_ok and wf_path:
            with tempfile.TemporaryDirectory(prefix="noteval_wf_seg_") as tmp:
                tmp_path = Path(tmp)
                try:
                    run_segment_pdf(wf_path, tmp_path, chunk_size=args.chunk_size)
                except (FileNotFoundError, ValueError, OSError) as e:
                    print(
                        f"ERROR: waterfall segmentation failed: {wf_path}: {e}",
                        file=sys.stderr,
                        flush=True,
                    )
                    failures += 1
                    if not args.continue_on_error:
                        raise SystemExit(1) from e
                else:
                    try:
                        bs._install_waterfall_artifacts(tmp_path, output_dir)
                    except OSError as e:
                        print(
                            f"ERROR: could not install waterfall artifacts: {e}",
                            file=sys.stderr,
                            flush=True,
                        )
                        failures += 1
                        if not args.continue_on_error:
                            raise SystemExit(1) from e

        if failures == fail_before:
            ok_dirs.append(output_dir)

    if args.dry_run:
        print("(dry-run; no segmentation)", file=sys.stderr, flush=True)
        return

    print(
        f"Done. output_root={out_root} failures={failures} skipped={skipped}",
        file=sys.stderr,
        flush=True,
    )
    if ok_dirs:
        print(
            "\nSegmentation complete. Next: use the Noteval Extractor agent (or SKILL) and "
            "draft 01_–04_ markdown from _chunks/ in each folder:\n",
            file=sys.stderr,
            flush=True,
        )
        for d in ok_dirs:
            print(f"  {d}", file=sys.stderr, flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
