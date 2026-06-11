"""
Read tail of ``logs/noteval_sdk_usage.log`` (written by ``cursor_sdk_compare/run-extract.mjs``).

Env: ``NOTEVAL_SDK_USAGE_LOG`` (same semantics as the Node helper; ``0``/``off`` disables).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent


def sdk_usage_log_path() -> Path | None:
    raw = os.environ.get("NOTEVAL_SDK_USAGE_LOG", "").strip().lower()
    if raw in ("0", "off", "false", "no"):
        return None
    if raw:
        return Path(raw).expanduser().resolve()
    return (_REPO_ROOT / "logs" / "noteval_sdk_usage.log").resolve()


def _summarize_sdk_entries(entries: list[dict]) -> dict:
    n = 0
    inp = out = cr = cw = 0
    cost_sum = 0.0
    n_cost = 0
    for e in entries:
        if not isinstance(e, dict):
            continue
        if "input_tokens" not in e and "output_tokens" not in e:
            continue
        n += 1
        for key, bucket in (
            ("input_tokens", "inp"),
            ("output_tokens", "out"),
            ("cache_read_tokens", "cr"),
            ("cache_write_tokens", "cw"),
        ):
            v = e.get(key)
            if isinstance(v, int):
                if bucket == "inp":
                    inp += v
                elif bucket == "out":
                    out += v
                elif bucket == "cr":
                    cr += v
                else:
                    cw += v
        cu = e.get("cost_usd")
        if cu is not None:
            try:
                cost_sum += float(cu)
                n_cost += 1
            except (TypeError, ValueError):
                pass
    total = inp + out + cr + cw
    return {
        "runs": n,
        "input_tokens": inp,
        "output_tokens": out,
        "cache_read_tokens": cr,
        "cache_write_tokens": cw,
        "total_tokens": total if total else None,
        "cost_usd_sum": round(cost_sum, 6) if n_cost else None,
        "lines_with_cost": n_cost,
    }


def jsonl_cost_sum_by_deal_folder(
    path: Path | None,
    *,
    folder_key: str = "deal_folder",
    max_bytes: int = 2_000_000,
) -> dict[str, float]:
    """
    Sum ``cost_usd`` per folder basename from a JSONL usage log (full file, tail-bounded read).
    """
    if path is None or not path.is_file():
        return {}
    try:
        data = path.read_bytes()
    except OSError:
        return {}
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    text = data.decode("utf-8", errors="replace")
    out: dict[str, float] = {}
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        folder = obj.get(folder_key)
        if not folder:
            continue
        cu = obj.get("cost_usd")
        if cu is None:
            continue
        try:
            cost = float(cu)
        except (TypeError, ValueError):
            continue
        key = str(folder).strip()
        if not key:
            continue
        out[key] = round(out.get(key, 0.0) + cost, 6)
    return out


def sdk_usage_cost_by_deal_folder(*, max_bytes: int = 2_000_000) -> dict[str, float]:
    """Estimated USD per deal folder from ``logs/noteval_sdk_usage.log``."""
    return jsonl_cost_sum_by_deal_folder(sdk_usage_log_path(), max_bytes=max_bytes)


def sdk_usage_log_read_tail(
    *,
    max_lines: int = 50,
    max_bytes: int = 512_000,
) -> dict:
    path = sdk_usage_log_path()
    if path is None:
        return {
            "enabled": False,
            "path": None,
            "raw_tail_lines": [],
            "parsed": [],
            "summary": None,
            "note": "usage logging disabled (NOTEVAL_SDK_USAGE_LOG=off)",
        }
    if not path.is_file():
        return {
            "enabled": True,
            "path": str(path),
            "raw_tail_lines": [],
            "parsed": [],
            "summary": None,
            "note": "log file not created yet (no SDK runs logged)",
        }
    try:
        data = path.read_bytes()
    except OSError as e:
        return {
            "enabled": True,
            "path": str(path),
            "raw_tail_lines": [],
            "parsed": [],
            "summary": None,
            "note": f"read error: {e}",
        }
    if len(data) > max_bytes:
        data = data[-max_bytes:]
    text = data.decode("utf-8", errors="replace")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    parsed: list[dict] = []
    for ln in tail:
        try:
            obj = json.loads(ln)
            parsed.append(obj if isinstance(obj, dict) else {"_non_object": str(obj)[:200]})
        except json.JSONDecodeError:
            parsed.append({"_unparsed_line": ln[:800]})
    usage_like = [
        x
        for x in parsed
        if isinstance(x, dict)
        and "_unparsed_line" not in x
        and "_non_object" not in x
        and ("input_tokens" in x or "output_tokens" in x)
    ]
    return {
        "enabled": True,
        "path": str(path),
        "raw_tail_lines": tail,
        "parsed": parsed,
        "summary": _summarize_sdk_entries(usage_like),
        "note": f"aggregated over last {len(tail)} non-empty line(s); approximate USD (see pricing_note per line)",
    }
