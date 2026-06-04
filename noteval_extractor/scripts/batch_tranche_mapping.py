"""
batch_tranche_mapping.py — Batch tranche mapping from agent export XML → Excel.

**Primary input:** ``noteval_export`` XML files (``{deal_id}_{YYYYMMDD}.xml``)
produced after extraction, e.g. via::

  py -3 noteval_extractor/scripts/export_noteval_xml.py <output_folder> --map-tranches

Input options (pick one):

1. **CSV** with ``xml_file`` (path to each XML), or ``deal_id`` + ``payment_date``
   (script resolves ``{xml_root}/{deal_id}_{YYYYMMDD}.xml``).

2. **``--xml``** one or more ``.xml`` paths.

3. **``--xml-dir``** — all ``*.xml`` in a folder (e.g. 10 deals for a pilot).

4. **``--deal`` / ``--date``** pairs (resolve under ``--xml-root``).

Usage (10-deal pilot)::

  py -3 noteval_extractor/scripts/export_noteval_xml.py output/DEAL_DATE --map-tranches
  # … repeat per deal, XML lands in noteval_extractor/xml/

  py -3 noteval_extractor/scripts/batch_tranche_mapping.py pilot_deals.csv \\
      -o tranche_mapping_10.xlsx

  py -3 noteval_extractor/scripts/batch_tranche_mapping.py --xml-dir noteval_extractor/xml \\
      -o tranche_mapping_all.xlsx --max-deals 10

Environment: NOTEVAL_ODBC_CONNECTION, or ``--tranche-cache`` + ``--no-db``.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from export_noteval_xml import parse_us_date  # noqa: E402
from map_tranches import TrancheMapper  # noqa: E402

_DEAL_XML_STEM = re.compile(r"^(\d+)_(\d{8})(?:_sdk|_llm)?$")

_MAPPING_HEADERS = [
    "deal_id",
    "payment_date",
    "xml_file",
    "schema_version",
    "deal_name",
    "class_name",
    "cusip",
    "moodystrancheid",
    "trustee_tranche_name",
    "map_tier",
    "map_status",
    "map_message",
    "xml_map_status",
    "beginning_balance",
    "interest_payment",
    "principal_payment",
    "ending_balance",
]

_SUMMARY_HEADERS = [
    "deal_id",
    "payment_date",
    "xml_file",
    "schema_version",
    "status",
    "class_rows",
    "mapped_ok",
    "unmapped",
    "ambiguous",
    "already_mapped_in_xml",
    "notes",
]


@dataclass
class XmlBatchItem:
    xml_path: Path
    deal_id: str
    payment_date_input: str = ""
    payment_iso: str = ""


def _default_xml_root() -> Path:
    return _SCRIPT_DIR.parent / "xml"


def openpyxl_available() -> bool:
    try:
        import openpyxl  # noqa: F401

        return True
    except ImportError:
        return False


def normalize_payment_date_yyyymmdd(raw: str) -> tuple[str, str]:
    """Return (YYYYMMDD, ISO YYYY-MM-DD or '')."""
    t = (raw or "").strip()
    if not t:
        return "", ""
    if len(t) == 8 and t.isdigit():
        ymd = t
    else:
        d = parse_us_date(t)
        if not d:
            digits = "".join(c for c in t if c.isdigit())
            if len(digits) == 8:
                ymd = digits
            else:
                return "", t
        else:
            ymd = f"{d.year:04d}{d.month:02d}{d.day:02d}"
    try:
        iso = datetime.strptime(ymd, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        iso = ""
    return ymd, iso


def parse_deal_date_from_xml_path(path: Path) -> tuple[str, str]:
    """Infer (deal_id, yyyymmdd) from ``869358159_20260420.xml`` stem."""
    stem = path.stem
    m = _DEAL_XML_STEM.match(stem)
    if m:
        return m.group(1), m.group(2)
    return "", ""


def resolve_xml_path(
    xml_root: Path,
    deal_id: str,
    payment_date_input: str,
) -> Path | None:
    pay_ymd, _ = normalize_payment_date_yyyymmdd(payment_date_input)
    if not pay_ymd:
        return None
    deal_id = deal_id.strip()
    for stem in (f"{deal_id}_{pay_ymd}", f"{deal_id}_{pay_ymd}_sdk"):
        p = xml_root / f"{stem}.xml"
        if p.is_file():
            return p.resolve()
    return None


def read_export_xml_meta(xml_path: Path) -> dict[str, str]:
    """Read deal_id, dates, deal_name, schema from noteval_export XML."""
    root = ET.parse(xml_path).getroot()
    if root.tag != "noteval_export":
        raise ValueError(f"Not a noteval_export file: {xml_path}")
    meta: dict[str, str] = {
        "schema_version": root.get("schema_version", "") or "",
        "source_folder": root.get("source_folder", "") or "",
    }
    md = root.find("metadata")
    if md is not None:
        for tag in ("deal_id", "deal_name", "payment_date", "currency"):
            el = md.find(tag)
            if el is not None and (el.text or "").strip():
                meta[tag] = el.text.strip()
            if tag == "payment_date" and el is not None:
                disp = el.get("display")
                if disp:
                    meta["payment_date_display"] = disp
    did_file, ymd_file = parse_deal_date_from_xml_path(xml_path)
    if not meta.get("deal_id") and did_file:
        meta["deal_id"] = did_file
    if ymd_file:
        meta["payment_date_ymd"] = ymd_file
    return meta


def class_lines_from_xml(xml_path: Path) -> list[dict[str, str]]:
    root = ET.parse(xml_path).getroot()
    out: list[dict[str, str]] = []
    classes = root.find("classes")
    if classes is None:
        return out
    for ce in classes.findall("class"):
        cname = (ce.get("name") or "").strip()
        if not cname:
            continue
        xml_tid = (ce.get("moodystrancheid") or "").strip()
        xml_map_status = (ce.get("map_status") or "").strip()
        base = {
            "class_name": cname,
            "cusip": "",
            "xml_moodystrancheid": xml_tid,
            "xml_map_status": xml_map_status,
            "beginning_balance": (ce.findtext("beginning_balance") or "").strip(),
            "interest_payment": (ce.findtext("interest_payment") or "").strip(),
            "principal_payment": (ce.findtext("principal_payment") or "").strip(),
            "ending_balance": (ce.findtext("ending_balance") or "").strip(),
        }
        idel = ce.find("identifiers")
        cusips: list[str] = []
        if idel is not None:
            for line in idel.findall("line"):
                c = (line.get("cusip") or "").strip()
                if c and c.upper() != "N/A":
                    cusips.append(c)
                if not xml_tid:
                    xml_tid = (line.get("moodystrancheid") or "").strip()
                    if xml_tid:
                        base["xml_moodystrancheid"] = xml_tid
        base["cusips"] = cusips
        base["cusip"] = "; ".join(cusips)
        out.append(base)
    return out


def load_requests_csv(path: Path, xml_root: Path) -> list[XmlBatchItem]:
    items: list[XmlBatchItem] = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return items
        fields = {h.strip().lower().replace(" ", "_"): h for h in reader.fieldnames if h}
        xml_col = fields.get("xml_file") or fields.get("xml_path") or fields.get("xml")
        did_col = fields.get("deal_id") or fields.get("moodysdealid")
        pd_col = fields.get("payment_date") or fields.get("date")

        for row in reader:
            xml_path: Path | None = None
            deal_id = ""
            pay_in = ""

            if xml_col:
                raw = (row.get(xml_col) or "").strip()
                if raw:
                    xml_path = Path(raw)
                    if not xml_path.is_absolute():
                        xml_path = (path.parent / xml_path).resolve()
            if did_col:
                deal_id = (row.get(did_col) or "").strip()
            if pd_col:
                pay_in = (row.get(pd_col) or "").strip()

            if xml_path is None and deal_id and pay_in:
                xml_path = resolve_xml_path(xml_root, deal_id, pay_in)

            if xml_path is None or not xml_path.is_file():
                raise FileNotFoundError(
                    f"XML not found for row deal_id={deal_id!r} payment_date={pay_in!r} "
                    f"(set xml_file column or place file under {xml_root})"
                )

            meta = read_export_xml_meta(xml_path)
            did = meta.get("deal_id") or deal_id or parse_deal_date_from_xml_path(xml_path)[0]
            pay_iso = meta.get("payment_date", "")
            ymd = meta.get("payment_date_ymd", "")
            if not pay_in and ymd:
                pay_in = ymd
            if not pay_iso and pay_in:
                _, pay_iso = normalize_payment_date_yyyymmdd(pay_in)

            items.append(
                XmlBatchItem(
                    xml_path=xml_path,
                    deal_id=did,
                    payment_date_input=pay_in or pay_iso,
                    payment_iso=pay_iso,
                )
            )
    return items


def items_from_xml_paths(paths: list[Path]) -> list[XmlBatchItem]:
    items: list[XmlBatchItem] = []
    for p in paths:
        p = p.resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        meta = read_export_xml_meta(p)
        did = meta.get("deal_id") or parse_deal_date_from_xml_path(p)[0]
        pay_iso = meta.get("payment_date", "")
        ymd = meta.get("payment_date_ymd", "")
        items.append(
            XmlBatchItem(
                xml_path=p,
                deal_id=did,
                payment_date_input=ymd or pay_iso,
                payment_iso=pay_iso,
            )
        )
    return items


def items_from_xml_dir(xml_dir: Path, *, max_deals: int = 0) -> list[XmlBatchItem]:
    paths = sorted(xml_dir.glob("*.xml"), key=lambda x: x.name.lower())
    if max_deals > 0:
        paths = paths[:max_deals]
    return items_from_xml_paths(paths)


def process_xml_item(
    item: XmlBatchItem,
    mapper: TrancheMapper,
) -> tuple[list[list[Any]], list[Any]]:
    xml_path = item.xml_path
    deal_id = item.deal_id
    notes: list[str] = []

    try:
        meta = read_export_xml_meta(xml_path)
    except (ET.ParseError, ValueError) as e:
        notes.append(str(e))
        meta = {}

    schema = meta.get("schema_version", "")
    deal_name = meta.get("deal_name", "")
    pay_iso = item.payment_iso or meta.get("payment_date", "")
    if schema and schema < "3":
        notes.append(f"old schema_version={schema}")

    class_lines = class_lines_from_xml(xml_path)
    mapping_rows: list[list[Any]] = []
    ok = unmapped = ambiguous = already = 0

    for line in class_lines:
        xml_tid = line.get("xml_moodystrancheid", "")
        xml_st = line.get("xml_map_status", "")

        if xml_tid and xml_st == "ok":
            r_tid = xml_tid
            r_tier = "xml"
            r_status = "ok"
            r_tname = ""
            r_msg = "from export XML"
            already += 1
        else:
        else:
            cusips_raw = line.get("cusips")
            if cusips_raw:
                r = mapper.resolve(
                    deal_id,
                    cusips=cusips_raw,
                    class_name=line.get("class_name") or None,
                )
            else:
                r = mapper.resolve(
                    deal_id,
                    cusip=line.get("cusip") or None,
                    class_name=line.get("class_name") or None,
                )
            r_tid = r.moodystrancheid or ""
            r_tier = r.map_tier or ""
            r_status = r.map_status or ""
            r_tname = r.trustee_tranche_name or ""
            r_msg = r.map_message or ""

        if r_status == "ok":
            ok += 1
        elif r_status == "ambiguous":
            ambiguous += 1
        else:
            unmapped += 1

        mapping_rows.append(
            [
                deal_id,
                pay_iso,
                str(xml_path),
                schema,
                deal_name,
                line.get("class_name", ""),
                line.get("cusip", ""),
                r_tid,
                r_tname,
                r_tier,
                r_status,
                r_msg,
                xml_st or ("ok" if xml_tid else ""),
                line.get("beginning_balance", ""),
                line.get("interest_payment", ""),
                line.get("principal_payment", ""),
                line.get("ending_balance", ""),
            ]
        )

    if not class_lines:
        notes.append("no <class> rows in XML")
        mapping_rows.append(
            [
                deal_id,
                pay_iso,
                str(xml_path),
                schema,
                deal_name,
                "",
                "",
                "",
                "",
                "",
                "no_data",
                "; ".join(notes),
                "",
                "",
                "",
                "",
                "",
            ]
        )

    if not class_lines:
        status = "missing"
    elif ambiguous or unmapped:
        status = "partial"
    else:
        status = "ok"

    summary = [
        deal_id,
        pay_iso,
        str(xml_path),
        schema,
        status,
        len(class_lines),
        ok,
        unmapped,
        ambiguous,
        already,
        "; ".join(notes),
    ]
    return mapping_rows, summary


def build_workbook(items: list[XmlBatchItem], mapper: TrancheMapper) -> bytes:
    if not openpyxl_available():
        raise SystemExit(
            "openpyxl is required. Install with: py -3 -m pip install openpyxl"
        )
    from openpyxl import Workbook
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    default = wb.active
    if default is not None:
        wb.remove(default)

    all_mapping: list[list[Any]] = []
    summaries: list[list[Any]] = []

    for did in sorted({x.deal_id for x in items if x.deal_id}):
        try:
            mapper.maps_for_deal(did)
        except Exception as e:
            print(f"warn: preload {did}: {e}", file=sys.stderr)

    for item in items:
        mrows, summ = process_xml_item(item, mapper)
        all_mapping.extend(mrows)
        summaries.append(summ)

    def write_sheet(ws, headers: list[str], rows: list[list[Any]]) -> None:
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for row in rows:
            ws.append(row)
        for col_idx, header in enumerate(headers, start=1):
            letter = get_column_letter(col_idx)
            max_len = len(header)
            for row in rows[:400]:
                if col_idx - 1 < len(row):
                    max_len = max(max_len, len(str(row[col_idx - 1] or "")))
            ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 52)

    ws_map = wb.create_sheet("Tranche mapping", 0)
    write_sheet(ws_map, _MAPPING_HEADERS, all_mapping)
    ws_sum = wb.create_sheet("Summary")
    write_sheet(ws_sum, _SUMMARY_HEADERS, summaries)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Batch tranche mapping from agent noteval_export XML files."
    )
    ap.add_argument(
        "csv",
        nargs="?",
        type=Path,
        help="CSV: xml_file column OR deal_id + payment_date",
    )
    ap.add_argument(
        "--xml",
        nargs="*",
        type=Path,
        default=[],
        help="One or more export XML paths",
    )
    ap.add_argument(
        "--xml-dir",
        type=Path,
        help="Directory of *.xml export files (e.g. noteval_extractor/xml)",
    )
    ap.add_argument(
        "--xml-root",
        type=Path,
        default=None,
        help=f"Resolve deal_id+date to XML here (default: {_default_xml_root()})",
    )
    ap.add_argument(
        "--deal",
        action="append",
        default=[],
        help="Deal id (with --date; XML under --xml-root)",
    )
    ap.add_argument("--date", action="append", default=[])
    ap.add_argument(
        "--max-deals",
        type=int,
        default=0,
        help="Cap deals when using --xml-dir (0 = no cap)",
    )
    ap.add_argument("-o", "--output", type=Path, required=True, help="Output .xlsx")
    ap.add_argument("--tranche-cache", type=Path, help="JSON from map_tranches --prefetch")
    ap.add_argument("--no-db", action="store_true", help="Use only --tranche-cache")
    args = ap.parse_args()

    xml_root = (args.xml_root or _default_xml_root()).resolve()
    items: list[XmlBatchItem] = []

    try:
        if args.csv:
            items.extend(load_requests_csv(args.csv.resolve(), xml_root))
        if args.xml:
            items.extend(items_from_xml_paths([p.resolve() for p in args.xml]))
        if args.xml_dir:
            items.extend(
                items_from_xml_dir(
                    args.xml_dir.resolve(),
                    max_deals=args.max_deals or 0,
                )
            )
        if args.deal:
            if len(args.deal) != len(args.date):
                print("--deal and --date must be paired equally", file=sys.stderr)
                return 2
            for did, pd in zip(args.deal, args.date):
                xp = resolve_xml_path(xml_root, did, pd)
                if xp is None:
                    print(f"XML not found: {did} {pd} under {xml_root}", file=sys.stderr)
                    return 1
                ymd, iso = normalize_payment_date_yyyymmdd(pd)
                items.append(
                    XmlBatchItem(
                        xml_path=xp,
                        deal_id=did.strip(),
                        payment_date_input=pd,
                        payment_iso=iso,
                    )
                )
    except FileNotFoundError as e:
        print(e, file=sys.stderr)
        return 1
    except ValueError as e:
        print(e, file=sys.stderr)
        return 1

    if not items:
        print(
            "Provide csv, --xml, --xml-dir, or --deal/--date. "
            "Input must be noteval_export XML from the agent pipeline.",
            file=sys.stderr,
        )
        return 2

    # dedupe by xml path
    seen: set[str] = set()
    unique: list[XmlBatchItem] = []
    for it in items:
        key = str(it.xml_path)
        if key not in seen:
            seen.add(key)
            unique.append(it)
    items = unique

    mapper = TrancheMapper(
        cache_file=args.tranche_cache.resolve() if args.tranche_cache else None,
        use_db=not args.no_db,
    )

    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(build_workbook(items, mapper))
    print(out)
    print(f"Deals: {len(items)}  (from XML) — see Summary sheet", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
