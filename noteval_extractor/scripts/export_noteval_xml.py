"""
export_noteval_xml.py — Build noteval_export.xml from markdown 01–03 per
noteval_extractor/references/xml-export.md (schema_version 3 or 4).

With ``--map-tranches``: writes ``01_report_metadata.xml``, resolves
``moodystrancheid`` on ``<class>`` / ``<line>``, sets ``schema_version="4"``.

Every ``<class>`` element gets a ``map_class`` attribute (compact EMS lookup key
from ``normalize_class_label``), on schema 3 and 4.

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
from dataclasses import dataclass, field
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


# --- Deliverable 01 metadata (markdown or standalone ``01_report_metadata.xml``) ---

FILENAME_01_MD = "01_report_metadata.md"
FILENAME_01_XML = "01_report_metadata.xml"
METADATA_01_SCHEMA_VERSION = "1"


@dataclass
class Metadata01:
    deal_id: str
    folder_stem: str
    deal_name: str = ""
    report_title: str = ""
    payment_iso: str = ""
    payment_display: str = ""
    date_source: str = "payment_date"
    date_mismatch_note: str = ""
    currency: str = ""
    trustee: str = ""
    key_dates: dict[str, str] = field(default_factory=dict)
    ident: dict[str, str] = field(default_factory=dict)
    extra_fields: dict[str, str] = field(default_factory=dict)


def parse_folder_deal_and_date(folder_name: str) -> tuple[str, str]:
    """Return (deal_id / moodysdealid, payment_date_yyyymmdd)."""
    stem = folder_name.strip()
    for suf in ("_sdk", "_llm"):
        if stem.endswith(suf):
            stem = stem[: -len(suf)]
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and len(parts[1]) == 8 and parts[1].isdigit():
        return parts[0], parts[1]
    return stem, ""


def _collect_kv_from_md_text(text: str) -> Metadata01:
    tables = parse_md_tables(text)
    kv = _parse_tables_kv(tables)
    ident: dict[str, str] = {}
    key_dates: dict[str, str] = {}
    routing: dict[str, str] = {}
    report_id: dict[str, str] = {}
    for d in kv:
        keys = " ".join(k.lower() for k in d)
        if "deal / trust" in keys or "series name" in keys:
            ident = d
        elif "payment date" in keys or "determination date" in keys:
            key_dates = d
        elif "currency" in keys and "isin" in keys:
            routing = d
        elif "report title" in keys:
            report_id = d
        else:
            for k, v in d.items():
                if k and v:
                    report_id.setdefault(k, v)

    deal_name = ""
    report_title = ""
    for d in (ident, report_id):
        for k, v in d.items():
            kl = k.lower()
            if "deal / trust" in kl or "series name" in kl:
                deal_name = v
            if "report title" in kl:
                report_title = v
    if not report_title and ident:
        report_title = ident.get("Report title (as printed)", "")

    pay_raw = key_dates.get("Payment date", "") or ""
    dist_raw = key_dates.get("Distribution date", "") or ""
    pay_iso = to_iso_date(pay_raw) or ""
    dist_iso = to_iso_date(dist_raw) or ""
    mismatch = ""
    if pay_iso and dist_iso and pay_iso != dist_iso:
        mismatch = f"Payment date {pay_raw!r} differs from Distribution date {dist_raw!r}"
    payment_display = pay_raw or dist_raw
    payment_iso = pay_iso or dist_iso or ""

    currency = routing.get("Currency", "") or key_dates.get("Currency", "")
    trustee = key_dates.get("Trustee / administrator name", "")
    if not trustee:
        for d in kv:
            for k, v in d.items():
                if "trustee" in k.lower() and "administrator" in k.lower():
                    trustee = v
                    break

    extra: dict[str, str] = {}
    for d in kv:
        for k, v in d.items():
            if not v or v.upper() == "N/A":
                continue
            kl = k.lower()
            if any(
                x in kl
                for x in (
                    "deal / trust",
                    "series name",
                    "report title",
                    "payment date",
                    "distribution date",
                    "determination date",
                    "record date",
                    "trustee",
                    "currency",
                    "isin",
                    "cusip",
                )
            ):
                continue
            extra[k] = v

    return Metadata01(
        deal_id="",
        folder_stem="",
        deal_name=deal_name,
        report_title=report_title,
        payment_iso=payment_iso,
        payment_display=payment_display,
        date_source="payment_date",
        date_mismatch_note=mismatch,
        currency=currency,
        trustee=trustee,
        key_dates=dict(key_dates),
        ident=dict(ident),
        extra_fields=extra,
    )


def metadata_from_md_path(path: Path, *, folder_stem: str = "") -> Metadata01:
    m = _collect_kv_from_md_text(path.read_text(encoding="utf-8", errors="replace"))
    m.folder_stem = folder_stem or path.parent.name
    m.deal_id, _ = parse_folder_deal_and_date(m.folder_stem)
    folder_date = parse_folder_deal_and_date(m.folder_stem)[1]
    ymd = to_yyyymmdd(m.key_dates.get("Payment date", "")) or to_yyyymmdd(
        m.key_dates.get("Distribution date", "")
    )
    if folder_date and ymd and folder_date != ymd:
        note = f"Folder suffix {folder_date} vs 01 date {ymd}"
        m.date_mismatch_note = (m.date_mismatch_note + "; " if m.date_mismatch_note else "") + note
    return m


def _metadata_text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def metadata_from_xml_path(path: Path) -> Metadata01:
    root = ET.parse(path).getroot()
    if root.tag != "noteval_metadata":
        raise ValueError(f"Expected <noteval_metadata>, got <{root.tag}> in {path}")

    deal_id = _metadata_text(root.find("deal_id"))
    m = Metadata01(
        deal_id=deal_id,
        folder_stem=_metadata_text(root.find("folder_stem")),
        deal_name=_metadata_text(root.find("deal_name")),
        report_title=_metadata_text(root.find("report_title")),
        currency=_metadata_text(root.find("currency")),
        trustee=_metadata_text(root.find("trustee")),
    )
    pd = root.find("payment_date")
    if pd is not None:
        m.payment_iso = _metadata_text(pd)
        m.payment_display = pd.get("display") or m.payment_iso
        m.date_source = pd.get("date_source") or "payment_date"
        m.date_mismatch_note = pd.get("date_mismatch_note") or ""

    kd = root.find("key_dates")
    if kd is not None:
        for child in kd:
            if child.tag and child.text:
                m.key_dates[child.tag] = child.text.strip()

    extras = root.find("extra_fields")
    if extras is not None:
        for child in extras:
            name = child.get("name") or child.tag
            if name and child.text:
                m.extra_fields[name] = child.text.strip()

    if not m.folder_stem:
        m.folder_stem = path.parent.name
    if not m.deal_id:
        m.deal_id, _ = parse_folder_deal_and_date(m.folder_stem)
    return m


def build_metadata_element(m: Metadata01) -> ET.Element:
    root = ET.Element("noteval_metadata")
    root.set("schema_version", METADATA_01_SCHEMA_VERSION)
    ET.SubElement(root, "deal_id").text = m.deal_id or ""
    if m.folder_stem:
        ET.SubElement(root, "folder_stem").text = m.folder_stem
    if m.deal_name:
        ET.SubElement(root, "deal_name").text = m.deal_name
    if m.report_title:
        ET.SubElement(root, "report_title").text = m.report_title
    if m.payment_iso or m.payment_display:
        pe = ET.SubElement(root, "payment_date")
        pe.text = m.payment_iso or m.payment_display
        if m.payment_display and m.payment_iso and m.payment_display != m.payment_iso:
            pe.set("display", m.payment_display)
        pe.set("date_source", m.date_source)
        if m.date_mismatch_note:
            pe.set("date_mismatch_note", m.date_mismatch_note.strip("; "))
    if m.currency and m.currency.upper() != "N/A":
        ET.SubElement(root, "currency").text = m.currency
    if m.trustee and m.trustee.upper() != "N/A":
        ET.SubElement(root, "trustee").text = m.trustee

    if m.key_dates:
        kd_el = ET.SubElement(root, "key_dates")
        for tag, label in (
            ("determination_date", "Determination date"),
            ("payment_date_raw", "Payment date"),
            ("distribution_date_raw", "Distribution date"),
            ("record_date", "Record date (if stated)"),
        ):
            v = m.key_dates.get(label, "")
            if v and v.upper() != "N/A":
                ET.SubElement(kd_el, tag).text = v
        for k, v in m.key_dates.items():
            if k in (
                "Determination date",
                "Payment date",
                "Distribution date",
                "Record date (if stated)",
            ):
                continue
            if v and v.upper() != "N/A":
                safe = re.sub(r"[^a-z0-9_]+", "_", k.lower()).strip("_") or "field"
                ET.SubElement(kd_el, safe).text = v

    if m.extra_fields:
        ex = ET.SubElement(root, "extra_fields")
        for name, val in sorted(m.extra_fields.items()):
            fe = ET.SubElement(ex, "field")
            fe.set("name", name)
            fe.text = val
    return root


def write_01_metadata_xml(extraction_dir: Path, m: Metadata01 | None = None) -> Path:
    """Write ``01_report_metadata.xml`` under the deal folder."""
    exdir = extraction_dir.resolve()
    out = exdir / FILENAME_01_XML
    if m is None:
        md = exdir / FILENAME_01_MD
        if not md.is_file():
            raise FileNotFoundError(f"Missing {FILENAME_01_MD} under {exdir}")
        m = metadata_from_md_path(md, folder_stem=exdir.name)
    tree = ET.ElementTree(build_metadata_element(m))
    ET.indent(tree, space="  ")
    tree.write(out, encoding="utf-8", xml_declaration=True)
    return out


def read_metadata_for_export(
    extraction_dir: Path,
    *,
    prefer_xml: bool = False,
) -> Metadata01:
    """
    Load deliverable 01 for combined XML export.

    When ``prefer_xml`` is True, use ``01_report_metadata.xml`` if present;
    otherwise fall back to markdown.
    """
    exdir = extraction_dir.resolve()
    xml_path = exdir / FILENAME_01_XML
    md_path = exdir / FILENAME_01_MD
    if prefer_xml and xml_path.is_file():
        return metadata_from_xml_path(xml_path)
    if md_path.is_file():
        return metadata_from_md_path(md_path, folder_stem=exdir.name)
    if xml_path.is_file():
        return metadata_from_xml_path(xml_path)
    raise FileNotFoundError(
        f"Missing {FILENAME_01_XML} and {FILENAME_01_MD} under {exdir}"
    )


def ensure_01_xml_for_mapping(extraction_dir: Path) -> Path:
    """Create or refresh ``01_report_metadata.xml`` from markdown when mapping."""
    exdir = extraction_dir.resolve()
    xml_path = exdir / FILENAME_01_XML
    md_path = exdir / FILENAME_01_MD
    if md_path.is_file():
        m = metadata_from_md_path(md_path, folder_stem=exdir.name)
        write_01_metadata_xml(exdir, m)
        return xml_path
    if xml_path.is_file():
        return xml_path
    raise FileNotFoundError(f"Need {FILENAME_01_MD} or {FILENAME_01_XML} under {exdir}")


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
    if getattr(result, "matched_cusip", None):
        el.set("map_cusip", result.matched_cusip)
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

    # Load pdfplumber structured data when available.
    # parse_pdfplumber_cusip_class → authoritative CUSIP→class (overrides markdown listing)
    # parse_pdfplumber_pdd_rows / parse_pdfplumber_idd_rows → per-CUSIP balance/rate/interest
    #   read directly from vector-geometry column cells (immune to nth-band positional errors)
    pdfplumber_cusip_class: dict[str, str] = {}
    pdfplumber_pdd: dict[str, dict[str, str]] = {}  # cusip.upper() → pdd row dict
    pdfplumber_idd: dict[str, dict[str, str]] = {}  # cusip.upper() → idd row dict
    structured_path = extraction_dir / "_chunks_structured" / "pdd_idd_pdfplumber.md"
    if structured_path.is_file():
        try:
            from pdfplumber_pdd_idd_md import (
                parse_pdfplumber_cusip_class,
                parse_pdfplumber_pdd_rows,
                parse_pdfplumber_idd_rows,
            )
            _structured_text = structured_path.read_text(encoding="utf-8")
            pdfplumber_cusip_class = parse_pdfplumber_cusip_class(_structured_text)
            for r in parse_pdfplumber_pdd_rows(_structured_text):
                pdfplumber_pdd[r["cusip"].upper()] = r
            for r in parse_pdfplumber_idd_rows(_structured_text):
                pdfplumber_idd[r["cusip"].upper()] = r
        except Exception:
            pass

    # Pre-collect primary class names so the pdfplumber override can be gated:
    # only override when the pdfplumber-assigned class actually exists in the primary
    # table (prevents phantom class names from pdfplumber truncation — e.g. "B" when
    # the deal only has "B-R" — from silently re-routing CUSIPs to non-existent classes).
    _cb_pre = find_class_balance_table(t02)
    _primary_classes: set[str] = set()
    if _cb_pre and len(_cb_pre) > 1:
        _ci_pre = lambda name: _col_exact(_cb_pre[0], name)
        _icls_pre = _ci_pre("Class") or 0
        for _r in _cb_pre[1:]:
            if len(_r) > _icls_pre:
                _cn = _r[_icls_pre].strip()
                if _cn and not _cn.lower().startswith("total"):
                    _primary_classes.add(_cn)

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
            md_class = gi(row, "Economic class")
            cusip_raw = gi(row, "CUSIP")
            # If pdfplumber says this CUSIP belongs to a different class than the
            # markdown listing, trust pdfplumber ONLY when:
            #   (a) the markdown listing class is empty/blank (CUSIP is orphaned), OR
            #   (b) the pdfplumber class exists in the primary table AND the markdown
            #       class does NOT exist in the primary table (pdfplumber is correcting
            #       a bad markdown assignment to a phantom class).
            # Do NOT override when the markdown already has a valid primary-class
            # assignment — the analyst listing is more reliable than the pdfplumber
            # parser's col0-glue heuristics (which can misread truncated "-R" suffixes).
            override_note = ""
            if pdfplumber_cusip_class and cusip_raw:
                pb_class = pdfplumber_cusip_class.get(cusip_raw.upper())
                if pb_class and pb_class != md_class:
                    md_in_primary = not _primary_classes or md_class in _primary_classes
                    pb_in_primary = not _primary_classes or pb_class in _primary_classes
                    apply_override = (
                        # Only override when: markdown has a non-blank class that doesn't
                        # exist in the primary table (phantom class), AND pdfplumber's
                        # class does exist in the primary table.
                        # Blank md_class = intentional orphan — do NOT route to any class.
                        bool(md_class)
                        and pb_in_primary
                        and not md_in_primary
                    )
                    if apply_override:
                        override_note = (
                            f"pdfplumber override: {cusip_raw} → {pb_class} "
                            f"(markdown had {md_class!r})"
                        )
                        md_class = pb_class
            cusip_key = cusip_raw.upper() if cusip_raw else ""
            pb_pdd = pdfplumber_pdd.get(cusip_key, {})
            pb_idd = pdfplumber_idd.get(cusip_key, {})
            # Use pdfplumber column values when present (direct column read beats
            # nth-band inference from linearised text).
            def _pb_or_md(pb_val: str, md_field: str) -> str:
                if pb_val:
                    return pb_val
                return gi(row, md_field)
            lr: dict[str, str] = {
                "economic_class": md_class,
                "isin": gi(row, "ISIN"),
                "cusip": cusip_raw,
                "original_balance": _pb_or_md(pb_pdd.get("original_face", ""), "Original balance"),
                "beginning_balance": _pb_or_md(pb_pdd.get("beginning_balance", ""), "Beginning balance"),
                "interest_rate": _pb_or_md(pb_idd.get("coupon_rate", ""), "Interest rate"),
                "interest_payment": _pb_or_md(pb_idd.get("interest_distribution", ""), "Interest payment"),
                "principal_payment": _pb_or_md(pb_pdd.get("principal_distribution", ""), "Principal payment"),
                "deferred_interest": _pb_or_md(pb_pdd.get("deferred_interest", ""), "Deferred interest"),
                "ending_balance": _pb_or_md(pb_pdd.get("ending_balance", ""), "Ending balance"),
            }
            if override_note:
                lr["_pdfplumber_override"] = override_note
            listing_rows.append(lr)

    by_class: dict[str, list[dict[str, str]]] = {}
    for lr in listing_rows:
        ec = lr.get("economic_class", "").strip()
        if ec:
            by_class.setdefault(ec, []).append(lr)

    from map_tranches import normalize_class_label

    cb = find_class_balance_table(t02)
    classes_el = ET.SubElement(root, "classes")
    primary_class_names: list[str] = []
    deal_maps = (
        tranche_mapper.maps_for_deal(deal_id)
        if tranche_mapper and deal_id
        else None
    )
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
            primary_class_names.append(cname)
        for row in cb[1:]:
            if len(row) <= iclass:
                continue
            cname = row[iclass].strip()
            if not cname or cname.lower().startswith("total"):
                continue
            ce = ET.SubElement(classes_el, "class")
            ce.set("name", cname)
            map_class = normalize_class_label(
                cname,
                deal_maps=deal_maps,
                peer_class_names=primary_class_names,
                deal_name=meta01.deal_name or None,
            )
            if map_class:
                ce.set("map_class", map_class)
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
                if not kept:
                    ce.remove(idel)

            if tranche_mapper and deal_id:
                listing_cusips: list[str] = []
                for lr in kids:
                    c = (lr.get("cusip") or "").strip()
                    if c and c.upper() != "N/A" and c not in listing_cusips:
                        listing_cusips.append(c)
                _apply_map_attrs(
                    ce,
                    tranche_mapper.resolve(
                        deal_id,
                        cusips=listing_cusips or None,
                        class_name=cname,
                        map_class=map_class or None,
                        peer_class_names=primary_class_names,
                        deal_name=meta01.deal_name or None,
                    ),
                )

    # ── moodystrancheid uniqueness conflict check ───────────────────────────────
    # When two or more <class> elements share the same moodystrancheid it means
    # one CUSIP was assigned to the wrong economic class in the listing table.
    # Emit a <mapping_conflicts> block so the issue is visible in the XML and
    # print a warning to stderr.
    if tranche_mapper:
        tid_to_classes: dict[str, list[str]] = {}
        for ce in classes_el:
            tid = ce.get("moodystrancheid", "")
            if tid:
                tid_to_classes.setdefault(tid, []).append(ce.get("name", "?"))
        conflicts = {
            tid: names
            for tid, names in tid_to_classes.items()
            if len(names) > 1
        }
        if conflicts:
            mc_el = ET.SubElement(root, "mapping_conflicts")
            mc_el.set("count", str(len(conflicts)))
            for tid, names in sorted(conflicts.items()):
                conf = ET.SubElement(mc_el, "conflict")
                conf.set("moodystrancheid", tid)
                conf.set("classes", ", ".join(names))
                conf.set(
                    "message",
                    f"moodystrancheid {tid} shared by {len(names)} classes: "
                    + ", ".join(names)
                    + " — check CUSIP→class assignment in listing table "
                    + "(pdfplumber_pdd_idd_md.py may have corrected some; "
                    + "verify remaining conflicts manually)",
                )
            import sys as _sys
            for tid, names in sorted(conflicts.items()):
                print(
                    f"WARNING mapping conflict: moodystrancheid {tid} "
                    f"shared by {', '.join(names)} — verify CUSIP→class in 02 listing",
                    file=_sys.stderr,
                )
    # ── end conflict check ──────────────────────────────────────────────────────

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
    return (exdir / FILENAME_01_XML).is_file() or (exdir / FILENAME_01_MD).is_file()


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
