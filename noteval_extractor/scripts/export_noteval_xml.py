"""
export_noteval_xml.py — Build noteval_export.xml from markdown 01–03 per
noteval_extractor/references/xml-export.md (schema_version 3 or 4).

With ``--map-tranches``: writes ``01_report_metadata.xml``, resolves
``moodystrancheid`` on ``<class>`` / ``<line>``, sets ``schema_version="4"``.

Usage:
  py -3 noteval_extractor/scripts/export_noteval_xml.py <extraction_dir>
  py -3 noteval_extractor/scripts/export_noteval_xml.py <extraction_dir> --map-tranches
  py -3 noteval_extractor/scripts/export_noteval_xml.py <extraction_dir> --out-dir <dir>

Default --out-dir: <repo>/noteval_extractor/xml/

Writes {deal_id}_{payment_date}.xml (basename of extraction_dir + .xml).
"""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from map_tranches import MapResult, TrancheMapper


def parse_md_tables(text: str) -> list[list[list[str]]]:
    """Parse markdown pipe tables; returns list of tables (each: header + body rows)."""
    tables: list[list[list[str]]] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("|") and i + 1 < len(lines):
            sep_line = lines[i + 1].strip()
            if re.match(r"^\|[\s\-:|]+\|$", sep_line):
                table: list[list[str]] = []
                header = [c.strip() for c in line.split("|")[1:-1]]
                table.append(header)
                j = i + 2
                while j < len(lines) and lines[j].strip().startswith("|"):
                    row = [c.strip() for c in lines[j].strip().split("|")[1:-1]]
                    table.append(row)
                    j += 1
                tables.append(table)
                i = j
                continue
        i += 1
    return tables


def _norm_header(s: str) -> str:
    return re.sub(r"\*+", "", s).strip().lower()


def field_value_dict(table: list[list[str]]) -> dict[str, str]:
    if len(table) < 2:
        return {}
    h0, h1 = _norm_header(table[0][0]), _norm_header(table[0][1]) if len(table[0]) > 1 else ""
    if h0 != "field" or h1 != "value":
        return {}
    out: dict[str, str] = {}
    for row in table[1:]:
        if len(row) >= 2:
            out[row[0].strip()] = row[1].strip()
    return out


def _parse_tables_kv(tables: list[list[list[str]]]) -> list[dict[str, str]]:
    return [d for t in tables if (d := field_value_dict(t))]


def _col_index(header: list[str], *needles: str) -> int | None:
    nh = [_norm_header(h) for h in header]
    for i, h in enumerate(nh):
        if all(n in h for n in needles):
            return i
    for i, h in enumerate(nh):
        if any(h == n or h.endswith(n) for n in needles if " " not in n):
            for n in needles:
                if h == n:
                    return i
    return None


def _col_exact(header: list[str], name: str) -> int | None:
    nl = _norm_header(name)
    for i, h in enumerate(header):
        if _norm_header(h) == nl:
            return i
    return None


def parse_us_date(s: str) -> datetime | None:
    if not s or s.upper() == "N/A":
        return None
    t = s.strip()
    for fmt in (
        "%m/%d/%Y",
        "%m/%d/%y",
        "%Y-%m-%d",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d-%b-%y",
    ):
        try:
            return datetime.strptime(t, fmt)
        except ValueError:
            continue
    return None


def to_yyyymmdd(s: str) -> str | None:
    d = parse_us_date(s)
    if not d:
        return None
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"


def to_iso_date(s: str) -> str | None:
    d = parse_us_date(s)
    if not d:
        return None
    return d.strftime("%Y-%m-%d")


def find_class_balance_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table or len(table[0]) < 3:
            continue
        h = " | ".join(_norm_header(x) for x in table[0])
        if "class" in h and "beginning balance" in h:
            if "interest payment" in h or "interest payable" in h:
                return table
    return None


def find_listing_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table:
            continue
        h = " | ".join(_norm_header(x) for x in table[0])
        if "cusip line id" in h and "economic class" in h:
            return table
    return None


def find_valuation_fees_table(tables: list[list[list[str]]]) -> list[list[str]] | None:
    for table in tables:
        if not table or len(table[0]) < 2:
            continue
        h = " | ".join(_norm_header(x) for x in table[0])
        if (
            "main category" in h
            and ("fee_type" in h or "sub category" in h or "standard fee type" in h)
            and "amount paid" in h
        ):
            return table
    return None


def _is_administrative_expenses_grid(table: list[list[str]]) -> bool:
    if not table or len(table) < 2:
        return False
    h = " ".join(_norm_header(c) for c in table[0])
    if "expense" not in h and "fee" not in h:
        return False
    if "paid on the distribution date" in h:
        return True
    if "paid" in h and ("distribution" in h or "during the period" in h):
        return True
    return False


def _admin_grid_paid_col_index(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        nh = _norm_header(cell)
        if "paid" in nh and "distribution" in nh:
            return i
    for i, cell in enumerate(header):
        if _norm_header(cell) == "paid on the distribution date":
            return i
    if len(header) >= 2 and "note" in _norm_header(header[-1]):
        return len(header) - 2
    if header:
        return len(header) - 1
    return None


def _money_cell_for_xml(s: str) -> str | None:
    t = re.sub(r"[\s$€£]", "", (s or "").strip()).replace(",", "")
    if not t or t.upper() == "N/A":
        return None
    if re.fullmatch(r"-?\d+(\.\d+)?", t):
        return t
    return None


def administrative_expenses_grid_total_from_tables(
    tables: list[list[list[str]]],
) -> str | None:
    """Grand total paid from ### Administrative Expenses grid, if unambiguous."""
    for table in tables:
        if not _is_administrative_expenses_grid(table):
            continue
        header = table[0]
        paid_i = _admin_grid_paid_col_index(header)
        if paid_i is None:
            continue
        candidates: list[str] = []
        for row in reversed(table[1:]):
            if not row or paid_i >= len(row):
                continue
            c0 = row[0].strip()
            if not c0 or c0.upper() == "N/A":
                continue
            c0_low = c0.lower()
            if re.match(r"^sub\s*total\b", c0_low):
                continue
            if re.search(r"\btotal\b", c0_low) or re.match(r"^totals\b", c0_low):
                raw = row[paid_i].strip()
                norm = _money_cell_for_xml(raw)
                if norm is not None:
                    candidates.append(norm)
        if candidates:
            # First match in reverse row order = bottom-most total row on the grid.
            return candidates[0]
    return None


def fee_type_col(header: list[str]) -> int:
    for i, cell in enumerate(header):
        cl = _norm_header(cell)
        if cl == "sub category" or cl == "fee_type" or "fee_type" in cl.replace(" ", ""):
            return i
    return 0


def fee_main_col(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        if "main category" in _norm_header(cell):
            return i
    return None


def fee_amount_col(header: list[str]) -> int:
    for i, cell in enumerate(header):
        if "amount paid" in _norm_header(cell):
            return i
    return len(header) - 1


def fee_priority_col(header: list[str]) -> int | None:
    for i, cell in enumerate(header):
        if _norm_header(cell) == "priority":
            return i
    return None


def fee_data_rows(table: list[list[str]]) -> list[list[str]]:
    if len(table) < 2:
        return []
    header = table[0]
    tc = fee_type_col(header)
    out: list[list[str]] = []
    for row in table[1:]:
        if not row or not any(c.strip() for c in row):
            continue
        leaf = row[tc].strip().lower() if tc < len(row) else ""
        if leaf in ("sub category", "fee_type", "standard fee type"):
            continue
        out.append(row)
    return out


def default_out_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "xml"


def _apply_map_attrs(el: ET.Element, result: Any) -> None:
    if result.moodystrancheid:
        el.set("moodystrancheid", result.moodystrancheid)
    if result.map_tier:
        el.set("map_tier", result.map_tier)
    if result.map_status:
        el.set("map_status", result.map_status)
    if result.trustee_tranche_name:
        el.set("trustee_tranche_name", result.trustee_tranche_name)
    if result.map_message:
        el.set("map_message", result.map_message)


def build_xml(
    extraction_dir: Path,
    *,
    tranche_mapper: TrancheMapper | None = None,
    prefer_01_xml: bool = False,
) -> tuple[ET.Element, str]:
    """Returns (root element, output_basename_without_xml)."""
    from noteval_01_xml import read_metadata_for_export

    meta01 = read_metadata_for_export(extraction_dir, prefer_xml=prefer_01_xml)
    d02 = (extraction_dir / "02_tranche_class_balances.md").read_text(encoding="utf-8")
    p03 = extraction_dir / "03_interest_principal_waterfall.md"
    d03 = p03.read_text(encoding="utf-8") if p03.is_file() else ""
    p05 = extraction_dir / "05_valuation_relevant_fees.md"
    d05 = p05.read_text(encoding="utf-8") if p05.is_file() else ""

    t02 = parse_md_tables(d02)
    t03 = parse_md_tables(d03) if d03 else []

    folder_stem = extraction_dir.name
    deal_id = meta01.deal_id
    out_base = folder_stem if folder_stem else (
        f"{deal_id}_{to_yyyymmdd(meta01.key_dates.get('Payment date', '')) or 'unknown'}"
    )

    schema = "4" if tranche_mapper is not None else "3"
    root = ET.Element("noteval_export")
    root.set("schema_version", schema)
    root.set("source_folder", folder_stem)

    md = ET.SubElement(root, "metadata")
    if deal_id:
        ET.SubElement(md, "deal_id").text = deal_id
    ET.SubElement(md, "deal_name").text = meta01.deal_name or ""
    if meta01.report_title:
        ET.SubElement(md, "report_title").text = meta01.report_title
    if meta01.payment_iso:
        pe = ET.SubElement(md, "payment_date")
        pe.text = meta01.payment_iso
        pe.set("date_source", meta01.date_source)
        if meta01.date_mismatch_note:
            pe.set("date_mismatch_note", meta01.date_mismatch_note.strip("; "))
    elif meta01.payment_display:
        ET.SubElement(md, "payment_date").text = meta01.payment_display

    currency = meta01.currency or meta01.key_dates.get("Currency", "")
    for label, key in (
        ("determination_date", "Determination date"),
        ("record_date", "Record date (if stated)"),
        ("currency", "Currency"),
    ):
        v = meta01.key_dates.get(key, "")
        if not v and key == "Currency":
            v = currency
        if v and v.upper() != "N/A":
            ET.SubElement(md, label).text = v

    if meta01.trustee and meta01.trustee.upper() != "N/A":
        ET.SubElement(md, "trustee").text = meta01.trustee

    listing_table = find_listing_table(t02)
    listing_rows: list[dict[str, str]] = []
    if listing_table and len(listing_table) > 1:
        hdr = listing_table[0]
        idx = { _norm_header(c): i for i, c in enumerate(hdr) }
        def gi(row, *names):
            for n in names:
                i = idx.get(_norm_header(n))
                if i is not None and i < len(row):
                    return row[i].strip()
            return ""
        for row in listing_table[1:]:
            if not any(x.strip() for x in row):
                continue
            listing_rows.append({
                "economic_class": gi(row, "Economic class"),
                "isin": gi(row, "ISIN"),
                "cusip": gi(row, "CUSIP"),
            })

    by_class: dict[str, list[dict[str, str]]] = {}
    for lr in listing_rows:
        ec = lr.get("economic_class", "").strip()
        if ec:
            by_class.setdefault(ec, []).append(lr)

    cb = find_class_balance_table(t02)
    classes_el = ET.SubElement(root, "classes")
    if cb and len(cb) > 1:
        hdr = cb[0]
        ci = lambda name: _col_exact(hdr, name)
        iclass = ci("Class") or 0
        cols = {
            "original_balance": ci("Original balance"),
            "beginning_balance": ci("Beginning balance"),
            "interest_rate": ci("Interest rate"),
            "interest_payment": ci("Interest payment"),
            "interest_payable": ci("Interest payable"),
            "principal_payment": ci("Principal payment"),
            "principal_payable": ci("Principal payable"),
            "deferred_interest": ci("Deferred interest"),
            "dividend": ci("Dividend"),
            "ending_balance": ci("Ending balance"),
            "notes": ci("Notes"),
        }
        for row in cb[1:]:
            if len(row) <= iclass:
                continue
            cname = row[iclass].strip()
            if not cname or cname.lower().startswith("total"):
                continue
            ce = ET.SubElement(classes_el, "class")
            ce.set("name", cname)
            for tag, ix in cols.items():
                if ix is None or ix >= len(row):
                    continue
                val = row[ix].strip()
                if val and val.upper() != "N/A":
                    ET.SubElement(ce, tag).text = val

            kids = by_class.get(cname, [])
            if kids:
                idel = ET.SubElement(ce, "identifiers")
                kept = False
                for lr in kids:
                    isin = (lr.get("isin") or "").strip()
                    cusip = (lr.get("cusip") or "").strip()
                    if isin.upper() == "N/A":
                        isin = ""
                    if cusip.upper() == "N/A":
                        cusip = ""
                    if not isin and not cusip:
                        continue
                    kept = True
                    line = ET.SubElement(idel, "line")
                    if isin:
                        line.set("isin", isin)
                    if cusip:
                        line.set("cusip", cusip)
                    if tranche_mapper and deal_id:
                        _apply_map_attrs(
                            line,
                            tranche_mapper.resolve(
                                deal_id, cusip=cusip or None, class_name=cname
                            ),
                        )
                if not kept:
                    ce.remove(idel)

            if tranche_mapper and deal_id:
                all_cusips: list[str] = []
                for lr in kids:
                    c = (lr.get("cusip") or "").strip()
                    if c and c.upper() != "N/A" and c not in all_cusips:
                        all_cusips.append(c)
                _apply_map_attrs(
                    ce,
                    tranche_mapper.resolve(
                        deal_id,
                        cusips=all_cusips or None,
                        class_name=cname,
                    ),
                )

    vf = find_valuation_fees_table(parse_md_tables(d05)) if d05 else None
    if vf is None:
        vf = find_valuation_fees_table(t03)
    admin_grid_total = administrative_expenses_grid_total_from_tables(t03)

    fees_el = ET.SubElement(root, "valuation_fees")
    fee_rows_added = False
    if vf and len(vf) > 1:
        header = vf[0]
        tc = fee_type_col(header)
        mc = fee_main_col(header)
        ac = fee_amount_col(header)
        pc = fee_priority_col(header)
        for row in fee_data_rows(vf):
            fe = ET.SubElement(fees_el, "fee")
            fee_rows_added = True
            if mc is not None and mc < len(row) and row[mc].strip():
                fe.set("main_category", row[mc].strip())
            if tc < len(row):
                fe.set("sub_category", row[tc].strip())
            if pc is not None and pc < len(row) and row[pc].strip() and row[pc].strip() != "—":
                fe.set("priority", row[pc].strip())
            if ac < len(row):
                fe.set("amount_paid", row[ac].strip())
    if not fee_rows_added and not admin_grid_total:
        fees_el.set("empty", "true")
    if admin_grid_total:
        ET.SubElement(fees_el, "administrative_expenses_grid_total").text = admin_grid_total

    return root, out_base


def write_pretty_xml(root: ET.Element, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _has_deliverable_01(exdir: Path) -> bool:
    return (exdir / "01_report_metadata.xml").is_file() or (
        exdir / "01_report_metadata.md"
    ).is_file()


def main() -> int:
    _script_dir = Path(__file__).resolve().parent
    if str(_script_dir) not in sys.path:
        sys.path.insert(0, str(_script_dir))

    ap = argparse.ArgumentParser(description="Export noteval XML from markdown 01–03.")
    ap.add_argument("extraction_dir", type=Path, help="Folder with 01–03 deliverables")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help=f"Output directory (default: {default_out_dir()})",
    )
    ap.add_argument(
        "--map-tranches",
        action="store_true",
        help="Write 01_report_metadata.xml, map moodystrancheid (schema 4)",
    )
    ap.add_argument(
        "--tranche-cache",
        type=Path,
        help="JSON cache from map_tranches.py --prefetch",
    )
    ap.add_argument(
        "--no-tranche-db",
        action="store_true",
        help="With --map-tranches, use only --tranche-cache",
    )
    args = ap.parse_args()
    exdir = args.extraction_dir.resolve()
    if not exdir.is_dir():
        print(f"Not a directory: {exdir}", file=sys.stderr)
        return 1
    if not _has_deliverable_01(exdir):
        print(
            "Missing 01_report_metadata.md or 01_report_metadata.xml under "
            f"{exdir}",
            file=sys.stderr,
        )
        return 1
    if not (exdir / "02_tranche_class_balances.md").is_file():
        print(f"Missing required file 02_tranche_class_balances.md under {exdir}", file=sys.stderr)
        return 1
    if not (exdir / "03_interest_principal_waterfall.md").is_file():
        print(
            "Note: 03 missing — XML will include metadata and classes only (no waterfall fees).",
            file=sys.stderr,
        )

    prefer_01_xml = False
    mapper: TrancheMapper | None = None
    if args.map_tranches:
        from map_tranches import TrancheMapper
        from noteval_01_xml import ensure_01_xml_for_mapping

        path_01 = ensure_01_xml_for_mapping(exdir)
        prefer_01_xml = True
        print(path_01, file=sys.stderr)
        mapper = TrancheMapper(
            cache_file=args.tranche_cache.resolve() if args.tranche_cache else None,
            use_db=not args.no_tranche_db,
        )

    out_dir = (args.out_dir or default_out_dir()).resolve()
    root, base = build_xml(
        exdir, tranche_mapper=mapper, prefer_01_xml=prefer_01_xml
    )
    out_path = out_dir / f"{base}.xml"
    write_pretty_xml(root, out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
