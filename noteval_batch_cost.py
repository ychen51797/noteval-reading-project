"""
Per-batch extraction cost manifests (UI batch LLM / SDK runs).

Written after each batch extraction; read by ``batch_validate_noteval.py`` so validation
summaries show cost for the **latest batch job**, not cumulative JSONL totals.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent
_BATCH_COST_DIR = _REPO_ROOT / "logs" / "batch_cost"


def batch_cost_dir() -> Path:
    return _BATCH_COST_DIR


def latest_manifest_path(source: str) -> Path:
    src = (source or "llm").strip().lower()
    if src not in ("llm", "sdk", "all"):
        src = "llm"
    return _BATCH_COST_DIR / f"latest_{src}.json"


def write_batch_cost_manifest(
    *,
    source: str,
    batch_id: str,
    costs: dict[str, float],
    folder_names: list[str] | None = None,
) -> Path:
    """Persist latest + archived manifest for a completed extraction batch."""
    src = (source or "llm").strip().lower()
    if src not in ("llm", "sdk", "all"):
        raise ValueError(f"unsupported source: {source!r}")
    bid = batch_id.strip()
    if not bid:
        raise ValueError("batch_id is required")
    cleaned: dict[str, float] = {}
    for k, v in costs.items():
        key = str(k).strip()
        if not key:
            continue
        try:
            cleaned[key] = round(float(v), 6)
        except (TypeError, ValueError):
            continue
    record: dict[str, Any] = {
        "batch_id": bid,
        "source": src,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "costs": cleaned,
        "folder_names": sorted({str(n).strip() for n in (folder_names or []) if str(n).strip()}),
    }
    _BATCH_COST_DIR.mkdir(parents=True, exist_ok=True)
    latest = latest_manifest_path(src)
    text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    latest.write_text(text, encoding="utf-8")
    archive = _BATCH_COST_DIR / f"{bid}.json"
    archive.write_text(text, encoding="utf-8")
    return latest


def read_manifest(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.is_file():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def load_latest_manifest(source: str) -> dict[str, Any] | None:
    return read_manifest(latest_manifest_path(source))


def costs_from_manifest(
    manifest: dict[str, Any] | None,
    *,
    folder_names: list[str] | None = None,
) -> dict[str, float]:
    if not manifest:
        return {}
    raw = manifest.get("costs")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in raw.items():
        key = str(k).strip()
        if not key:
            continue
        try:
            out[key] = float(v)
        except (TypeError, ValueError):
            continue
    if folder_names:
        want = {str(n).strip() for n in folder_names if str(n).strip()}
        return {k: out[k] for k in want if k in out}
    return out
