"""
map_tranches.py — Resolve moodystrancheid for noteval class rows.

Tier 1 (CUSIP present): agent CUSIP → [CDOnet_DL].CUSTOM_CDONET_TRANCHE_DATA
        .MOODYSTRANCHEID (fallback MOODY_TRANCHE_ID), scoped by moodysdealid via
        CUSTOM_CDONET_DEAL_DATA2. CUSIP columns: CUSIP, CUSIP2 … CUSIP9.
        When a class has multiple CUSIPs, **one** match is enough. No name fallback.

Tier 2 (no CUSIP): deal_id + normalized XML class name ↔
        ems.dbo.noteval_tranche_mapping.trustee_tranche_name → .tranche_id
        (populates moodystrancheid).

Environment (optional SQL Server via pyodbc)::

  NOTEVAL_ODBC_CONNECTION   — full ODBC connection string (preferred)
  DB_SERVER, DB_DATABASE, DB_USERNAME, DB_PASSWORD — fallback (same as get_file_path.py)
  NOTEVAL_CDONET_DATABASE   — default CDOnet_DL
  NOTEVAL_EMS_DATABASE      — default ems

Offline cache JSON (--cache-file) keyed by deal_id::

  {
    "824237876": {
      "cusip_index": {"123456789": "824237877"},
      "name_index": [["A1", "824237877"], ["A1R", "825368707"]]
    }
  }

Usage::

  py -3 noteval_extractor/scripts/map_tranches.py --deal-id 824237876 --class-name "Class A-1-R3"
  py -3 noteval_extractor/scripts/map_tranches.py --deal-id 824237876 --cusip 123456789
  py -3 noteval_extractor/scripts/map_tranches.py --prefetch 824237876 -o tranche_cache.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_CUSIP_COLS = ("CUSIP", "CUSIP2", "CUSIP3", "CUSIP4", "CUSIP5", "CUSIP6", "CUSIP7", "CUSIP8", "CUSIP9")

_TIER1_BULK_SQL = """
SELECT COALESCE(
         NULLIF(LTRIM(RTRIM(CAST(t.MOODYSTRANCHEID AS varchar(50)))), ''),
         NULLIF(LTRIM(RTRIM(CAST(t.MOODY_TRANCHE_ID AS varchar(50)))), ''),
         NULLIF(LTRIM(RTRIM(CAST(t.trancheid AS varchar(50)))), '')
       ) AS moodystrancheid,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP , '')))) AS c0,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP2, '')))) AS c1,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP3, '')))) AS c2,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP4, '')))) AS c3,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP5, '')))) AS c4,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP6, '')))) AS c5,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP7, '')))) AS c6,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP8, '')))) AS c7,
       UPPER(LTRIM(RTRIM(ISNULL(t.CUSIP9, '')))) AS c8
FROM [{cdonet_db}].[dbo].[CUSTOM_CDONET_DEAL_DATA2] d
INNER JOIN [{cdonet_db}].[dbo].[CUSTOM_CDONET_TRANCHE_DATA] t
  ON t.dealid = d.dealid
WHERE d.moodysdealid = ?
"""

_TIER2_SQL = """
SELECT trustee_tranche_name, tranche_id
FROM [{ems_db}].[dbo].[noteval_tranche_mapping]
WHERE deal_id = ?
"""


@dataclass(frozen=True)
class MapResult:
    moodystrancheid: str | None
    map_tier: str | None
    map_status: str
    trustee_tranche_name: str | None = None
    map_message: str | None = None


@dataclass
class DealTrancheMaps:
    """In-memory indexes for one deal (moodysdealid / deal_id)."""

    deal_id: str
    cusip_index: dict[str, set[str]]
    name_index: list[tuple[str, str]]

    def to_cache_dict(self) -> dict[str, Any]:
        cusip: dict[str, str] = {}
        ambiguous_cusips: list[str] = []
        for c, ids in self.cusip_index.items():
            if len(ids) == 1:
                cusip[c] = next(iter(ids))
            elif len(ids) > 1:
                ambiguous_cusips.append(c)
        return {
            "cusip_index": cusip,
            "ambiguous_cusips": ambiguous_cusips,
            "name_index": [[n, tid] for n, tid in self.name_index],
        }

    @classmethod
    def from_cache_dict(cls, deal_id: str, data: dict[str, Any]) -> DealTrancheMaps:
        cusip_index: dict[str, set[str]] = {}
        raw = data.get("cusip_index") or {}
        for c, tid in raw.items():
            nc = normalize_cusip(str(c))
            if nc and tid:
                cusip_index.setdefault(nc, set()).add(str(tid).strip())
        for c in data.get("ambiguous_cusips") or []:
            nc = normalize_cusip(str(c))
            if nc and nc not in cusip_index:
                cusip_index[nc] = set()
        name_index = [
            (str(n).strip(), str(tid).strip())
            for n, tid in (data.get("name_index") or [])
            if n and tid
        ]
        name_index.sort(key=lambda x: len(x[0]), reverse=True)
        return cls(deal_id=deal_id, cusip_index=cusip_index, name_index=name_index)


def normalize_cusip(cusip: str | None) -> str | None:
    if not cusip:
        return None
    s = re.sub(r"[\s\-]", "", cusip.strip()).upper()
    if not s or s == "N/A":
        return None
    if re.fullmatch(r"[0-9A-Z]{9}", s):
        return s
    return None


_CLASS_NAME_PREFIXES = (
    "CLASS ",
    "CLASSES ",
    "NOTE CLASS ",
    "NOTES CLASS ",
    "NOTE ",
    "NOTES ",
    "HOLDERS OF THE ",
    "THE ",
    "TRANCHE ",
)

# Leading token only — not a tranche id (use full-label fallback instead).
_DESCRIPTOR_TOKENS = frozenset(
    {
        "SENIOR",
        "MEZZANINE",
        "JUNIOR",
        "SUBORDINATED",
        "PREFERRED",
        "PREFERENCE",
        "SECURED",
        "UNSECURED",
        "DEFERRABLE",
        "DEFERRED",
        "FLOATING",
        "FIXED",
    }
)

_CLASS_ALIASES = {
    "SUBORDINATEDNOTES": "SUB",
    "SUBORDINATEDNOTE": "SUB",
    "SUBNOTES": "SUB",
    "PREFERENCESHARE": "PREF",
    "PREFERENCESHARES": "PREF",
    "PREFERREDSTOCK": "PREF",
}

# Trustee: "A-1-R", "D-R", "B-R" … EMS noteval_tranche_mapping: "A1R", "DR", "BR".
_TRANCHE_LEAD_TOKEN = re.compile(r"^([A-Z0-9]+(?:[-/][A-Z0-9]+)*)\b")


def normalize_trustee_name_key(trustee_tranche_name: str) -> str:
    """Compact EMS / trustee tranche name (hyphens and punctuation removed)."""
    return re.sub(r"[^A-Z0-9]", "", trustee_tranche_name.strip().upper())


def normalize_class_label(class_name: str | None) -> str:
    """
    Compact token for matching noteval_tranche_mapping.trustee_tranche_name.

    Strips trustee prefixes ("Class ", …), takes the leading tranche token
    (e.g. ``D-R`` → ``DR``, ``A-1-R`` → ``A1R``) before descriptive suffixes
    ("Senior Secured Floating Rate Notes", …), then removes remaining punctuation.
    """
    if not class_name:
        return ""
    s = class_name.strip().upper()
    for prefix in _CLASS_NAME_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
    lead = _TRANCHE_LEAD_TOKEN.match(s)
    if lead:
        token = lead.group(1)
        if token not in _DESCRIPTOR_TOKENS:
            core = normalize_trustee_name_key(token)
            if core:
                return _CLASS_ALIASES.get(core, core)
    compact = normalize_trustee_name_key(s)
    return _CLASS_ALIASES.get(compact, compact)


def _prefix_key_boundary_ok(normalized: str, key: str) -> bool:
    """Avoid treating ``A1`` as a prefix of ``A10``."""
    if not key or not normalized.startswith(key):
        return False
    if len(normalized) == len(key):
        return True
    nxt = normalized[len(key)]
    return not (key[-1].isdigit() and nxt.isdigit())


def match_trustee_tranche_name(
    normalized: str, name_index: list[tuple[str, str]]
) -> tuple[str | None, str | None, str, str | None]:
    """
    Return (moodystrancheid, trustee_tranche_name, status, message).
    name_index: (trustee_tranche_name, tranche_id) from noteval_tranche_mapping.
    """
    if not normalized:
        return None, None, "unmapped", "no class name to match"
    if not name_index:
        return None, None, "unmapped", "no trustee_tranche_name rows for deal"

    exact: list[tuple[str, str]] = []
    prefix: list[tuple[str, str]] = []
    suffix: list[tuple[str, str]] = []
    for tname, tid in name_index:
        key = normalize_trustee_name_key(tname)
        if not key:
            continue
        if normalized == key:
            exact.append((tname, tid))
        elif _prefix_key_boundary_ok(normalized, key):
            prefix.append((tname, tid))
        elif normalized.endswith(key):
            suffix.append((tname, tid))

    if len(exact) == 1:
        return exact[0][1], exact[0][0], "ok", None
    if len(exact) > 1:
        ids = {tid for _, tid in exact}
        if len(ids) == 1:
            return exact[0][1], exact[0][0], "ok", "multiple names, same tranche_id"
        return None, None, "ambiguous", f"exact name collision: {exact!r}"

    if len(prefix) == 1:
        return prefix[0][1], prefix[0][0], "ok", None
    if len(prefix) > 1:
        ids = {tid for _, tid in prefix}
        if len(ids) == 1:
            return prefix[0][1], prefix[0][0], "ok", "multiple prefix matches, same tranche_id"
        names = [n for n, _ in prefix]
        return (
            None,
            None,
            "ambiguous",
            f"prefix matches: {names!r} for normalized={normalized!r}",
        )

    if len(suffix) == 1:
        return suffix[0][1], suffix[0][0], "ok", None
    if len(suffix) > 1:
        ids = {tid for _, tid in suffix}
        if len(ids) == 1:
            return suffix[0][1], suffix[0][0], "ok", "multiple suffix matches, same tranche_id"
        names = [n for n, _ in suffix]
        return (
            None,
            None,
            "ambiguous",
            f"suffix matches: {names!r} for normalized={normalized!r}",
        )

    return None, None, "unmapped", f"no trustee_tranche_name match for {normalized!r}"


def resolve_tranche(
    maps: DealTrancheMaps,
    *,
    cusip: str | None = None,
    cusips: list[str] | None = None,
    class_name: str | None = None,
) -> MapResult:
    """Tier 1 (CDOnet CUSIP) when any CUSIP present; tier 2 (EMS name map) when not."""
    candidates: list[str] = []
    for raw in cusips or ([] if cusip is None else [cusip]):
        nc = normalize_cusip(raw)
        if nc and nc not in candidates:
            candidates.append(nc)

    if candidates:
        matched_id: str | None = None
        matched_cusip: str | None = None
        ambiguous_notes: list[str] = []
        for nc in candidates:
            ids = maps.cusip_index.get(nc, set())
            if len(ids) == 1:
                tid = next(iter(ids))
                if matched_id is None:
                    matched_id = tid
                    matched_cusip = nc
                elif matched_id != tid:
                    return MapResult(
                        moodystrancheid=None,
                        map_tier="cusip",
                        map_status="ambiguous",
                        map_message=(
                            f"cusips matched different moodystrancheids: "
                            f"{matched_cusip}→{matched_id}, {nc}→{tid}"
                        ),
                    )
            elif len(ids) > 1:
                ambiguous_notes.append(f"cusip {nc} ambiguous in CDOnet: {sorted(ids)}")

        if matched_id:
            msg = (
                f"matched via cusip {matched_cusip}"
                if len(candidates) > 1 and matched_cusip
                else None
            )
            return MapResult(
                moodystrancheid=matched_id,
                map_tier="cusip",
                map_status="ok",
                map_message=msg,
            )
        if ambiguous_notes:
            return MapResult(
                moodystrancheid=None,
                map_tier="cusip",
                map_status="ambiguous",
                map_message="; ".join(ambiguous_notes),
            )
        tried = ", ".join(candidates)
        return MapResult(
            moodystrancheid=None,
            map_tier="cusip",
            map_status="unmapped",
            map_message=(
                f"no cusip in CDOnet CUSTOM_CDONET_TRANCHE_DATA for deal {maps.deal_id} "
                f"(tried: {tried})"
            ),
        )

    norm = normalize_class_label(class_name)
    tid, tname, status, msg = match_trustee_tranche_name(norm, maps.name_index)
    if status == "ok" and tid:
        return MapResult(
            moodystrancheid=str(tid),
            map_tier="name",
            map_status="ok",
            trustee_tranche_name=tname,
            map_message=msg,
        )
    if not norm:
        return MapResult(
            moodystrancheid=None,
            map_tier=None,
            map_status="unmapped",
            map_message="no cusip and no class name to match",
        )
    return MapResult(
        moodystrancheid=None,
        map_tier="name",
        map_status=status,
        trustee_tranche_name=tname,
        map_message=msg,
    )


def _ensure_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    here = Path(__file__).resolve().parent
    for p in (here / ".env", here.parent / ".env", here.parents[1] / ".env"):
        if p.is_file():
            load_dotenv(p, override=False)


def _connect_from_db_vars() -> Any:
    """Connect using DB_SERVER / DB_DATABASE / DB_USERNAME / DB_PASSWORD (same as get_file_path)."""
    import pyodbc

    _ensure_dotenv()
    server = os.environ.get("DB_SERVER", "").strip()
    database = os.environ.get("DB_DATABASE", "").strip()
    username = os.environ.get("DB_USERNAME", "").strip()
    password = os.environ.get("DB_PASSWORD", "").strip()
    if not all([server, database, username, password]):
        raise RuntimeError(
            "Set NOTEVAL_ODBC_CONNECTION, or DB_SERVER + DB_DATABASE + DB_USERNAME + DB_PASSWORD in .env."
        )
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
        f"Could not connect with any ODBC driver ({drivers}). Last error: {last}"
    ) from last


def _connect_pyodbc():
    try:
        import pyodbc  # noqa: F401
    except ImportError as e:
        raise RuntimeError(
            "pyodbc is required for database mapping. Install: py -3 -m pip install pyodbc"
        ) from e
    _ensure_dotenv()
    conn_s = os.environ.get("NOTEVAL_ODBC_CONNECTION", "").strip()
    if conn_s:
        import pyodbc

        return pyodbc.connect(conn_s)
    return _connect_from_db_vars()


def _cdonet_db() -> str:
    return os.environ.get("NOTEVAL_CDONET_DATABASE", "CDOnet_DL").strip() or "CDOnet_DL"


def _ems_db() -> str:
    return os.environ.get("NOTEVAL_EMS_DATABASE", "ems").strip() or "ems"


def load_deal_maps_from_db(deal_id: str, *, connection: Any | None = None) -> DealTrancheMaps:
    """Load tier 1 + tier 2 indexes for one moodysdealid / deal_id."""
    own_conn = connection is None
    conn = connection or _connect_pyodbc()
    try:
        cusip_index: dict[str, set[str]] = defaultdict(set)
        cdonet = _cdonet_db()
        cur = conn.cursor()
        cur.execute(_TIER1_BULK_SQL.format(cdonet_db=cdonet), (deal_id,))
        for row in cur.fetchall():
            mid = str(row[0]).strip() if row[0] is not None else ""
            if not mid:
                continue
            for i in range(1, 10):
                c = row[i]
                if c and str(c).strip():
                    nc = normalize_cusip(str(c))
                    if nc:
                        cusip_index[nc].add(mid)

        name_index: list[tuple[str, str]] = []
        ems = _ems_db()
        cur.execute(_TIER2_SQL.format(ems_db=ems), (deal_id,))
        for tname, tranche_id in cur.fetchall():
            if tname is None or tranche_id is None:
                continue
            name_index.append((str(tname).strip(), str(tranche_id).strip()))
        name_index.sort(key=lambda x: len(x[0]), reverse=True)

        return DealTrancheMaps(
            deal_id=deal_id,
            cusip_index=dict(cusip_index),
            name_index=name_index,
        )
    finally:
        if own_conn:
            conn.close()


def load_tranche_cache(path: Path) -> dict[str, DealTrancheMaps]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, DealTrancheMaps] = {}
    for deal_id, block in data.items():
        if isinstance(block, dict):
            out[str(deal_id).strip()] = DealTrancheMaps.from_cache_dict(str(deal_id), block)
    return out


def save_tranche_cache(path: Path, deals: dict[str, DealTrancheMaps]) -> None:
    payload = {did: maps.to_cache_dict() for did, maps in sorted(deals.items())}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class TrancheMapper:
    """Batch resolver with per-deal cache (DB or JSON)."""

    def __init__(
        self,
        *,
        cache_file: Path | None = None,
        use_db: bool = True,
        connection: Any | None = None,
    ) -> None:
        self._cache_file = cache_file
        self._use_db = use_db
        self._connection = connection
        self._file_cache: dict[str, DealTrancheMaps] = (
            load_tranche_cache(cache_file) if cache_file and cache_file.is_file() else {}
        )
        self._deal_maps: dict[str, DealTrancheMaps] = dict(self._file_cache)

    def maps_for_deal(self, deal_id: str) -> DealTrancheMaps:
        did = str(deal_id).strip()
        if did in self._deal_maps:
            return self._deal_maps[did]
        if self._use_db:
            self._deal_maps[did] = load_deal_maps_from_db(did, connection=self._connection)
            return self._deal_maps[did]
        return DealTrancheMaps(deal_id=did, cusip_index={}, name_index=[])

    def resolve(
        self,
        deal_id: str,
        *,
        cusip: str | None = None,
        cusips: list[str] | None = None,
        class_name: str | None = None,
    ) -> MapResult:
        return resolve_tranche(
            self.maps_for_deal(deal_id),
            cusip=cusip,
            cusips=cusips,
            class_name=class_name,
        )

    def enrich_class_row(
        self,
        row: list[Any],
        *,
        deal_id_col: int = 0,
        class_name_col: int = 2,
        cusip_col: int = 3,
    ) -> list[Any]:
        """Append mapping columns to a class export row."""
        if len(row) <= cusip_col:
            return row + ["", "", "", "", ""]
        deal_id = str(row[deal_id_col] or "").strip()
        class_name = str(row[class_name_col] or "").strip()
        cusip = str(row[cusip_col] or "").strip()
        r = self.resolve(deal_id, cusip=cusip or None, class_name=class_name)
        return row + [
            r.moodystrancheid or "",
            r.trustee_tranche_name or "",
            r.map_tier or "",
            r.map_status or "",
            r.map_message or "",
        ]


CLASS_MAP_EXTRA_HEADERS = [
    "moodystrancheid",
    "trustee_tranche_name",
    "map_tier",
    "map_status",
    "map_message",
]


def prefetch_deals(
    deal_ids: list[str],
    *,
    output: Path,
    connection: Any | None = None,
) -> dict[str, DealTrancheMaps]:
    deals: dict[str, DealTrancheMaps] = {}
    own_conn = connection is None
    conn = connection
    if own_conn:
        conn = _connect_pyodbc()
    try:
        for did in deal_ids:
            did = did.strip()
            if not did:
                continue
            deals[did] = load_deal_maps_from_db(did, connection=conn)
            print(f"prefetched {did}: {len(deals[did].cusip_index)} cusips, {len(deals[did].name_index)} names")
    finally:
        if own_conn and conn is not None:
            conn.close()
    save_tranche_cache(output, deals)
    return deals


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve moodystrancheid for noteval class rows.")
    ap.add_argument("--deal-id", required=True, help="Moodys deal id (moodysdealid / agent deal_id)")
    ap.add_argument("--class-name", default="", help="Primary Class from 02")
    ap.add_argument("--cusip", default="", help="CUSIP from listing")
    ap.add_argument(
        "--cache-file",
        type=Path,
        help="JSON cache from --prefetch (skips DB when deal present)",
    )
    ap.add_argument(
        "--no-db",
        action="store_true",
        help="Do not query SQL Server (cache file only)",
    )
    ap.add_argument(
        "--prefetch",
        nargs="+",
        metavar="DEAL_ID",
        help="Load deals from DB and write --output cache JSON",
    )
    ap.add_argument("-o", "--output", type=Path, help="Cache path for --prefetch")
    args = ap.parse_args()

    if args.prefetch:
        if not args.output:
            print("--output required with --prefetch", file=sys.stderr)
            return 2
        prefetch_deals(args.prefetch, output=args.output.resolve())
        return 0

    mapper = TrancheMapper(
        cache_file=args.cache_file.resolve() if args.cache_file else None,
        use_db=not args.no_db,
    )
    result = mapper.resolve(
        args.deal_id,
        cusip=args.cusip or None,
        class_name=args.class_name or None,
    )
    print(json.dumps(result.__dict__, indent=2))
    return 0 if result.map_status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
