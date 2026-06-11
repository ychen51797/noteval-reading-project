"""
Tool definitions and execution for noteval LLM draft (OpenAI function calling).

Enabled by default. Disable with ``NOTEVAL_DRAFT_USE_TOOLS=0`` / ``off`` or ``use_tools: false`` on draft / pipeline requests.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import noteval_chunk_select as _chunk_select

ChunkTree = Literal["primary", "waterfall", "both"]
TargetId = Literal["01", "02", "03", "04"]

_MAX_PAGE_INDEX_CHARS = 48_000
_MAX_MANIFEST_CHARS = 16_000
_MAX_CHUNK_TOOL_CHARS = 140_000
_MAX_TEMPLATE_CHARS = 80_000
_MAX_PRIOR_CHARS = 120_000


def draft_use_tools_enabled() -> bool:
    raw = os.environ.get("NOTEVAL_DRAFT_USE_TOOLS", "1").strip().lower()
    if raw in ("0", "false", "off", "no"):
        return False
    return raw in ("", "1", "true", "yes", "on")


def draft_max_tool_turns() -> int:
    try:
        n = int((os.environ.get("NOTEVAL_DRAFT_MAX_TOOL_TURNS") or "14").strip())
    except ValueError:
        n = 14
    return max(3, min(n, 30))


def tool_definitions_for_target(target: TargetId) -> list[dict[str, Any]]:
    """OpenAI Chat Completions ``tools`` list."""
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "read_page_index",
                "description": (
                    "Read the page index (one-line preview per PDF page). "
                    "Call first to plan which pages to open. "
                    "Use tree=waterfall for Wells Fargo waterfall PDF index when present."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tree": {
                            "type": "string",
                            "enum": ["primary", "waterfall"],
                            "description": "primary = note valuation PDF; waterfall = waterfall PDF index",
                        },
                    },
                    "required": ["tree"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_manifest",
                "description": "Read chunk manifest (which pages_*.txt file covers which page range).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tree": {
                            "type": "string",
                            "enum": ["primary", "waterfall"],
                        },
                    },
                    "required": ["tree"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_chunk_pages",
                "description": (
                    "Read PDF text for specific 1-based page numbers from segmented chunks. "
                    "Includes --- Page N --- markers. For deliverable 03, the first call must "
                    "include every page in the mandatory waterfall span from the user message."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "pages": {
                            "type": "array",
                            "items": {"type": "integer", "minimum": 1},
                            "description": "PDF page numbers to include (e.g. [2, 3, 7, 8])",
                        },
                        "tree": {
                            "type": "string",
                            "enum": ["primary", "waterfall"],
                        },
                    },
                    "required": ["pages", "tree"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "read_template_excerpt",
                "description": (
                    "Read the canonical markdown template section for the current deliverable "
                    "(table headers, checklist, structure)."
                ),
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
    ]
    if target == "02":
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "read_structured_tables",
                    "description": (
                        "Read optional pdfplumber markdown for PDD/IDD or Payment Date Report "
                        "when present (column layout aid for 02 only)."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "kind": {
                                "type": "string",
                                "enum": ["pdd_idd", "payment_date_report", "both"],
                            },
                        },
                        "required": ["kind"],
                        "additionalProperties": False,
                    },
                },
            }
        )
    if target == "04":
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "read_prior_deliverables",
                    "description": (
                        "Read 01–03 markdown already written in this output folder (for 04 summary only)."
                    ),
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            }
        )
    return tools


def _read_capped(path: Path, cap: int) -> str:
    if not path.is_file():
        return f"[File not found: {path.name}]"
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= cap:
        return text
    return text[:cap] + f"\n\n[TRUNCATED at {cap} characters]\n"


def _chunk_pages_text(
    out: Path,
    pages: list[int],
    *,
    tree: ChunkTree,
    max_chars: int,
) -> str:
    page_set = {int(p) for p in pages if int(p) >= 1}
    if not page_set:
        return "[No pages requested]"
    prefix = "_chunks" if tree == "primary" else "_chunks_waterfall"
    chunk_dir = out / prefix
    if not chunk_dir.is_dir():
        return f"[Missing {prefix}/ under output dir]"

    spans = _chunk_select.parse_manifest_chunks(
        out / ("_manifest.md" if tree == "primary" else "_manifest_waterfall.md"),
        prefix=prefix,
    )
    if not spans:
        spans = _chunk_select.discover_chunks_from_dir(chunk_dir, prefix)

    rels = _chunk_select.chunks_covering_pages(spans, page_set)
    if not rels:
        return f"[No chunk files cover pages {sorted(page_set)}]"

    parts: list[str] = []
    total = 0
    for rel in rels:
        path = out / rel.replace("/", os.sep)
        if not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace")
        filtered = _chunk_select.filter_chunk_text_to_pages(raw, page_set)
        block = f"### {rel}\n\n{filtered}"
        if total + len(block) > max_chars:
            remain = max_chars - total
            if remain > 400:
                parts.append(block[:remain] + "\n\n[TRUNCATED — request fewer pages]\n")
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts) if parts else "[Empty chunk text]"


def execute_tool(
    name: str,
    arguments_json: str,
    *,
    out_dir: Path,
    target: TargetId,
    template_excerpt: str,
    prior_deliverables: str,
    read_prior_fn: Any,
) -> str:
    """Run one tool; return string content for the ``tool`` message."""
    try:
        args = json.loads(arguments_json) if arguments_json.strip() else {}
    except json.JSONDecodeError as e:
        return f"[Invalid tool arguments JSON: {e}]"
    if not isinstance(args, dict):
        args = {}

    if name == "read_page_index":
        tree = str(args.get("tree") or "primary").lower()
        fname = "_page_index.md" if tree == "primary" else "_page_index_waterfall.md"
        return _read_capped(out_dir / fname, _MAX_PAGE_INDEX_CHARS)

    if name == "read_manifest":
        tree = str(args.get("tree") or "primary").lower()
        fname = "_manifest.md" if tree == "primary" else "_manifest_waterfall.md"
        return _read_capped(out_dir / fname, _MAX_MANIFEST_CHARS)

    if name == "read_chunk_pages":
        pages_raw = args.get("pages") or []
        if not isinstance(pages_raw, list):
            return "[pages must be an array of integers]"
        tree = str(args.get("tree") or "primary").lower()
        if tree not in ("primary", "waterfall"):
            tree = "primary"
        return _chunk_pages_text(
            out_dir,
            [int(p) for p in pages_raw if isinstance(p, (int, float))],
            tree=tree,  # type: ignore[arg-type]
            max_chars=_MAX_CHUNK_TOOL_CHARS,
        )

    if name == "read_template_excerpt":
        text = template_excerpt.strip()
        if len(text) > _MAX_TEMPLATE_CHARS:
            return text[:_MAX_TEMPLATE_CHARS] + "\n\n[TRUNCATED]\n"
        return text or "[Empty template excerpt]"

    if name == "read_structured_tables" and target == "02":
        kind = str(args.get("kind") or "both").lower()
        parts: list[str] = []
        specs = []
        if kind in ("pdd_idd", "both"):
            specs.append(("pdd_idd_pdfplumber.md", "PDD/IDD"))
        if kind in ("payment_date_report", "both"):
            specs.append(("payment_date_report_pdfplumber.md", "Payment Date Report"))
        for fname, label in specs:
            p = out_dir / "_chunks_structured" / fname
            if p.is_file():
                parts.append(f"## {label}\n\n" + _read_capped(p, 60_000))
        return "\n\n".join(parts) if parts else "[No structured table files in _chunks_structured/]"

    if name == "read_prior_deliverables" and target == "04":
        if prior_deliverables.strip():
            text = prior_deliverables
        else:
            text = read_prior_fn()
        if len(text) > _MAX_PRIOR_CHARS:
            return text[:_MAX_PRIOR_CHARS] + "\n\n[TRUNCATED]\n"
        return text or "[No prior 01–03 files on disk yet]"

    return f"[Unknown tool: {name}]"


SYSTEM_PROMPT_TOOLS = """You are a structured extraction assistant for U.S. CLO / RMBS trustee and note valuation PDFs.

You have tools to read the segmented deal folder (page index, manifest, chunk text by page).
Workflow:
1. read_page_index (primary; waterfall index too for 03 when dual PDF).
2. read_chunk_pages — for **03**, include **all** pages in the mandatory waterfall span (one call); for other targets, open only needed pages.
3. read_template_excerpt for required layout.
4. For 02, optionally read_structured_tables when PDD/IDD or Payment Date Report files exist.
5. For 04, read_prior_deliverables — do not re-extract from PDF chunks.

Write the FULL deliverable markdown when you have enough evidence — starting with the `#` title from the template.
Use ## Extracted Data, ## Completeness Checklist, ## Source Text in order.
In Source Text, quote chunk excerpts with **Page N** labels.

Map by printed column headers only — never by column position, token order, or “nth $ after rate/CUSIP”.
**02 header-first (non-negotiable):** Reconstruct the table’s **column titles** from the chunk header block (titles may wrap across lines). Map each **$** to the column whose **printed name** matches (**Interest Paid**, **Deferred Interest Paid**, **Principal Paid**, etc.). **Forbidden as primary method:** nth-amount-after-**All In Rate**, after-coupon-%, after-CUSIP, “next non-zero €”, or “last $ on the line”. **All In Rate 0.00000% on Subordinated Notes is normal** — still use the **Interest Paid** (or **Interest Distribution**) column when it shows cash; **0% rate ≠ 0 interest paid**.
**02:** Interest paid → Interest payment; Principal paid → Principal payment; Ending balance is not principal paid.
**02 ending-zero paydown:** When **Principal payment** is blank/0, **Beginning balance** > 0, and **Ending balance** = 0.00
(from **Aggregate Outstanding … after Principal Payments** or equivalent — `-` → 0.00), **read waterfall pages** (Section 11.1
class principal **Amount paid**). Fill **Principal payment** only when that waterfall **$** **matches Beginning balance** —
**do not** set **Principal payment = Beginning balance** without the waterfall match.
**02 SUB interest:** When **Interest payment** is blank/0 on the class / Distribution Summary table but (**a**) IDD **Sub Totals / Interest Distribution** or **From Interest Proceeds** shows non-zero cash, **or** (**b**) **`03`** (or waterfall chunks) shows **non-zero Payment** to **Holders of the Subordinated Notes** on the **interest-proceeds** ladder (e.g. clause **(V)**), fill **Interest payment** from that exhibit — not from coupon alone. **Interest payable** may still come from **Current Payable** / **TOTAL PAYABLE** when printed. **Do not** use principal-waterfall sub lines for **Interest payment**.
**02 multi-listing:** **A-R-144A** and **A-R-REGS** = same tranche → one primary row **A-R** + listing rows for 144A/REGS;
same for **A-144A**/**A-REGS** → **A**, **SUB-144A**/**SUB-REGS** → **SUB**. Never two primary rows for program slices.
**02 Computershare PDD/IDD:** After **read_page_index**, **read_chunk_pages** for **every** **Interest Distribution Detail** and **Principal Distribution Detail** page (often pages 2–7 — use the index). **Section layout:** each tranche is a **block** — the **first row** prints **Note Class** (e.g. **D-R**, **D-RR**, **E**, **SUB**) with the **first CUSIP**; **continuation rows** are **more CUSIPs**; the class ends with a **Sub Totals / class footer** row under the **Interest Distribution** column (often a two-number line: interest cash + accrued/cumulative). **Primary `Interest payment`** = that **Sub Totals Interest Distribution $** for the class — **not** **0.00** from a **period-beginning-aligned** row (`36,600,000.00  0.00  0.00…`). **SUB / 0% coupon:** **Coupon 0.00000** or **Residual** on another page does **not** override non-zero **Interest Distribution** on IDD. Sum listing CUSIP **Interest Distribution** cells when no footer prints. **Sub Totals:** label = layout rollup per class, **not** tranche **SUB** by itself. **Refinance:** **-R** / **-RR** / **CR2** = separate classes; latest suffix usually carries cash. Merge **IDD** + **PDD** by **Note Class**; **Class** = **Note Class**, never CUSIP.
**03:** When **`_page_index_waterfall.md`** exists (Wells Fargo / split waterfall PDF), Section **11.1** is in **`_chunks_waterfall/`** — call **`read_chunk_pages`** with `tree=waterfall`, **not** `tree=primary` for those page numbers. Note-val **`_chunks/`** page **5** may hold the **Administrative Expenses grid** (audit only). **Never** mark Section 11.1 **N/A** when the waterfall index exists. Read the **entire** mandatory waterfall page span (interest + principal). Amount paid = first trailing **$** on each clause line (Computershare two-number rows), not Available/Running. **Do not** put account-balance lines (Interest Collection Account, etc.) in fee rows.
**Clause-only / no grid:** fill **`### Disbursement ladder`** (one payee, one amount per row) — ladder is primary; transcribe **both** interest and principal ladders through the last mandatory page.
**Both grid + ladder:** fee **$** in **`### Waterfall table` only** (or ladder only) — do not paste the same fee in both.
**One amount per cell** — never `54.42; 2,343.73`. **No `### Valuation-relevant fees` in `03`** — `05` from `map_valuation_fees.py`.
**Subordinated management fees:** map from the **interest** Priority ladder when the PDF prints **Subordinated Asset/Management Fee** with non-zero **Paid** — do not infer **0.00** from principal cross-reference lines alone.
Do not invent amounts. Non-numeric placeholders in money cells → N/A in tables.

When finished, respond with ONLY the markdown document (no tool calls)."""


def build_tools_user_message(
    *,
    target: TargetId,
    filename: str,
    repository_context: str,
    extra_instructions: str,
    out_dir: Path | None = None,
) -> str:
    parts = [
        f"Deliverable: **{filename}** (section `{target}`).",
        f"Output directory: use tools to read files under the deal folder only.",
        "",
    ]
    if repository_context.strip():
        parts += ["## Repository instructions\n", repository_context.strip(), ""]
    if target == "04":
        parts += [
            "## Note",
            "Synthesize 04 from prior deliverables via read_prior_deliverables; "
            "do not use read_chunk_pages unless cross-checking one page.",
            "",
            "## 04 — 02 vs 03 cross-check (cautious)",
            "Sum **03** subordinated / class **Amount paid** (not fees). Compare to **02**.",
            "**Gated:** when **02** **Interest payment** is 0.00/blank and **Interest payable** ≈ waterfall sum → "
            "report **Y** with math + suggest reviewing **02** Total Payable rule.",
            "**Compare-only** when **Interest payment** already filled — never tell the pipeline to copy **03** into **02**.",
            "",
        ]
    if extra_instructions.strip():
        parts += ["## Additional instructions\n", extra_instructions.strip(), ""]
    if target == "02":
        parts += [
            "## 02 — header-first (do not guess column position)",
            "Read the exhibit **header block** in the chunk (headers may wrap: e.g. **Interest Due**, **Deferred Interest Due**, "
            "**Interest Paid**, **Deferred Interest Paid**). Map each amount to the column whose **printed title** matches. "
            "**Never** assign **$** by position after **All In Rate**, after **coupon %**, after **CUSIP**, or 'next/largest € on the line'. "
            "**All In Rate 0.00000% on Subordinated Notes is normal** — if **Interest Paid** shows cash, that is **Interest payment**, "
            "not **Deferred interest**, regardless of 0% rate. Use the **Total** row to confirm which column a figure belongs to.",
            "",
            "## 02 — required tool workflow",
            "**A) Computershare / dual PDD + IDD:** read **all** index-tagged IDD/PDD pages (often 2–7); **SUB** from IDD footer.",
            "**B) DISTRIBUTION REPORT / Section 10.5(b):** read **page 1** (class summary) **and** **Applicable Periodic Rate** page **(v)** (often page 4). "
            "**(C) interest payable** secured → **Interest payable**; **(D) payments on Subordinated Notes** → **Interest payment** (required).",
            "**C) Notes Information (BNY):** index page **Notes Information** — reconstruct headers from the chunk; "
            "**Interest Paid** → **Interest payment** by **column title** (not position after **All In Rate**); "
            "**Deferred Interest Paid** → **Deferred interest** only.",
            "1. **read_page_index** (primary).",
            "2. From the index, collect **every** page number tagged **Interest Distribution Detail** and "
            "**Principal Distribution Detail** (on many Computershare note valuation reports this span is "
            "**pages 2–7** — read **all** index-tagged IDD/PDD pages, not only the first).",
            "3. **read_chunk_pages** with `pages` = that full list (plus **Coupon** / **Factor** / "
            "**Distribution in US$** pages if the index shows them).",
            "4. **read_template_excerpt**; optionally **read_structured_tables** when `_chunks_structured/` exists.",
            "5. **Computershare blocks:** **Note Class** on the **top** row of each section with its CUSIPs listed "
            "below; **Sub Totals:** = aggregated **$** for **all listings in that section** — **not** tranche **SUB**. "
            "6. **Primary:** one row per **Note Class** from IDD **Sub Totals → Interest Distribution** (required for "
            "**SUB** when coupon is **0** but footer shows e.g. **1,107,786.98** or **1,238,322.03**). **Do not** use "
            "the **0.00** on the period-balance subtotal line above the footer. **Next Payment / Residual** pages "
            "are for **Interest rate** only — not to zero **Interest payment** when IDD has cash.",
            "",
            "## 02 rollup (required when Distribution in US$ has -144A / -REGS / -AI rows)",
            "Strip trailing program suffix to get economic class: **A-R-144A** + **A-R-REGS** → primary **A-R** only; "
            "listing = one row per printed slice. Do not put slice names in **### Class balance table (primary)**.",
            "",
            "## 02 — Note Details and Payment Summary (stacked columns)",
            "When the exhibit uses that title (or similar) with repeated class lines under row labels: "
            "**Aggregate Amount … at the beginning of the Due Period** → **Beginning balance**; "
            "**Amount of Principal Payments to be made to the Notes** (principal column block) → **Principal payment**; "
            "**Aggregate Outstanding Amount of Notes after giving effect to Principal Payments** → **Ending balance** "
            "(ending principal — `-`/blank → **0.00**). Do not leave **Ending balance** = **Beginning balance** when "
            "outstanding after principal is `-` or **0.00% after Payment Date**. Multiple **From Principal Proceeds** "
            "snippets in `_chunks/` — align to the principal-payments column, not the first snippet only.",
            "**Note Valuation Report — Periodic Interest Amount:** When **NOTE VALUATION REPORT** (Section 10.5(b) style) "
            "prints **Periodic Interest Amount on [Class]** with a numeric **$**, map to **`Interest payment`** — "
            "**not** **`Interest payable`** only. **Beginning** = Aggregate Principal as of Calculation Date; "
            "**Ending** = after principal payments. Do not replace with partial **03** waterfall interest when NVR prints the class **$**.",
            "",
            "**DISTRIBUTION REPORT Section 10.5(b):** **(C) interest payable** on secured notes → **`Interest payable`**; "
            "**(D) payments on the Subordinated Notes** → **`Interest payment`** (required). "
            "**Applicable Periodic Rate** (subsection **(v)**) → **`Interest rate`** — read that page, not page 1 only.",
            "",
            "**Notes Information (BNY Payment Date Report):** Map by **printed column titles** in the header block "
            "(**Interest Paid**, **Deferred Interest Paid**, …) — **never** by €/$ position after **All In Rate**. "
            "**0.00000% All In Rate on Subordinated Notes is normal**; non-zero **Interest Paid** → **`Interest payment`**, "
            "not **`Deferred interest`**. Confirm with the **Total** row.",
            "",
            "**Preference Share / Preferred Shares (required primary row):** When the **class / tranche summary** "
            "lists **Preference Share** or **Preferred Shares** **alongside note classes**, add **one primary row** "
            "with the printed label — map balances and interest/principal from the **same summary columns** as notes. "
            "**Never** supplementary-only when that line is on the class summary; **`### Supplementary lines`** is for "
            "**issuer-level aggregates not on any class row**. **Interest rate** may be N/A when only notes appear on "
            "the rate page. Equity may show principal paid while printed **Ending balance** ≠ beginning − principal — "
            "copy trustee figures verbatim.",
            "",
            "## 02 — automatic fill rules (when primary columns are blank)",
            "**SUB / zero-coupon interest:** When **Interest payment** is 0/blank on the class table but (**a**) IDD **Sub Totals / Interest Distribution** "
            "or **From Interest Proceeds** shows non-zero cash, **or** (**b**) **`03`** / waterfall chunks show **non-zero Payment** to "
            "**Holders of the Subordinated Notes** on the **interest** waterfall (e.g. U.S. Bank **(V)**), fill **Interest payment** from that "
            "**paid** **$** — **required**. **Interest payable** may stay from **Amount Current Payable** / **TOTAL PAYABLE**. "
            "Principal-waterfall sub **(R)** **$** is **not** **Interest payment**.",
            "**Principal payment — ending zero paydown (all required):** Fill **Principal payment** only when "
            "(1) **Principal payment** is 0/blank, (2) **Beginning balance** > 0, (3) **Ending balance** = **0.00** from "
            "**Aggregate Outstanding … after Principal Payments** (or equivalent — `-` → **0.00**), and "
            "(4) Section **11.1** / principal waterfall **class principal Amount paid** (read waterfall pages via "
            "**read_chunk_pages** or **`03` on disk if present) **matches Beginning balance** for that class. "
            "Then set **Principal payment** to the **waterfall Amount paid** — **never** infer **Principal payment = Beginning balance** "
            "without the waterfall match. Skip when **Ending balance** equals **Beginning balance**.",
            "",
        ]
    if target == "02":
        parts.append(
            "Start with **read_page_index**, then **read_chunk_pages**: "
            "**all** IDD/PDD pages for Computershare deals; for **DISTRIBUTION REPORT** / Section **10.5(b)**, "
            "read **page 1** (class summary) **and** the **Applicable Periodic Rate** page (subsection **(v)**) when present."
        )
    elif target == "03":
        mandatory_brief = ""
        if out_dir is not None:
            primary_previews, primary_total = _chunk_select.parse_page_index(
                out_dir / "_page_index.md"
            )
            wf_previews, _wf_total = _chunk_select.parse_page_index(
                out_dir / "_page_index_waterfall.md"
            )
            mandatory_pages = _chunk_select.resolve_03_mandatory_waterfall_pages(out_dir)
            if mandatory_pages:
                mandatory_brief = _chunk_select.format_03_mandatory_waterfall_brief(
                    mandatory_pages,
                    primary_previews=primary_previews,
                    wf_previews=wf_previews or None,
                    out_dir=out_dir,
                )
        if mandatory_brief:
            parts += [mandatory_brief, ""]
        parts += [
            "## 03 — required structure (`map_valuation_fees.py`)",
            "1. **read_page_index** (primary; waterfall index if dual PDF).",
            "2. **read_chunk_pages** for **every** page in the mandatory waterfall span above "
            "(one call with the full `pages` list — interest **and** principal, including generic-looking middle pages).",
            "3. **read_template_excerpt**.",
            "4. **Do not** add **`### Valuation-relevant fees`** in `03`.",
            "5. **At least one** structured fee source must have rows: **`### Waterfall table`** (multi-column grid) "
            "**or** **`### Disbursement ladder`** (clause-only). Mapper uses the grid when it has fee rows; else ladder.",
            "6. **One payee, one amount per row** — never `54.42; 2,343.73` in one cell.",
            "7. **Do not** add an empty **`### Waterfall table`** on ladder-only deals — use **Layout** Logical only.",
            "8. Class cash already in **02**: optional **0.00** + **Notes** `see 02` in a grid when you use one.",
            "",
            "Start with **read_page_index**, then **read_chunk_pages** for the **full** mandatory page list.",
        ]
    else:
        parts.append(
            "Start by reading the page index, then open only the pages you need."
        )
    return "\n".join(parts)


_TARGET_TO_FILE: dict[TargetId, str] = {
    "01": "01_report_metadata.md",
    "02": "02_tranche_class_balances.md",
    "03": "03_interest_principal_waterfall.md",
    "04": "04_extraction_summary.md",
}


def _slice_template(repo_root: Path, target: TargetId) -> str:
    path = repo_root / "noteval_extractor" / "references" / "extraction-templates.md"
    if not path.is_file():
        raise FileNotFoundError(path)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    markers: dict[str, int] = {}
    for i, line in enumerate(lines):
        if line.startswith("## File "):
            key = line[8:10]
            if key in ("01", "02", "03", "04", "06"):
                markers[key] = i
    end_map = {"01": markers["02"], "02": markers["03"], "03": markers.get("06", markers["04"]), "04": len(lines)}
    start = markers[target]
    return "\n".join(lines[start : end_map[target]]).strip() + "\n"


def _read_prior(out: Path, cap: int = 42_000) -> str:
    parts: list[str] = []
    for tid in ("01", "02", "03"):
        p = out / _TARGET_TO_FILE[tid]  # type: ignore[index]
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if len(text) > cap:
            text = text[:cap] + "\n\n[TRUNCATED]\n"
        parts.append(f"### `{p.name}`\n\n{text}")
    return "\n\n".join(parts)


def _load_dotenv(repo_root: Path) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    for p in (
        repo_root / ".env",
        repo_root / "noteval_extractor" / ".env",
        repo_root / "noteval_extractor" / "scripts" / ".env",
    ):
        if p.is_file():
            load_dotenv(p, override=False)


def main() -> None:
    """CLI: one tool-calling draft for a single deliverable."""
    import argparse

    import noteval_llm as llm

    repo = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser(
        description="Draft one noteval file using LLM function calling (noteval_llm_tools)."
    )
    ap.add_argument(
        "output_dir",
        type=Path,
        help="Segmented deal folder (contains _chunks/, _page_index.md)",
    )
    ap.add_argument(
        "--target",
        choices=["01", "02", "03", "04"],
        required=True,
        help="Which deliverable to draft",
    )
    ap.add_argument("--write", action="store_true", help="Save markdown into output_dir")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--max-turns", type=int, default=None)
    args = ap.parse_args()

    _load_dotenv(repo)
    out = args.output_dir.resolve()
    if not (out / "_chunks").is_dir():
        raise SystemExit(f"Missing _chunks/ under {out}")

    key, _, model = llm.draft_env()
    if not key:
        raise SystemExit("Set NOTEVAL_DRAFT_API_KEY or OPENAI_API_KEY (or .env).")

    target: TargetId = args.target  # type: ignore[assignment]
    fn = _TARGET_TO_FILE[target]
    prior = _read_prior(out) if target == "04" else ""

    print(f"Model: {model}")
    print(f"Tool-calling draft {target} -> {fn} …")

    md, meta, usage = llm.openai_chat_completion_with_tools(
        out_dir=out,
        target=target,
        filename=fn,
        template_excerpt=_slice_template(repo, target),
        repository_context="",
        prior_deliverables=prior,
        extra_instructions="",
        read_prior_fn=lambda: _read_prior(out),
        timeout=args.timeout,
        max_turns=args.max_turns,
    )

    print(f"Done: {meta.get('tool_turns')} turn(s), {len(meta.get('tools_called') or [])} tool call(s)")
    if usage.get("cost_usd") is not None:
        print(f"Estimated cost USD: {usage['cost_usd']} ({usage.get('pricing_note')})")

    if args.write:
        dest = out / fn
        dest.write_text(md.strip() + "\n", encoding="utf-8", newline="\n")
        print(f"Wrote {dest}")
    else:
        print("\n--- markdown (first 2000 chars) ---\n")
        print(md[:2000])
        if len(md) > 2000:
            print("\n… [truncated; use --write to save full file]")


if __name__ == "__main__":
    main()
