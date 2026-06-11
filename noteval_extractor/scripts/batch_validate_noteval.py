#!/usr/bin/env python3
"""
Run validate_noteval on many extraction folders under an output root.

Discovers subdirectories that contain ``01_report_metadata.md`` (same layout as
``batch_segment.py`` / ``pdf_workflow`` outputs), sorts by name, validates each,
writes ``validation_report.md`` per deal, and a roll-up summary under the output root:
``batch_validation_summary.md`` (``--source all`` or ``llm``) or
``batch_validation_summary_sdk.md`` (``--source sdk``).

With ``--inventory-segmented`` (default **on**), also lists every child folder whose
name matches ``<digits>_<YYYYMMDD>`` and that has ``_chunks/pages_*.txt`` — even when
``01_report_metadata.md`` is missing — under **Segmentation-only (not validated)**.

  py -3 noteval_extractor/scripts/batch_validate_noteval.py
  py -3 noteval_extractor/scripts/batch_validate_noteval.py --max-deals 0 --strict
  py -3 noteval_extractor/scripts/batch_validate_noteval.py --no-inventory-segmented

``--max-deals 0`` means no cap on validated extraction folders (after sort).

Exit code: 1 if any deal has validation errors (or warnings when ``--strict``).
If there are **no** extraction folders to validate but inventory rows exist, exit **0**.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import validate_noteval as vn


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _ensure_import_paths() -> None:
    root = _repo_root()
    for p in (root / "noteval_extractor" / "scripts", root / "LLM", root):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)


_ensure_import_paths()

import noteval_batch_cost as _batch_cost  # noqa: E402
import noteval_llm as _llm_usage  # noqa: E402
import noteval_sdk_usage as _sdk_usage  # noqa: E402

_DEAL_FOLDER = re.compile(r"^\d+_\d{8}$")
_DEAL_FOLDER_SDK = re.compile(r"^\d+_\d{8}_sdk$")


def default_output_root() -> Path:
    return _repo_root() / "noteval_extractor" / "output"


def _pipeline_label(
    folder_name: str,
    *,
    sdk_costs: dict[str, float] | None = None,
    llm_costs: dict[str, float] | None = None,
    batch_source: str | None = None,
) -> str:
    """SDK agent output lives in ``{dealId}_{date}`` folders (not only ``*_sdk``)."""
    fn = folder_name.strip()
    if _DEAL_FOLDER_SDK.match(fn):
        return "SDK"
    sdk_costs = sdk_costs or {}
    llm_costs = llm_costs or {}
    in_sdk = fn in sdk_costs
    in_llm = fn in llm_costs
    if in_sdk and not in_llm:
        return "SDK"
    if in_llm and not in_sdk:
        return "LLM"
    if in_sdk and in_llm:
        if batch_source == "llm":
            return "LLM"
        return "SDK"
    if batch_source == "sdk":
        return "SDK"
    if batch_source == "llm":
        return "LLM"
    return "LLM"


def _folder_matches_source(name: str, source: str) -> bool:
    src = (source or "all").strip().lower()
    if src == "sdk":
        return bool(_DEAL_FOLDER.match(name) or _DEAL_FOLDER_SDK.match(name))
    if src == "llm":
        return bool(_DEAL_FOLDER.match(name))
    return bool(_DEAL_FOLDER.match(name) or _DEAL_FOLDER_SDK.match(name))


def discover_deal_dirs(output_root: Path, source: str = "all") -> list[Path]:
    """Child dirs with ``01_report_metadata.md``, filtered by pipeline (LLM / SDK / all)."""
    marker = "01_report_metadata.md"
    if not output_root.is_dir():
        return []
    out: list[Path] = []
    for p in output_root.iterdir():
        if not p.is_dir() or not (p / marker).is_file():
            continue
        if not _folder_matches_source(p.name, source):
            continue
        out.append(p)
    return sorted(out, key=lambda x: x.name.lower())


def _has_segmented_chunks(d: Path) -> bool:
    ch = d / "_chunks"
    if not ch.is_dir():
        return False
    return any(ch.glob("pages_*.txt"))


def discover_segmented_deal_dirs(output_root: Path, source: str = "all") -> list[Path]:
    """Child dirs with ``_chunks/pages_*.txt`` matching LLM / SDK / all folder naming."""
    if not output_root.is_dir():
        return []
    out: list[Path] = []
    for p in output_root.iterdir():
        if not p.is_dir():
            continue
        if not _folder_matches_source(p.name, source):
            continue
        if _has_segmented_chunks(p):
            out.append(p)
    return sorted(out, key=lambda x: x.name.lower())


def _read_total_pages(page_index: Path) -> str:
    if not page_index.is_file():
        return "—"
    try:
        text = page_index.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "—"
    for line in text.splitlines():
        if line.strip().lower().startswith("total pages:"):
            return line.split(":", 1)[-1].strip()
    return "—"


def _segmentation_inventory_row(d: Path) -> tuple[str, str, str, str]:
    """Folder name, pages, dual WF flag, 01 present."""
    pages = _read_total_pages(d / "_page_index.md")
    wf = "yes" if (d / "_chunks_waterfall").is_dir() and any((d / "_chunks_waterfall").glob("pages_*.txt")) else "no"
    has01 = "yes" if (d / "01_report_metadata.md").is_file() else "no"
    return (d.name, pages, wf, has01)


def _counts(checks: list[vn.Check]) -> tuple[int, int]:
    errors = sum(1 for c in checks if not c.ok and c.severity == "error")
    warns = sum(1 for c in checks if not c.ok and c.severity == "warn")
    return errors, warns


def _deal_failed(checks: list[vn.Check], strict: bool) -> bool:
    errors, warns = _counts(checks)
    if errors:
        return True
    if strict and warns:
        return True
    return False


def _load_extraction_cost_maps_all_log() -> tuple[dict[str, float], dict[str, float], str | None, str | None]:
    """SDK and LLM estimated USD per folder basename from JSONL usage logs (cumulative)."""
    sdk_costs = _sdk_usage.sdk_usage_cost_by_deal_folder()
    llm_costs = _llm_usage.draft_usage_cost_by_deal_folder()
    sdk_path = _sdk_usage.sdk_usage_log_path()
    llm_path = _llm_usage.draft_usage_log_path()
    return sdk_costs, llm_costs, str(sdk_path) if sdk_path else None, str(llm_path) if llm_path else None


def _fill_costs_from_latest_usage_log(
    sdk_costs: dict[str, float],
    llm_costs: dict[str, float],
    *,
    source: str,
    folder_names: list[str] | None,
) -> bool:
    """Add per-folder costs from the latest log line / pipeline run when manifest has no entry."""
    src = (source or "all").strip().lower()
    filled = False
    want = {str(n).strip() for n in (folder_names or []) if str(n).strip()} or None

    if src in ("all", "sdk"):
        sdk_log = _sdk_usage.sdk_usage_cost_latest_by_deal_folder()
        keys = want if want else sdk_log.keys()
        for fn in keys:
            if fn in sdk_costs:
                continue
            val = sdk_log.get(fn)
            if val is not None:
                sdk_costs[fn] = float(val)
                filled = True

    if src in ("all", "llm"):
        llm_log = _llm_usage.draft_usage_cost_latest_run_by_deal_folder()
        keys = want if want else llm_log.keys()
        for fn in keys:
            if fn in llm_costs:
                continue
            val = llm_log.get(fn)
            if val is not None:
                llm_costs[fn] = float(val)
                filled = True
    return filled


def _load_batch_manifest(
    *,
    manifest_path: Path | None = None,
    batch_id: str | None = None,
) -> dict | None:
    if manifest_path is not None:
        return _batch_cost.read_manifest(manifest_path.resolve())
    if batch_id and batch_id.strip():
        return _batch_cost.read_manifest(_batch_cost.batch_cost_dir() / f"{batch_id.strip()}.json")
    return None


def _manifest_batch_source(manifest: dict | None) -> str | None:
    if not manifest:
        return None
    src = str(manifest.get("source") or "").strip().lower()
    if src in ("llm", "sdk", "all"):
        return src
    return None


def _load_extraction_cost_maps_from_manifest(
    source: str,
    *,
    manifest_path: Path | None = None,
    batch_id: str | None = None,
    folder_names: list[str] | None = None,
) -> tuple[dict[str, float], dict[str, float], str | None, str | None]:
    """
    Costs for the latest (or specified) batch extraction manifest, not cumulative JSONL.
    Returns (sdk_costs, llm_costs, cost_scope_note, batch_source).
    """
    src = (source or "all").strip().lower()
    manifest: dict | None = _load_batch_manifest(
        manifest_path=manifest_path,
        batch_id=batch_id,
    )
    scope_note = ""

    if manifest_path is not None:
        scope_note = f"batch manifest `{manifest_path}`"
    elif batch_id and batch_id.strip():
        scope_note = f"batch `{batch_id.strip()}`"

    batch_source = _manifest_batch_source(manifest)

    if manifest_path is not None or (batch_id and batch_id.strip()):
        if not manifest:
            sdk_costs: dict[str, float] = {}
            llm_costs: dict[str, float] = {}
            if src in ("all", "sdk"):
                sdk_costs = _sdk_usage.sdk_usage_cost_latest_by_deal_folder()
            if src in ("all", "llm"):
                llm_costs = _llm_usage.draft_usage_cost_latest_run_by_deal_folder()
            if folder_names:
                want = {str(n).strip() for n in folder_names if str(n).strip()}
                sdk_costs = {k: v for k, v in sdk_costs.items() if k in want}
                llm_costs = {k: v for k, v in llm_costs.items() if k in want}
            note = scope_note or "batch manifest missing or unreadable"
            if sdk_costs or llm_costs:
                note += "; using latest usage log per folder"
            return sdk_costs, llm_costs, note, batch_source

        costs = _batch_cost.costs_from_manifest(manifest, folder_names=folder_names)
        m_src = str(manifest.get("source") or "").lower()
        if m_src == "sdk":
            sdk_costs, llm_costs = costs, {}
        elif m_src == "llm":
            sdk_costs, llm_costs = {}, costs
        else:
            sdk_costs = {k: v for k, v in costs.items() if k.endswith("_sdk")}
            llm_costs = {k: v for k, v in costs.items() if not k.endswith("_sdk")}
        if _fill_costs_from_latest_usage_log(
            sdk_costs, llm_costs, source=src, folder_names=folder_names
        ):
            scope_note += "; missing folders filled from latest usage log line per deal"
        return sdk_costs, llm_costs, scope_note, batch_source

    parts: list[str] = []
    sdk_costs = {}
    llm_costs = {}
    if src in ("all", "llm"):
        m_llm = _batch_cost.load_latest_manifest("llm")
        if m_llm:
            llm_costs = _batch_cost.costs_from_manifest(m_llm, folder_names=folder_names)
            parts.append(f"LLM `{_batch_cost.latest_manifest_path('llm')}`")
    if src in ("all", "sdk"):
        m_sdk = _batch_cost.load_latest_manifest("sdk")
        if m_sdk:
            sdk_costs = _batch_cost.costs_from_manifest(m_sdk, folder_names=folder_names)
            parts.append(f"SDK `{_batch_cost.latest_manifest_path('sdk')}`")
            if batch_source is None:
                batch_source = _manifest_batch_source(m_sdk)
    if parts:
        scope_note = "latest batch extraction: " + ", ".join(parts)
    else:
        sdk_costs = {}
        llm_costs = {}
        if src in ("all", "sdk"):
            sdk_costs = _sdk_usage.sdk_usage_cost_latest_by_deal_folder()
            if folder_names:
                want = {str(n).strip() for n in folder_names if str(n).strip()}
                sdk_costs = {k: v for k, v in sdk_costs.items() if k in want}
        if src in ("all", "llm"):
            llm_costs = _llm_usage.draft_usage_cost_latest_run_by_deal_folder()
            if folder_names:
                want = {str(n).strip() for n in folder_names if str(n).strip()}
                llm_costs = {k: v for k, v in llm_costs.items() if k in want}
        if sdk_costs or llm_costs:
            scope_note = "latest extraction run per folder from usage JSONL (no batch manifest)"
        else:
            scope_note = "no batch cost manifest and no usage log lines for these folders"
        return sdk_costs, llm_costs, scope_note, batch_source
    if _fill_costs_from_latest_usage_log(
        sdk_costs, llm_costs, source=src, folder_names=folder_names
    ):
        scope_note += "; missing folders filled from latest usage log line per deal"
    return sdk_costs, llm_costs, scope_note, batch_source


def _cost_for_folder(
    folder_name: str,
    pipeline: str,
    sdk_costs: dict[str, float],
    llm_costs: dict[str, float],
) -> float | None:
    costs = sdk_costs if pipeline == "SDK" else llm_costs
    val = costs.get(folder_name)
    if val is None:
        return None
    return float(val)


def _format_cost_usd(cost: float | None) -> str:
    if cost is None:
        return "—"
    return f"${cost:.4f}"


def batch_summary_filename(source: str) -> str:
    """Roll-up markdown basename for ``--source`` (SDK uses a separate file)."""
    if (source or "all").strip().lower() == "sdk":
        return "batch_validation_summary_sdk.md"
    return "batch_validation_summary.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch-run validate_noteval on deal folders.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Parent of per-deal folders (default: noteval_extractor/output).",
    )
    parser.add_argument(
        "--max-deals",
        type=int,
        default=10,
        help="Max extraction folders to validate after sort; **0** = no limit. Default: 10.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings like errors for exit code (same as validate_noteval.py --strict).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List deal folders that would be validated; do not write reports.",
    )
    parser.add_argument(
        "--no-inventory-segmented",
        action="store_true",
        help="Omit **Segmentation-only** section from the batch summary markdown.",
    )
    parser.add_argument(
        "--source",
        choices=("all", "llm", "sdk"),
        default="all",
        help="Validate LLM folders, SDK folders (`<id>_<date>` or legacy `*_sdk`), or all.",
    )
    parser.add_argument(
        "--folders",
        nargs="*",
        default=(),
        metavar="NAME",
        help="If set, only validate these folder basenames under output-root.",
    )
    parser.add_argument(
        "--all-log-costs",
        action="store_true",
        help="Sum all cost_usd lines per folder from usage JSONL logs (cumulative; legacy).",
    )
    parser.add_argument(
        "--batch-cost-manifest",
        type=Path,
        default=None,
        help="JSON manifest from a batch extraction run (see logs/batch_cost/).",
    )
    parser.add_argument(
        "--extraction-batch-id",
        default="",
        help="Batch UUID; load logs/batch_cost/<id>.json for per-deal costs.",
    )
    args = parser.parse_args()

    out_root = args.output_root
    if out_root is None:
        out_root = default_output_root()
    out_root = out_root.resolve()

    source = str(args.source or "all").lower()
    dirs = discover_deal_dirs(out_root, source=source)
    if args.folders:
        want = {f.strip() for f in args.folders if f.strip()}
        dirs = [d for d in dirs if d.name in want]
    if args.max_deals and args.max_deals > 0:
        dirs = dirs[: args.max_deals]

    segmented = (
        discover_segmented_deal_dirs(out_root, source=source)
        if not args.no_inventory_segmented
        else []
    )
    if args.folders:
        want = {f.strip() for f in args.folders if f.strip()}
        segmented = [d for d in segmented if d.name in want]

    if not dirs and not segmented:
        print(f"No folders found under {out_root} (no */01_report_metadata.md and no segmented deal dirs).", file=sys.stderr)
        return 1

    print(f"output_root={out_root}", file=sys.stderr, flush=True)
    print(f"Pipeline filter: {source}", file=sys.stderr, flush=True)
    print(f"Extraction folders to validate: {len(dirs)}.", file=sys.stderr, flush=True)
    if segmented:
        print(f"Segmented deal-shaped folders (inventory): {len(segmented)}.", file=sys.stderr, flush=True)

    if args.dry_run:
        for d in dirs:
            print(f"validate: {d}", flush=True)
        for d in segmented:
            if d not in dirs:
                print(f"inventory only: {d}", flush=True)
        return 0

    folder_filter = [f.strip() for f in args.folders if f and f.strip()]
    cost_scope_note: str | None = None
    sdk_log_path: str | None = None
    llm_log_path: str | None = None
    if args.all_log_costs:
        sdk_costs, llm_costs, sdk_log_path, llm_log_path = _load_extraction_cost_maps_all_log()
        cost_scope_note = "cumulative usage JSONL (all logged runs per folder)"
    else:
        sdk_costs, llm_costs, cost_scope_note, batch_source = _load_extraction_cost_maps_from_manifest(
            source,
            manifest_path=args.batch_cost_manifest,
            batch_id=args.extraction_batch_id or None,
            folder_names=folder_filter or None,
        )
    if batch_source is None and source in ("llm", "sdk"):
        batch_source = source

    summary_rows: list[tuple[str, str, int, int, str, float | None]] = []
    any_fail = False

    for d in dirs:
        checks = vn.validate_dir(d)
        vn.write_report(d, checks)
        errors, warns = _counts(checks)
        failed = _deal_failed(checks, args.strict)
        if failed:
            any_fail = True
        status = "FAIL" if failed else ("WARN" if warns else "OK")
        pipe = _pipeline_label(
            d.name,
            sdk_costs=sdk_costs,
            llm_costs=llm_costs,
            batch_source=batch_source,
        )
        deal_cost = _cost_for_folder(d.name, pipe, sdk_costs, llm_costs)
        summary_rows.append((d.name, pipe, errors, warns, status, deal_cost))
        rp = d / "validation_report.md"
        cost_note = f" cost≈{_format_cost_usd(deal_cost)}" if deal_cost is not None else ""
        print(f"{d.name}: errors={errors} warnings={warns}{cost_note} -> {rp}", flush=True)
        if errors:
            for c in checks:
                if not c.ok and c.severity == "error":
                    print(f"  FAIL: [{c.category}] {c.name}: {c.detail}", file=sys.stderr)
        if warns:
            stream = sys.stderr if (args.strict or errors) else sys.stdout
            for c in checks:
                if not c.ok and c.severity == "warn":
                    print(f"  WARN: [{c.category}] {c.name}: {c.detail}", file=stream)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    source_label = {
        "all": "ALL (LLM + SDK)",
        "llm": "LLM only (`<dealId>_<YYYYMMDD>`)",
        "sdk": "SDK (`<dealId>_<YYYYMMDD>` deal folders or legacy `*_sdk`)",
    }.get(source, source.upper())

    lines = [
        "# Batch noteval validation summary",
        "",
        f"- **Output root:** `{out_root}`",
        f"- **Pipeline filter:** {source_label}",
        f"- **Extraction folders validated:** {len(summary_rows)}",
        f"- **Segmented deal folders (inventory):** {len(segmented)}",
        f"- **Strict:** {'yes' if args.strict else 'no'}",
        f"- **Generated:** {ts}",
        "",
    ]
    if cost_scope_note:
        lines.append(f"- **Cost scope:** {cost_scope_note}")
        lines.append("")
    if args.folders:
        lines.append(f"- **Folder allow-list:** {', '.join(f'`{n}`' for n in sorted(args.folders))}")
        lines.append("")

    section_title = "## Validated extractions (`01` … present)"
    if source == "sdk":
        section_title = "## Validated extractions — SDK"
    elif source == "llm":
        section_title = "## Validated extractions — LLM"
    lines.append(section_title)
    lines.append("")
    if summary_rows:
        lines.extend(
            [
                "| Folder | Pipeline | Errors | Warnings | Status | Cost (est.) |",
                "|--------|----------|--------|----------|--------|-------------|",
            ]
        )
        total_cost = 0.0
        n_cost = 0
        for name, pipe, err, war, st, deal_cost in summary_rows:
            lines.append(
                f"| {name} | {pipe} | {err} | {war} | {st} | {_format_cost_usd(deal_cost)} |"
            )
            if deal_cost is not None:
                total_cost += deal_cost
                n_cost += 1
        total_err = sum(r[2] for r in summary_rows)
        total_war = sum(r[3] for r in summary_rows)
        lines.extend(
            [
                "",
                f"**Subtotal errors:** {total_err}  **Subtotal warnings:** {total_war}",
            ]
        )
        if n_cost:
            if args.all_log_costs:
                cost_tail = (
                    f"({n_cost} folder(s) with usage in log; approximate — see pricing_note in usage JSONL)"
                )
            else:
                cost_tail = (
                    f"({n_cost} folder(s) from latest batch extraction; approximate — not cumulative log total)"
                )
            lines.append(f"**Total batch cost (estimated):** ${total_cost:.4f} USD {cost_tail}")
            if args.all_log_costs and (sdk_log_path or llm_log_path):
                log_bits = []
                if sdk_log_path:
                    log_bits.append(f"SDK `{sdk_log_path}`")
                if llm_log_path:
                    log_bits.append(f"LLM `{llm_log_path}`")
                lines.append(f"- **Usage logs:** {', '.join(log_bits)}")
        else:
            if args.all_log_costs:
                no_cost_msg = (
                    "no matching usage lines; run extraction with usage logging enabled, then re-validate"
                )
            else:
                no_cost_msg = (
                    "no costs in latest batch manifest for these folders; run batch LLM/SDK extraction, "
                    "then re-validate (or pass --all-log-costs for cumulative JSONL totals)"
                )
            lines.append(f"**Total batch cost (estimated):** — ({no_cost_msg})")
    else:
        lines.append("*No child folders under this root currently contain `01_report_metadata.md` (nothing validated).*")
        lines.append("")
        lines.append("Run the noteval extractor (or copy template outputs) into each `dealid_YYYYMMDD` folder, then re-run this script.")

    if segmented and not args.no_inventory_segmented:
        lines.extend(
            [
                "",
                "## Segmentation-only (not validated)",
                "",
                "Folders match `dealid_YYYYMMDD` and contain `_chunks/pages_*.txt`. They are listed for inventory; **validate_noteval** was **not** run unless `01_report_metadata.md` exists.",
                "",
                "| Folder | Pipeline | Total pages (`_page_index.md`) | `_chunks_waterfall` | Has `01` |",
                "|--------|----------|----------------------------------|---------------------|----------|",
            ]
        )
        for d in segmented:
            name, pages, wf, has01 = _segmentation_inventory_row(d)
            lines.append(
                f"| {name} | {_pipeline_label(name, sdk_costs=sdk_costs, llm_costs=llm_costs, batch_source=batch_source)} | {pages} | {wf} | {has01} |"
            )

    lines.append("")
    if summary_rows:
        if any_fail:
            lines.append("**Batch STATUS: FAIL** (see per-deal `validation_report.md`).")
        else:
            lines.append("**Batch STATUS: PASS** (no failing deals under current strictness).")
    else:
        lines.append("**Batch STATUS: N/A** — no extraction markdown to validate; see inventory table above.")

    summary_name = batch_summary_filename(source)
    summary_path = out_root / summary_name
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {summary_path}", flush=True)
    if summary_rows:
        batch_cost = sum(c for *_, c in summary_rows if c is not None)
        n_with_cost = sum(1 for *_, c in summary_rows if c is not None)
        if n_with_cost:
            scope = "latest batch extraction" if not args.all_log_costs else "usage log (cumulative)"
            print(
                f"Total batch cost (estimated): ${batch_cost:.4f} USD "
                f"({n_with_cost}/{len(summary_rows)} folder(s); {scope})",
                file=sys.stderr,
                flush=True,
            )

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
