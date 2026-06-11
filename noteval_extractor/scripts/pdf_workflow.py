"""
PDF workflow for trustee / note-valuation style documents (noteval_extractor).

Step 1 — Segment the PDF in-process (pypdf): per-page text, ``_chunks/``,
``_page_index.md``, ``_manifest.md``. When **pdfplumber** is installed, also writes
``_chunks_structured/pdd_idd_pdfplumber.md`` (PDD/IDD) and, when fingerprints match,
``_chunks_structured/payment_date_report_pdfplumber.md`` (Payment Date Report / consolidated
grids) for LLM **02** drafts.

Self-contained: deploy **pdf_workflow.py** alone for this step (requires ``pip install pypdf``;
optional ``pip install pdfplumber`` for structured tables).

CLI::

    py -3 pdf_workflow.py <path-to.pdf> <output-folder> [--chunk-size 30]

``run_segment_pdf`` is exported for programmatic use (import from this module).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        "pdf_workflow.py requires pypdf. Install with: pip install pypdf"
    ) from e


def _preview_lines(page_text: str, max_lines: int = 2, max_len: int = 120) -> str:
    """First few non-empty lines, joined for the page index (matches prior format)."""
    lines: list[str] = []
    for raw in page_text.splitlines():
        s = raw.strip()
        if not s:
            continue
        s = re.sub(r"\s+", " ", s)
        if len(s) > max_len:
            s = s[: max_len - 1].rstrip() + "…"
        lines.append(s)
        if len(lines) >= max_lines:
            break
    if not lines:
        return "(no text)"
    out = " / ".join(lines)
    return out.replace("|", "¦")


# Full-page scan for class labels often missing from the first two lines (e.g. Reinvesting Holder).
_CLASS_INDEX_HINT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Reinvesting Holder", re.compile(r"reinvesting\s+holder(?:\s+note)?s?", re.I)),
    ("Income Notes", re.compile(r"income\s+notes?", re.I)),
    ("M Notes", re.compile(r"\bclass\s+m\s+notes?\b|\bm\s+notes?\b", re.I)),
    ("Subordinated Notes", re.compile(r"subordinated\s+notes?", re.I)),
    ("Preferred", re.compile(r"preferred\s+(?:return|stock|shares?)", re.I)),
)


def _class_labels_in_page_text(page_text: str, *, max_labels: int = 5) -> list[str]:
    """Short class/tranche labels found anywhere on the page (for ``_page_index.md``)."""
    if not page_text or not page_text.strip():
        return []
    scan = page_text if len(page_text) <= 24_000 else page_text[:24_000]
    found: list[str] = []
    seen: set[str] = set()
    for label, pat in _CLASS_INDEX_HINT_PATTERNS:
        if pat.search(scan):
            key = label.lower()
            if key not in seen:
                found.append(label)
                seen.add(key)
    for m in re.finditer(
        r"\bclass\s+([a-z][a-z0-9\-\.]{0,12}(?:\s*-\s*[a-z])?)\b",
        scan,
        re.I,
    ):
        token = re.sub(r"\s+", "", m.group(1).lower())
        if token in ("balance", "total", "name", "type", "notes"):
            continue
        label = f"Class {m.group(1).strip()}"
        key = label.lower()
        if key not in seen:
            found.append(label)
            seen.add(key)
        if len(found) >= max_labels:
            break
    return found[:max_labels]


# Section titles for ``_page_index.md`` (full-page scan). ``02`` layout uses these to
# prioritize **Distribution in US$** and skip factor grids for balance mapping.
_SECTION_INDEX_HINT_PATTERNS: tuple[tuple[str, re.Pattern[str], bool], ...] = (
    ("Distribution in US$", re.compile(r"distribution\s+in\s+us\$?", re.I), True),
    ("Interest Detail", re.compile(r"\binterest\s+detail\b", re.I), False),
    (
        "Factor per 1000 (coupon only — not balances)",
        re.compile(r"factor\s+information\s+per\s+1000", re.I),
        False,
    ),
    (
        "Administrative Cap and Expenses (admin grid under Administrative Expenses only)",
        re.compile(r"administrative\s+cap\s+and\s+expenses", re.I),
        False,
    ),
)


def _section_hints_in_page_text(page_text: str) -> tuple[str | None, list[str]]:
    """Return ``(prepend_label, also_labels)`` for page-index previews."""
    if not page_text or not page_text.strip():
        return None, []
    scan = page_text if len(page_text) <= 24_000 else page_text[:24_000]
    prepend: str | None = None
    also: list[str] = []
    seen: set[str] = set()
    for label, pat, do_prepend in _SECTION_INDEX_HINT_PATTERNS:
        if not pat.search(scan):
            continue
        key = label.lower()
        if key in seen:
            continue
        seen.add(key)
        if do_prepend and prepend is None:
            prepend = label
        else:
            also.append(label)
    return prepend, also


def _page_index_preview(page_text: str, *, max_len: int = 200) -> str:
    """First lines plus section/class hints so index-driven ``02`` selection sees the right exhibits."""
    prepend, section_also = _section_hints_in_page_text(page_text)
    base = _preview_lines(page_text, max_lines=2, max_len=120)
    if prepend:
        base = f"{prepend} / {base}"
    class_hints = _class_labels_in_page_text(page_text)
    also = section_also + [h for h in class_hints if h.lower() not in {s.lower() for s in section_also}]
    if not also:
        out = base
    else:
        out = f"{base} [also: {', '.join(also)}]"
    if len(out) > max_len:
        out = out[: max_len - 1].rstrip() + "…"
    return out.replace("|", "¦")


def run_segment_pdf(
    pdf_path: Path,
    output_dir: Path,
    *,
    chunk_size: int = 30,
) -> None:
    """Extract text with pypdf; write ``_chunks/``, ``_page_index.md``, ``_manifest.md``."""
    pdf_path = pdf_path.resolve()
    output_dir = output_dir.resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")

    reader = PdfReader(str(pdf_path))
    total = len(reader.pages)
    if total == 0:
        raise ValueError(f"No pages in PDF: {pdf_path}")

    page_texts: list[str] = []
    for i in range(total):
        page = reader.pages[i]
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        page_texts.append(t)

    chunks_dir = output_dir / "_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)

    chunk_rows: list[tuple[str, str, int]] = []
    total_chars = 0

    for start in range(1, total + 1, chunk_size):
        end = min(start + chunk_size - 1, total)
        name = f"pages_{start:03d}_{end:03d}.txt"
        rel = f"_chunks/{name}"
        parts: list[str] = []
        for p in range(start, end + 1):
            header = f"--- Page {p} of {total} ---\n"
            body = page_texts[p - 1]
            if body and not body.endswith("\n"):
                body += "\n"
            parts.append(header + body)
        content = "".join(parts)
        total_chars += len(content)
        (chunks_dir / name).write_text(content, encoding="utf-8", newline="\n")
        chunk_rows.append((rel, f"{start}-{end}", len(content)))

    index_lines = [
        "# Page Index",
        "",
        f"Total pages: {total}",
        "",
        "Use this index to identify which pages contain the sections you need.",
        "Previews lead with section tags when found (e.g. **Distribution in US$**), then first lines, "
        "then `[also: …]` for **Interest Detail**, **Factor per 1000** (coupon only), or class labels.",
        "Then read the corresponding chunk file from `_chunks/` for full text.",
        "",
        "| Page | First Lines |",
        "|------|-------------|",
    ]
    for p in range(1, total + 1):
        prev = _page_index_preview(page_texts[p - 1])
        index_lines.append(f"| {p} | {prev} |")
    index_lines.append("")
    (output_dir / "_page_index.md").write_text(
        "\n".join(index_lines), encoding="utf-8", newline="\n"
    )

    structured_lines: list[str] = []
    try:
        from pdfplumber_pdd_idd_md import (
            write_structured_pdd_idd_markdown,
            write_structured_payment_date_report_markdown,
        )

        sp = write_structured_pdd_idd_markdown(pdf_path, output_dir, page_texts)
        if sp is not None and sp.is_file():
            structured_lines.append("- **Structured PDD/IDD (pdfplumber):** `_chunks_structured/pdd_idd_pdfplumber.md`")
        sp2 = write_structured_payment_date_report_markdown(
            pdf_path, output_dir, page_texts
        )
        if sp2 is not None and sp2.is_file():
            structured_lines.append(
                "- **Structured Payment Date Report (pdfplumber, fingerprint pages):** "
                "`_chunks_structured/payment_date_report_pdfplumber.md`"
            )
    except ImportError:
        pass
    except Exception:
        # Optional step — do not fail segmentation
        pass

    src_display = str(pdf_path).replace("`", "'")
    man_lines = [
        "# Extraction Manifest",
        "",
        f"- **Source PDF:** `{src_display}`",
        f"- **Total pages:** {total}",
        f"- **Total characters:** {total_chars:,}",
        f"- **Chunks created:** {len(chunk_rows)}",
        "",
    ]
    if structured_lines:
        man_lines.extend(structured_lines)
        man_lines.append("")
    man_lines += [
        "## Chunk Files",
        "",
        "| File | Pages | Characters |",
        "|------|-------|------------|",
    ]
    for rel, prange, nch in chunk_rows:
        man_lines.append(f"| `{rel}` | {prange} | {nch:,} |")
    man_lines.append("")
    (output_dir / "_manifest.md").write_text(
        "\n".join(man_lines), encoding="utf-8", newline="\n"
    )


def run_step_segment_pdf(
    pdf_path: Path,
    output_dir: Path,
    *,
    chunk_size: int,
) -> None:
    print("Step 1: segment PDF")
    print(f"  {pdf_path} -> {output_dir} (chunk_size={chunk_size})")
    run_segment_pdf(pdf_path, output_dir, chunk_size=chunk_size)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PDF workflow: Step 1 segments the PDF (chunks + page index + manifest).",
        epilog=(
            "Example: py -3 pdf_workflow.py C:\\data\\197545_1.pdf C:\\data\\runs\\197545_1\n"
            "Needs exactly two paths: the PDF file, then one output folder (created if missing).\n"
            "Use a different output subfolder per PDF (e.g. ...\\runs\\<stem>) so runs do not overwrite."
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
        help="Pages per chunk file (default: 30)",
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

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        run_step_segment_pdf(
            pdf_path,
            output_dir,
            chunk_size=args.chunk_size,
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1) from e
    print("Step 1 finished. Review output_dir/_page_index.md then add later steps.")


if __name__ == "__main__":
    main()
