#!/usr/bin/env python3
# py -3 -m pip install pyodbc pandas python-dotenv
"""
Query ARD for trustee PDF paths and write deal_paths.csv for batch segmentation / testing.

Uses the same .env pattern as get_filepaths_from_db: DB_SERVER, DB_DATABASE, DB_USERNAME,
DB_PASSWORD; optional SQL_ODBC_DRIVER, NOTEVAL_ARD_BASE_PATH (UNC root for relative filepath).

Examples (from repo root):
  py -3 noteval_extractor/scripts/get_file_path.py -o noteval_extractor/test/deal_paths.csv
  py -3 noteval_extractor/scripts/get_file_path.py --requests noteval_extractor/test/requests.csv -o noteval_extractor/test/deal_paths.csv
  py -3 noteval_extractor/scripts/get_file_path.py --deal-id 825275100 --payment-date 3/16/2026 -o deal_paths.csv

If you omit --requests and --deal-id/--payment-date, the script uses
``noteval_extractor/test/requests.csv`` when that file exists (same as
``…\\noteval_extractor\\test\\requests.csv`` under the repo).

Then run ``batch_segment.py`` to segment ``pdf_path`` (and optional
``waterfall_path`` for Wells Fargo) into ``noteval_extractor/output/<deal_id>_YYYYMMDD/``
when ``deal_id`` and ``payment_date`` are present in ``deal_paths.csv``; otherwise
``output/<pdf-stem>/``.

requests.csv must include columns deal_id and payment_date (extra columns ignored).
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path, PureWindowsPath

import pandas as pd
import pyodbc
from dotenv import load_dotenv

# Default UNC root for relative filepath from SQL (override with NOTEVAL_ARD_BASE_PATH).
_DEFAULT_BASE_PATH = r"\\amznfsxzygudex4.analytics.moodys.net\sdpprod\ard\temp"

# One row per (deal_id, payment_date): same shape as read_noteval_deutsche/scripts/get_filepaths_from_db.py
_DEFAULT_DEAL_QUERY = """
select r.deal_id, r.trustee, ad.deal_name, r.payment_date, r.report_type, filepath
from ard.dbo.ard_reports r
left join ard.[dbo].[ard_deals] ad
on ad.deal_id = r.deal_id
where 
r.sent = '0' and  ad.send_dm = 1 and
( ( r.report_format = 'PDF' and r.report_type like 'Quarterly%' )
or (r.report_format = 'PDF' and r.report_type like 'Note%' )
or (r.report_format = 'PDF' and r.report_type like '%Waterfall%'  )
or (r.report_format = 'PDF' and r.report_type like '%payment%') 
or (
(trustee_file_name like '%Quarterly%' or trustee_file_name like '%Note%' or trustee_file_name like '%waterfall%' or trustee_file_name like '%payment%') 
and  trustee_file_name not like '%notice%' and r.trustee = 'CDOMonitoring') 
)
and r.report_type not like '%notice%' and r.report_type <> 'Noteholder Updates'
and r.payment_date is not null
and r.payment_date <= GETDATE()
AND r.deal_id = ?
AND CAST(r.payment_date AS DATE) = CAST(? AS DATE)
"""


def ard_base_path() -> str:
    return os.environ.get("NOTEVAL_ARD_BASE_PATH", _DEFAULT_BASE_PATH).strip() or _DEFAULT_BASE_PATH


def deal_query_sql() -> str:
    path = os.environ.get("NOTEVAL_DEAL_QUERY_FILE", "").strip()
    if path:
        p = Path(path)
        if not p.is_file():
            raise SystemExit(f"NOTEVAL_DEAL_QUERY_FILE is not a file: {p}")
        return p.read_text(encoding="utf-8")
    return _DEFAULT_DEAL_QUERY


def _real_file_path(relative: object, base: str) -> str:
    if relative is None or (isinstance(relative, float) and pd.isna(relative)):
        return ""
    s = str(relative).strip()
    if not s or s.lower() == "nan":
        return ""
    if s.startswith("\\\\") or (len(s) > 1 and s[1] == ":"):
        return str(PureWindowsPath(s))
    rel = s.lstrip("/\\").replace("/", "\\")
    return str(PureWindowsPath(base) / rel)


def _parse_payment_date(user_value: str) -> str:
    s = str(user_value).strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    raise SystemExit(
        f"Could not parse payment date {user_value!r}. Use e.g. 3/16/2026 or 2026-03-16."
    )


def _load_env() -> tuple[str, str, str, str]:
    here = Path(__file__).resolve().parent
    load_dotenv(here / ".env")
    load_dotenv(here.parent / ".env")
    load_dotenv(here.parents[1] / ".env")
    if getattr(sys, "frozen", False):
        load_dotenv(Path(sys.executable).resolve().parent / ".env")
    server = os.environ.get("DB_SERVER", "").strip()
    database = os.environ.get("DB_DATABASE", "").strip()
    username = os.environ.get("DB_USERNAME", "").strip()
    password = os.environ.get("DB_PASSWORD", "").strip()
    if not all([server, database, username, password]):
        print(
            "ERROR: Set DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD in .env "
            "(noteval_extractor/scripts/, noteval_extractor/, or repo root).",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return server, database, username, password


def _connect(server: str, database: str, username: str, password: str) -> pyodbc.Connection:
    preferred = os.environ.get("SQL_ODBC_DRIVER", "").strip()
    drivers = [d for d in [preferred] if d]
    drivers.extend(
        [
            "ODBC Driver 18 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "SQL Server",
        ]
    )
    seen: set[str] = set()
    drivers = [d for d in drivers if not (d in seen or seen.add(d))]

    last: Exception | None = None
    for drv in drivers:
        conn_str = (
            f"DRIVER={{{drv}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={username};"
            f"PWD={password};"
            "Encrypt=yes;"
            "TrustServerCertificate=yes;"
        )
        try:
            return pyodbc.connect(conn_str, timeout=30)
        except Exception as e:
            last = e
            continue
    raise RuntimeError(
        f"Could not connect with any ODBC driver ({drivers}). "
        f"Install 'ODBC Driver 17/18 for SQL Server'. Last error: {last}"
    ) from last


def _resolve_column(df: pd.DataFrame, logical_name: str) -> str | None:
    for c in df.columns:
        if str(c).strip().lower() == logical_name.lower():
            return str(c)
    return None


def fetch_deal_report_rows(deal_id: str, payment_date_user: str) -> pd.DataFrame:
    deal_id_clean = str(deal_id).strip()
    pay_iso = _parse_payment_date(payment_date_user)
    base = ard_base_path()
    server, database, username, password = _load_env()
    conn = _connect(server, database, username, password)
    try:
        df = pd.read_sql_query(deal_query_sql(), conn, params=[deal_id_clean, pay_iso])
    finally:
        conn.close()
    if df.empty:
        return df
    fp_col = _resolve_column(df, "filepath")
    if not fp_col:
        raise SystemExit(
            "No filepath column in SQL result. Columns: " + ", ".join(map(str, df.columns))
        )
    out = df.copy()
    out["pdf_path"] = out[fp_col].apply(lambda x: _real_file_path(x, base))
    return out


def _filtered_pdf_rows(df: pd.DataFrame) -> tuple[pd.DataFrame | None, str | None]:
    """Rows with non-empty resolved path and PDF format (if ``report_format`` exists)."""
    rfp = _resolve_column(df, "pdf_path")
    if not rfp:
        return None, "missing pdf_path column"
    nonempty = df[df[rfp].fillna("").astype(str).str.strip() != ""]
    if nonempty.empty:
        return None, "all paths empty"
    fmt_col = _resolve_column(df, "report_format")
    if not fmt_col:
        return nonempty, None
    is_pdf = (
        nonempty[fmt_col]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.casefold()
        == "pdf"
    )
    pdf_rows = nonempty[is_pdf]
    if pdf_rows.empty:
        return None, "no row with report_format PDF and non-empty path"
    return pdf_rows, None


def pick_primary_and_waterfall_paths(df: pd.DataFrame) -> tuple[str | None, str | None, str]:
    """
    ``pdf_path``: prefer Note Valuation-style ``report_type``; else first non-waterfall
    PDF row; else first PDF row.

    ``waterfall_path``: first PDF row whose ``report_type`` contains ``waterfall``
    (e.g. Wells Fargo Waterfall Calculations Report). Empty when none.

    Returns ``(pdf_path, waterfall_path, message)``.
    """
    rfp = _resolve_column(df, "pdf_path")
    if not rfp:
        return None, None, "missing pdf_path column"
    pdf_rows, err = _filtered_pdf_rows(df)
    if pdf_rows is None:
        return None, None, err or "unknown"
    rt_col = _resolve_column(df, "report_type")
    lowered = (
        pdf_rows[rt_col].fillna("").astype(str).str.strip().str.casefold()
        if rt_col
        else pd.Series([""] * len(pdf_rows), index=pdf_rows.index)
    )

    wf_mask = lowered.str.contains("waterfall", na=False)
    waterfall_path: str | None = None
    if wf_mask.any():
        p = str(pdf_rows[wf_mask].iloc[0][rfp]).strip()
        waterfall_path = p or None

    nv_mask = lowered.str.contains("note", na=False) & lowered.str.contains(
        "valuation", na=False
    )
    pdf_path: str | None = None
    if nv_mask.any():
        pdf_path = str(pdf_rows[nv_mask].iloc[0][rfp]).strip() or None

    if not pdf_path:
        if wf_mask.any() and (~wf_mask).any():
            pdf_path = str(pdf_rows[~wf_mask].iloc[0][rfp]).strip() or None
        if not pdf_path:
            pdf_path = str(pdf_rows.iloc[0][rfp]).strip() or None

    if waterfall_path and pdf_path and waterfall_path == pdf_path:
        waterfall_path = None

    return pdf_path, waterfall_path, "ok"


def build_deal_path_row(df: pd.DataFrame, deal_id: str, payment_date_raw: str) -> dict[str, str]:
    pay_iso = _parse_payment_date(payment_date_raw)
    row: dict[str, str] = {
        "deal_id": str(deal_id).strip(),
        "payment_date": pay_iso,
        "deal_name": "",
        "trustee": "",
        "report_type": "",
        "pdf_path": "",
        "waterfall_path": "",
        "status": "",
    }
    if df.empty:
        row["status"] = "no_sql_rows"
        return row
    dname = _resolve_column(df, "deal_name")
    tr = _resolve_column(df, "trustee")
    rt = _resolve_column(df, "report_type")
    if dname and pd.notna(df.iloc[0][dname]):
        row["deal_name"] = str(df.iloc[0][dname]).strip()
    if tr and pd.notna(df.iloc[0][tr]):
        row["trustee"] = str(df.iloc[0][tr]).strip()
    if rt and pd.notna(df.iloc[0][rt]):
        row["report_type"] = str(df.iloc[0][rt]).strip()
    path, wf_path, msg = pick_primary_and_waterfall_paths(df)
    if path:
        row["pdf_path"] = path
        row["waterfall_path"] = wf_path or ""
        row["status"] = "ok"
    else:
        row["status"] = msg
    return row


def default_requests_csv_path() -> Path:
    """``noteval_extractor/test/requests.csv`` next to this script's package."""
    return Path(__file__).resolve().parent.parent / "test" / "requests.csv"


def read_requests_csv(path: Path) -> pd.DataFrame:
    req = pd.read_csv(path)
    colmap = {str(c).strip().lower(): c for c in req.columns}
    for need in ("deal_id", "payment_date"):
        if need not in colmap:
            raise SystemExit(
                f"{path}: missing required column {need!r} (case-insensitive). "
                f"Found: {list(req.columns)}"
            )
    out = pd.DataFrame(
        {
            "deal_id": req[colmap["deal_id"]].astype(str).str.strip(),
            "payment_date": req[colmap["payment_date"]].astype(str).str.strip(),
        }
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Query ARD and write deal_paths.csv (deal_id, payment_date, pdf_path, …)."
    )
    parser.add_argument(
        "--deal-id",
        help="Single deal id (use with --payment-date).",
    )
    parser.add_argument(
        "--payment-date",
        help="Single payment date, e.g. 3/16/2026 or 2026-03-16.",
    )
    parser.add_argument(
        "--requests",
        type=Path,
        metavar="CSV",
        default=None,
        help=(
            "CSV with columns deal_id, payment_date (one pair per row). "
            "If omitted, uses noteval_extractor/test/requests.csv when that file exists."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("deal_paths.csv"),
        help="Output CSV path (default: deal_paths.csv in cwd).",
    )
    args = parser.parse_args()

    requests_path = args.requests
    if (
        requests_path is None
        and not (args.deal_id and args.payment_date)
    ):
        auto = default_requests_csv_path()
        if auto.is_file():
            requests_path = auto
            print(f"Using default requests file: {auto}", file=sys.stderr, flush=True)

    if requests_path:
        pairs = read_requests_csv(requests_path.resolve())
    elif args.deal_id and args.payment_date:
        pairs = pd.DataFrame(
            [{"deal_id": str(args.deal_id).strip(), "payment_date": str(args.payment_date).strip()}]
        )
    else:
        parser.error(
            "Provide (--deal-id and --payment-date), or --requests CSV, or create "
            f"{default_requests_csv_path()}"
        )

    base = ard_base_path()
    print(f"ARD base path: {base}", file=sys.stderr, flush=True)
    server, database, username, password = _load_env()
    print(f"Connecting to {server} / {database} …", file=sys.stderr, flush=True)

    rows_out: list[dict[str, str]] = []
    for _, r in pairs.iterrows():
        did, pdt = r["deal_id"], r["payment_date"]
        print(f"  Query deal_id={did!r} payment_date={pdt!r}", file=sys.stderr, flush=True)
        df = fetch_deal_report_rows(did, pdt)
        rows_out.append(build_deal_path_row(df, did, pdt))

    out_df = pd.DataFrame(rows_out)
    # Stable column order for downstream batch tools
    cols = [
        "deal_id",
        "payment_date",
        "deal_name",
        "trustee",
        "report_type",
        "pdf_path",
        "waterfall_path",
        "status",
    ]
    out_df = out_df[[c for c in cols if c in out_df.columns]]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(args.output.resolve(), index=False)
    print(f"Wrote {args.output.resolve()} ({len(out_df)} row(s))", file=sys.stderr, flush=True)
    ok = (out_df["status"] == "ok").sum() if "status" in out_df.columns else 0
    if ok < len(out_df):
        print(
            f"WARNING: {len(out_df) - ok} row(s) without a usable pdf_path; check status column.",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    main()
