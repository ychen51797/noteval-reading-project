"""
view_noteval_xml.py — Human-readable report from noteval_export XML.

Usage::

  py -3 noteval_extractor/scripts/view_noteval_xml.py path/to/824237876_20260427.xml
  py -3 noteval_extractor/scripts/view_noteval_xml.py path/to/deal.xml -o report.html --open
  py -3 noteval_extractor/scripts/view_noteval_xml.py path/to/deal.xml -o report.md --format md

Requires no extra packages (stdlib only).
"""

from __future__ import annotations

import argparse
import html as html_mod
import sys
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path


def _esc(s: str | None) -> str:
    return html_mod.escape(s or "", quote=True)


def _text(el: ET.Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _attrs(el: ET.Element, *names: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for n in names:
        v = el.get(n)
        if v:
            out[n] = v
    return out


def _status_class(status: str | None) -> str:
    if status == "ok":
        return "ok"
    if status == "ambiguous":
        return "warn"
    if status == "unmapped":
        return "bad"
    return ""


def parse_export_xml(path: Path) -> ET.Element:
    root = ET.parse(path).getroot()
    if root.tag != "noteval_export":
        raise ValueError(f"Expected <noteval_export>, got <{root.tag}> in {path}")
    return root


def build_markdown(root: ET.Element, *, source: str) -> str:
    lines: list[str] = []
    schema = root.get("schema_version", "?")
    folder = root.get("source_folder", "")
    lines.append(f"# Noteval export report")
    lines.append("")
    lines.append(f"- **Source XML:** `{source}`")
    lines.append(f"- **Schema:** {schema}")
    if folder:
        lines.append(f"- **Folder:** {folder}")
    lines.append("")

    md = root.find("metadata")
    if md is not None:
        lines.append("## Metadata")
        lines.append("")
        for tag in (
            "deal_id",
            "deal_name",
            "report_title",
            "payment_date",
            "determination_date",
            "record_date",
            "currency",
            "trustee",
        ):
            v = _text(md.find(tag))
            if v:
                lines.append(f"- **{tag.replace('_', ' ').title()}:** {v}")
        lines.append("")

    classes = root.find("classes")
    if classes is not None:
        lines.append("## Classes")
        lines.append("")
        headers = [
            "Class",
            "Moodys tranche id",
            "Map tier",
            "Map status",
            "Trustee tranche",
            "Original",
            "Beginning",
            "Interest pmt",
            "Principal pmt",
            "Ending",
        ]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")
        for ce in classes.findall("class"):
            name = ce.get("name", "")
            row = [
                name,
                ce.get("moodystrancheid", ""),
                ce.get("map_tier", ""),
                ce.get("map_status", ""),
                ce.get("trustee_tranche_name", ""),
                _text(ce.find("original_balance")),
                _text(ce.find("beginning_balance")),
                _text(ce.find("interest_payment")),
                _text(ce.find("principal_payment")),
                _text(ce.find("ending_balance")),
            ]
            lines.append("| " + " | ".join(row) + " |")
            idel = ce.find("identifiers")
            if idel is not None:
                for line in idel.findall("line"):
                    cusip = line.get("cusip", "")
                    isin = line.get("isin", "")
                    tid = line.get("moodystrancheid", "")
                    if cusip or isin:
                        lines.append(
                            f"  - listing: CUSIP `{cusip}` ISIN `{isin}` → tranche `{tid}`"
                        )
        lines.append("")

    fees = root.find("valuation_fees")
    if fees is not None:
        lines.append("## Valuation fees")
        lines.append("")
        lines.append("| Main | Sub | Priority | Amount paid |")
        lines.append("| --- | --- | --- | --- |")
        for fe in fees.findall("fee"):
            lines.append(
                "| "
                + " | ".join(
                    [
                        fe.get("main_category", ""),
                        fe.get("sub_category", ""),
                        fe.get("priority", ""),
                        fe.get("amount_paid", ""),
                    ]
                )
                + " |"
            )
        total = _text(fees.find("administrative_expenses_grid_total"))
        if total:
            lines.append("")
            lines.append(f"- **Administrative expenses grid total:** {total}")
        lines.append("")

    return "\n".join(lines)


def build_html(root: ET.Element, *, source: str) -> str:
    schema = _esc(root.get("schema_version"))
    folder = _esc(root.get("source_folder"))
    md = root.find("metadata")

    meta_rows = ""
    if md is not None:
        for tag, label in (
            ("deal_id", "Deal ID"),
            ("deal_name", "Deal name"),
            ("report_title", "Report title"),
            ("payment_date", "Payment date"),
            ("determination_date", "Determination date"),
            ("currency", "Currency"),
            ("trustee", "Trustee"),
        ):
            v = _text(md.find(tag))
            if v:
                meta_rows += f"<tr><th>{_esc(label)}</th><td>{_esc(v)}</td></tr>\n"

    class_rows = ""
    classes = root.find("classes")
    if classes is not None:
        for ce in classes.findall("class"):
            st = ce.get("map_status", "")
            tr_cls = _status_class(st)
            class_rows += (
                f'<tr class="{tr_cls}">'
                f"<td>{_esc(ce.get('name'))}</td>"
                f"<td>{_esc(ce.get('moodystrancheid'))}</td>"
                f"<td>{_esc(ce.get('map_tier'))}</td>"
                f"<td>{_esc(st)}</td>"
                f"<td>{_esc(ce.get('trustee_tranche_name'))}</td>"
                f"<td class='num'>{_esc(_text(ce.find('original_balance')))}</td>"
                f"<td class='num'>{_esc(_text(ce.find('beginning_balance')))}</td>"
                f"<td class='num'>{_esc(_text(ce.find('interest_payment')))}</td>"
                f"<td class='num'>{_esc(_text(ce.find('principal_payment')))}</td>"
                f"<td class='num'>{_esc(_text(ce.find('ending_balance')))}</td>"
                f"</tr>\n"
            )
            idel = ce.find("identifiers")
            if idel is not None:
                for line in idel.findall("line"):
                    cusip = line.get("cusip", "")
                    isin = line.get("isin", "")
                    tid = line.get("moodystrancheid", "")
                    if not (cusip or isin):
                        continue
                    class_rows += (
                        f'<tr class="sub {tr_cls}">'
                        f"<td colspan='2'>↳ {_esc(cusip or isin)}</td>"
                        f"<td colspan='2'>{_esc(line.get('map_tier'))}</td>"
                        f"<td>{_esc(line.get('map_status'))}</td>"
                        f"<td colspan='5'>tranche {_esc(tid)}</td>"
                        f"</tr>\n"
                    )

    fee_rows = ""
    fees = root.find("valuation_fees")
    admin_total = ""
    if fees is not None:
        for fe in fees.findall("fee"):
            fee_rows += (
                "<tr>"
                f"<td>{_esc(fe.get('main_category'))}</td>"
                f"<td>{_esc(fe.get('sub_category'))}</td>"
                f"<td>{_esc(fe.get('priority'))}</td>"
                f"<td class='num'>{_esc(fe.get('amount_paid'))}</td>"
                "</tr>\n"
            )
        t = _text(fees.find("administrative_expenses_grid_total"))
        if t:
            admin_total = f"<p><strong>Admin grid total:</strong> {_esc(t)}</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Noteval report — {_esc(_text(md.find('deal_id')) if md is not None else source)}</title>
  <style>
    body {{ font-family: Segoe UI, system-ui, sans-serif; margin: 24px; color: #1a1a1a; }}
    h1 {{ font-size: 1.35rem; margin-bottom: 0.25rem; }}
    .meta {{ color: #555; font-size: 0.9rem; margin-bottom: 1.5rem; }}
    h2 {{ font-size: 1.1rem; margin-top: 1.75rem; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 0.88rem; margin-top: 8px; }}
    th, td {{ border: 1px solid #ccc; padding: 6px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f0f4f8; }}
    tr.ok td:nth-child(4) {{ color: #0d6b0d; font-weight: 600; }}
    tr.bad td:nth-child(4) {{ color: #b00020; font-weight: 600; }}
    tr.warn td:nth-child(4) {{ color: #9a6b00; font-weight: 600; }}
    tr.sub td {{ background: #fafafa; font-size: 0.82rem; }}
    td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  </style>
</head>
<body>
  <h1>Noteval export report</h1>
  <p class="meta">Source: <code>{_esc(source)}</code> · schema <strong>{schema}</strong>
    {f' · folder <code>{folder}</code>' if folder else ''}</p>

  <h2>Metadata</h2>
  <table><tbody>{meta_rows or '<tr><td colspan="2">(none)</td></tr>'}</tbody></table>

  <h2>Classes &amp; tranche mapping</h2>
  <table>
    <thead>
      <tr>
        <th>Class</th><th>Moodys tranche id</th><th>Tier</th><th>Status</th>
        <th>Trustee tranche</th><th>Original</th><th>Beginning</th><th>Interest pmt</th>
        <th>Principal pmt</th><th>Ending</th>
      </tr>
    </thead>
    <tbody>{class_rows or '<tr><td colspan="9">(no classes)</td></tr>'}</tbody>
  </table>

  <h2>Valuation fees</h2>
  <table>
    <thead><tr><th>Main</th><th>Sub</th><th>Priority</th><th>Amount paid</th></tr></thead>
    <tbody>{fee_rows or '<tr><td colspan="4">(no fees)</td></tr>'}</tbody>
  </table>
  {admin_total}
</body>
</html>
"""


def default_output_path(xml_path: Path, fmt: str) -> Path:
    ext = ".html" if fmt == "html" else ".md"
    return xml_path.with_name(xml_path.stem + "_report" + ext)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build a visible HTML or Markdown report from noteval_export XML."
    )
    ap.add_argument("xml_path", type=Path, help="Path to {deal_id}_{date}.xml")
    ap.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output path (.html or .md). Default: next to XML as *_report.html",
    )
    ap.add_argument(
        "--format",
        choices=("html", "md", "both"),
        default="html",
        help="Output format (default: html)",
    )
    ap.add_argument(
        "--open",
        action="store_true",
        help="Open HTML report in the default browser (html format only)",
    )
    args = ap.parse_args()

    xml_path = args.xml_path.resolve()
    if not xml_path.is_file():
        print(f"Not found: {xml_path}", file=sys.stderr)
        return 1

    root = parse_export_xml(xml_path)
    source = str(xml_path)
    written: list[Path] = []

    if args.format in ("html", "both"):
        out = args.output.resolve() if args.output and args.format == "html" else default_output_path(xml_path, "html")
        if args.format == "both" and args.output:
            out = args.output.resolve().with_suffix(".html")
        out.write_text(build_html(root, source=source), encoding="utf-8")
        written.append(out)
        print(out)
        if args.open:
            webbrowser.open(out.as_uri())

    if args.format in ("md", "both"):
        out = default_output_path(xml_path, "md")
        if args.output and args.format == "md":
            out = args.output.resolve()
        elif args.format == "both":
            out = (args.output.resolve() if args.output else default_output_path(xml_path, "md")).with_suffix(".md")
        out.write_text(build_markdown(root, source=source), encoding="utf-8")
        written.append(out)
        print(out)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
