import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

BASE = Path(__file__).resolve().parent
_SCRIPTS = BASE / "noteval_extractor" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

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
import draft_llm as _draft  # noqa: E402
import get_file_path as _gfp  # noqa: E402  # type: ignore[import-untyped]

app = FastAPI()

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.get("/")
def root_page():
    return FileResponse(BASE / "static" / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "msg": "noteval UI backend"}


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


class SegmentBody(BaseModel):
    deal_id: str = Field(..., min_length=1)
    payment_date: str = Field(..., min_length=1)
    pdf_path: str = Field(..., min_length=1)
    waterfall_path: str = ""
    status: str = ""


class CheckReportPathsBody(BaseModel):
    """Verify resolved UNC/local paths exist before segmentation."""

    pdf_path: str = Field(..., min_length=1)
    waterfall_path: str = ""


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
    return {
        "ok": pdf_ok and (wf_ok is not False),
        "pdf_exists": pdf_ok,
        "waterfall_checked": bool(wf_raw),
        "waterfall_ok": wf_ok,
        "errors": errors,
    }


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
            ],
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=7200,
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
)

_DELIVERABLE_SET = frozenset(_DELIVERABLES)

_TARGET_TO_FILE: dict[str, str] = {
    "01": "01_report_metadata.md",
    "02": "02_tranche_class_balances.md",
    "03": "03_interest_principal_waterfall.md",
    "04": "04_extraction_summary.md",
}

_EXTRACTION_TEMPLATES_MD = (
    BASE / "noteval_extractor" / "references" / "extraction-templates.md"
)
_SKILL_MD = BASE / "noteval_extractor" / "SKILL.md"


def _noteval_agent_md_path() -> Path | None:
    for candidate in (
        BASE / "noteval_extractor" / "agents" / "noteval-extractor-agent.md",
        BASE / ".cursor" / "agents" / "noteval-extractor-agent.md",
    ):
        if candidate.is_file():
            return candidate
    return None


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


def _build_draft_repository_context(
    *,
    include_full_templates: bool,
    full_templates_max_chars: int,
    include_skill_md: bool,
    skill_max_chars: int,
    include_agent_md: bool,
    agent_max_chars: int,
) -> tuple[str, dict[str, object]]:
    """Plain-text blocks for the LLM (SKILL, agent, optional full templates)."""
    blocks: list[str] = []
    meta: dict[str, object] = {}

    if include_full_templates:
        text, tr = _read_text_capped(_EXTRACTION_TEMPLATES_MD, full_templates_max_chars)
        if text:
            label = _EXTRACTION_TEMPLATES_MD.name
            blocks.append(f"### Full `{label}` (entire reference; truncated={tr})\n\n{text}")
            meta["full_templates"] = {"path": str(_EXTRACTION_TEMPLATES_MD), "truncated": tr}
        else:
            meta["full_templates"] = {"path": str(_EXTRACTION_TEMPLATES_MD), "skipped": True}

    if include_skill_md:
        text, tr = _read_text_capped(_SKILL_MD, skill_max_chars)
        if text:
            blocks.append(f"### Full `{_SKILL_MD.name}` (noteval workflow skill; truncated={tr})\n\n{text}")
            meta["skill"] = {"path": str(_SKILL_MD), "truncated": tr}
        else:
            meta["skill"] = {"path": str(_SKILL_MD), "skipped": True}

    if include_agent_md:
        ap = _noteval_agent_md_path()
        if ap:
            text, tr = _read_text_capped(ap, agent_max_chars)
            if text:
                blocks.append(
                    f"### `{ap.name}` (noteval extractor agent text; truncated={tr})\n\n{text}"
                )
                meta["agent"] = {"path": str(ap), "truncated": tr}
            else:
                meta["agent"] = {"path": str(ap), "skipped": True}
        else:
            meta["agent"] = {"skipped": True, "reason": "noteval-extractor-agent.md not found"}

    return "\n\n---\n\n".join(blocks), meta


def _slice_extraction_template(target: Literal["01", "02", "03", "04"]) -> str:
    """Return the `## File NN` section from extraction-templates.md (excludes deprecated File 06 from File 03)."""
    path = _EXTRACTION_TEMPLATES_MD
    if not path.is_file():
        raise HTTPException(
            status_code=500,
            detail=f"Missing {_EXTRACTION_TEMPLATES_MD}",
        )
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    markers: dict[str, int] = {}
    for i, line in enumerate(lines):
        if line.startswith("## File "):
            key = line[8:10]
            if key in ("01", "02", "03", "04", "06"):
                markers[key] = i
    for need in ("01", "02", "03", "04"):
        if need not in markers:
            raise HTTPException(
                status_code=500,
                detail=f"Could not find '## File {need}' in extraction-templates.md",
            )
    end_map = {
        "01": markers["02"],
        "02": markers["03"],
        "03": markers.get("06", markers["04"]),
        "04": len(lines),
    }
    start = markers[target]
    end = end_map[target]
    return "\n".join(lines[start:end]).strip() + "\n"


def _allowed_output_dir(raw: str) -> Path:
    p = Path(raw).expanduser()
    try:
        p = p.resolve()
    except OSError as e:
        raise HTTPException(status_code=400, detail=f"Invalid output_dir: {e!s}") from e
    if not p.is_dir():
        raise HTTPException(status_code=400, detail="output_dir is not an existing directory")
    try:
        p.relative_to(_OUTPUT_ROOT)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"output_dir must be under {_OUTPUT_ROOT}",
        ) from None
    return p


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


def _run_validate_noteval(out: Path) -> dict[str, Any]:
    """Run validate_noteval.py on ``out`` and return report text plus process metadata."""
    val_script = BASE / "noteval_extractor" / "scripts" / "validate_noteval.py"
    cmd = [sys.executable, str(val_script), str(out)]
    proc = subprocess.run(
        cmd,
        cwd=str(BASE),
        capture_output=True,
        text=True,
        timeout=180,
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
    }


class ExtractionDirBody(BaseModel):
    output_dir: str = Field(..., min_length=1)


class ExtractionFileBody(ExtractionDirBody):
    relative_path: str = Field(..., min_length=1)
    max_bytes: int | None = Field(default=2_500_000, ge=1, le=10_000_000)
    allow_missing: bool = False


class ExtractionValidateBody(ExtractionDirBody):
    strict: bool = False


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
    for name in _DELIVERABLES:
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
    if body.allow_missing and rel_norm not in _DELIVERABLE_SET:
        raise HTTPException(
            status_code=400,
            detail="allow_missing is only allowed for 01–04 deliverable filenames",
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


def _normalize_chunk_rel(p: str) -> str:
    n = p.replace("\\", "/").strip().lstrip("/")
    if not n or ".." in Path(n).parts:
        raise HTTPException(status_code=400, detail="Invalid chunk_paths entry")
    if not (n.startswith("_chunks/") or n.startswith("_chunks_waterfall/")):
        raise HTTPException(
            status_code=400,
            detail="chunk_paths must be under _chunks/ or _chunks_waterfall/",
        )
    if Path(n).suffix.lower() != ".txt":
        raise HTTPException(status_code=400, detail="Only .txt chunk files are allowed")
    return n


def _gather_chunk_bundle(
    out: Path,
    *,
    chunk_paths: list[str],
    chunk_tree: Literal["primary", "waterfall", "both"],
    max_bytes_per_chunk: int,
    max_total_chunk_chars: int,
) -> tuple[str, list[str], str | None]:
    note_parts: list[str] = []
    used: list[str] = []
    parts: list[str] = []
    budget = max_total_chunk_chars
    per = max_bytes_per_chunk

    if chunk_paths:
        rels = [_normalize_chunk_rel(x) for x in chunk_paths]
    else:
        rels = []
        if chunk_tree in ("primary", "both"):
            d = out / "_chunks"
            if d.is_dir():
                rels.extend("_chunks/" + f.name for f in sorted(d.glob("pages_*.txt")))
        if chunk_tree in ("waterfall", "both"):
            d = out / "_chunks_waterfall"
            if d.is_dir():
                rels.extend(
                    "_chunks_waterfall/" + f.name for f in sorted(d.glob("pages_*.txt"))
                )
        if not rels:
            raise HTTPException(
                status_code=400,
                detail="No chunk files found. Segment the PDF or pass chunk_paths explicitly.",
            )

    total_chars = 0
    for rel in rels:
        if total_chars >= budget:
            note_parts.append(
                f"Stopped at global chunk budget ({budget} characters); remaining files omitted."
            )
            break
        path = _child_file(out, rel)
        if not path.is_file():
            note_parts.append(f"Skipped missing: {rel}")
            continue
        try:
            sz = path.stat().st_size
        except OSError:
            continue
        read_n = min(sz, per)
        with path.open("rb") as f:
            raw = f.read(read_n)
        text = raw.decode("utf-8", errors="replace")
        truncated_file = sz > per
        header = f"### File: `{rel}`"
        if truncated_file:
            header += " (truncated: max_bytes_per_chunk)"
        block = header + "\n\n" + text
        if total_chars + len(block) > budget:
            remain = budget - total_chars
            if remain > 500:
                block = block[:remain] + "\n\n[TRUNCATED to global chunk budget]\n"
                parts.append(block)
                used.append(rel)
            note_parts.append("Global chunk character budget reached mid-file.")
            break
        parts.append(block)
        used.append(rel)
        total_chars += len(block)

    note = "; ".join(note_parts) if note_parts else None
    return "\n\n".join(parts), used, note


class ExtractionDraftBody(ExtractionDirBody):
    target: Literal["01", "02", "03", "04"]
    chunk_paths: list[str] = Field(default_factory=list, max_length=48)
    chunk_tree: Literal["primary", "waterfall", "both"] = "primary"
    max_bytes_per_chunk: int = Field(default=100_000, ge=4096, le=500_000)
    max_total_chunk_chars: int = Field(default=180_000, ge=8000, le=500_000)
    include_current_draft: bool = False
    current_draft: str = ""
    extra_instructions: str = ""
    timeout_seconds: int = Field(default=300, ge=60, le=600)
    include_full_extraction_templates: bool = False
    full_templates_max_chars: int = Field(default=100_000, ge=5000, le=250_000)
    include_skill_md: bool = True
    skill_max_chars: int = Field(default=50_000, ge=2000, le=120_000)
    include_agent_md: bool = True
    agent_max_chars: int = Field(default=35_000, ge=2000, le=80_000)


def _draft_deliverable_core(
    out: Path,
    target: Literal["01", "02", "03", "04"],
    s: dict[str, Any],
    *,
    prior_deliverables: str = "",
) -> dict[str, Any]:
    """Run one LLM draft (no write). ``s`` is draft settings without output_dir/target."""
    template_excerpt = _slice_extraction_template(target)
    fn = _TARGET_TO_FILE[target]
    chunk_bundle, used_paths, gather_note = _gather_chunk_bundle(
        out,
        chunk_paths=list(s.get("chunk_paths") or []),
        chunk_tree=s["chunk_tree"],
        max_bytes_per_chunk=int(s["max_bytes_per_chunk"]),
        max_total_chunk_chars=int(s["max_total_chunk_chars"]),
    )
    repo_ctx, context_meta = _build_draft_repository_context(
        include_full_templates=bool(s.get("include_full_extraction_templates")),
        full_templates_max_chars=int(s.get("full_templates_max_chars", 100_000)),
        include_skill_md=bool(s.get("include_skill_md", True)),
        skill_max_chars=int(s.get("skill_max_chars", 50_000)),
        include_agent_md=bool(s.get("include_agent_md", True)),
        agent_max_chars=int(s.get("agent_max_chars", 35_000)),
    )
    current = str(s.get("current_draft") or "") if s.get("include_current_draft") else ""
    user_msg = _draft.build_user_message(
        target=target,
        filename=fn,
        repository_context=repo_ctx,
        template_excerpt=template_excerpt,
        prior_deliverables=prior_deliverables,
        chunk_bundle=chunk_bundle,
        current_draft=current,
        extra_instructions=str(s.get("extra_instructions") or ""),
    )
    markdown = _draft.openai_chat_completion(
        _draft.SYSTEM_PROMPT,
        user_msg,
        timeout=int(s.get("timeout_seconds", 300)),
    )
    return {
        "markdown": markdown.strip(),
        "filename": fn,
        "chunks_used": used_paths,
        "gather_note": gather_note,
        "context_included": context_meta,
        "model": _draft.draft_config_public().get("model"),
    }


def _read_prior_deliverables_for_04(out: Path, cap_each: int) -> str:
    parts: list[str] = []
    for tid in ("01", "02", "03"):
        name = _TARGET_TO_FILE[tid]
        p = out / name
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > cap_each:
            text = text[:cap_each] + "\n\n[TRUNCATED]\n"
        parts.append(f"### `{name}`\n\n{text}")
    return "\n\n".join(parts)


_PIPELINE_LOCK = threading.Lock()
_PIPELINE_JOBS: dict[str, dict[str, Any]] = {}


def _local_now_iso() -> str:
    """Wall time on the server in the OS-configured local timezone (ISO 8601 with offset)."""
    return datetime.now().astimezone().isoformat()


def _pipeline_log(job_id: str, message: str) -> None:
    line = f"{_local_now_iso()} {message}"
    with _PIPELINE_LOCK:
        job = _PIPELINE_JOBS.get(job_id)
        if job is not None:
            job["logs"].append(line)


class PipelineStartBody(ExtractionDirBody):
    """Unattended 01→04 draft+write, then optional validate (background job)."""

    targets: list[Literal["01", "02", "03", "04"]] | None = None
    chunk_paths: list[str] = Field(default_factory=list, max_length=48)
    chunk_tree_03: Literal["primary", "waterfall", "both"] = "both"
    max_bytes_per_chunk: int = Field(default=100_000, ge=4096, le=500_000)
    max_total_chunk_chars: int = Field(default=160_000, ge=8000, le=500_000)
    max_total_chunk_chars_04: int = Field(default=80_000, ge=4000, le=300_000)
    include_full_extraction_templates: bool = False
    full_templates_max_chars: int = Field(default=100_000, ge=5000, le=250_000)
    include_skill_md: bool = True
    skill_max_chars: int = Field(default=50_000, ge=2000, le=120_000)
    include_agent_md: bool = True
    agent_max_chars: int = Field(default=35_000, ge=2000, le=80_000)
    prior_caps_per_file: int = Field(default=42_000, ge=2000, le=80_000)
    extra_instructions: str = ""
    timeout_seconds_per_step: int = Field(default=300, ge=60, le=600)
    run_validate: bool = True


def _pipeline_worker(job_id: str, body: PipelineStartBody) -> None:
    with _PIPELINE_LOCK:
        job = _PIPELINE_JOBS.get(job_id)
        if job is None:
            return
        job["status"] = "running"
        job["started_at"] = _local_now_iso()

    result: dict[str, Any] = {"steps": [], "validation": None}
    try:
        cfg = _draft.draft_config_public()
        if not cfg.get("configured"):
            raise RuntimeError(f"LLM not configured. {_DRAFT_KEY_HINT}")
        out = _allowed_output_dir(body.output_dir)
        if not (out / "_chunks").is_dir():
            raise RuntimeError("Missing _chunks/ — segment the PDF into this folder first.")

        order = ("01", "02", "03", "04")
        want = set(body.targets) if body.targets else set(order)
        targets = [t for t in order if t in want]
        if not targets:
            raise RuntimeError("No valid targets")

        base_settings = {
            "chunk_paths": list(body.chunk_paths),
            "max_bytes_per_chunk": body.max_bytes_per_chunk,
            "max_total_chunk_chars": body.max_total_chunk_chars,
            "include_current_draft": False,
            "current_draft": "",
            "extra_instructions": body.extra_instructions,
            "timeout_seconds": body.timeout_seconds_per_step,
            "include_full_extraction_templates": body.include_full_extraction_templates,
            "full_templates_max_chars": body.full_templates_max_chars,
            "include_skill_md": body.include_skill_md,
            "skill_max_chars": body.skill_max_chars,
            "include_agent_md": body.include_agent_md,
            "agent_max_chars": body.agent_max_chars,
        }

        for target in targets:
            chunk_tree: Literal["primary", "waterfall", "both"] = (
                body.chunk_tree_03 if target == "03" else "primary"
            )
            max_total = (
                body.max_total_chunk_chars_04 if target == "04" else body.max_total_chunk_chars
            )
            step_s = {
                **base_settings,
                "chunk_tree": chunk_tree,
                "max_total_chunk_chars": max_total,
            }
            prior = ""
            if target == "04":
                prior = _read_prior_deliverables_for_04(out, body.prior_caps_per_file)
                if not prior.strip():
                    _pipeline_log(
                        job_id,
                        "WARN: 04 has no prior 01–03 files on disk yet; model will draft from chunks only.",
                    )

            _pipeline_log(job_id, f"LLM draft {target} (chunk_tree={chunk_tree}, max_chars={max_total})…")
            core = _draft_deliverable_core(out, target, step_s, prior_deliverables=prior)
            fn = str(core["filename"])
            path = out / fn
            path.write_text(str(core["markdown"]), encoding="utf-8", newline="\n")
            _pipeline_log(job_id, f"Wrote {fn} ({len(core['markdown'])} chars).")
            result["steps"].append(
                {
                    "target": target,
                    "filename": fn,
                    "chunks_used": core["chunks_used"],
                    "gather_note": core.get("gather_note"),
                }
            )

        if body.run_validate:
            _pipeline_log(job_id, "Running validate_noteval.py…")
            result["validation"] = _run_validate_noteval(out)
            v = result["validation"]
            rc = v.get("returncode") if isinstance(v, dict) else None
            rp = v.get("report_path") if isinstance(v, dict) else ""
            _pipeline_log(job_id, f"validate_noteval exit {rc}; report at {rp}")

        result["draft_usage"] = _draft.draft_usage_log_read_tail(
            max_lines=max(48, len(targets) * 8)
        )
        du_sum = (result["draft_usage"].get("summary") or {}) if isinstance(
            result["draft_usage"], dict
        ) else {}
        _pipeline_log(
            job_id,
            "API usage (log tail): "
            f"requests={du_sum.get('requests', 0)} "
            f"total_tokens≈{du_sum.get('total_tokens')} "
            f"cost_usd_sum={du_sum.get('cost_usd_sum')} "
            f"— file {result['draft_usage'].get('path')}",
        )

        with _PIPELINE_LOCK:
            job = _PIPELINE_JOBS.get(job_id)
            if job is not None:
                job["status"] = "done"
                job["result"] = result
                job["finished_at"] = _local_now_iso()
        _pipeline_log(job_id, "Pipeline finished OK.")
    except Exception as e:
        _pipeline_log(job_id, f"ERROR: {e!s}")
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


@app.get("/api/extraction/draft-config")
def extraction_draft_config():
    """Whether LLM draft is configured (no secrets returned)."""
    cfg = _draft.draft_config_public()
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
    Call an OpenAI-compatible chat completion to draft one deliverable from
    template excerpt + chunk text.
    """
    cfg = _draft.draft_config_public()
    if not cfg.get("configured"):
        raise HTTPException(status_code=503, detail=f"LLM not configured. {_DRAFT_KEY_HINT}")
    out = _allowed_output_dir(body.output_dir)
    s = body.model_dump(exclude={"output_dir", "target"})
    try:
        core = _draft_deliverable_core(
            out,
            body.target,
            s,
            prior_deliverables="",
        )
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"ok": True, "target": body.target, **core}


@app.post("/api/extraction/pipeline/start")
def extraction_pipeline_start(body: PipelineStartBody):
    """
    Start unattended multi-step pipeline (draft+write 01→04, then validate) in a background thread.
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
        timeout=120,
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
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
