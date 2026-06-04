"""
noteval_01_xml.py — Deliverable 01 as XML for DB / export pipelines.

When tranche mapping is enabled, metadata is written and read as
``01_report_metadata.xml`` instead of relying on markdown alone.

Combined export still uses ``export_noteval_xml.py``; this module owns the
standalone 01 artifact and shared metadata parsing.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

def _xml_parse_deps():
    from export_noteval_xml import _parse_tables_kv, parse_md_tables, to_iso_date, to_yyyymmdd

    return _parse_tables_kv, parse_md_tables, to_iso_date, to_yyyymmdd

FILENAME_MD = "01_report_metadata.md"
FILENAME_XML = "01_report_metadata.xml"
SCHEMA_VERSION = "1"


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
    _parse_tables_kv, parse_md_tables, to_iso_date, to_yyyymmdd = _xml_parse_deps()
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
    _, _, _, to_yyyymmdd = _xml_parse_deps()
    folder_date = parse_folder_deal_and_date(m.folder_stem)[1]
    ymd = to_yyyymmdd(m.key_dates.get("Payment date", "")) or to_yyyymmdd(
        m.key_dates.get("Distribution date", "")
    )
    if folder_date and ymd and folder_date != ymd:
        note = f"Folder suffix {folder_date} vs 01 date {ymd}"
        m.date_mismatch_note = (m.date_mismatch_note + "; " if m.date_mismatch_note else "") + note
    return m


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def metadata_from_xml_path(path: Path) -> Metadata01:
    root = ET.parse(path).getroot()
    if root.tag != "noteval_metadata":
        raise ValueError(f"Expected <noteval_metadata>, got <{root.tag}> in {path}")

    deal_id = _text(root.find("deal_id"))
    m = Metadata01(
        deal_id=deal_id,
        folder_stem=_text(root.find("folder_stem")),
        deal_name=_text(root.find("deal_name")),
        report_title=_text(root.find("report_title")),
        currency=_text(root.find("currency")),
        trustee=_text(root.find("trustee")),
    )
    pd = root.find("payment_date")
    if pd is not None:
        m.payment_iso = _text(pd)
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
    root.set("schema_version", SCHEMA_VERSION)
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
    out = exdir / FILENAME_XML
    if m is None:
        md = exdir / FILENAME_MD
        if not md.is_file():
            raise FileNotFoundError(f"Missing {FILENAME_MD} under {exdir}")
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
    xml_path = exdir / FILENAME_XML
    md_path = exdir / FILENAME_MD
    if prefer_xml and xml_path.is_file():
        return metadata_from_xml_path(xml_path)
    if md_path.is_file():
        return metadata_from_md_path(md_path, folder_stem=exdir.name)
    if xml_path.is_file():
        return metadata_from_xml_path(xml_path)
    raise FileNotFoundError(
        f"Missing {FILENAME_XML} and {FILENAME_MD} under {exdir}"
    )


def ensure_01_xml_for_mapping(extraction_dir: Path) -> Path:
    """Create or refresh ``01_report_metadata.xml`` from markdown when mapping."""
    exdir = extraction_dir.resolve()
    xml_path = exdir / FILENAME_XML
    md_path = exdir / FILENAME_MD
    if md_path.is_file():
        m = metadata_from_md_path(md_path, folder_stem=exdir.name)
        write_01_metadata_xml(exdir, m)
        return xml_path
    if xml_path.is_file():
        return xml_path
    raise FileNotFoundError(f"Need {FILENAME_MD} or {FILENAME_XML} under {exdir}")
