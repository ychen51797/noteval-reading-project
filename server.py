import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
_SCRIPTS = BASE / "noteval_extractor" / "scripts"
_LLM = BASE / "LLM"
for _mod_dir in (_SCRIPTS, _LLM, BASE):
    _mod_path = str(_mod_dir)
    if _mod_path not in sys.path:
        sys.path.insert(0, _mod_path)

# Windows: subprocess text mode defaults to cp1252; markdown/agent output is UTF-8.
_SUBPROCESS_TEXT_KW: dict[str, str] = {"encoding": "utf-8", "errors": "replace"}


def _python_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    path_parts = [str(_SCRIPTS), str(_LLM), str(BASE)]
    existing = env.get("PYTHONPATH", "")
    if existing:
        path_parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(path_parts)
    return env

try:
    from dotenv import load_dotenv

    for _env_path in (
        BASE / ".env",
        BASE / "noteval_extractor" / ".env",
        _SCRIPTS / ".env",
    ):
        if _env_path.is_file():
            load_dotenv(_env_path, override=False)
except ImportError:
    pass

_DRAFT_KEY_HINT = (
    "Set NOTEVAL_DRAFT_API_KEY or OPENAI_API_KEY in the environment, or add one of them to "
    f"{BASE / '.env'}, {BASE / 'noteval_extractor' / '.env'}, or {_SCRIPTS / '.env'} "
    "(then restart the server). "
    "Install python-dotenv if .env is not loaded: py -3 -m pip install python-dotenv"
)

import batch_segment as _bs  # noqa: E402  # type: ignore[import-untyped]
import noteval_batch_cost as _batch_cost  # noqa: E402
import noteval_llm_pipeline as _llm_pipeline  # noqa: E402
import noteval_pipeline_log as _pipeline_log_file  # noqa: E402
import noteval_llm as _draft  # noqa: E402
import noteval_sdk_usage as _sdk_usage  # noqa: E402
import get_file_path as _gfp  # noqa: E402  # type: ignore[import-untyped]
import batch_validate_noteval as _batch_validate  # noqa: E402
import report_gate as _report_gate  # noqa: E402
import noteval_resolve_and_extract as _resolve_extract  # noqa: E402

try:
    import batch_tranche_mapping as _xml_db_compare  # noqa: E402
except ImportError:
    _xml_db_compare = None  # type: ignore[assignment]

app = FastAPI()

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def root_page():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "msg": "noteval UI backend",
        "capabilities": {
            "map_valuation_fees": True,
            "classify_waterfall_fees": (_SCRIPTS / "classify_waterfall_fees.py").is_file(),
            "run_fee_pipeline": (_SCRIPTS / "run_fee_pipeline.py").is_file(),
            "fee_classification_pipeline": (_SCRIPTS / "run_fee_pipeline.py").is_file()
            and (_SCRIPTS / "classify_waterfall_fees.py").is_file(),
            "apply_pdfplumber_pdd": (_SCRIPTS / "apply_pdfplumber_pdd.py").is_file(),
            "apply_pdfplumber_idd": (_SCRIPTS / "apply_pdfplumber_idd.py").is_file(),
            "apply_distribution_usd": (_SCRIPTS / "apply_distribution_usd.py").is_file(),
            "apply_distribution_summary": (
                _SCRIPTS / "apply_distribution_summary.py"
            ).is_file(),
            "apply_distribution_report": (
                _SCRIPTS / "apply_distribution_report.py"
            ).is_file(),
            "apply_payment_date_report": (
                _SCRIPTS / "apply_payment_date_report.py"
            ).is_file(),
            "apply_waterfall_optimal_paid": (
                _SCRIPTS / "apply_waterfall_optimal_paid.py"
            ).is_file(),
            "export_xml": _XML_EXPORT_SCRIPT.is_file(),
            "draft_tools_mode": True,
            "batch_export_xml": _XML_EXPORT_SCRIPT.is_file(),
            "compare_xml_db": _xml_db_compare is not None
            and _xml_db_compare.openpyxl_available(),
        },
    }


class ResolvePathBody(BaseModel):
    deal_id: str = Field(..., min_length=1)
    payment_date: str = Field(..., min_length=1)


def _system_exit_message(exc: SystemExit) -> str:
    code = exc.code
    if code is None or code == 0:
        return "Request aborted."
    if isinstance(code, int) and code == 1:
        return (
            "Database not configured, connection failed, or SQL error. "
            "Set DB_* in .env under noteval_extractor/scripts, noteval_extractor, or repo root."
        )
    return str(code)


@app.post("/api/resolve-path")
def resolve_path(body: ResolvePathBody):
    """
    Resolve ARD PDF path(s) for one deal_id + payment_date using get_file_path logic.
    """
    try:
        df = _gfp.fetch_deal_report_rows(body.deal_id, body.payment_date)
        row = _gfp.build_deal_path_row(df, body.deal_id, body.payment_date)
    except SystemExit as e:
        raise HTTPException(status_code=400, detail=_system_exit_message(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Could not query ARD: {e!s}",
        ) from e
    return row


class ResolveAndExtractBody(BaseModel):
    deal_id: str = Field(..., min_length=1)
    payment_date: str = Field(..., min_length=1)
    output_dir: str = Field(
        "",
        description=(
            "Directory to write _chunks/, _page_index.md, _manifest.md (and "
            "_chunks_waterfall/ for Wells Fargo). "
            "When empty, auto-derived as the default output root / {deal_id}_{YYYYMMDD}."
        ),
    )
    include_tables: bool = Field(
        True,
        description="Include raw pdfplumber table rows per page in the response body.",
    )
    include_structured: bool = Field(
        True,
        description=(
            "Run fingerprint detection for PDD/IDD, Distribution in US$, and "
            "Distribution Summary pages."
        ),
    )
    extract_waterfall: bool = Field(
        True,
        description="Also extract the waterfall PDF when ARD returns one (Wells Fargo).",
    )
    summary_only: bool = Field(
        False,
        description=(
            "When True, omit the full per-page text list from the response and return "
            "only the compact summary (deal metadata + fingerprint page lists)."
        ),
    )
    force_resegment: bool = Field(
        False,
        description=(
            "When True, delete existing _chunks/, _chunks_structured/, indexes, and "
            "manifests under output_dir before writing new segmentation."
        ),
    )


@app.post("/api/resolve-and-extract")
def resolve_and_extract(body: ResolveAndExtractBody):
    """
    Resolve the ARD PDF filepath via get_file_path, then extract text and structured
    table layouts using pdfplumber — all from the server-side UNC path, without
    uploading the PDF.

    Returns a JSON body with:
    - ``resolved``  — ARD metadata (deal_name, trustee, pdf_path, waterfall_path, status)
    - ``primary``   — pdfplumber extraction of the note-val PDF
    - ``waterfall`` — pdfplumber extraction of the waterfall PDF (Wells Fargo, or null)
    - ``chunks_written`` — chunk-write summary when output_dir is set
    - ``output_dir`` — resolved output directory path (or null)
    - ``error``     — top-level error message (or null)

    When ``summary_only=true``, the full ``pages`` lists are replaced by compact
    fingerprint summaries (page counts + structured layout page numbers).
    """
    # Auto-derive output_dir from deal_id + payment_date when not provided,
    # mirroring the CLI behaviour of noteval_resolve_and_extract.py.
    if body.output_dir.strip():
        out_dir: Path | None = Path(body.output_dir.strip())
    else:
        folder = _bs.output_folder_name(body.deal_id, body.payment_date, "")
        out_dir = _bs.default_output_root() / folder

    try:
        result = _resolve_extract.resolve_and_extract(
            body.deal_id,
            body.payment_date,
            output_dir=out_dir,
            include_tables=body.include_tables,
            include_structured=body.include_structured,
            extract_waterfall=body.extract_waterfall,
            force_resegment=body.force_resegment,
        )
    except SystemExit as e:
        raise HTTPException(status_code=400, detail=_system_exit_message(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ImportError as e:
        raise HTTPException(
            status_code=501,
            detail=f"pdfplumber not installed on server: {e!s}. "
                   "Run: py -3 -m pip install pdfplumber",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Extraction failed: {e!s}",
        ) from e

    if body.summary_only:
        return _resolve_extract.extraction_summary(result)
    return result


class SegmentBody(BaseModel):
    deal_id: str = Field(..., min_length=1)
    payment_date: str = Field(..., min_length=1)
    pdf_path: str = Field(..., min_length=1)
    waterfall_path: str = ""
    status: str = ""
    bypass_primary_pdf_gate: bool = False


class CheckReportPathsBody(BaseModel):
    """Verify resolved UNC/local paths exist before segmentation."""

    pdf_path: str = Field(..., min_length=1)
    waterfall_path: str = ""
    run_primary_pdf_gate: bool = False


@app.post("/api/check-report-paths")
def check_report_paths(body: CheckReportPathsBody):
    """
    Return whether pdf_path (and optional waterfall_path) exist as regular files on the server.
    Used by the batch queue to fail fast with a clear message before segment runs.
    """
    pdf_raw = body.pdf_path.strip()
    pdf = Path(pdf_raw)
    pdf_ok = pdf.is_file()
    errors: list[str] = []
    if not pdf_ok:
        errors.append(f"PDF not found or not a file: {pdf_raw}")

    wf_raw = (body.waterfall_path or "").strip()
    wf_ok: bool | None = None
    if wf_raw:
        wf = Path(wf_raw)
        wf_ok = wf.is_file()
        if not wf_ok:
            errors.append(f"Waterfall PDF not found or not a file: {wf_raw}")
    out: dict[str, Any] = {
        "ok": pdf_ok and (wf_ok is not False),
        "pdf_exists": pdf_ok,
        "waterfall_checked": bool(wf_raw),
        "waterfall_ok": wf_ok,
        "errors": errors,
    }
    if body.run_primary_pdf_gate and pdf_ok:
        ok_g, msg_g, meta_g = _report_gate.assess_primary_noteval_pdf(pdf, force=True)
        out["primary_pdf_gate"] = {
            "pass": ok_g,
            "message": msg_g,
            "meta": meta_g,
        }
    return out


@app.post("/api/segment")
def segment_pdf(body: SegmentBody):
    """
    Run batch_segment.py for a single row (same rules as deal_paths.csv).
    """
    st = (body.status or "").strip().casefold()
    if st and st != "ok":
        raise HTTPException(
            status_code=400,
            detail="Only rows with status ok are segmented (matches batch_segment.py).",
        )
    pdf = Path(body.pdf_path)
    if not pdf.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"pdf_path is not an existing file: {body.pdf_path}",
        )
    wf_raw = (body.waterfall_path or "").strip()
    if wf_raw:
        wf = Path(wf_raw)
        if not wf.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"waterfall_path is set but not a file: {wf_raw}",
            )

    if not body.bypass_primary_pdf_gate:
        wf_for_gate = Path(wf_raw) if wf_raw and Path(wf_raw).is_file() else None
        ok_g, msg_g, meta_g = _report_gate.assess_primary_noteval_pdf(
            pdf, waterfall_pdf=wf_for_gate
        )
        if not ok_g:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "primary_pdf_gate_failed",
                    "message": msg_g,
                    "meta": meta_g,
                    "hint": "Set bypass_primary_pdf_gate=true to segment anyway, or pass "
                    "--no-primary-pdf-gate via CLI batch_segment.",
                },
            )

    row = {
        "deal_id": str(body.deal_id).strip(),
        "payment_date": str(body.payment_date).strip(),
        "pdf_path": str(body.pdf_path).strip(),
        "waterfall_path": wf_raw,
        "status": "ok",
    }
    batch_script = BASE / "noteval_extractor" / "scripts" / "batch_segment.py"
    if not batch_script.is_file():
        raise HTTPException(status_code=500, detail=f"batch_segment.py missing: {batch_script}")

    folder = _bs.output_folder_name(body.deal_id, body.payment_date, pdf.stem)
    out_dir = _bs.default_output_root() / folder

    with tempfile.TemporaryDirectory(prefix="noteval_deal_paths_") as td:
        csv_path = Path(td) / "row.csv"
        pd.DataFrame([row]).to_csv(csv_path, index=False)
        proc = subprocess.run(
            [
                sys.executable,
                str(batch_script),
                "--deal-paths",
                str(csv_path),
            ]
            + (["--no-primary-pdf-gate"] if body.bypass_primary_pdf_gate else []),
            cwd=str(BASE),
            capture_output=True,
            text=True,
            **_SUBPROCESS_TEXT_KW,
            timeout=7200,
            env=_python_subprocess_env(),
        )

    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        tail = log.strip()[-8000:] if log.strip() else "(no subprocess output)"
        raise HTTPException(
            status_code=502,
            detail=f"batch_segment exited with {proc.returncode}. Last output:\n{tail}",
        )

    banner = (
        f"{'=' * 80}\n"
        "NOTEVAL SEGMENT OUTPUT\n"
        f"  deal_id={body.deal_id!r}   payment_date (input)={body.payment_date!r}\n"
        f"  Output folder: {folder!r}   (pattern: {{deal_id}}_{{YYYYMMDD}} when both are set)\n"
        f"  Full output path:\n  {out_dir}\n"
        f"{'=' * 80}\n\n"
    )
    log = banner + log

    return {
        "ok": True,
        "output_dir": str(out_dir),
        "folder": folder,
        "returncode": proc.returncode,
        "log": log,
    }


_OUTPUT_ROOT = _bs.default_output_root().resolve()

_DELIVERABLES = (
    "01_report_metadata.md",
    "02_tranche_class_balances.md",
    "03_interest_principal_waterfall.md",
    "04_extraction_summary.md",
    "05_valuation_relevant_fees.md",
)

_FEE_ARTIFACTS = (
    "fee_classification.md",
    "fee_mapping_report.md",
)

_DELIVERABLE_SET = frozenset(_DELIVERABLES)
_ALLOW_MISSING_FILES = _DELIVERABLE_SET | frozenset(_FEE_ARTIFACTS)

_TARGET_TO_FILE: dict[str, str] = {
    "01": "01_report_metadata.md",
    "02": "02_tranche_class_balances.md",
    "03": "03_interest_principal_waterfall.md",
    "04": "04_extraction_summary.md",
}

_EXTRACTION_TEMPLATES_MD = _draft.EXTRACTION_TEMPLATES_MD
_SKILL_MD = _draft.SKILL_MD


def _noteval_agent_md_path() -> Path | None:
    return _draft.noteval_agent_md_path()


def _read_text_capped(path: Path, max_chars: int) -> tuple[str, bool]:
    """Return (text, truncated). Empty if missing or max_chars <= 0."""
    if max_chars <= 0 or not path.is_file():
        return "", False
    raw = path.read_text(encoding="utf-8", errors="replace")
    if len(raw) <= max_chars:
        return raw, False
    return (
        raw[:max_chars] + "\n\n[TRUNCATED — raise full_templates_max_chars / skill_max_chars / agent_max_chars]\n",
        True,
    )


def _slice_extraction_template(target: Literal["01", "02", "03", "04"]) -> str:
    """Thin wrapper: map noteval_llm errors to HTTP 500 for the UI API."""
    try:
        return _draft.slice_extraction_template(target)
    except (RuntimeError, ValueError) as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _allowed_output_dir(raw: str) -> Path:
    p = _resolve_output_dir(raw)
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="output_dir is not an existing directory")
    return p


def _resolve_output_dir(raw: str) -> Path:
    """Resolve under ``noteval_extractor/output``; relative paths are rooted there."""
    raw_s = str(raw or "").strip()
    if not raw_s:
        raise HTTPException(status_code=400, detail="output_dir is empty")
    p = Path(raw_s).expanduser()
    try:
        if not p.is_absolute():
            p = (_OUTPUT_ROOT / p).resolve()
        else:
            p = p.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Invalid output_dir: {e!s}") from e
    try:
        p.relative_to(_OUTPUT_ROOT)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"output_dir must be under {_OUTPUT_ROOT}",
        ) from None
    return p


class LookupSegmentedFolderBody(BaseModel):
    deal_id: str = Field(..., min_length=1)
    payment_date: str = Field(..., min_length=1)
    pdf_stem: str = ""


def _expected_output_dir_for_deal(deal_id: str, payment_date: str, pdf_stem: str = "") -> Path:
    folder = _bs.output_folder_name(
        str(deal_id).strip(),
        str(payment_date).strip(),
        (pdf_stem or "deal").strip() or "deal",
    )
    return _OUTPUT_ROOT / folder


def _folder_has_segment_chunks(p: Path) -> bool:
    ch = p / "_chunks"
    return ch.is_dir() and any(ch.glob("pages_*.txt"))


@app.post("/api/lookup-segmented-folder")
def lookup_segmented_folder(body: LookupSegmentedFolderBody):
    """
    Resolve the standard output folder name for deal_id + payment_date and report whether
    segmentation artifacts already exist (``_chunks/pages_*.txt``).
    """
    out_dir = _expected_output_dir_for_deal(body.deal_id, body.payment_date, body.pdf_stem)
    folder = out_dir.name
    exists = out_dir.is_dir()
    segmented = exists and _folder_has_segment_chunks(out_dir)
    if not exists:
        detail = f"No folder yet ({folder}). Run segmentation to create it."
    elif segmented:
        detail = "Already segmented — run SDK or LLM extraction."
    else:
        detail = "Folder exists but _chunks/ is missing — run segmentation."
    return {
        "ok": True,
        "folder": folder,
        "output_dir": str(out_dir),
        "exists": exists,
        "segmented": segmented,
        "detail": detail,
    }


class CheckOutputFolderBody(BaseModel):
    output_dir: str = Field(..., min_length=1)


@app.post("/api/extraction/check-output-folder")
def extraction_check_output_folder(body: CheckOutputFolderBody):
    """
    Verify a segmented deal folder exists under the output root and has ``_chunks/pages_*.txt``.
    Accepts a full path or a folder basename like ``824048437_20260422``.
    """
    p = _resolve_output_dir(body.output_dir)
    if not p.is_dir():
        return {
            "ok": False,
            "output_dir": str(p),
            "segmented": False,
            "detail": "Directory does not exist.",
        }
    has_chunks = _folder_has_segment_chunks(p)
    name = p.name
    deal_id = ""
    payment_date = ""
    m = re.match(r"^(\d+)_(\d{8})(?:_sdk)?$", name)
    if m:
        deal_id = m.group(1)
        y, mo, d = m.group(2)[:4], m.group(2)[4:6], m.group(2)[6:8]
        payment_date = f"{int(mo)}/{int(d)}/{y}"
    return {
        "ok": has_chunks,
        "output_dir": str(p),
        "folder": name,
        "segmented": has_chunks,
        "deal_id": deal_id,
        "payment_date": payment_date,
        "detail": (
            "Ready for SDK or LLM extraction."
            if has_chunks
            else "Missing _chunks/pages_*.txt — segment this deal first."
        ),
    }


class CheckExtractionCompleteBody(BaseModel):
    output_dir: str = Field(..., min_length=1)
    targets: list[str] = Field(default_factory=list)
    force: bool = False
    """When true, always return ``complete: false`` so callers proceed with re-extraction."""


def _normalize_pipeline_targets(targets: list[str]) -> list[str]:
    out: list[str] = []
    for raw in targets:
        tid = str(raw).strip()
        if tid in _TARGET_TO_FILE and tid not in out:
            out.append(tid)
    if not out:
        return ["01", "02", "03", "04"]
    return out


def _extraction_targets_complete(out: Path, targets: list[str]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for tid in targets:
        fn = _TARGET_TO_FILE[tid]
        if not (out / fn).is_file():
            missing.append(fn)
    return len(missing) == 0, missing


@app.post("/api/extraction/check-extraction-complete")
def extraction_check_extraction_complete(body: CheckExtractionCompleteBody):
    """
    Return whether selected deliverables (``01``–``04`` markdown) already exist in the deal folder.
    Used by batch SDK/LLM to skip re-extraction when outputs are present.

    Pass ``force: true`` to always return ``complete: false``, forcing callers to re-extract
    even when all deliverable files are present on disk.
    """
    p = _resolve_output_dir(body.output_dir)
    targets = _normalize_pipeline_targets(body.targets)
    if not p.is_dir():
        return {
            "ok": False,
            "output_dir": str(p),
            "folder": p.name,
            "complete": False,
            "forced": body.force,
            "targets": targets,
            "missing": [_TARGET_TO_FILE[t] for t in targets],
            "detail": "Directory does not exist.",
        }
    complete, missing = _extraction_targets_complete(p, targets)
    if body.force and complete:
        # User requested forced re-extraction — report as incomplete so callers proceed.
        complete = False
        missing = [_TARGET_TO_FILE[t] for t in targets]
        detail = (
            f"Force re-extraction requested — {len(missing)} deliverable(s) will be overwritten: "
            + ", ".join(missing)
        )
    elif complete:
        detail = (
            f"Deliverables present for {', '.join(targets)} — extraction can be skipped."
        )
    else:
        detail = f"Missing {len(missing)} file(s): {', '.join(missing)}"
    return {
        "ok": True,
        "output_dir": str(p),
        "folder": p.name,
        "complete": complete,
        "forced": body.force,
        "targets": targets,
        "missing": missing,
        "detail": detail,
    }


def _child_file(base: Path, relative: str) -> Path:
    rel_norm = relative.replace("\\", "/").strip().lstrip("/")
    if not rel_norm or ".." in Path(rel_norm).parts:
        raise HTTPException(status_code=400, detail="Invalid relative_path")
    target = (base / rel_norm).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError as e:
        raise HTTPException(status_code=400, detail="relative_path escapes output_dir") from e
    return target


def _run_apply_distribution_usd(out: Path) -> dict[str, Any]:
    """Patch ``02`` from pdfplumber Distribution in US$ when structured file exists."""
    structured = out / "_chunks_structured" / "distribution_usd_pdfplumber.md"
    if not structured.is_file():
        return {
            "ok": True,
            "skipped": True,
            "reason": "no distribution_usd_pdfplumber.md",
            "changes": [],
        }
    if not (out / "02_tranche_class_balances.md").is_file():
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing 02_tranche_class_balances.md",
            "changes": [],
        }
    try:
        from apply_distribution_usd import run as apply_distribution_usd_run  # type: ignore[import-untyped]
    except ImportError as e:
        return {"ok": False, "skipped": True, "reason": f"apply_distribution_usd import failed: {e}"}
    try:
        return apply_distribution_usd_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _run_apply_distribution_summary(out: Path) -> dict[str, Any]:
    """Patch ``02`` from pdfplumber Distribution Summary (U.S. Bank) when structured file exists."""
    structured = out / "_chunks_structured" / "distribution_summary_pdfplumber.md"
    if not structured.is_file():
        return {
            "ok": True,
            "skipped": True,
            "reason": "no distribution_summary_pdfplumber.md",
            "changes": [],
        }
    if not (out / "02_tranche_class_balances.md").is_file():
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing 02_tranche_class_balances.md",
            "changes": [],
        }
    try:
        from apply_distribution_summary import (  # type: ignore[import-untyped]
            run as apply_distribution_summary_run,
        )
    except ImportError as e:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"apply_distribution_summary import failed: {e}",
        }
    try:
        return apply_distribution_summary_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _run_apply_distribution_report(out: Path) -> dict[str, Any]:
    """Patch ``02`` from pdfplumber Distribution Report (GoldenTree Pass-Through) when structured file exists."""
    structured = out / "_chunks_structured" / "distribution_report_pdfplumber.md"
    if not structured.is_file():
        return {
            "ok": True,
            "skipped": True,
            "reason": "no distribution_report_pdfplumber.md",
            "changes": [],
        }
    if not (out / "02_tranche_class_balances.md").is_file():
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing 02_tranche_class_balances.md",
            "changes": [],
        }
    try:
        from apply_distribution_report import (  # type: ignore[import-untyped]
            run as apply_distribution_report_run,
        )
    except ImportError as e:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"apply_distribution_report import failed: {e}",
        }
    try:
        return apply_distribution_report_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _run_apply_payment_date_report(out: Path) -> dict[str, Any]:
    """Patch ``02`` from pdfplumber Payment Date Report when structured file exists."""
    structured = out / "_chunks_structured" / "payment_date_report_pdfplumber.md"
    if not structured.is_file():
        return {
            "ok": True,
            "skipped": True,
            "reason": "no payment_date_report_pdfplumber.md",
            "changes": [],
        }
    if not (out / "02_tranche_class_balances.md").is_file():
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing 02_tranche_class_balances.md",
            "changes": [],
        }
    try:
        from apply_payment_date_report import (  # type: ignore[import-untyped]
            run as apply_payment_date_report_run,
        )
    except ImportError as e:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"apply_payment_date_report import failed: {e}",
        }
    try:
        return apply_payment_date_report_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _run_apply_payment_date_factors(out: Path) -> dict[str, Any]:
    raw = out / "_chunks_structured" / "payment_date_factors_raw.md"
    if not raw.is_file():
        return {
            "ok": True,
            "skipped": True,
            "reason": "no payment_date_factors_raw.md",
            "changes": [],
        }
    if not (out / "02_tranche_class_balances.md").is_file():
        return {
            "ok": False,
            "skipped": True,
            "reason": "missing 02_tranche_class_balances.md",
            "changes": [],
        }
    try:
        from apply_payment_date_factors import (  # type: ignore[import-untyped]
            run as apply_payment_date_factors_run,
        )
    except ImportError as e:
        return {
            "ok": False,
            "skipped": True,
            "reason": f"apply_payment_date_factors import failed: {e}",
        }
    try:
        return apply_payment_date_factors_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _run_apply_distribution_report_indenture(out: Path) -> dict[str, Any]:
    if not (out / "02_tranche_class_balances.md").is_file():
        return {"ok": True, "skipped": True, "reason": "no 02_tranche_class_balances.md", "changes": []}
    try:
        from apply_distribution_report_indenture import (  # type: ignore[import-untyped]
            run as apply_distribution_report_indenture_run,
        )
    except ImportError as e:
        return {"ok": False, "skipped": True, "reason": f"apply_distribution_report_indenture import failed: {e}"}
    try:
        return apply_distribution_report_indenture_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _run_apply_02_distribution_sources(out: Path) -> dict[str, Any]:
    """Layer 1: header-mapped pdfplumber distribution columns overwrite ``02`` before validate."""
    return {
        "distribution_usd": _run_apply_distribution_usd(out),
        "distribution_summary": _run_apply_distribution_summary(out),
        "distribution_report": _run_apply_distribution_report(out),
        "distribution_report_indenture": _run_apply_distribution_report_indenture(out),
        "payment_date_report": _run_apply_payment_date_report(out),
        "payment_date_factors": _run_apply_payment_date_factors(out),
    }


def _log_distribution_apply(
    log_fn: Any,
    distribution_apply: dict[str, Any] | None,
) -> None:
    """Emit pipeline/SDK log lines for Layer 1 distribution apply results."""
    if not isinstance(distribution_apply, dict):
        return
    for key, label in (
        ("distribution_usd", "apply_distribution_usd"),
        ("distribution_summary", "apply_distribution_summary"),
        ("distribution_report", "apply_distribution_report"),
        ("distribution_report_indenture", "apply_distribution_report_indenture"),
        ("payment_date_report", "apply_payment_date_report"),
        ("payment_date_factors", "apply_payment_date_factors"),
    ):
        result = distribution_apply.get(key)
        if not isinstance(result, dict):
            continue
        if result.get("skipped"):
            reason = str(result.get("reason") or "").strip()
            if reason and "no distribution_" not in reason:
                log_fn(f"{label} skipped: {reason}")
                for ek in ("grid_map_errors", "arithmetic_rejected_rows", "incomplete_rows"):
                    extra = result.get(ek)
                    if extra:
                        preview = extra[:3] if isinstance(extra, list) else extra
                        log_fn(f"  {label} {ek}: {preview}")
        else:
            src = result.get("map_source")
            src_bit = f", map={src}" if src else ""
            log_fn(
                f"{label}: {len(result.get('changes') or [])} column patch(es) "
                f"({result.get('printed_rows', '?')} printed / "
                f"{result.get('economic_rows', '?')} economic rows{src_bit})"
            )


def _run_validate_noteval(out: Path) -> dict[str, Any]:
    """Run validate_noteval.py on ``out`` and return report text plus process metadata."""
    distribution_apply = _run_apply_02_distribution_sources(out)
    try:
        import validate_noteval as vn

        vn.fix_02_primary_table(out)
    except Exception:
        pass
    val_script = BASE / "noteval_extractor" / "scripts" / "validate_noteval.py"
    cmd = [sys.executable, str(val_script), str(out)]
    proc = subprocess.run(
        cmd,
        cwd=str(BASE),
        capture_output=True,
        text=True,
        **_SUBPROCESS_TEXT_KW,
        timeout=180,
        env=_python_subprocess_env(),
    )
    report_path = out / "validation_report.md"
    report_text = ""
    if report_path.is_file():
        try:
            report_text = report_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            report_text = f"(could not read report: {e})"
    return {
        "returncode": proc.returncode,
        "report": report_text[:50_000],
        "report_path": str(report_path),
        "log_tail": ((proc.stdout or "") + (proc.stderr or ""))[-8000:],
        "manual_review_flags": _manual_review_flags_for_dir(out),
        "distribution_apply": distribution_apply,
    }


def _manual_review_flags_for_dir(out: Path) -> list[dict[str, str]]:
    """Structured R2/R3/R4/R13/R25 flags for UI and downstream (re-runs validate_dir in-process)."""
    try:
        import validate_noteval as vn

        return vn.manual_review_flags(vn.validate_dir(out))
    except Exception:
        return []


class ExtractionDirBody(BaseModel):
    output_dir: str = Field(..., min_length=1)


class ExtractionExportXmlBody(ExtractionDirBody):
    map_tranches: bool = False
    tranche_cache: str = ""
    no_tranche_db: bool = False


class ExtractionFileBody(ExtractionDirBody):
    relative_path: str = Field(..., min_length=1)
    max_bytes: int | None = Field(default=2_500_000, ge=1, le=10_000_000)
    allow_missing: bool = False


class ExtractionValidateBody(ExtractionDirBody):
    strict: bool = False


class RunFeePipelineBody(ExtractionDirBody):
    """Run Step 5 fee pipeline on an already-extracted deal folder."""

    run_llm: bool = Field(
        True,
        description="Run Step 5b LLM on uncertain / mapper-dropped fee rows.",
    )
    run_map: bool = Field(
        True,
        description="Run map_valuation_fees.py after classification (writes 05).",
    )
    apply_waterfall_cols: bool = Field(
        True,
        description="Run apply_waterfall_optimal_paid.py before classify when applicable.",
    )


@app.post("/api/extraction/artifacts")
def extraction_artifacts(body: ExtractionDirBody):
    """List page index, chunks, manifests, deliverables for one segmentation folder."""
    out = _allowed_output_dir(body.output_dir)

    def is_file(rel: str) -> bool:
        return (out / rel).is_file()

    def is_dir(rel: str) -> bool:
        return (out / rel).is_dir()

    chunk_files: list[dict[str, object]] = []
    chunks_dir = out / "_chunks"
    if chunks_dir.is_dir():
        for f in sorted(chunks_dir.glob("pages_*.txt")):
            rel = "_chunks/" + f.name
            try:
                st = f.stat()
                sz = st.st_size
            except OSError:
                sz = -1
            chunk_files.append(
                {
                    "name": f.name,
                    "relative_path": rel.replace("\\", "/"),
                    "size": sz,
                }
            )

    wf_chunk_files: list[dict[str, object]] = []
    wf_dir = out / "_chunks_waterfall"
    if wf_dir.is_dir():
        for f in sorted(wf_dir.glob("pages_*.txt")):
            rel = "_chunks_waterfall/" + f.name
            try:
                sz = f.stat().st_size
            except OSError:
                sz = -1
            wf_chunk_files.append(
                {
                    "name": f.name,
                    "relative_path": rel.replace("\\", "/"),
                    "size": sz,
                }
            )

    deliverables: list[dict[str, object]] = []
    for name in (*_DELIVERABLES, *_FEE_ARTIFACTS):
        fp = out / name
        ex = fp.is_file()
        sz = fp.stat().st_size if ex else 0
        deliverables.append(
            {
                "name": name,
                "exists": ex,
                "size": sz,
                "relative_path": name,
            }
        )

    return {
        "output_dir": str(out),
        "folder": out.name,
        "output_root": str(_OUTPUT_ROOT),
        "badges": {
            "page_index": is_file("_page_index.md"),
            "page_index_waterfall": is_file("_page_index_waterfall.md"),
            "_chunks": is_dir("_chunks"),
            "_chunks_waterfall": is_dir("_chunks_waterfall"),
            "manifest": is_file("_manifest.md"),
            "manifest_waterfall": is_file("_manifest_waterfall.md"),
            "validation_report": is_file("validation_report.md"),
        },
        "chunk_files": chunk_files,
        "waterfall_chunk_files": wf_chunk_files,
        "deliverables": deliverables,
    }


@app.post("/api/extraction/file")
def extraction_file(body: ExtractionFileBody):
    """Read a text file under output_dir (page index, chunk, manifest, deliverable)."""
    out = _allowed_output_dir(body.output_dir)
    rel_norm = body.relative_path.replace("\\", "/").strip().lstrip("/")
    if body.allow_missing and rel_norm not in _ALLOW_MISSING_FILES:
        raise HTTPException(
            status_code=400,
            detail="allow_missing is only allowed for 01–05 deliverables and fee_classification.md / fee_mapping_report.md",
        )
    target = _child_file(out, body.relative_path)
    if not target.is_file():
        if body.allow_missing:
            return {
                "relative_path": rel_norm,
                "total_bytes": 0,
                "truncated": False,
                "exists": False,
                "content": "",
            }
        raise HTTPException(status_code=404, detail=f"Not a file: {body.relative_path}")
    max_b = body.max_bytes or 2_500_000
    try:
        total = target.stat().st_size
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    truncated = total > max_b
    read_n = min(total, max_b)
    with target.open("rb") as f:
        raw = f.read(read_n)
    text = raw.decode("utf-8", errors="replace")
    return {
        "relative_path": rel_norm,
        "total_bytes": total,
        "truncated": truncated,
        "exists": True,
        "content": text,
    }


@app.post("/api/extraction/validate")
def extraction_validate(body: ExtractionDirBody):
    """Run validate_noteval.py on output_dir; returns validation_report.md body and exit code."""
    out = _allowed_output_dir(body.output_dir)
    return _run_validate_noteval(out)


_MAP_VALUATION_FEES_SCRIPT = BASE / "noteval_extractor" / "scripts" / "map_valuation_fees.py"
_CLASSIFY_WATERFALL_FEES_SCRIPT = _SCRIPTS / "classify_waterfall_fees.py"


def _run_classify_waterfall_fees(out: Path) -> dict[str, Any]:
    if not _CLASSIFY_WATERFALL_FEES_SCRIPT.is_file():
        return {
            "returncode": 1,
            "skipped": True,
            "reason": f"classify_waterfall_fees.py missing: {_CLASSIFY_WATERFALL_FEES_SCRIPT}",
            "output_file": str(out / "fee_classification.md"),
            "mapped_count": 0,
        }
    try:
        from classify_waterfall_fees import run as classify_waterfall_fees_run  # type: ignore[import-untyped]
    except ImportError as e:
        return {
            "returncode": 1,
            "skipped": True,
            "reason": f"Could not import classify_waterfall_fees: {e}",
            "output_file": str(out / "fee_classification.md"),
            "mapped_count": 0,
        }
    out_path = out / "fee_classification.md"
    try:
        result = classify_waterfall_fees_run(out)
    except FileNotFoundError as e:
        return {
            "returncode": 1,
            "report_path": str(out_path),
            "log_tail": str(e),
            "mapped_count": 0,
            "output_file": str(out_path),
        }
    mapped = int(result.get("mapped_count") or 0)
    confident = int(result.get("confident_count") or 0)
    uncertain = int(result.get("uncertain_count") or 0)
    excluded = int(result.get("excluded_count") or 0)
    wf_rows = int(result.get("waterfall_row_count") or 0)
    log_tail = (
        f"Wrote {result.get('output_file', out_path)}\n"
        f"Classified {mapped} fee row(s) ({confident} confident, {uncertain} uncertain), "
        f"excluded {excluded}, from {wf_rows} non-zero waterfall row(s)."
    )
    return {
        "returncode": 0,
        "log_tail": log_tail,
        "mapped_count": mapped,
        "confident_count": confident,
        "uncertain_count": uncertain,
        "excluded_count": excluded,
        "waterfall_row_count": wf_rows,
        "output_file": result.get("output_file", str(out_path)),
    }


def _maybe_run_classify_waterfall_fees(
    out: Path, targets: list[str]
) -> dict[str, Any] | None:
    """Classify fee rows from ``03`` waterfall when **03** was extracted."""
    if "03" not in targets:
        return None
    p03 = out / "03_interest_principal_waterfall.md"
    if not p03.is_file():
        return None
    return _run_classify_waterfall_fees(out)


def _llm_classify_fees(
    out: Path,
    *,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Step 5b — delegate to ``LLM/noteval_fee_classify.py``."""
    import noteval_fee_classify  # noqa: E402

    def _log(msg: str) -> None:
        if job_id:
            _pipeline_log(job_id, msg)

    return noteval_fee_classify.classify_uncertain_fees(out, log=_log if job_id else None)


def _apply_fee_pipeline_to_result(
    result: dict[str, Any],
    fee_pipeline: dict[str, Any],
    *,
    pipeline_usage_records: list[dict[str, Any]] | None = None,
) -> None:
    """Mirror ``run_fee_pipeline`` step dicts onto legacy API response keys."""
    result["fee_pipeline"] = fee_pipeline
    if fee_pipeline.get("waterfall_optimal_paid") is not None:
        result["waterfall_optimal_paid"] = fee_pipeline["waterfall_optimal_paid"]
    if fee_pipeline.get("classify") is not None:
        result["fee_classification"] = fee_pipeline["classify"]
    if fee_pipeline.get("llm_classify") is not None:
        result["llm_fee_classification"] = fee_pipeline["llm_classify"]
        if pipeline_usage_records is not None:
            _draft.ensure_fee_classify_usage_in_records(pipeline_usage_records, fee_pipeline)
        llm_fc = fee_pipeline["llm_classify"]
        if isinstance(llm_fc, dict):
            u = llm_fc.get("usage")
            if isinstance(u, dict) and _draft.usage_record_is_billable(u):
                result["fee_classify_usage"] = u
    if fee_pipeline.get("map_fees") is not None:
        result["fee_mapping"] = fee_pipeline["map_fees"]


def _run_fee_pipeline(
    out: Path,
    *,
    targets: list[str],
    run_llm: bool,
    run_validate: bool = False,
    job_id: str | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> dict[str, Any] | None:
    """Headless Step 5 — ``run_fee_pipeline.run`` when **03** exists."""
    if "03" not in targets:
        return None
    if not (out / "03_interest_principal_waterfall.md").is_file():
        return None
    from run_fee_pipeline import run as run_fee_pipeline_run  # type: ignore[import-untyped]

    def _log(msg: str) -> None:
        if log_fn is not None:
            log_fn(msg)
        elif job_id:
            _pipeline_log(job_id, msg)

    return run_fee_pipeline_run(
        out,
        apply_waterfall_cols=True,
        run_classify=True,
        run_llm=run_llm,
        run_map=True,
        run_validate=run_validate,
        log=_log,
    )


def _run_map_valuation_fees(out: Path) -> dict[str, Any]:
    script = _MAP_VALUATION_FEES_SCRIPT
    if not script.is_file():
        raise HTTPException(status_code=500, detail=f"map_valuation_fees.py missing: {script}")
    try:
        from map_valuation_fees import (  # type: ignore[import-untyped]
            FeeClassificationIncompleteError,
            run as map_valuation_fees_run,
        )
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not import map_valuation_fees: {e}",
        ) from e
    report_path = out / "fee_mapping_report.md"
    try:
        result = map_valuation_fees_run(out)
    except (FeeClassificationIncompleteError, FileNotFoundError) as e:
        return {
            "returncode": 1,
            "report": "",
            "report_path": str(report_path),
            "log_tail": str(e),
            "mapped_count": 0,
            "output_file": str(out / "05_valuation_relevant_fees.md"),
        }
    report_text = ""
    if report_path.is_file():
        try:
            report_text = report_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            report_text = f"(could not read report: {e})"
    mapped = int(result.get("mapped_count") or 0)
    log_tail = (
        f"Wrote {result.get('output_file', '')}\n"
        f"Mapped {mapped} fee row(s) from {result.get('candidate_count', 0)} candidate(s)."
    )
    return {
        "returncode": 0,
        "report": report_text[:20_000],
        "report_path": str(report_path),
        "log_tail": log_tail,
        "mapped_count": mapped,
        "output_file": result.get("output_file"),
        "candidate_count": result.get("candidate_count"),
    }


def _run_apply_pdfplumber_idd(out: Path) -> dict[str, Any]:
    try:
        from apply_pdfplumber_idd import run as apply_pdfplumber_idd_run  # type: ignore[import-untyped]
    except ImportError as e:
        return {"ok": False, "skipped": True, "reason": f"apply_pdfplumber_idd import failed: {e}"}
    try:
        return apply_pdfplumber_idd_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _maybe_run_apply_pdfplumber_idd(
    out: Path, targets: list[str]
) -> dict[str, Any] | None:
    """Patch ``02`` interest columns from pdfplumber IDD when **02** was extracted."""
    if "02" not in targets:
        return None
    p02 = out / "02_tranche_class_balances.md"
    if not p02.is_file():
        return None
    structured = out / "_chunks_structured" / "pdd_idd_pdfplumber.md"
    if not structured.is_file():
        return None
    return _run_apply_pdfplumber_idd(out)


def _run_apply_pdfplumber_pdd(out: Path) -> dict[str, Any]:
    try:
        from apply_pdfplumber_pdd import run as apply_pdfplumber_pdd_run  # type: ignore[import-untyped]
    except ImportError as e:
        return {"ok": False, "skipped": True, "reason": f"apply_pdfplumber_pdd import failed: {e}"}
    try:
        return apply_pdfplumber_pdd_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _maybe_run_apply_pdfplumber_pdd(
    out: Path, targets: list[str]
) -> dict[str, Any] | None:
    """Patch ``02`` principal/balance columns from pdfplumber PDD when **02** was extracted."""
    if "02" not in targets:
        return None
    p02 = out / "02_tranche_class_balances.md"
    if not p02.is_file():
        return None
    structured = out / "_chunks_structured" / "pdd_idd_pdfplumber.md"
    if not structured.is_file():
        return None
    return _run_apply_pdfplumber_pdd(out)


def _run_apply_waterfall_optimal_paid(out: Path) -> dict[str, Any]:
    try:
        from apply_waterfall_optimal_paid import (  # type: ignore[import-untyped]
            run as apply_waterfall_optimal_paid_run,
        )
    except ImportError as e:
        return {"ok": False, "skipped": True, "reason": f"apply_waterfall_optimal_paid import failed: {e}"}
    try:
        return apply_waterfall_optimal_paid_run(out)
    except FileNotFoundError as e:
        return {"ok": False, "skipped": True, "reason": str(e)}


def _maybe_run_apply_waterfall_optimal_paid(
    out: Path, targets: list[str]
) -> dict[str, Any] | None:
    """Patch Available|Optimal|Paid|Unpaid waterfall grids in ``03``."""
    if "03" not in targets:
        return None
    if not (out / "03_interest_principal_waterfall.md").is_file():
        return None
    return _run_apply_waterfall_optimal_paid(out)


def _maybe_run_map_valuation_fees(
    out: Path, targets: list[str]
) -> dict[str, Any] | None:
    """Run fee mapper when **03** was extracted and the waterfall file exists."""
    if "03" not in targets:
        return None
    p03 = out / "03_interest_principal_waterfall.md"
    if not p03.is_file():
        return None
    return _run_map_valuation_fees(out)


def _extraction_map_valuation_fees_handler(body: ExtractionDirBody) -> dict[str, Any]:
    """Map fee rows from ``03`` into ``05_valuation_relevant_fees.md``."""
    out = _allowed_output_dir(body.output_dir)
    p03 = out / "03_interest_principal_waterfall.md"
    if not p03.is_file():
        raise HTTPException(
            status_code=400,
            detail="03_interest_principal_waterfall.md missing — run extraction first.",
        )
    classify_result = _run_fee_pipeline(
        out,
        targets=["03"],
        run_llm=False,
        run_validate=False,
    )
    if classify_result is None:
        classify_result = _run_classify_waterfall_fees(out)
    result = _run_map_valuation_fees(out)
    if classify_result is not None:
        result["fee_classification"] = classify_result.get("classify") or classify_result
        result["fee_pipeline"] = classify_result
    if result["returncode"] != 0:
        raise HTTPException(
            status_code=400 if "Missing" in (result.get("log_tail") or "") else 500,
            detail=result.get("log_tail") or "map_valuation_fees.py failed",
        )
    return result


@app.post("/api/extraction/map-valuation-fees")
def extraction_map_valuation_fees(body: ExtractionDirBody):
    """Map fee rows from ``03_interest_principal_waterfall.md`` into ``05`` (deterministic)."""
    return _extraction_map_valuation_fees_handler(body)


@app.post("/api/extraction/map_valuation_fees")
def extraction_map_valuation_fees_alt(body: ExtractionDirBody):
    """Alias for clients that use underscores in the path."""
    return _extraction_map_valuation_fees_handler(body)


def _extraction_run_fee_pipeline_handler(body: RunFeePipelineBody) -> dict[str, Any]:
    """
    Run Step 5 fee pipeline on an extracted deal: classify → optional LLM 5b → optional map 05.
    """
    out = _allowed_output_dir(body.output_dir)
    p03 = out / "03_interest_principal_waterfall.md"
    if not p03.is_file():
        raise HTTPException(
            status_code=400,
            detail="03_interest_principal_waterfall.md missing — run extraction with 03 first.",
        )
    try:
        from run_fee_pipeline import run as run_fee_pipeline_run  # type: ignore[import-untyped]
    except ImportError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Could not import run_fee_pipeline: {e}",
        ) from e

    pipeline = run_fee_pipeline_run(
        out,
        apply_waterfall_cols=body.apply_waterfall_cols,
        run_classify=True,
        run_llm=body.run_llm,
        run_map=body.run_map,
        run_validate=False,
    )
    if pipeline.get("skipped"):
        raise HTTPException(
            status_code=400,
            detail=pipeline.get("reason") or "fee pipeline skipped",
        )
    classify = pipeline.get("classify") or {}
    if classify.get("skipped"):
        raise HTTPException(
            status_code=400,
            detail=classify.get("reason") or "classify_waterfall_fees failed",
        )

    response: dict[str, Any] = {
        "ok": bool(pipeline.get("ok")),
        "output_dir": str(out),
        "reason": pipeline.get("reason"),
    }
    _apply_fee_pipeline_to_result(response, pipeline)
    llm_fc = pipeline.get("llm_classify") or {}
    if isinstance(llm_fc, dict):
        u = llm_fc.get("usage")
        if isinstance(u, dict) and _draft.usage_record_is_billable(u):
            response["fee_classify_usage"] = u
            if u.get("cost_usd") is not None:
                response["fee_classify_cost_usd"] = u.get("cost_usd")
    return response


@app.post("/api/extraction/run-fee-pipeline")
def extraction_run_fee_pipeline(body: RunFeePipelineBody):
    """Classify fees from 03, optionally run LLM Step 5b, optionally map to 05."""
    return _extraction_run_fee_pipeline_handler(body)


@app.post("/api/extraction/run_fee_pipeline")
def extraction_run_fee_pipeline_alt(body: RunFeePipelineBody):
    """Alias for clients that use underscores in the path."""
    return _extraction_run_fee_pipeline_handler(body)


_XML_EXPORT_SCRIPT = BASE / "noteval_extractor" / "scripts" / "export_noteval_xml.py"
_XML_EXPORT_OUT = BASE / "noteval_extractor" / "xml"


def _run_export_noteval_xml(
    out: Path,
    *,
    map_tranches: bool = False,
    tranche_cache: Path | None = None,
    no_tranche_db: bool = False,
) -> dict[str, Any]:
    script = _XML_EXPORT_SCRIPT
    if not script.is_file():
        raise HTTPException(status_code=500, detail=f"export_noteval_xml.py missing: {script}")
    if not (out / "02_tranche_class_balances.md").is_file():
        raise HTTPException(
            status_code=400,
            detail="02_tranche_class_balances.md missing — run extraction (at least 01–02) first.",
        )
    xml_out = _XML_EXPORT_OUT
    try:
        xml_out.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not create xml output dir: {e!s}") from e

    cmd = [
        sys.executable,
        str(script),
        str(out),
        "--out-dir",
        str(xml_out),
    ]
    if map_tranches:
        cmd.append("--map-tranches")
    if tranche_cache and tranche_cache.is_file():
        cmd.extend(["--tranche-cache", str(tranche_cache)])
    if no_tranche_db:
        cmd.append("--no-tranche-db")
    proc = subprocess.run(
        cmd,
        cwd=str(BASE),
        capture_output=True,
        text=True,
        **_SUBPROCESS_TEXT_KW,
        timeout=180,
        env=_python_subprocess_env(),
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    expected = (xml_out / f"{out.name}.xml").resolve()
    if proc.returncode != 0:
        tail = log.strip()[-8000:] if log.strip() else "(no subprocess output)"
        raise HTTPException(
            status_code=502,
            detail=f"export_noteval_xml exited with {proc.returncode}. Output:\n{tail}",
        )
    return {
        "ok": True,
        "xml_path": str(expected),
        "xml_exists": expected.is_file(),
        "folder": out.name,
        "log_tail": log.strip()[-2000:] if log.strip() else "",
    }


def _deal_stem_for_xml(folder_name: str) -> str:
    """Map output folder basename to ``noteval_extractor/xml/{stem}.xml``."""
    stem = folder_name.strip()
    if stem.endswith("_sdk"):
        stem = stem[: -len("_sdk")]
    elif stem.endswith("_llm"):
        stem = stem[: -len("_llm")]
    return stem


def _resolve_xml_paths_for_compare(folder_names: list[str]) -> tuple[list[Path], list[str]]:
    """Return (existing XML paths, folder stems with no XML file)."""
    found: list[Path] = []
    missing: list[str] = []
    for raw in folder_names:
        stem = _deal_stem_for_xml(raw)
        if not stem:
            continue
        xml_path = (_XML_EXPORT_OUT / f"{stem}.xml").resolve()
        if xml_path.is_file():
            found.append(xml_path)
        else:
            missing.append(stem)
    return found, missing


def _build_xml_db_compare_xlsx(items: list[Any]) -> bytes:
    if _xml_db_compare is None:
        raise HTTPException(
            status_code=500,
            detail="batch_tranche_mapping.py is missing or failed to import.",
        )
    if not _xml_db_compare.openpyxl_available():
        raise HTTPException(
            status_code=500,
            detail="openpyxl is not installed. Run: py -3 -m pip install openpyxl",
        )
    from map_tranches import TrancheMapper  # type: ignore[import-untyped]

    try:
        mapper = TrancheMapper(use_db=True)
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Database tranche mapping unavailable: {e!s}",
        ) from e
    try:
        return _xml_db_compare.build_workbook(items, mapper, compare_db=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"XML DB compare failed: {e!s}") from e


class CompareXmlDbBody(BaseModel):
    """Compare ``noteval_export`` XML tranche rows against ``cdo_noteval_tranches``."""

    output_dir: str = Field(
        ...,
        min_length=1,
        description="Active deal folder under noteval_extractor/output (confirms access).",
    )
    folder_names: list[str] = Field(
        default_factory=list,
        description=(
            "If non-empty, compare XML for these folder basenames; "
            "else compare XML for the active folder only."
        ),
    )


@app.post("/api/extraction/compare-xml-db")
def extraction_compare_xml_db(body: CompareXmlDbBody):
    """
    Map tranches from export XML and compare class fields to EMS ``cdo_noteval_tranches``.
    Also compares summed ``valuation_fees`` in XML to ``SUM(amount)`` in ``cdo_noteval_deal``.
    Returns an .xlsx with Match rates, Fee totals, Tranche mapping, and Summary sheets.
    """
    out = _allowed_output_dir(body.output_dir)
    names = [n.strip() for n in body.folder_names if n and n.strip()]
    if not names:
        names = [_deal_stem_for_xml(out.name)]

    xml_paths, missing = _resolve_xml_paths_for_compare(names)
    if not xml_paths:
        missing_hint = ", ".join(missing[:5])
        if len(missing) > 5:
            missing_hint += "…"
        raise HTTPException(
            status_code=400,
            detail=(
                f"No export XML found under {_XML_EXPORT_OUT} for: {missing_hint}. "
                "Run Export XML first (writes noteval_extractor/xml/{deal}_{date}.xml)."
            ),
        )

    items = _xml_db_compare.items_from_xml_paths(xml_paths)
    xlsx = _build_xml_db_compare_xlsx(items)

    if len(xml_paths) == 1:
        filename = f"xml_db_compare_{xml_paths[0].stem}.xlsx"
    else:
        filename = f"xml_db_compare_{len(xml_paths)}deals.xlsx"

    note = ""
    if missing:
        note = f"; skipped {len(missing)} folder(s) with no XML"

    return Response(
        content=xlsx,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Noteval-Compared": str(len(xml_paths)),
            "X-Noteval-Missing-Xml": str(len(missing)),
            "X-Noteval-Compare-Note": note.strip("; "),
        },
    )


@app.post("/api/extraction/export-xml")
def extraction_export_xml(body: ExtractionExportXmlBody):
    """
    Run export_noteval_xml.py for the active deal folder; writes
    ``noteval_extractor/xml/<folder_basename>.xml`` under the repo.
    """
    out = _allowed_output_dir(body.output_dir)
    cache = Path(body.tranche_cache).resolve() if body.tranche_cache.strip() else None
    return _run_export_noteval_xml(
        out,
        map_tranches=body.map_tranches,
        tranche_cache=cache,
        no_tranche_db=body.no_tranche_db,
    )


def _batch_export_folder_path(folder_name: str, source: str) -> Path:
    """Resolve output folder for batch XML export.

    SDK and LLM deliverables both live in ``{dealId}_{YYYYMMDD}`` folders. Legacy
    ``*_sdk`` / ``*_llm`` suffixes on queue names are stripped before lookup.
    """
    _ = source  # discovery filter only; path resolution is the same for both pipelines
    base = folder_name.strip()
    for suf in ("_sdk", "_llm"):
        if base.endswith(suf):
            base = base[: -len(suf)]
            break
    return (_OUTPUT_ROOT / base).resolve()


class BatchExportXmlBody(BaseModel):
    output_dir: str = Field(..., min_length=1)
    source: Literal["all", "llm", "sdk"] = "llm"
    folder_names: list[str] = Field(default_factory=list)
    max_deals: int = Field(default=0, ge=0, le=500)
    map_tranches: bool = False
    tranche_cache: str = ""
    no_tranche_db: bool = False


@app.post("/api/extraction/batch-export-xml")
def extraction_batch_export_xml(body: BatchExportXmlBody):
    """
    Export ``noteval_export`` XML for each batch deal folder into ``noteval_extractor/xml/``.
    Requires at least ``01`` and ``02`` in each folder (``03`` optional for 01–02-only runs).
    """
    _ = _allowed_output_dir(body.output_dir)
    if not _XML_EXPORT_SCRIPT.is_file():
        raise HTTPException(status_code=500, detail="export_noteval_xml.py missing")

    names = [n.strip() for n in body.folder_names if n and n.strip()]
    if names:
        deal_dirs = [_batch_export_folder_path(n, body.source) for n in names]
    else:
        deal_dirs = _batch_validate.discover_deal_dirs(_OUTPUT_ROOT, source=body.source)
        if int(body.max_deals) > 0:
            deal_dirs = deal_dirs[: int(body.max_deals)]

    if not deal_dirs:
        raise HTTPException(
            status_code=400,
            detail="No extraction folders found. Run batch extraction first or pass folder_names.",
        )

    cache = Path(body.tranche_cache).resolve() if body.tranche_cache.strip() else None
    results: list[dict[str, Any]] = []
    ok_count = 0
    for d in deal_dirs:
        if not d.is_dir():
            results.append(
                {"folder": d.name, "ok": False, "error": "folder not found", "xml_path": ""}
            )
            continue
        try:
            row = _run_export_noteval_xml(
                d,
                map_tranches=body.map_tranches,
                tranche_cache=cache,
                no_tranche_db=body.no_tranche_db,
            )
            results.append({**row, "folder": d.name, "output_dir": str(d)})
            ok_count += 1
        except HTTPException as e:
            results.append(
                {
                    "folder": d.name,
                    "ok": False,
                    "error": str(e.detail),
                    "xml_path": "",
                    "output_dir": str(d),
                }
            )

    return {
        "ok": ok_count == len(deal_dirs),
        "exported": ok_count,
        "total": len(deal_dirs),
        "xml_root": str(_XML_EXPORT_OUT.resolve()),
        "map_tranches": body.map_tranches,
        "results": results,
    }


_BATCH_SUMMARY_MAX_CHARS = 500_000
_BATCH_VALIDATE_SCRIPT = BASE / "noteval_extractor" / "scripts" / "batch_validate_noteval.py"


def _batch_validation_summary_name(source: str = "all") -> str:
    """Roll-up summary filename under the output root (SDK uses a separate file)."""
    if (source or "all").strip().lower() == "sdk":
        return "batch_validation_summary_sdk.md"
    return "batch_validation_summary.md"


class BatchValidateBody(BaseModel):
    """Run ``batch_validate_noteval.py`` on folders under the output root."""

    output_dir: str = Field(
        ...,
        min_length=1,
        description="Any deal folder under noteval_extractor/output (used to confirm access).",
    )
    source: Literal["all", "llm", "sdk"] = "all"
    strict: bool = False
    max_deals: int = Field(
        default=0,
        ge=0,
        description="Max folders to validate; 0 = no limit.",
    )
    folder_names: list[str] = Field(
        default_factory=list,
        description="If non-empty, only validate these folder basenames.",
    )
    inventory_segmented: bool = True
    all_log_costs: bool = Field(
        default=False,
        description="If true, sum cumulative cost_usd from usage JSONL logs (legacy).",
    )
    extraction_batch_id: str = Field(
        default="",
        description="Optional batch UUID; load logs/batch_cost/<id>.json for costs.",
    )


class BatchCostManifestBody(BaseModel):
    """Persist per-deal costs from a completed UI batch extraction run."""

    batch_id: str = Field(..., min_length=1)
    source: Literal["llm", "sdk", "all"] = "llm"
    costs: dict[str, float] = Field(default_factory=dict)
    folder_names: list[str] = Field(default_factory=list)


@app.post("/api/extraction/batch-cost-manifest")
def extraction_batch_cost_manifest(body: BatchCostManifestBody):
    """Write latest batch cost manifest for batch validation summaries."""
    try:
        path = _batch_cost.write_batch_cost_manifest(
            source=body.source,
            batch_id=body.batch_id.strip(),
            costs=body.costs,
            folder_names=body.folder_names,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not write manifest: {e!s}") from e
    return {
        "ok": True,
        "path": str(path.resolve()),
        "batch_id": body.batch_id.strip(),
        "source": body.source,
        "deal_count": len(body.costs),
    }


class BatchValidationSummaryBody(BaseModel):
    output_dir: str = Field(..., min_length=1)
    source: Literal["all", "llm", "sdk"] = "all"


@app.post("/api/extraction/batch-validation-summary")
def extraction_batch_validation_summary(body: BatchValidationSummaryBody):
    """
    Read the batch validation roll-up next to per-deal folders (same directory as
    ``validate_noteval`` output root). SDK runs use ``batch_validation_summary_sdk.md``;
    LLM / all use ``batch_validation_summary.md``.
    """
    _ = _allowed_output_dir(body.output_dir)
    summary_name = _batch_validation_summary_name(body.source)
    summary_path = (_OUTPUT_ROOT / summary_name).resolve()
    if not summary_path.is_file():
        return {
            "found": False,
            "path": str(summary_path),
            "content": "",
            "truncated": False,
            "source": body.source,
            "hint": (
                f"No {summary_name} yet. From repo root run e.g.: "
                f'py -3 noteval_extractor/scripts/batch_validate_noteval.py --output-root "{_OUTPUT_ROOT}" '
                f"--source {body.source}"
            ),
        }
    text, truncated = _read_text_capped(summary_path, _BATCH_SUMMARY_MAX_CHARS)
    return {
        "found": True,
        "path": str(summary_path),
        "content": text,
        "truncated": truncated,
        "source": body.source,
    }


@app.post("/api/extraction/batch-validate")
def extraction_batch_validate(body: BatchValidateBody):
    """
    Run ``batch_validate_noteval.py`` and return the roll-up summary for ``source``.
    SDK → ``batch_validation_summary_sdk.md``; LLM / all → ``batch_validation_summary.md``.
    """
    _ = _allowed_output_dir(body.output_dir)
    if not _BATCH_VALIDATE_SCRIPT.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"batch_validate_noteval.py missing: {_BATCH_VALIDATE_SCRIPT}",
        )
    cmd: list[str] = [
        sys.executable,
        str(_BATCH_VALIDATE_SCRIPT),
        "--output-root",
        str(_OUTPUT_ROOT),
        "--source",
        body.source,
        "--max-deals",
        str(int(body.max_deals)),
    ]
    if body.strict:
        cmd.append("--strict")
    if not body.inventory_segmented:
        cmd.append("--no-inventory-segmented")
    if body.all_log_costs:
        cmd.append("--all-log-costs")
    bid = body.extraction_batch_id.strip()
    if bid:
        cmd.extend(["--extraction-batch-id", bid])
    names = [n.strip() for n in body.folder_names if n and n.strip()]
    if names:
        cmd.extend(["--folders", *names])
    proc = subprocess.run(
        cmd,
        cwd=str(BASE),
        capture_output=True,
        text=True,
        **_SUBPROCESS_TEXT_KW,
        timeout=3600,
        env=_python_subprocess_env(),
    )
    log = (proc.stdout or "") + (proc.stderr or "")
    summary_path = (_OUTPUT_ROOT / _batch_validation_summary_name(body.source)).resolve()
    summary_text = ""
    truncated = False
    if summary_path.is_file():
        summary_text, truncated = _read_text_capped(summary_path, _BATCH_SUMMARY_MAX_CHARS)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "source": body.source,
        "strict": body.strict,
        "folder_names": names,
        "summary_path": str(summary_path),
        "summary_found": summary_path.is_file(),
        "content": summary_text,
        "truncated": truncated,
        "log_tail": log.strip()[-12_000:] if log.strip() else "",
    }


class ExtractionDeliverableSaveBody(ExtractionDirBody):
    target: Literal["01", "02", "03", "04"]
    content: str = Field(default="")


@app.get("/api/extraction/template-hints/{target}")
def extraction_template_hints(target: str):
    if target not in _TARGET_TO_FILE:
        raise HTTPException(status_code=400, detail="target must be 01, 02, 03, or 04")
    text = _slice_extraction_template(target)  # type: ignore[arg-type]
    return {"target": target, "filename": _TARGET_TO_FILE[target], "content": text}


@app.put("/api/extraction/deliverable")
def extraction_deliverable_save(body: ExtractionDeliverableSaveBody):
    """Write one of 01–04 markdown files into output_dir."""
    out = _allowed_output_dir(body.output_dir)
    fn = _TARGET_TO_FILE[body.target]
    path = out / fn
    try:
        path.write_text(body.content, encoding="utf-8", newline="\n")
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not write file: {e!s}") from e
    return {"ok": True, "path": str(path.resolve()), "filename": fn}


class ExtractionDraftBody(ExtractionDirBody):
    target: Literal["01", "02", "03", "04"]
    extra_instructions: str = ""
    timeout_seconds: int = Field(default=300, ge=60, le=600)
    include_full_extraction_templates: bool = False
    full_templates_max_chars: int = Field(default=100_000, ge=5000, le=250_000)
    include_skill_md: bool = True
    skill_max_chars: int = Field(default=50_000, ge=2000, le=120_000)
    include_agent_md: bool = True
    agent_max_chars: int = Field(default=35_000, ge=2000, le=80_000)
    max_tool_turns: int | None = Field(default=None, ge=3, le=30)
    prior_caps_per_file: int = Field(default=42_000, ge=2000, le=80_000)


def _draft_deliverable_core(
    out: Path,
    target: Literal["01", "02", "03", "04"],
    s: dict[str, Any],
    *,
    prior_deliverables: str = "",
) -> dict[str, Any]:
    """Run one LLM draft via tool-calling (no write). ``s`` is draft settings without output_dir/target."""
    template_excerpt = _slice_extraction_template(target)
    fn = _TARGET_TO_FILE[target]
    repo_ctx, context_meta = _draft.build_draft_repository_context(
        include_full_templates=bool(s.get("include_full_extraction_templates")),
        full_templates_max_chars=int(s.get("full_templates_max_chars", 100_000)),
        include_skill_md=bool(s.get("include_skill_md", True)),
        skill_max_chars=int(s.get("skill_max_chars", 50_000)),
        include_agent_md=bool(s.get("include_agent_md", True)),
        agent_max_chars=int(s.get("agent_max_chars", 35_000)),
    )
    prior = prior_deliverables
    if target == "04" and not prior.strip():
        prior = _draft.read_prior_deliverables_for_04(out, int(s.get("prior_caps_per_file", 42_000)))
    max_turns = s.get("max_tool_turns")
    markdown, draft_meta, usage_record = _draft.openai_chat_completion_with_tools(
        out_dir=out,
        target=target,
        filename=fn,
        template_excerpt=template_excerpt,
        repository_context=repo_ctx,
        prior_deliverables=prior,
        extra_instructions=str(s.get("extra_instructions") or ""),
        read_prior_fn=lambda: _draft.read_prior_deliverables_for_04(
            out, int(s.get("prior_caps_per_file", 42_000))
        ),
        timeout=int(s.get("timeout_seconds", 300)),
        max_turns=int(max_turns) if max_turns is not None else None,
    )
    completion_mode = str(draft_meta.get("mode") or "tools_clean")
    gather_note = (
        f"Tool-calling mode ({completion_mode}); "
        f"turns={draft_meta.get('tool_turns')}/{draft_meta.get('max_tool_turns')}; "
        f"tools={len(draft_meta.get('tools_called') or [])} call(s)"
    )
    if draft_meta.get("tools_exhausted"):
        gather_note += " — WARN: synthesis recovery after max turns"
    return {
        "markdown": markdown.strip(),
        "filename": fn,
        "chunks_used": [],
        "gather_note": gather_note,
        "context_included": context_meta,
        "model": _draft.draft_config_public().get("model"),
        "draft_meta": draft_meta,
        "usage": usage_record,
        "mode": completion_mode,
    }


_PIPELINE_LOCK = threading.Lock()
_PIPELINE_JOBS: dict[str, dict[str, Any]] = {}

_SDK_LOCK = threading.Lock()
_SDK_JOBS: dict[str, dict[str, Any]] = {}

_CURSOR_SDK_DIR = BASE / "cursor_sdk_compare"
_CURSOR_SDK_SCRIPT = _CURSOR_SDK_DIR / "run-extract.mjs"
_CURSOR_API_KEY_HINT = (
    "Set CURSOR_API_KEY in noteval_extractor/.env, repo .env, or cursor_sdk_compare/.env "
    "(Dashboard → Integrations), then restart the server."
)


def _local_now_iso() -> str:
    """Wall time on the server in the OS-configured local timezone (ISO 8601 with offset)."""
    return datetime.now().astimezone().isoformat()


def _pipeline_log(job_id: str, message: str) -> None:
    ts = _local_now_iso()
    line = f"{ts} {message}"
    with _PIPELINE_LOCK:
        job = _PIPELINE_JOBS.get(job_id)
        if job is not None:
            job["logs"].append(line)
    _pipeline_log_file.append(job_id, message, ts=ts)


class PipelineStartBody(ExtractionDirBody):
    """Unattended 01→04 draft+write, then optional validate (background job)."""

    use_llm_folder: bool = False
    """When false (default), draft into ``output_dir`` (segmented ``<deal>_mmddyyyy``). Legacy: true copies to ``<deal>_llm``."""
    targets: list[Literal["01", "02", "03", "04"]] | None = None
    force_reextract: bool = False
    """When true, delete and overwrite all target deliverable files even if they already exist on disk."""
    force_reextract_targets: list[Literal["01", "02", "03", "04"]] | None = None
    """Subset of targets to force-overwrite. When None and force_reextract is true, all targets are forced."""
    include_full_extraction_templates: bool = False
    full_templates_max_chars: int = Field(default=100_000, ge=5000, le=250_000)
    include_skill_md: bool = True
    skill_max_chars: int = Field(default=50_000, ge=2000, le=120_000)
    include_agent_md: bool = True
    agent_max_chars: int = Field(default=35_000, ge=2000, le=80_000)
    prior_caps_per_file: int = Field(default=42_000, ge=2000, le=80_000)
    extra_instructions: str = ""
    timeout_seconds_per_step: int = Field(default=300, ge=60, le=600)
    run_map_fees: bool = True
    """When true and **03** is in targets, run classify_waterfall_fees.py then map_valuation_fees.py after drafting."""
    run_llm_fee_classify: bool = True
    """When true (and run_map_fees is true), run LLM step 5b after classify_waterfall_fees.py
    to resolve uncertain/catch-all rows the regex could not confidently map.
    Default on: regex covers ~90% of rows; LLM only sees the residual uncertain rows
    so the incremental cost is small (~$0.001/deal on average)."""
    run_validate: bool = True
    max_tool_turns: int | None = Field(default=None, ge=3, le=30)


def _prepare_sibling_folder(source: Path, suffix: str, *, force: bool) -> Path:
    """Copy segmentation artifacts to ``<source.name><suffix>`` (e.g. ``_llm``, ``_sdk``)."""
    source = source.resolve()
    if suffix not in ("_sdk", "_llm"):
        raise ValueError(f"unsupported suffix: {suffix!r}")
    dest = source.parent / f"{source.name}{suffix}"
    prepare_script = BASE / "noteval_extractor" / "scripts" / "prepare_sdk_compare_folder.py"
    if not prepare_script.is_file():
        raise RuntimeError(f"Missing {prepare_script}")
    args = [sys.executable, str(prepare_script), str(source), "--dest", str(dest)]
    if force or dest.exists():
        args.append("--force")
    proc = subprocess.run(
        args,
        cwd=str(BASE),
        capture_output=True,
        text=True,
        **_SUBPROCESS_TEXT_KW,
        timeout=120,
    )
    if proc.returncode != 0:
        tail = ((proc.stdout or "") + (proc.stderr or ""))[-4000:]
        raise RuntimeError(f"prepare_sdk_compare_folder failed:\n{tail}")
    return dest


def _pipeline_worker(job_id: str, body: PipelineStartBody) -> None:
    with _PIPELINE_LOCK:
        job = _PIPELINE_JOBS.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        job["started_at"] = _local_now_iso()

    pipe_cfg = _llm_pipeline.LlmPipelineConfig(
        targets=body.targets,
        use_llm_folder=body.use_llm_folder,
        force_reextract=body.force_reextract,
        force_reextract_targets=body.force_reextract_targets,
        include_full_extraction_templates=body.include_full_extraction_templates,
        full_templates_max_chars=body.full_templates_max_chars,
        include_skill_md=body.include_skill_md,
        skill_max_chars=body.skill_max_chars,
        include_agent_md=body.include_agent_md,
        agent_max_chars=body.agent_max_chars,
        prior_caps_per_file=body.prior_caps_per_file,
        extra_instructions=body.extra_instructions,
        timeout_seconds_per_step=body.timeout_seconds_per_step,
        run_map_fees=body.run_map_fees,
        run_llm_fee_classify=body.run_llm_fee_classify,
        run_validate=body.run_validate,
        max_tool_turns=body.max_tool_turns,
        write_cost_manifest=True,
    )

    try:
        result = _llm_pipeline.run_llm_pipeline(
            body.output_dir,
            run_id=job_id,
            config=pipe_cfg,
            log=lambda msg: _pipeline_log(job_id, msg),
        )
        with _PIPELINE_LOCK:
            job = _PIPELINE_JOBS.get(job_id)
            if job is not None:
                job["status"] = "done"
                job["result"] = result
                job["finished_at"] = _local_now_iso()
                if result.get("pipeline_log_path"):
                    job["log_path"] = result["pipeline_log_path"]
    except Exception as e:
        with _PIPELINE_LOCK:
            job = _PIPELINE_JOBS.get(job_id)
            if job is not None:
                job["status"] = "error"
                job["error"] = str(e)
                job["finished_at"] = _local_now_iso()


@app.get("/api/extraction/draft-usage-log")
def extraction_draft_usage_log(tail: int = Query(default=40, ge=1, le=500)):
    """Tail of JSONL usage log + aggregated token/cost summary for those lines."""
    return _draft.draft_usage_log_read_tail(max_lines=tail)


@app.get("/api/extraction/sdk-usage-log")
def extraction_sdk_usage_log(tail: int = Query(default=40, ge=1, le=500)):
    """Tail of SDK agent JSONL usage log (tokens + estimated cost per run)."""
    return _sdk_usage.sdk_usage_log_read_tail(max_lines=tail)


@app.get("/api/extraction/draft-config")
def extraction_draft_config():
    """Whether LLM draft and Cursor SDK are configured (no secrets returned)."""
    cfg = _draft.draft_config_public()
    if not cfg.get("configured"):
        cfg["hint"] = _DRAFT_KEY_HINT
    cfg["cursor_sdk"] = sdk_config_public()
    plog_dir = _pipeline_log_file.pipeline_log_dir()
    cfg["pipeline_log"] = {
        "enabled": _pipeline_log_file.pipeline_log_enabled(),
        "dir": str(plog_dir) if _pipeline_log_file.pipeline_log_enabled() else None,
        "deal_mirror": "pipeline_run.log",
    }
    ap = _noteval_agent_md_path()
    cfg["repo_context_files"] = {
        "extraction_templates_md": _EXTRACTION_TEMPLATES_MD.is_file(),
        "skill_md": _SKILL_MD.is_file(),
        "agent_md": bool(ap),
        "agent_resolved_path": str(ap) if ap else None,
    }
    return cfg


@app.post("/api/extraction/draft")
def extraction_draft(body: ExtractionDraftBody):
    """
    Draft one deliverable via the tool-calling LLM loop (read index/chunks via tools).
    """
    cfg = _draft.draft_config_public()
    if not cfg.get("configured"):
        raise HTTPException(status_code=503, detail=f"LLM not configured. {_DRAFT_KEY_HINT}")
    out = _allowed_output_dir(body.output_dir)
    s = body.model_dump(exclude={"output_dir", "target"})
    prior = ""
    if body.target == "04":
        prior = _draft.read_prior_deliverables_for_04(out, 42_000)
    try:
        core = _draft_deliverable_core(
            out,
            body.target,
            s,
            prior_deliverables=prior,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True, "target": body.target, **core}


@app.post("/api/extraction/pipeline/start")
def extraction_pipeline_start(body: PipelineStartBody):
    """
    Start unattended multi-step pipeline (draft+write 01→04, map fees when 03, then validate) in a background thread.
    Poll GET /api/extraction/pipeline/{job_id} for status and logs.
    """
    cfg = _draft.draft_config_public()
    if not cfg.get("configured"):
        raise HTTPException(status_code=503, detail=f"LLM not configured. {_DRAFT_KEY_HINT}")
    _ = _allowed_output_dir(body.output_dir)
    job_id = str(uuid.uuid4())
    with _PIPELINE_LOCK:
        _PIPELINE_JOBS[job_id] = {
            "status": "queued",
            "logs": [],
            "result": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
    threading.Thread(
        target=_pipeline_worker,
        args=(job_id, body),
        daemon=True,
    ).start()
    return {"job_id": job_id, "poll_url": f"/api/extraction/pipeline/{job_id}"}


@app.get("/api/extraction/pipeline/{job_id}")
def extraction_pipeline_status(job_id: str):
    with _PIPELINE_LOCK:
        job = _PIPELINE_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {"job_id": job_id, **job}


def _cursor_api_key_configured() -> bool:
    return bool(os.environ.get("CURSOR_API_KEY", "").strip())


def _resolve_node_npm() -> tuple[Path, Path]:
    """Return (node.exe, npm.cmd) for Cursor SDK subprocess."""
    candidates = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "nodejs",
        Path(r"C:\Program Files\nodejs"),
    ]
    for base in candidates:
        node = base / "node.exe"
        npm = base / "npm.cmd"
        if node.is_file() and npm.is_file():
            return node, npm
    node_which = shutil.which("node")
    npm_which = shutil.which("npm.cmd") or shutil.which("npm")
    if node_which and npm_which:
        return Path(node_which), Path(npm_which)
    raise RuntimeError(
        "Node.js not found. Install Node LTS (npm in PATH) and restart the server terminal."
    )


def sdk_config_public() -> dict[str, bool | str | None]:
    node_ok = False
    sdk_installed = (_CURSOR_SDK_DIR / "node_modules" / "@cursor" / "sdk").is_dir()
    note = None
    try:
        _resolve_node_npm()
        node_ok = True
    except RuntimeError as e:
        note = str(e)
    if node_ok and not sdk_installed:
        note = (
            (note + " " if note else "")
            + f"Run: cd {_CURSOR_SDK_DIR.name} && npm install"
        )
    return {
        "configured": _cursor_api_key_configured() and node_ok and sdk_installed,
        "api_key_set": _cursor_api_key_configured(),
        "node_ok": node_ok,
        "sdk_package_installed": sdk_installed,
        "script_path": str(_CURSOR_SDK_SCRIPT) if _CURSOR_SDK_SCRIPT.is_file() else None,
        "note": note,
    }


def _sdk_log(job_id: str, message: str) -> None:
    line = f"{_local_now_iso()} {message}"
    with _SDK_LOCK:
        job = _SDK_JOBS.get(job_id)
        if job is not None:
            job["logs"].append(line)


def _sdk_failure_message_from_output(output: str, returncode: int) -> str:
    """Summarize run-extract.mjs failure for the UI job error field."""
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    cursor_err = next((ln for ln in reversed(lines) if ln.startswith("Cursor error:")), None)
    missing = next((ln for ln in reversed(lines) if ln.startswith("Missing deliverables:")), None)
    run_line = next(
        (ln for ln in reversed(lines) if ln.startswith("Run finished: status=error")),
        None,
    )
    startup = next(
        (ln for ln in reversed(lines) if ln.startswith("Agent startup failed:")),
        None,
    )
    if returncode == 1 and startup:
        return startup
    if cursor_err:
        detail = cursor_err[len("Cursor error:") :].strip() or "unknown"
        parts = [f"Cursor SDK agent error: {detail}"]
        if missing:
            parts.append(missing)
        if run_line and "id=" in run_line:
            parts.append(run_line)
        return " | ".join(parts)
    if missing:
        return f"Cursor SDK agent failed — {missing} (exit {returncode})"
    if run_line:
        return f"{run_line} (exit {returncode}). See log above."
    return f"run-extract.mjs exited {returncode}. See log above."


class SdkStartBody(ExtractionDirBody):
    """Run local Cursor Agent to draft deliverables in the segmented deal folder (``{deal_id}_{YYYYMMDD}``)."""

    prepare: bool = Field(
        default=False,
        description="Legacy flag — only verifies ``_chunks/`` exists; no copy to ``*_sdk``.",
    )
    targets: list[Literal["01", "02", "03", "04"]] | None = Field(
        default=None,
        description="Subset to draft (default 01–04). Use [01, 02] for tranche mapping pilot.",
    )
    run_map_fees: bool = Field(
        default=True,
        description="When true, run run_fee_pipeline.py (classify → map 05) after the agent when 03 is in targets.",
    )
    run_llm_fee_classify: bool = Field(
        default=True,
        description="When true (and run_map_fees), run Step 5b LLM on uncertain fee rows via run_fee_pipeline.",
    )
    run_validate: bool = Field(
        default=False,
        description="When true, run validate_noteval.py after the agent (default: validate in UI).",
    )
    model: str = ""
    timeout_seconds: int = Field(default=7200, ge=120, le=14_400)


def _sdk_dirs_from_source(source: Path) -> tuple[Path, Path]:
    """Return (segmented deal folder, sibling ``<deal>_sdk`` folder)."""
    source = source.resolve()
    if source.name.endswith("_sdk"):
        sdk_dir = source
        deal_dir = source.parent / source.name[: -len("_sdk")]
    else:
        deal_dir = source
        sdk_dir = source.parent / f"{source.name}_sdk"
    return deal_dir, sdk_dir


def _llm_deal_dir_from_active(active: Path) -> Path:
    """LLM deliverables always go in the segmented deal folder, never ``*_sdk``."""
    active = active.resolve()
    if active.name.endswith("_sdk"):
        deal_dir, _ = _sdk_dirs_from_source(active)
        return deal_dir
    if active.name.endswith("_llm"):
        deal_dir = active.parent / active.name[: -len("_llm")]
        if deal_dir.is_dir():
            return deal_dir
    return active


def _sdk_resolve_dirs(source: Path, *, prepare: bool) -> tuple[Path, Path]:
    """Return (deal folder, compare folder). Agent output is ``deal_dir``; compare uses sibling ``*_sdk`` when present."""
    deal_dir = _llm_deal_dir_from_active(source)
    sdk_sibling = deal_dir.parent / f"{deal_dir.name}_sdk"
    if prepare and not (deal_dir / "_chunks").is_dir():
        raise RuntimeError(f"Missing _chunks/ under {deal_dir}. Segment the PDF first.")
    compare_dir = sdk_sibling if sdk_sibling.is_dir() else deal_dir
    return deal_dir, compare_dir


def _sdk_worker(job_id: str, body: SdkStartBody) -> None:
    with _SDK_LOCK:
        job = _SDK_JOBS.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        job["started_at"] = _local_now_iso()

    result: dict[str, Any] = {
        "llm_dir": None,
        "sdk_dir": None,
        "fee_mapping": None,
        "validation": None,
    }
    try:
        if not _cursor_api_key_configured():
            raise RuntimeError(f"CURSOR_API_KEY not set. {_CURSOR_API_KEY_HINT}")
        if not _CURSOR_SDK_SCRIPT.is_file():
            raise RuntimeError(f"Missing {_CURSOR_SDK_SCRIPT}")
        if not (_CURSOR_SDK_DIR / "node_modules").is_dir():
            raise RuntimeError(
                f"Cursor SDK not installed. From repo root: cd {_CURSOR_SDK_DIR.name} && npm install"
            )

        source = _allowed_output_dir(body.output_dir)
        deal_dir = _llm_deal_dir_from_active(source)
        if source != deal_dir:
            _sdk_log(
                job_id,
                f"Active folder is {source.name}; SDK agent reads {deal_dir.name} (not *_sdk).",
            )
        if not (deal_dir / "_chunks").is_dir():
            raise RuntimeError(
                f"Missing _chunks/ under {deal_dir}. Segment the PDF into this folder first."
            )
        result["llm_dir"] = str(deal_dir)
        result["sdk_dir"] = str(deal_dir)
        result["deal_dir"] = str(deal_dir)
        result["in_place"] = True
        _sdk_log(job_id, f"Output folder: {deal_dir}")

        node_exe, _npm = _resolve_node_npm()

        sdk_targets = body.targets if body.targets else ["01", "02", "03", "04"]
        cmd = [
            str(node_exe),
            str(_CURSOR_SDK_SCRIPT.resolve()),
            str(deal_dir.resolve()),
            "--no-validate",
            "--targets",
            ",".join(sdk_targets),
        ]
        if body.model.strip():
            cmd.extend(["--model", body.model.strip()])

        env = os.environ.copy()
        _sdk_log(
            job_id,
            f"Starting Cursor SDK agent (targets: {','.join(sdk_targets)}) — may take many minutes…",
        )
        proc = subprocess.run(
            cmd,
            cwd=str(_CURSOR_SDK_DIR),
            capture_output=True,
            text=True,
            **_SUBPROCESS_TEXT_KW,
            timeout=int(body.timeout_seconds),
            env=env,
        )
        out_tail = ((proc.stdout or "") + (proc.stderr or ""))[-12_000:]
        for line in out_tail.splitlines():
            if line.strip():
                _sdk_log(job_id, line[:2000])
        if proc.returncode != 0:
            raise RuntimeError(
                _sdk_failure_message_from_output(
                    (proc.stdout or "") + (proc.stderr or ""),
                    proc.returncode,
                )
            )
        _sdk_log(job_id, "Cursor agent finished OK.")
        sdk_usage_tail = _sdk_usage.sdk_usage_log_read_tail(max_lines=80)
        if sdk_usage_tail.get("enabled") and sdk_usage_tail.get("path"):
            _sdk_log(job_id, f"SDK usage log: {sdk_usage_tail['path']}")
            parsed = sdk_usage_tail.get("parsed") or []
            want_folder = deal_dir.name
            last: dict[str, Any] | None = None
            for entry in reversed(parsed):
                if not isinstance(entry, dict):
                    continue
                if "_unparsed_line" in entry or "input_tokens" not in entry:
                    continue
                if str(entry.get("deal_folder") or "").strip() == want_folder:
                    last = entry
                    break
            if last is None:
                for entry in reversed(parsed):
                    if isinstance(entry, dict) and "_unparsed_line" not in entry and "input_tokens" in entry:
                        last = entry
                        break
            if last is not None:
                result["sdk_usage"] = {
                    "deal_folder": last.get("deal_folder"),
                    "model": last.get("model"),
                    "input_tokens": last.get("input_tokens"),
                    "output_tokens": last.get("output_tokens"),
                    "total_tokens": last.get("total_tokens"),
                    "cost_usd": last.get("cost_usd"),
                    "pricing_note": last.get("pricing_note"),
                }
                _sdk_log(
                    job_id,
                    "Logged run for this folder: "
                    f"deal={last.get('deal_folder')} "
                    f"tokens≈{last.get('total_tokens')} "
                    f"cost_usd≈{last.get('cost_usd')} "
                    f"({last.get('pricing_note')})",
                )
                cost_raw = last.get("cost_usd")
                folder_key = str(last.get("deal_folder") or want_folder).strip()
                if folder_key and cost_raw is not None:
                    try:
                        cost_val = float(cost_raw)
                        _batch_cost.write_batch_cost_manifest(
                            source="sdk",
                            batch_id=job_id,
                            costs={folder_key: cost_val},
                            folder_names=[folder_key],
                        )
                    except (TypeError, ValueError, OSError):
                        pass

        pdd = _maybe_run_apply_pdfplumber_pdd(deal_dir, sdk_targets)
        if pdd is not None:
            result["pdd_mapping"] = pdd
            if pdd.get("skipped"):
                _sdk_log(job_id, f"apply_pdfplumber_pdd skipped: {pdd.get('reason', '')}")
            else:
                _sdk_log(
                    job_id,
                    f"apply_pdfplumber_pdd: {len(pdd.get('changes') or [])} column patch(es); "
                    f"{pdd.get('cusip_rows', '?')} CUSIP / {pdd.get('class_rows', '?')} class rows",
                )
        elif "02" in sdk_targets:
            _sdk_log(job_id, "apply_pdfplumber_pdd skipped (no pdd_idd_pdfplumber.md).")

        idd = _maybe_run_apply_pdfplumber_idd(deal_dir, sdk_targets)
        if idd is not None:
            result["idd_mapping"] = idd
            if idd.get("skipped"):
                _sdk_log(job_id, f"apply_pdfplumber_idd skipped: {idd.get('reason', '')}")
            else:
                _sdk_log(
                    job_id,
                    f"apply_pdfplumber_idd: {len(idd.get('changes') or [])} column patch(es); "
                    f"{idd.get('cusip_rows', '?')} CUSIP / {idd.get('class_rows', '?')} class rows",
                )
        elif "02" in sdk_targets:
            _sdk_log(job_id, "apply_pdfplumber_idd skipped (no pdd_idd_pdfplumber.md).")

        if body.run_map_fees:
            _sdk_log(job_id, "Running run_fee_pipeline.py (waterfall cols → classify → LLM → map 05)…")
            fee_pipeline = _run_fee_pipeline(
                deal_dir,
                targets=sdk_targets,
                run_llm=body.run_llm_fee_classify,
                log_fn=lambda msg, _jid=job_id: _sdk_log(_jid, msg),
            )
            if fee_pipeline is None:
                if "03" not in sdk_targets:
                    _sdk_log(job_id, "run_fee_pipeline skipped (03 not in targets).")
            else:
                _apply_fee_pipeline_to_result(result, fee_pipeline)
                fc = fee_pipeline.get("classify") or {}
                if isinstance(fc, dict):
                    if fc.get("skipped"):
                        _sdk_log(
                            job_id,
                            f"classify_waterfall_fees skipped: {fc.get('reason', '')}",
                        )
                    else:
                        _sdk_log(
                            job_id,
                            f"classify_waterfall_fees: {fc.get('confident_count', '?')} confident, "
                            f"{fc.get('uncertain_count', '?')} uncertain fee row(s)",
                        )
                llm_fc = fee_pipeline.get("llm_classify") or {}
                if isinstance(llm_fc, dict) and body.run_llm_fee_classify:
                    if llm_fc.get("skipped"):
                        _sdk_log(
                            job_id,
                            f"LLM fee classify skipped: {llm_fc.get('reason', '')}",
                        )
                    elif llm_fc.get("error"):
                        _sdk_log(job_id, f"LLM fee classify error: {llm_fc.get('error')}")
                    elif not llm_fc.get("skipped"):
                        u = llm_fc.get("usage") or {}
                        _sdk_log(
                            job_id,
                            f"LLM fee classify: patched {llm_fc.get('patched_count', 0)} row(s) "
                            f"(tokens≈{u.get('total_tokens')} cost≈${u.get('cost_usd') or 0:.4f})",
                        )
                fm = fee_pipeline.get("map_fees") or {}
                if isinstance(fm, dict):
                    _sdk_log(
                        job_id,
                        f"map_valuation_fees mapped {fm.get('mapped_count', '?')} fee row(s); "
                        f"exit {fm.get('returncode')}",
                    )

        if body.run_validate:
            _sdk_log(
                job_id,
                "Layer 1: apply_distribution_usd/summary → fix_02 → validate_noteval.py…",
            )
            result["validation"] = _run_validate_noteval(deal_dir)
            v = result["validation"]
            if isinstance(v, dict):
                _log_distribution_apply(
                    lambda msg: _sdk_log(job_id, msg),
                    v.get("distribution_apply"),
                )
            _sdk_log(
                job_id,
                f"validate_noteval exit {v.get('returncode')}; report at {v.get('report_path')}",
            )

        with _SDK_LOCK:
            job = _SDK_JOBS.get(job_id)
            if job is not None:
                job["status"] = "done"
                job["result"] = result
                job["finished_at"] = _local_now_iso()
        _sdk_log(job_id, "SDK extraction job finished OK.")
    except Exception as e:
        _sdk_log(job_id, f"ERROR: {e!s}")
        with _SDK_LOCK:
            job = _SDK_JOBS.get(job_id)
            if job is not None:
                job["status"] = "error"
                job["error"] = str(e)
                job["result"] = result
                job["finished_at"] = _local_now_iso()


@app.get("/api/extraction/sdk-config")
def extraction_sdk_config():
    """Whether Cursor SDK compare is ready (no secrets returned)."""
    cfg = sdk_config_public()
    cfg["api_key_hint"] = _CURSOR_API_KEY_HINT if not cfg.get("api_key_set") else None
    return cfg


@app.post("/api/extraction/sdk-prepare")
def extraction_sdk_prepare(body: ExtractionDirBody):
    """
    Verify segmentation exists in the deal folder (``{deal_id}_{YYYYMMDD}``).
    Does not copy to ``*_sdk`` or run the Cursor agent — use before ``/api/extraction/sdk/start``.

    (Path is ``sdk-prepare``, not ``sdk/prepare``, so it is not captured by ``sdk/{job_id}``.)
    """
    raw = _allowed_output_dir(body.output_dir)
    deal_dir = _llm_deal_dir_from_active(raw)
    if not (deal_dir / "_chunks").is_dir():
        raise HTTPException(
            status_code=400,
            detail=f"Missing _chunks/ under {deal_dir}. Segment the PDF into the deal folder first.",
        )
    return {
        "ok": True,
        "source_dir": str(deal_dir),
        "deal_dir": str(deal_dir),
        "sdk_dir": str(deal_dir),
    }


@app.post("/api/extraction/sdk/start")
def extraction_sdk_start(body: SdkStartBody):
    """
    Background job: run ``cursor_sdk_compare/run-extract.mjs`` (extraction + classify/map fees when 03).
    Set ``run_validate=true`` to run validate_noteval.py after the agent.
    """
    cfg = sdk_config_public()
    if not cfg.get("configured"):
        detail = cfg.get("note") or _CURSOR_API_KEY_HINT
        raise HTTPException(status_code=503, detail=detail)
    _ = _allowed_output_dir(body.output_dir)
    job_id = str(uuid.uuid4())
    with _SDK_LOCK:
        _SDK_JOBS[job_id] = {
            "status": "queued",
            "logs": [],
            "result": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
        }
    threading.Thread(
        target=_sdk_worker,
        args=(job_id, body),
        daemon=True,
    ).start()
    return {"job_id": job_id, "poll_url": f"/api/extraction/sdk/{job_id}"}


@app.get("/api/extraction/sdk/{job_id}")
def extraction_sdk_status(job_id: str):
    with _SDK_LOCK:
        job = _SDK_JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {"job_id": job_id, **job}


@app.post("/api/extraction/validate")
def extraction_validate(body: ExtractionValidateBody):
    """Run validate_noteval.py on output_dir; return report text and exit code."""
    out = _allowed_output_dir(body.output_dir)
    val_script = BASE / "noteval_extractor" / "scripts" / "validate_noteval.py"
    if not val_script.is_file():
        raise HTTPException(status_code=500, detail=f"validate_noteval.py missing: {val_script}")
    cmd = [sys.executable, str(val_script), str(out)]
    if body.strict:
        cmd.append("--strict")
    proc = subprocess.run(
        cmd,
        cwd=str(BASE),
        capture_output=True,
        text=True,
        **_SUBPROCESS_TEXT_KW,
        timeout=120,
        env=_python_subprocess_env(),
    )
    report_path = out / "validation_report.md"
    report_text = ""
    if report_path.is_file():
        try:
            report_text = report_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            report_text = f"(Could not read validation_report.md: {e})"
    log = (proc.stdout or "") + (proc.stderr or "")
    return {
        "returncode": proc.returncode,
        "report": report_text,
        "log": log,
        "report_path": str(report_path),
        "manual_review_flags": _manual_review_flags_for_dir(out),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
