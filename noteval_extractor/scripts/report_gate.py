"""
Optional pre-segmentation gate: drop oversized or non–note-valuation primary PDFs.

Enable with NOTEVAL_SEGMENT_GATE_PRIMARY=1 (or true/yes/on). When disabled, every
call returns ``(True, "gate disabled", ...)``.

Uses pypdf (same stack as ``pdf_workflow``). Tuning via environment:

- NOTEVAL_PRIMARY_PDF_MAX_PAGES — default ``100``; reject when ``len(reader.pages)`` exceeds this.
- NOTEVAL_PRIMARY_PDF_PROBE_CHARS — max characters of early-page text to scan (default ``120000``).
- NOTEVAL_PRIMARY_PDF_REQUIRED_MARKERS — comma-separated substrings (case-insensitive); at least
  one must appear in the probed text. Default requires one of: ``note valuation report``,
  ``principal distribution detail``, ``interest distribution detail`` (Computershare-style),
  ``distribution report``, ``redemption report``, ``payment report`` (trustee **report** titles),
  plus ``payment date report`` and ``interest payment/distribution`` (U.S. Bank / Octagon-style grids).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def primary_pdf_gate_enabled() -> bool:
    return _env_truthy("NOTEVAL_SEGMENT_GATE_PRIMARY")


def max_primary_pages() -> int:
    raw = os.environ.get("NOTEVAL_PRIMARY_PDF_MAX_PAGES", "100").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 100
    return max(1, min(n, 2000))


def max_chars_probe() -> int:
    raw = os.environ.get("NOTEVAL_PRIMARY_PDF_PROBE_CHARS", "120000").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 120_000
    return max(5000, min(n, 2_000_000))


def _required_markers() -> list[str]:
    raw = os.environ.get(
        "NOTEVAL_PRIMARY_PDF_REQUIRED_MARKERS",
        "note valuation report,principal distribution detail,interest distribution detail,"
        "distribution report,redemption report,payment report,payment date report,"
        "interest payment/distribution",
    )
    return [s.strip().casefold() for s in raw.split(",") if s.strip()]


def assess_primary_noteval_pdf(
    pdf_path: Path, *, force: bool = False
) -> tuple[bool, str, dict[str, Any]]:
    """
    Return ``(pass, message, meta)``.

    ``pass`` is True when segmentation should proceed for the noteval pipeline.

    When ``force`` is False (default), the full gate runs only if
    ``NOTEVAL_SEGMENT_GATE_PRIMARY`` is truthy; otherwise returns pass with
    ``gate: off`` in meta.

    When ``force`` is True (e.g. UI preview via ``check_report_paths``), page and
    marker checks always run regardless of that env var.
    """
    if not force and not primary_pdf_gate_enabled():
        return (
            True,
            "gate disabled for batch runs (set NOTEVAL_SEGMENT_GATE_PRIMARY=1; "
            "or use force=True to preview checks)",
            {"gate": "off"},
        )

    pdf_path = pdf_path.resolve()
    meta: dict[str, Any] = {"path": str(pdf_path)}
    if not pdf_path.is_file():
        return False, "primary PDF path is not a readable file", meta

    try:
        from pypdf import PdfReader
    except ImportError:
        return (
            False,
            "pypdf is required for the primary PDF gate; install pypdf or disable the gate",
            {**meta, "error": "import_pypdf"},
        )

    try:
        reader = PdfReader(str(pdf_path))
        n_pages = len(reader.pages)
    except Exception as e:
        return False, f"cannot open or parse PDF: {e}", {**meta, "error": str(e)[:500]}

    meta["pages"] = n_pages
    cap_pages = max_primary_pages()
    if n_pages > cap_pages:
        return (
            False,
            f"too many pages for noteval primary PDF gate: {n_pages} > {cap_pages} "
            f"(raise NOTEVAL_PRIMARY_PDF_MAX_PAGES if this is intentional)",
            {**meta, "max_pages": cap_pages},
        )

    probe_limit = min(16, n_pages)
    cap_chars = max_chars_probe()
    parts: list[str] = []
    total_chars = 0
    for i in range(probe_limit):
        try:
            t = reader.pages[i].extract_text() or ""
        except Exception:
            t = ""
        parts.append(t)
        total_chars += len(t)
        if total_chars >= cap_chars:
            break

    blob = "\n".join(parts).casefold()
    meta["pages_probed"] = probe_limit
    meta["probed_chars"] = len(blob)

    markers = _required_markers()
    if not markers:
        return True, "no required markers configured; gate passes", meta

    if not any(m in blob for m in markers):
        return (
            False,
            "primary PDF failed noteval content gate: none of the required early-page markers "
            f"matched (set NOTEVAL_PRIMARY_PDF_REQUIRED_MARKERS to comma-separated substrings that "
            f"appear in your trustee PDF; default includes NVR/PDD–IDD wording plus report titles "
            f"(distribution / redemption / payment), payment date report, and interest payment/distribution)",
            {**meta, "required_markers": markers},
        )

    return True, "primary PDF passed noteval gate", meta
