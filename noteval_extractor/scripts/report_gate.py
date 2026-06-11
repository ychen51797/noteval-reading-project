"""
Optional pre-segmentation gate: keep PDFs that look like noteval / payment reports.

Enable with NOTEVAL_SEGMENT_GATE_PRIMARY=1 (or true/yes/on). When disabled, every
call returns ``(True, "gate disabled", ...)``.

**Pass rule (content):** early-page text must show a **payment-date anchor** and at
least one of **tranche/class** content or **waterfall / proceeds** content.

- **Tranche + waterfall** — normal full extraction (01–04).
- **Waterfall only** (common on redeemed deals) — still passes; downstream may leave
  **02** blank and focus on fees / **03** (see ``meta["extraction_profile"]``).

When a separate ``waterfall_path`` PDF is supplied, its probed text is combined with
the primary PDF for section detection (payment date may appear on either file).

Uses pypdf (same stack as ``pdf_workflow``). Tuning via environment:

- NOTEVAL_PRIMARY_PDF_MAX_PAGES — default ``100``
- NOTEVAL_PRIMARY_PDF_PROBE_CHARS — max characters scanned (default ``120000``)
- NOTEVAL_PRIMARY_PDF_PROBE_PAGES — max pages per file (default ``16``)
- NOTEVAL_PRIMARY_PDF_PAYMENT_DATE_MARKERS — comma-separated (payment-date anchor)
- NOTEVAL_PRIMARY_PDF_TRANCHE_MARKERS — tranche / class / NVR / PDD–IDD cues
- NOTEVAL_PRIMARY_PDF_WATERFALL_MARKERS — waterfall / proceeds / fee-ladder cues
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


def max_pages_probe() -> int:
    raw = os.environ.get("NOTEVAL_PRIMARY_PDF_PROBE_PAGES", "16").strip()
    try:
        n = int(raw)
    except ValueError:
        n = 16
    return max(1, min(n, 64))


def _markers_from_env(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [s.strip().casefold() for s in raw.split(",") if s.strip()]


def payment_date_markers() -> list[str]:
    return _markers_from_env(
        "NOTEVAL_PRIMARY_PDF_PAYMENT_DATE_MARKERS",
        "payment date,next payment,distribution date,payment date report,"
        "as of payment,payable on,determination date",
    )


def tranche_section_markers() -> list[str]:
    return _markers_from_env(
        "NOTEVAL_PRIMARY_PDF_TRANCHE_MARKERS",
        "note valuation report,principal distribution detail,interest distribution detail,"
        "distribution in us$,distribution in u.s.,class balance,note class,tranche detail,"
        "notes information,beginning principal,current principal balance,"
        "prior principal balance,interest distribution detail",
    )


def waterfall_section_markers() -> list[str]:
    return _markers_from_env(
        "NOTEVAL_PRIMARY_PDF_WATERFALL_MARKERS",
        "waterfall,application of interest,application of principal,"
        "interest proceeds,principal proceeds,section 11.1,"
        "distribution of interest proceeds,distribution of principal proceeds,"
        "payment date waterfall,disbursement ladder,redemption report,"
        "distribution report,payment report,administrative cap and expenses,"
        "administrative expenses cap,interest payment/distribution",
    )


def _probe_pdf_text(pdf_path: Path, *, cap_pages: int, cap_chars: int) -> tuple[str, dict[str, Any]]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    n_pages = len(reader.pages)
    probe_limit = min(cap_pages, n_pages)
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
    blob = "\n".join(parts)
    return blob, {
        "pages": n_pages,
        "pages_probed": probe_limit,
        "probed_chars": len(blob),
    }


def _match_any(blob_cf: str, markers: list[str]) -> list[str]:
    return [m for m in markers if m in blob_cf]


def assess_primary_noteval_pdf(
    pdf_path: Path,
    *,
    force: bool = False,
    waterfall_pdf: Path | None = None,
) -> tuple[bool, str, dict[str, Any]]:
    """
    Return ``(pass, message, meta)``.

    ``pass`` is True when segmentation should proceed for the noteval pipeline.

    Content pass requires:
      - at least one **payment-date** marker in probed text (primary ± optional waterfall PDF), and
      - at least one **tranche** marker **or** at least one **waterfall** marker.

    When only waterfall markers match, ``meta["extraction_profile"]`` is
    ``"waterfall_only"`` (fees / 03 focus; **02** may be N/A).

    When ``force`` is False (default), the full gate runs only if
    ``NOTEVAL_SEGMENT_GATE_PRIMARY`` is truthy; otherwise returns pass with
    ``gate: off`` in meta.

    When ``force`` is True (e.g. UI preview via ``check_report_paths``), checks always run.
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
        from pypdf import PdfReader  # noqa: F401 — availability check
    except ImportError:
        return (
            False,
            "pypdf is required for the primary PDF gate; install pypdf or disable the gate",
            {**meta, "error": "import_pypdf"},
        )

    cap_pages = max_pages_probe()
    cap_chars = max_chars_probe()
    max_pages = max_primary_pages()

    try:
        primary_blob, primary_probe = _probe_pdf_text(
            pdf_path, cap_pages=cap_pages, cap_chars=cap_chars
        )
    except Exception as e:
        return False, f"cannot open or parse primary PDF: {e}", {**meta, "error": str(e)[:500]}

    meta["primary"] = primary_probe
    n_pages = int(primary_probe["pages"])
    if n_pages > max_pages:
        return (
            False,
            f"too many pages for noteval primary PDF gate: {n_pages} > {max_pages} "
            f"(raise NOTEVAL_PRIMARY_PDF_MAX_PAGES if this is intentional)",
            {**meta, "max_pages": max_pages},
        )

    blobs: list[tuple[str, str]] = [("primary", primary_blob)]
    wf_meta: dict[str, Any] | None = None
    if waterfall_pdf is not None:
        wf = waterfall_pdf.resolve()
        if wf.is_file() and wf != pdf_path:
            try:
                wf_blob, wf_probe = _probe_pdf_text(wf, cap_pages=cap_pages, cap_chars=cap_chars)
                blobs.append(("waterfall_pdf", wf_blob))
                wf_meta = {"path": str(wf), **wf_probe}
                meta["waterfall_pdf"] = wf_meta
            except Exception as e:
                meta["waterfall_pdf_error"] = str(e)[:500]

    combined = "\n".join(b for _, b in blobs)
    blob_cf = combined.casefold()

    pay_m = payment_date_markers()
    tr_m = tranche_section_markers()
    wf_m = waterfall_section_markers()

    pay_hits = _match_any(blob_cf, pay_m)
    tr_hits = _match_any(blob_cf, tr_m)
    wf_hits = _match_any(blob_cf, wf_m)

    has_payment_date = bool(pay_hits)
    has_tranche = bool(tr_hits)
    has_waterfall = bool(wf_hits)

    meta.update(
        {
            "has_payment_date": has_payment_date,
            "has_tranche_section": has_tranche,
            "has_waterfall_section": has_waterfall,
            "payment_date_markers_matched": pay_hits[:12],
            "tranche_markers_matched": tr_hits[:12],
            "waterfall_markers_matched": wf_hits[:12],
            "probed_sources": [label for label, _ in blobs],
        }
    )

    if not pay_m and not tr_m and not wf_m:
        return True, "no content markers configured; gate passes", meta

    if not has_payment_date:
        return (
            False,
            "primary PDF failed noteval content gate: no payment-date anchor in probed text "
            "(need a label such as Payment Date, Next Payment, or Distribution date). "
            "Adjust NOTEVAL_PRIMARY_PDF_PAYMENT_DATE_MARKERS if your trustee uses different wording.",
            {**meta, "required_payment_date_markers": pay_m},
        )

    if not has_tranche and not has_waterfall:
        return (
            False,
            "primary PDF failed noteval content gate: no tranche/class section and no "
            "waterfall/proceeds section in probed text. Need at least one of: note valuation / "
            "PDD–IDD / Distribution in US$ (tranche) OR waterfall / Section 11.1 / proceeds "
            "application (waterfall). Adjust NOTEVAL_PRIMARY_PDF_TRANCHE_MARKERS or "
            "NOTEVAL_PRIMARY_PDF_WATERFALL_MARKERS.",
            {
                **meta,
                "tranche_markers": tr_m,
                "waterfall_markers": wf_m,
            },
        )

    if has_tranche and has_waterfall:
        profile = "full"
        note = "tranche and waterfall sections detected"
    elif has_waterfall:
        profile = "waterfall_only"
        note = (
            "waterfall-only report (no tranche/class cues in probe); segmentation OK — "
            "expect fees/waterfall extraction with tranche section (02) blank or N/A"
        )
    else:
        profile = "tranche_only"
        note = "tranche/class section detected without waterfall cues in probe"

    meta["extraction_profile"] = profile
    return True, f"primary PDF passed noteval gate ({note})", meta
