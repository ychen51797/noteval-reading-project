"""
PDF workflow for trustee / note-valuation style documents (noteval_extractor).

Step 1 — Segment the PDF: run ``segment_pdf.py`` (pypdf, per-page text,
``_chunks/``, ``_page_index.md``, ``_manifest.md``).

Default ``segment_pdf.py`` (clone **CS-Structured-Skills** next to your repo
under the same parent folder, e.g. ``.cursor/projects``):

    <parent>/CS-Structured-Skills/plugins/rmbs-deal-creator/skills/
    rmbs-deal-doc-extractor/scripts/segment_pdf.py

Also tries the same relative path from the **repo root** (if the clone lives
inside the repo).

Override with env ``NOTEVAL_SEGMENT_PDF`` or ``--segment-script``.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _repo_and_projects_roots() -> tuple[Path, Path]:
    """This file: .../<repo>/noteval_extractor/scripts/pdf_workflow.py"""
    here = Path(__file__).resolve().parent
    if here.parent.name != "noteval_extractor":
        raise RuntimeError("Expected pdf_workflow.py under noteval_extractor/scripts/")
    repo = here.parents[2]
    projects = here.parents[3]
    return repo, projects


def _default_segment_script() -> Path | None:
    repo, projects = _repo_and_projects_roots()
    rel = Path(
        "CS-Structured-Skills/plugins/rmbs-deal-creator/skills/"
        "rmbs-deal-doc-extractor/scripts/segment_pdf.py"
    )
    for base in (projects, repo):
        p = (base / rel).resolve()
        if p.is_file():
            return p
    return None


def resolve_segment_script(explicit: Path | None) -> Path:
    if explicit is not None:
        if not explicit.is_file():
            raise FileNotFoundError(f"segment_pdf.py not found: {explicit}")
        return explicit
    env = os.environ.get("NOTEVAL_SEGMENT_PDF", "").strip()
    if env:
        p = Path(env)
        if not p.is_file():
            raise FileNotFoundError(f"NOTEVAL_SEGMENT_PDF not a file: {p}")
        return p
    d = _default_segment_script()
    if d is not None:
        return d
    raise FileNotFoundError(
        "segment_pdf.py not found. Clone CS-Structured-Skills alongside this repo "
        "(same parent directory), set NOTEVAL_SEGMENT_PDF, or pass --segment-script."
    )


def run_step_segment_pdf(
    pdf_path: Path,
    output_dir: Path,
    *,
    segment_script: Path,
    chunk_size: int,
) -> None:
    cmd = [
        sys.executable,
        str(segment_script),
        str(pdf_path),
        str(output_dir),
        "--chunk-size",
        str(chunk_size),
    ]
    print("Step 1: segment PDF")
    print(" ", subprocess.list2cmdline(cmd))
    proc = subprocess.run(cmd, check=False)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PDF workflow: Step 1 runs segment_pdf.py (page chunks + index).",
        epilog=(
            "Example: py -3 pdf_workflow.py C:\\data\\report.pdf C:\\data\\my_run_out\n"
            "Needs exactly two paths: the PDF file, then one output folder (created if missing)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("pdf_path", type=Path, help="Input PDF (.pdf file)")
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory for _chunks/, _page_index.md, _manifest.md",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=30,
        help="Pages per chunk file (passed to segment_pdf.py, default 30)",
    )
    parser.add_argument(
        "--segment-script",
        type=Path,
        default=None,
        help="Path to segment_pdf.py if not using default or NOTEVAL_SEGMENT_PDF",
    )
    args, unknown = parser.parse_known_args()
    if unknown:
        print(
            "ERROR: Too many arguments. pdf_workflow.py only accepts:\n"
            "  1) path to the PDF file\n"
            "  2) one output directory (where _chunks and _page_index.md will be written)\n\n"
            f"Remove these extra token(s): {' '.join(unknown)}\n",
            file=sys.stderr,
        )
        parser.print_help(file=sys.stderr)
        raise SystemExit(2)

    pdf_path = args.pdf_path.resolve()
    output_dir = args.output_dir.resolve()
    if pdf_path.is_dir():
        print(
            "ERROR: First argument must be the PDF file path, not a folder.\n"
            "  Usage: py -3 pdf_workflow.py <path-to.pdf> <output-folder>",
            file=sys.stderr,
        )
        sys.exit(1)
    if not pdf_path.is_file():
        print(f"ERROR: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    segment_script = resolve_segment_script(
        args.segment_script.resolve() if args.segment_script else None
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    run_step_segment_pdf(
        pdf_path,
        output_dir,
        segment_script=segment_script,
        chunk_size=args.chunk_size,
    )
    print("Step 1 finished. Review output_dir/_page_index.md then add later steps.")


if __name__ == "__main__":
    main()
