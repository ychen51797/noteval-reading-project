"""
map_tranches.py — Resolve moodystrancheid for noteval class rows.

Tier 1 (CUSIP present): agent CUSIP → [CDOnet_DL].CUSTOM_CDONET_TRANCHE_DATA
        .MOODYSTRANCHEID (fallback MOODY_TRANCHE_ID), scoped by moodysdealid via
        CUSTOM_CDONET_DEAL_DATA2. CUSIP columns: CUSIP, CUSIP2 … CUSIP9.
        When a class has multiple CUSIPs, use them **in listing order**; the **first**
        CUSIP with a unique CDOnet hit wins — remaining CUSIPs are not tried.
        **Whenever any CUSIP is present, tier 1 always runs** (``map_tier="cusip"``);
        there is **no** tier-2 name fallback for that row — fix the CUSIP or CDOnet row.

Tier 2 (no CUSIP): deal_id + ``map_class`` / normalized class name ↔
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
from dataclasses import dataclass, field
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

_NOTEVAL_TRANCHES_SQL = """
SELECT tranche_name,
       interest_rate,
       interest_payment,
       principal_payment,
       deferred_interest,
       beginning_period_balance,
       end_period_balance
FROM [{ems_db}].[dbo].[cdo_noteval_tranches]
WHERE deal_id = ?
  AND CONVERT(varchar(10), payment_date, 23) = ?
"""

_TRANCHE_MASTER_SQL = """
SELECT tranche_id,
       orig_balance
FROM [{ems_db}].[dbo].[cdo_tranche_master]
WHERE deal_id = ?
"""

DB_COMPARE_FIELDS = (
    "interest_rate",
    "interest_payment",
    "principal_payment",
    "deferred_interest",
    "beginning_balance",
    "ending_balance",
)

# ``cdo_tranche_master.orig_balance`` vs export ``original_balance`` (deal_id + tranche_id).
MASTER_COMPARE_FIELDS = ("original_balance",)

MASTER_COMPARE_HEADERS = (
    "db_orig_balance",
    "tm_match_status",
    "diff_original_balance",
)
_DB_FIELD_FROM_SQL = {
    "interest_rate": "interest_rate",
    "interest_payment": "interest_payment",
    "principal_payment": "principal_payment",
    "deferred_interest": "deferred_interest",
    "beginning_balance": "beginning_period_balance",
    "ending_balance": "end_period_balance",
}
DB_COMPARE_HEADERS = (
    [f"db_{f}" for f in DB_COMPARE_FIELDS]
    + ["db_match_name", "db_match_status"]
    + [f"diff_{f}" for f in DB_COMPARE_FIELDS]
)


@dataclass(frozen=True)
class MapResult:
    moodystrancheid: str | None
    map_tier: str | None
    map_status: str
    trustee_tranche_name: str | None = None
    map_message: str | None = None
    matched_cusip: str | None = None


@dataclass
class DealTrancheMaps:
    """In-memory indexes for one deal (moodysdealid / deal_id)."""

    deal_id: str
    cusip_index: dict[str, set[str]]
    name_index: list[tuple[str, str]]
    # tranche_id (== moodystrancheid in our pipeline) -> set of all names that point at it.
    # Includes the tranche_id itself so cdo_noteval_tranches rows whose
    # ``tranche_name`` is the numeric moodystrancheid still join.
    tranche_id_to_names: dict[str, set[str]] = field(default_factory=dict)

    def names_for_tranche_id(self, tranche_id: str | None) -> list[str]:
        if not tranche_id:
            return []
        names = self.tranche_id_to_names.get(str(tranche_id).strip())
        if not names:
            return [str(tranche_id).strip()] if tranche_id else []
        return sorted(names, key=len)

    def has_subordinated_tranche_mapping(self) -> bool:
        """True when EMS lists sub notes (or ``PS2`` / ``PREF``, implying sub + pref split)."""
        has_ps2 = False
        for tname, _ in self.name_index:
            raw = str(tname).strip().upper()
            if _subordinated_notes_key(raw) is not None:
                return True
            if _ps_sub_tier_key(raw) is not None:
                return True
            key = normalize_trustee_name_key(str(tname))
            if key in ("PS1", "SUB") or _SUB_TIER_KEY.fullmatch(key):
                return True
            if key in ("PS2", "PREF"):
                has_ps2 = True
        return has_ps2

    def has_inc_tranche_mapping(self) -> bool:
        """True when ``noteval_tranche_mapping`` lists ``INC`` / ``INCOME`` (or income-note label)."""
        for tname, _ in self.name_index:
            raw = str(tname).strip().upper()
            key = normalize_trustee_name_key(str(tname))
            if key in ("INC", "INCOME"):
                return True
            if _income_notes_key(raw):
                return True
        return False

    def ps_mapped_to_sub_or_pref(self) -> bool:
        """
        True when EMS ``PS`` / ``PS1`` / ``PS2`` rows represent subordinated notes or preference shares.

        When False, a lone ``PS`` key may represent **income notes** (no ``INC`` row in EMS).
        """
        keys: set[str] = set()
        for tname, _ in self.name_index:
            raw = str(tname).strip().upper()
            key = normalize_trustee_name_key(str(tname))
            if key:
                keys.add(key)
            if _subordinated_notes_key(raw) or _ps_sub_tier_key(raw):
                return True
            if key in ("SUB", "PS1") or _SUB_TIER_KEY.fullmatch(key or ""):
                return True
            if key in ("PS2", "PREF"):
                return True
            if _is_preferred_share_label(raw):
                return True
        if ("PS2" in keys or "PREF" in keys) and (
            "PS" in keys or "PS1" in keys or "SUB" in keys
        ):
            return True
        return False

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
            "tranche_id_to_names": {
                tid: sorted(names) for tid, names in self.tranche_id_to_names.items()
            },
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
        tid_to_names: dict[str, set[str]] = {}
        for tid, names in (data.get("tranche_id_to_names") or {}).items():
            tid_str = str(tid).strip()
            if not tid_str:
                continue
            tid_to_names[tid_str] = {str(n).strip() for n in names if n}
        for n, tid in name_index:
            tid_to_names.setdefault(str(tid).strip(), set()).add(n)
        return cls(
            deal_id=deal_id,
            cusip_index=cusip_index,
            name_index=name_index,
            tranche_id_to_names=tid_to_names,
        )


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
    "SUBNOTE": "SUB",
    "INCOME": "INC",
    "COMBONOTES": "COMB",
    "COMBONOTE": "COMB",
    "COMBO": "COMB",
    "PERFORMANCE": "P",
    "PERFORMANCENOTES": "P",
    "PERFORMANCENOTE": "P",
    "PERF": "P",
}

# Combo / combination notes: trustee ``COMB``; EMS often lists ``COMBO``.
_COMBO_LOOKUP_VARIANTS: tuple[str, ...] = ("COMB", "COMBO")

# Performance notes (termination / equity-style): trustee ``Performance Notes``; EMS ``P``.
_PERFORMANCE_LOOKUP_VARIANTS: tuple[str, ...] = ("P", "PERF", "PERFORMANCE")

# Subordinated notes: EMS often lists ``PS`` / ``PS1``; extraction may print ``SUB``.
# Tiered sub notes: ``SUBA`` / ``PSA`` ↔ ``Subordinated Notes A``, etc.
_SUB_LOOKUP_KEYS = frozenset({"SUB", "PS", "PS1"})
_SUB_NOTES_LOOKUP_VARIANTS: tuple[str, ...] = ("PS", "SUB", "PS1")
_SUB_TIER_KEY = re.compile(r"^(?:SUB|PS)([A-Z])$")


def _sub_tier_lookup_variants(normalized: str) -> tuple[str, ...] | None:
    """``SUBA`` ↔ ``PSA`` (and other letter tiers) for ``noteval_tranche_mapping``."""
    m = _SUB_TIER_KEY.fullmatch(normalized)
    if not m:
        return None
    letter = m.group(1)
    sub = f"SUB{letter}"
    ps = f"PS{letter}"
    return (sub, ps)


def _tranche_key_over_subordinated_notes(raw_upper: str) -> str | None:
    """
    ``Class M-1 Subordinated Notes`` → ``M1`` (not ``SUB``).

    When a tranche token precedes ``Subordinated Notes``, the letter/number id wins.
    Bare ``Subordinated Notes`` → None (caller uses ``SUB``).
    Tiered ``Subordinated Notes A`` → None (handled as ``SUBA``).
    """
    t = re.sub(r"\s+", " ", raw_upper.strip())
    for prefix in _CLASS_NAME_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    if re.search(r"^SUBORDINATED\s+(?:NOTE|NOTES)\s+[A-Z]\b", t):
        return None
    if re.search(r"^SUB\s+[A-Z]\b", t):
        return None
    sub_pos = re.search(r"\bSUBORDINATED\b", t)
    if not sub_pos:
        return None
    tranche_part = t[: sub_pos.start()].strip()
    if not tranche_part:
        return None
    lead = _TRANCHE_LEAD_TOKEN.match(tranche_part)
    if not lead:
        return None
    token = _extend_tranche_lead_token(lead.group(1), tranche_part[lead.end() :])
    core = normalize_trustee_name_key(token)
    if not core or core in _DESCRIPTOR_TOKENS or _is_junk_mapping_key(core):
        return None
    if core in ("SUB", "SUBORDINATEDNOTES", "SUBORDINATEDNOTE"):
        return None
    return _CLASS_ALIASES.get(core, core)


def _subordinated_notes_key(raw_upper: str) -> str | None:
    """Sub notes → ``SUB`` or tiered ``SUBA`` / ``SUBB`` (EMS may also list ``PSA`` / ``PSB``)."""
    t = re.sub(r"\s+", " ", raw_upper.strip())
    for prefix in _CLASS_NAME_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    m = re.search(r"^SUBORDINATED\s+(?:NOTE|NOTES)\s+([A-Z])\b", t)
    if m:
        return f"SUB{m.group(1)}"
    m = re.search(r"^SUB\s+([A-Z])\b", t)
    if m:
        return f"SUB{m.group(1)}"
    if "SUBORDINATED" in t and re.search(r"NOTE|S", t):
        return "SUB"
    if t in ("SUB NOTES", "SUB NOTE", "SUBORDINATED NOTES", "SUBORDINATED NOTE"):
        return "SUB"
    if t == "SUB":
        return "SUB"
    return None


def _combo_notes_key(raw_upper: str) -> str | None:
    """Combo / combination notes → ``COMB`` (EMS often lists ``COMBO``)."""
    t = re.sub(r"\s+", " ", raw_upper.strip())
    for prefix in _CLASS_NAME_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    if t in (
        "COMB",
        "COMBO",
        "COMBO NOTES",
        "COMBO NOTE",
        "COMBINATION NOTES",
        "COMBINATION NOTE",
    ):
        return "COMB"
    if "COMBO" in t and re.search(r"NOTE|S", t):
        return "COMB"
    compact = normalize_trustee_name_key(t)
    if compact in ("COMB", "COMBO", "COMBONOTES", "COMBONOTE"):
        return "COMB"
    return None


# ``Series 1 Combination Securities`` / ``Series I Combination Securities`` → ``SERIES1``.
_SERIES_COMBINATION = re.compile(
    r"^SERIES\s+([IVXLCDM]+|\d+)\s+COMBINATION\s+SECURIT",
    re.I,
)
_SERIES_ROMAN_TO_ARABIC = {
    "I": "1",
    "II": "2",
    "III": "3",
    "IV": "4",
    "V": "5",
    "VI": "6",
    "VII": "7",
    "VIII": "8",
    "IX": "9",
    "X": "10",
}
_ARABIC_TO_SERIES_ROMAN = {v: k for k, v in _SERIES_ROMAN_TO_ARABIC.items()}


def _series_combination_number(token: str) -> str:
    t = token.strip().upper()
    if t.isdigit():
        return str(int(t))
    return _SERIES_ROMAN_TO_ARABIC.get(t, t)


def _series_combination_key(raw_upper: str) -> str | None:
    """
    Combination-security series rows → ``SERIES1``, ``SERIES2``, …

    Trustee ``Series 1 Combination Securities`` or ``Series I Combination Securities``
    (EMS may list ``S-1`` / ``Series I Combination Securities``).
    """
    t = re.sub(r"\s+", " ", raw_upper.strip())
    for prefix in _CLASS_NAME_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    m = _SERIES_COMBINATION.match(t)
    if not m:
        return None
    return f"SERIES{_series_combination_number(m.group(1))}"


def _series_combination_short_key(raw_upper: str) -> str | None:
    """EMS short keys ``S-1`` / ``S-2`` → ``SERIES1`` / ``SERIES2`` (same tranche as full label)."""
    t = re.sub(r"\s+", " ", raw_upper.strip())
    for prefix in _CLASS_NAME_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    m = re.fullmatch(r"S\s*[-/]\s*(\d+)", t, re.I)
    if not m:
        return None
    return f"SERIES{str(int(m.group(1)))}"


def _series_combination_lookup_variants(normalized: str) -> tuple[str, ...] | None:
    """``SERIES1`` ↔ ``S1`` / ``S-1`` / ``SERIESI`` / full trustee label (bidirectional)."""
    m = re.fullmatch(r"SERIES(\d+)", normalized)
    if not m:
        m = re.fullmatch(r"S(\d+)", normalized)
    if not m:
        m = re.fullmatch(r"SERIES([IVXLCDM]+)", normalized)
        if m:
            arabic = _series_combination_number(m.group(1))
            if arabic.isdigit():
                m = re.fullmatch(r"SERIES(\d+)", f"SERIES{arabic}")
    if not m:
        return None
    n = m.group(1)
    if not n.isdigit():
        n = _series_combination_number(n)
    variants = [normalized, f"SERIES{n}", f"S{n}"]
    roman = _ARABIC_TO_SERIES_ROMAN.get(n)
    if roman:
        variants.append(f"SERIES{roman}")
    return tuple(dict.fromkeys(variants))


def _performance_notes_key(raw_upper: str) -> str | None:
    """Performance notes → ``P`` (EMS key on termination / equity-style deals)."""
    t = re.sub(r"\s+", " ", raw_upper.strip())
    for prefix in _CLASS_NAME_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    if t in ("P", "PERFORMANCE NOTES", "PERFORMANCE NOTE", "PERFORMANCE", "PERF"):
        return "P"
    if "PERFORMANCE" in t and re.search(r"NOTE|S", t):
        return "P"
    compact = normalize_trustee_name_key(t)
    if compact in ("P", "PERFORMANCE", "PERFORMANCENOTES", "PERFORMANCENOTE", "PERF"):
        return "P"
    return None


def _ps_sub_tier_key(raw_upper: str) -> str | None:
    """
    Trustee ``PSA`` / ``PSB`` (and ``PS A``) → ``SUBA`` / ``SUBB``.

    Distinct from ``PS1`` / ``PS2`` preference-share keys and bare ``PS``.
    """
    t = re.sub(r"\s+", " ", raw_upper.strip())
    for prefix in _CLASS_NAME_PREFIXES:
        if t.startswith(prefix):
            t = t[len(prefix) :].strip()
            break
    compact = normalize_trustee_name_key(t)
    if not compact:
        return None
    m = re.fullmatch(r"PS([A-Z])", compact)
    if m:
        return f"SUB{m.group(1)}"
    return None

# Preference shares: EMS often lists the full trustee label (``Preference Shares``)
# while compact keys vary (``PS``, ``PS2``, ``PREF``). Always try the full compact
# label plus short aliases so PS ↔ PS2 ↔ PREFERENCESHARES align.
_PREF_SHARE_LOOKUP_VARIANTS: tuple[str, ...] = (
    "PREFERENCESHARES",
    "PREFERENCESHARE",
    "PREFERREDSHARES",
    "PREFERREDSHARE",
    "PS",
    "PS1",
    "PS2",
    "PREF",
)

# Dual sub + pref deals (e.g. 823259672): sub notes EMS keys — ``PS`` → ``SUB`` → ``PS1``.
_SUB_OR_DUAL_PS_LOOKUP: tuple[str, ...] = ("PS", "SUB", "PS1")

# Preference equity on dual deals (``PS2`` norm): try ``PS2`` first — **not** ``PS1`` (often = sub).
_PS2_LOOKUP_VARIANTS: tuple[str, ...] = (
    "PS2",
    "PREFERENCESHARES",
    "PREFERENCESHARE",
    "PREFERREDSHARES",
    "PREFERREDSHARE",
    "PREF",
    "PS",
)

# Alternate EMS keys for the same economic tranche (try in order — first hit wins).
_PREF_ONLY_PS_FALLBACK: tuple[str, ...] = tuple(
    x for x in _PREF_SHARE_LOOKUP_VARIANTS if x not in _SUB_OR_DUAL_PS_LOOKUP
)

_LOOKUP_VARIANTS: dict[str, tuple[str, ...]] = {
    "PS": _SUB_OR_DUAL_PS_LOOKUP + _PREF_ONLY_PS_FALLBACK,
    "PS1": _SUB_OR_DUAL_PS_LOOKUP,
    "PS2": _PS2_LOOKUP_VARIANTS,
    "PREF": _PS2_LOOKUP_VARIANTS,
    "PREFERENCESHARES": _PS2_LOOKUP_VARIANTS,
    "PREFERENCESHARE": _PS2_LOOKUP_VARIANTS,
    "PREFERREDSHARES": _PS2_LOOKUP_VARIANTS,
    "PREFERREDSHARE": _PS2_LOOKUP_VARIANTS,
    "SUB": _SUB_NOTES_LOOKUP_VARIANTS,
    "COMB": _COMBO_LOOKUP_VARIANTS,
    "COMBO": _COMBO_LOOKUP_VARIANTS,
    "P": _PERFORMANCE_LOOKUP_VARIANTS,
    "PERF": _PERFORMANCE_LOOKUP_VARIANTS,
    "PERFORMANCE": _PERFORMANCE_LOOKUP_VARIANTS,
    "INC": ("INC", "INCOME"),
    "INCOME": ("INC", "INCOME"),
}

# Trustee: "A-1-R", "A - 1", "A-1 R", "D-R" … EMS: "A1R", "A1", "DR". Do not use ``\\b`` —
# it stops at the hyphen in "A-1" and yields "A" only.
_TRANCHE_LEAD_TOKEN = re.compile(
    r"^([A-Z0-9]+(?:\s*[-/]\s*[A-Z0-9]+)*)(?=\s|$|[,/])"
)

# ``Class A-1 R`` / ``A-1 R3`` — revision letter glued with a space, not a hyphen.
# ``Class A-1 AV`` / ``A-1 ANV`` — spaced multi-letter tranche suffix (→ ``A1AV``, ``A1ANV``).
_TRANCHE_SPACED_SUFFIX = re.compile(r"^\s+(RR|[A-Z]{2,4}|[A-Z]\d{0,2})\b", re.I)

# ``Class A 1`` / ``A 1 Floating …`` — digit glued with a space, not a hyphen (→ ``A1``).
_TRANCHE_SPACED_DIGIT = re.compile(r"^\s+(\d+)")

_SUFFIX_STOP_WORDS = frozenset(
    {
        *_DESCRIPTOR_TOKENS,
        "NOTE",
        "NOTES",
        "LOAN",
        "LOANS",
        "HOLDERS",
        "SHARE",
        "SHARES",
        "STOCK",
        "EQUITY",
        "CP",
        "LT",
        "ST",
        "MEZZ",
        "FLOATING",
        "FIXED",
        "RATE",
        "DEFERRABLE",
        "DEFERRED",
    }
)

# Moodys / tranche id rows sometimes appear as bare numerics in trustee_tranche_name.
_JUNK_MAPPING_KEY = re.compile(r"^\d{7,}$")

# When the PDF glues deal / series id before the tranche label (``DRSLF 2018-70A SUB A``),
# strip through the last token before a known class anchor.
_CLASS_LABEL_ANCHOR = re.compile(
    r"(?:"
    r"\bSUBORDINATED\s+(?:NOTE|NOTES)\b"
    r"|\b(?:NOTE\s+)?CLASS\s+"
    r"|\b(?:PREFERENCE|PREFERRED)\s+"
    r"|\bINCOME\s+"
    r"|\bSUB\s+[A-Z]\b"
    r"|\bSUB\b"
    r")",
    re.I,
)


def _deal_name_prefix_candidates(deal_name: str | None) -> tuple[str, ...]:
    """Variants of ``deal_name`` to strip when glued as a class-field prefix."""
    dn = (deal_name or "").strip()
    if not dn:
        return ()
    out: list[str] = []
    for raw in (dn, re.split(r"\s*\*\*", dn, maxsplit=1)[0].strip()):
        if raw and raw not in out:
            out.append(raw)
        if "," in raw:
            head = raw.split(",", 1)[0].strip()
            if head and head not in out:
                out.append(head)
    return tuple(out)


# ``DRSLF 2020-78A A-1-R`` / ``DRSLF 2020-85 A-1-R`` — issuer / series id glued before tranche.
_SERIES_ID_PREFIX = re.compile(
    r"^[A-Z][A-Z0-9-]{0,12}\s+\d{4}\s*[-/]\s*\d+[A-Z0-9]*\s+",
    re.I,
)
# After issuer code already removed: ``2020-85 A-1-R`` → ``A-1-R``.
_VINTAGE_ONLY_PREFIX = re.compile(
    r"^\d{4}\s*[-/]\s*\d+[A-Z0-9]*\s+",
    re.I,
)


# Tokens that may appear in a glued deal / series prefix — not tranche ids.
_SERIES_DEAL_TOKEN_EXCLUDE = frozenset(
    {
        "CLASS",
        "CLASSES",
        "NOTE",
        "NOTES",
        "HOLDERS",
        "THE",
        "TRANCHE",
        "SUB",
        "INC",
        "PS",
        "PS1",
        "PS2",
        "PREF",
        "MEZZ",
        "CLO",
    }
)


def _is_series_deal_token(token: str) -> bool:
    """
    True for issuer / vintage tokens glued before the tranche label.

    ``DRSLF``, ``2018-70A`` — yes; ``SUB``, ``Class``, ``A-1-R`` — no.
    """
    t = re.sub(r"\s+", "", (token or "").strip().upper())
    if not t or t in _SERIES_DEAL_TOKEN_EXCLUDE:
        return False
    if re.fullmatch(r"\d{4}[-/]\d+[A-Z0-9]*", t):
        return True
    if re.fullmatch(r"[A-Z]{4,12}", t):
        return True
    return False


def _series_token_compare_key(token: str) -> str:
    """
    Normalize series tokens for shared-prefix detection.

    ``2020-85A`` and ``2020-85`` (spaced before the tranche) compare equal.
    """
    t = re.sub(r"\s+", "", (token or "").strip().upper())
    m = re.fullmatch(r"(\d{4})[-/](\d+)([A-Z0-9]*)", t)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return t


def _shared_leading_token_count(names: list[str]) -> int:
    """Count leading series/deal tokens shared by every non-empty class label."""
    token_lists = [re.split(r"\s+", n.strip()) for n in names if n and n.strip()]
    if len(token_lists) < 2:
        return 0
    min_len = min(len(tokens) for tokens in token_lists)
    shared = 0
    for i in range(min_len):
        tok = token_lists[0][i]
        if not _is_series_deal_token(tok):
            break
        key = _series_token_compare_key(tok)
        if all(
            _series_token_compare_key(tokens[i]) == key for tokens in token_lists
        ):
            shared = i + 1
        else:
            break
    return shared


def _strip_shared_deal_prefix_from_class(
    class_name: str,
    peer_class_names: list[str] | None,
) -> str:
    """
    Drop deal / series tokens shared across all classes in the same export.

    ``DRSLF 2020-78A A-1-R`` + peers ``DRSLF 2020-78A Sub`` → ``A-1-R``.
    ``2020-85`` / ``2020-85A`` vintage variants normalize to the same shared prefix.
    """
    s = (class_name or "").strip()
    if not s or not peer_class_names:
        return s
    peers = [str(p).strip() for p in peer_class_names if p and str(p).strip()]
    if s not in peers:
        peers.append(s)
    if len(peers) < 2:
        return s
    n_shared = _shared_leading_token_count(peers)
    if n_shared < 1:
        return s
    parts = re.split(r"\s+", s)
    if len(parts) <= n_shared:
        return s
    return " ".join(parts[n_shared:])


def _strip_series_id_prefix(class_name: str) -> str:
    """Fallback when peer class names are unavailable (CLI / single-row resolve)."""
    s = (class_name or "").strip()
    if not s:
        return s
    m = _SERIES_ID_PREFIX.match(s)
    if m:
        rest = s[m.end() :].strip()
        return rest or s
    m = _VINTAGE_ONLY_PREFIX.match(s)
    if m:
        rest = s[m.end() :].strip()
        return rest or s
    return s


def _strip_deal_prefix_from_class(
    class_name: str,
    deal_name: str | None = None,
    *,
    peer_class_names: list[str] | None = None,
) -> str:
    """
    Remove a leading deal name / series id from the class label when present.

    ``Dryden 70 CLO Class A`` → ``Class A``; ``DRSLF 2018-70A SUB A`` → ``SUB A``;
    ``DRSLF 2020-78A A-1-R`` → ``A-1-R`` when peers share the ``DRSLF 2020-78A`` prefix.
    """
    s = (class_name or "").strip()
    if not s:
        return s
    s = _normalize_class_separators(s)
    upper = s.upper()
    for prefix in _deal_name_prefix_candidates(deal_name):
        pu = prefix.upper()
        if upper.startswith(pu):
            rest = s[len(prefix) :].lstrip(" -–—/:;,")
            if rest:
                s = rest
                upper = s.upper()
    s = _strip_shared_deal_prefix_from_class(s, peer_class_names)
    s = _strip_series_id_prefix(s)
    m = _CLASS_LABEL_ANCHOR.search(s)
    if m and m.start() > 0:
        s = s[m.start() :].strip()
    return s


def normalize_trustee_name_key(trustee_tranche_name: str) -> str:
    """Compact EMS / trustee tranche name (hyphens, underscores, punctuation removed)."""
    s = re.sub(r"_+", " ", trustee_tranche_name.strip().upper())
    return re.sub(r"[^A-Z0-9]", "", s)


def _normalize_class_separators(text: str) -> str:
    """Treat underscores like spaces in trustee class labels (``A1-R_Loan`` → ``A1-R Loan``)."""
    return re.sub(r"_+", " ", (text or "").strip())


def _split_tranche_type_suffix(raw_upper: str) -> tuple[str, bool]:
    """
    Remove trailing ``Note`` / ``Loan`` type words from a class label.

    ``A1-R LOAN`` → (``A1-R``, loan=True); ``A1-R NOTE`` → (``A1-R``, loan=False).
    """
    s = re.sub(r"\s+", " ", raw_upper.strip())
    is_loan = bool(re.search(r"\bLOANS?\b", s, re.I))
    core = re.sub(r"\s+(?:NOTE|NOTES|LOAN|LOANS)\s*$", "", s, flags=re.I).strip()
    return core, is_loan


def _income_notes_key(raw_upper: str) -> str | None:
    """Income notes / ``INCOME`` tranche → ``INC`` in ``noteval_tranche_mapping``."""
    t = re.sub(r"\s+", " ", raw_upper.strip())
    if t in ("INC", "INCOME"):
        return "INC"
    if re.search(r"\bINCOME\s+NOTE", t):
        return "INC"
    if re.search(r"\bINCOME\s+NOTEHOLDERS?\b", t):
        return "INC"
    if re.search(r"^INCOME(?:[\s\-/]|$)", t):
        return "INC"
    return None


def _is_preferred_share_label(raw_upper: str) -> bool:
    if not re.search(r"PREFERRED|PREFERENCE", raw_upper):
        return False
    if re.search(r"SHARE|STOCK|EQUITY", raw_upper):
        return True
    return bool(re.search(r"PREFERRED\s+(SHARES?|STOCK)|PREFERENCE\s+SHARES?", raw_upper))


def _strip_trustee_prefixes(raw_upper: str) -> str:
    s = raw_upper.strip()
    for prefix in _CLASS_NAME_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
            break
    return s


def _preference_share_full_key(raw_upper: str) -> str | None:
    """Compact EMS key from the full printed label (``Preference Shares`` → ``PREFERENCESHARES``)."""
    if not _is_preferred_share_label(raw_upper):
        return None
    full = normalize_trustee_name_key(_strip_trustee_prefixes(raw_upper))
    if not full or _is_junk_mapping_key(full):
        return None
    return full


def deal_has_subordinated_notes(
    *,
    deal_maps: DealTrancheMaps | None = None,
    peer_class_names: list[str] | None = None,
    deal_name: str | None = None,
    default_when_unknown: bool = True,
) -> bool:
    """
    Whether this deal also has subordinated notes (not preferred-only).

    Uses extracted peer class names when supplied; otherwise EMS ``noteval_tranche_mapping``.
    """
    if peer_class_names is not None:
        return any(
            _subordinated_notes_key(
                _strip_deal_prefix_from_class(
                    c, deal_name, peer_class_names=peer_class_names
                )
                .strip()
                .upper()
            )
            is not None
            or _ps_sub_tier_key(
                _strip_deal_prefix_from_class(
                    c, deal_name, peer_class_names=peer_class_names
                )
                .strip()
                .upper()
            )
            is not None
            for c in peer_class_names
            if c and c.strip()
        )
    if deal_maps is not None:
        return deal_maps.has_subordinated_tranche_mapping()
    return default_when_unknown


def _preferred_share_lookup_key(
    raw_upper: str,
    *,
    deal_maps: DealTrancheMaps | None = None,
    peer_class_names: list[str] | None = None,
    deal_name: str | None = None,
) -> str | None:
    """
    Preferred / equity lines → ``PS2`` when sub notes also exist; else ``PS``.

    When the deal has only preferred shares, ``noteval_tranche_mapping`` uses ``PS``.
    """
    if not _is_preferred_share_label(raw_upper):
        return None
    if deal_has_subordinated_notes(
        deal_maps=deal_maps,
        peer_class_names=peer_class_names,
        deal_name=deal_name,
    ):
        return "PS2"
    return "PS"


def _preferred_share_key(raw_upper: str) -> str | None:
    """Legacy wrapper — assumes dual-tranche deal when context is unknown."""
    return _preferred_share_lookup_key(raw_upper)


# ``Class A CP Notes`` / ``A-LT`` → ``ACP`` / ``ALT`` (not bare ``A``).
_CLASS_LETTER_CP_LT_ST = re.compile(
    r"^(?:CLASS\s+)?([A-Z])\s+(CP|LT|ST)\b",
    re.IGNORECASE,
)
_CLASS_LETTER_CP_LT_ST_HYPHEN = re.compile(
    r"^([A-Z])\s*[-/]\s*(CP|LT|ST)\b",
    re.IGNORECASE,
)


def _class_letter_cp_lt_st_key(label: str) -> str | None:
    """
    Map ``Class A {CP|LT|ST} Notes`` (and ``A-CP``) to ``ACP`` / ``ALT`` / ``AST``.

    Aligns trustee long names with EMS short keys ``A-CP``, ``A-LT``, ``A-ST``.
    """
    t = re.sub(r"[;,.]", " ", (label or "").strip().upper())
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return None
    m = _CLASS_LETTER_CP_LT_ST.match(t)
    if not m:
        m = _CLASS_LETTER_CP_LT_ST_HYPHEN.match(t)
    if not m:
        return None
    return f"{m.group(1).upper()}{m.group(2).upper()}"


def _loan_tranche_label(raw_upper: str) -> bool:
    """True for tranche rows like ``Class A-1 Loan`` (not deal-level "Loan Fund" metadata)."""
    return bool(re.search(r"\bLOANS?\b", raw_upper))


def _with_loan_tranche_suffix(
    key: str,
    raw_upper: str,
    *,
    is_loan: bool | None = None,
) -> str:
    """
    Loan tranches in ``noteval_tranche_mapping`` often end in ``L`` (``A1L``, ``A1RL``).

    ``Class A-1 Loan`` → lead token ``A1`` + ``L`` → ``A1L``;
    ``A1-R_Loan`` / ``A1-R Loan`` → ``A1R`` + ``L`` → ``A1RL``.
    """
    loan = is_loan if is_loan is not None else _loan_tranche_label(raw_upper)
    if not key or not loan:
        return key
    if _SUB_TIER_KEY.fullmatch(key) or key in ("PS", "PS1", "PS2", "SUB", "PREF"):
        return key
    if key.endswith("L") and len(key) > 1 and key[-2].isalnum():
        return key
    if key in ("COMB", "COMBO"):
        return "COMB"
    if key == "P":
        return "P"
    return f"{key}L"


def _extend_tranche_token_with_spaced_suffix(base_token: str, remainder: str) -> str:
    """
    Append spaced revision / variant tokens: ``A-1`` + `` R`` → ``A-1R`` (→ ``A1R``);
    ``A-1`` + `` AV`` → ``A1AV``.

    Trustee reports sometimes omit the hyphen before ``R`` / ``R3`` / ``RR`` / ``AV``.
    """
    m = _TRANCHE_SPACED_SUFFIX.match(remainder or "")
    if not m:
        return base_token
    suffix = m.group(1).upper()
    if suffix in _SUFFIX_STOP_WORDS:
        return base_token
    return f"{base_token}{suffix}" if base_token else suffix


def _extend_tranche_lead_token(base_token: str, remainder: str) -> str:
    """
    Glue spaced tranche parts: ``A`` + `` 1`` → ``A-1`` (→ ``A1``), then `` R`` → ``A1R``.
    """
    token = base_token
    rest = remainder or ""
    compact = re.sub(r"\s+", "", token)
    if re.fullmatch(r"[A-Z]", compact):
        m = _TRANCHE_SPACED_DIGIT.match(rest)
        if m:
            token = f"{compact}-{m.group(1)}"
            rest = rest[m.end() :]
    token = _extend_tranche_token_with_spaced_suffix(token, rest)
    return re.sub(r"\s+", "", token)


def normalize_class_label(
    class_name: str | None,
    *,
    deal_maps: DealTrancheMaps | None = None,
    peer_class_names: list[str] | None = None,
    deal_name: str | None = None,
) -> str:
    """
    Compact token for matching noteval_tranche_mapping.trustee_tranche_name.

    Strips trustee prefixes ("Class ", …), takes the leading tranche token
    (e.g. ``D-R`` → ``DR``, ``A-1`` / ``A - 1`` / ``A 1`` → ``A1``, ``A-1 R`` → ``A1R``,
    ``A-1 AV`` → ``A1AV``) before descriptive
    suffixes ("Senior Secured Floating Rate Notes", …).

    When ``deal_name`` (or a deal / series id prefix) is glued into the class
    field (``DRSLF 2018-70A SUB A`` / ``DRSLF 2020-78A A-1-R``), that prefix is
    removed before matching — including tokens shared across all peer classes.

    ``Class M-1 Subordinated Notes`` (tranche token + sub notes) → ``M1``, not ``SUB``.
    Bare subordinated notes → ``SUB`` at normalize time; EMS lookup tries ``PS`` → ``SUB`` → ``PS1``.
    Combo / combination notes → ``COMB``; EMS lookup tries ``COMB`` → ``COMBO``.
    ``Series 1 Combination Securities`` / ``Series I Combination Securities`` → ``SERIES1``
    (EMS ``S-1`` / ``Series I Combination Securities`` — same underlying tranche).
    Performance notes → ``P``; EMS lookup tries ``P`` → ``PERF`` → ``PERFORMANCE``.
    Tiered ``SUBA`` / ``SUBB`` ↔ trustee ``PSA`` / ``PSB`` /
    ``Subordinated Notes A`` / ``B``. Preferred / preference
    shares → ``PS2`` when sub notes are also present, else ``PS`` (preferred-only deals).
    Income notes / ``INCOME`` → ``INC`` when EMS lists ``INC``/``INCOME``, or when ``PS`` is
    not the subordinated / preference-share tranche; otherwise preference-share keys apply.
    ``Class A CP/LT/ST Notes`` → ``ACP`` / ``ALT`` / ``AST`` (EMS ``A-CP``, ``A-LT``, ``A-ST``).
    ``Class A-1 Loan`` / ``A1-R_Loan`` → ``A1L`` / ``A1RL`` (loan tranche suffix ``L``).
    """
    if not class_name:
        return ""
    raw_upper = _normalize_class_separators(
        _strip_deal_prefix_from_class(
            class_name,
            deal_name,
            peer_class_names=peer_class_names,
        )
    ).strip().upper()
    raw_upper = re.sub(r"\s+", " ", raw_upper)
    work_label, is_loan_tranche = _split_tranche_type_suffix(raw_upper)
    pref = _preferred_share_lookup_key(
        work_label,
        deal_maps=deal_maps,
        peer_class_names=peer_class_names,
        deal_name=deal_name,
    )
    if pref:
        return pref
    ps_tier = _ps_sub_tier_key(work_label)
    if ps_tier:
        return ps_tier
    tranche_sub = _tranche_key_over_subordinated_notes(work_label)
    if tranche_sub:
        return _with_loan_tranche_suffix(
            tranche_sub, raw_upper, is_loan=is_loan_tranche
        )
    sub = _subordinated_notes_key(work_label)
    if sub:
        return sub
    combo = _combo_notes_key(work_label)
    if combo:
        return combo
    series_comb = _series_combination_key(work_label)
    if series_comb:
        return series_comb
    series_short = _series_combination_short_key(work_label)
    if series_short:
        return series_short
    perf = _performance_notes_key(work_label)
    if perf:
        return perf
    inc = _income_notes_key(work_label)
    if inc:
        if deal_maps is not None and not deal_maps.has_inc_tranche_mapping():
            if deal_maps.ps_mapped_to_sub_or_pref():
                pref = _preferred_share_lookup_key(
                    work_label,
                    deal_maps=deal_maps,
                    peer_class_names=peer_class_names,
                    deal_name=deal_name,
                )
                if pref:
                    return pref
            else:
                return inc
        else:
            return inc
    cp_lt_st = _class_letter_cp_lt_st_key(work_label)
    if cp_lt_st:
        return cp_lt_st
    s = work_label
    for prefix in _CLASS_NAME_PREFIXES:
        if s.startswith(prefix):
            s = s[len(prefix) :].strip()
    lead = _TRANCHE_LEAD_TOKEN.match(s)
    if lead:
        token = _extend_tranche_lead_token(lead.group(1), s[lead.end() :])
        if token not in _DESCRIPTOR_TOKENS:
            core = normalize_trustee_name_key(token)
            if core:
                core = _CLASS_ALIASES.get(core, core)
                return _with_loan_tranche_suffix(
                    core, raw_upper, is_loan=is_loan_tranche
                )
    compact = normalize_trustee_name_key(s)
    compact = _CLASS_ALIASES.get(compact, compact)
    return _with_loan_tranche_suffix(compact, raw_upper, is_loan=is_loan_tranche)


def _income_notes_lookup_variants(
    deal_maps: DealTrancheMaps | None = None,
) -> tuple[str, ...]:
    """
    EMS keys for income notes / ``INCOME`` extraction labels.

    Prefer ``INC`` / ``INCOME``. When EMS has no ``INC`` row and ``PS`` is not the
    subordinated or preference-share tranche, also try ``PS`` (some deals store
    income notes under ``PS`` only).
    """
    variants: list[str] = ["INC", "INCOME"]
    if (
        deal_maps is not None
        and not deal_maps.has_inc_tranche_mapping()
        and not deal_maps.ps_mapped_to_sub_or_pref()
    ):
        variants.append("PS")
    return tuple(dict.fromkeys(variants))


def _with_loan_lr_lookup_variants(variants: tuple[str, ...]) -> tuple[str, ...]:
    """Some EMS rows use ``A1LR`` while the PDF prints ``A1-R_Loan`` → ``A1RL``."""
    out: list[str] = list(variants)
    for key in variants:
        m = re.fullmatch(r"([A-Z]\d+)RL", key)
        if m:
            alt = f"{m.group(1)}LR"
            if alt not in out:
                out.append(alt)
    return tuple(out)


def _with_revision_r2_variants(variants: tuple[str, ...]) -> tuple[str, ...]:
    """
    EMS often stores refinance ``R2`` keys (``A1R2``) while the PDF prints ``A-1-R`` → ``A1R``.
    """
    out: list[str] = list(variants)
    for key in variants:
        if key and re.fullmatch(r"[A-Z]\d+R", key):
            r2 = f"{key}2"
            if r2 not in out:
                out.append(r2)
    return tuple(out)


def _lookup_variants(
    normalized: str,
    *,
    deal_maps: DealTrancheMaps | None = None,
) -> tuple[str, ...]:
    if not normalized:
        return ()
    if normalized in ("INC", "INCOME"):
        return _income_notes_lookup_variants(deal_maps)
    alts = _LOOKUP_VARIANTS.get(normalized)
    if alts:
        return _with_loan_lr_lookup_variants(_with_revision_r2_variants(alts))
    tier = _sub_tier_lookup_variants(normalized)
    if tier:
        return _with_loan_lr_lookup_variants(_with_revision_r2_variants(tier))
    series = _series_combination_lookup_variants(normalized)
    if series:
        return series
    return _with_loan_lr_lookup_variants(_with_revision_r2_variants((normalized,)))


def _is_junk_mapping_key(key: str) -> bool:
    return bool(_JUNK_MAPPING_KEY.fullmatch(key))


def _resolve_sub_alias_collision(
    exact: list[tuple[str, str]],
) -> tuple[tuple[str, str] | None, str | None]:
    """
    When ``SUB`` and ``PS`` both appear in ``noteval_tranche_mapping``, prefer ``PS`` /
    ``PS1`` (typical EMS subordinated key) when unique; else ``SUB``.
    """
    ps_rows = [p for p in exact if normalize_trustee_name_key(p[0]) in ("PS", "PS1")]
    if len(ps_rows) == 1:
        return ps_rows[0], "preferred PS/PS1 trustee key"
    sub_rows = [
        p
        for p in exact
        if normalize_trustee_name_key(p[0]) == "SUB"
        or _subordinated_notes_key(str(p[0]).strip().upper()) is not None
    ]
    if len(sub_rows) == 1:
        return sub_rows[0], "preferred SUB trustee key"
    return None, None


def match_trustee_tranche_name(
    normalized: str,
    name_index: list[tuple[str, str]],
    *,
    deal_maps: DealTrancheMaps | None = None,
) -> tuple[str | None, str | None, str, str | None]:
    """
    Return (moodystrancheid, trustee_tranche_name, status, message).

    Both sides use ``normalize_class_label`` so trustee long names
    ("Class A-1 Senior …") and short EMS keys ("A1") align. Exact match only
    (no prefix/suffix) to avoid false positives such as SUB → B.

    Preference / preference shares also index the full compact trustee label
    (``PREFERENCESHARES``) so ``PS`` / ``PS2`` extraction keys can match EMS
    rows stored as ``Preference Shares`` in ``noteval_tranche_mapping``.
    """
    if not normalized:
        return None, None, "unmapped", "no class name to match"
    if not name_index:
        return None, None, "unmapped", "no trustee_tranche_name rows for deal"

    by_key: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for tname, tid in name_index:
        raw_upper = str(tname).strip().upper()
        key = normalize_class_label(tname, deal_maps=deal_maps)
        if not key or _is_junk_mapping_key(key):
            continue
        by_key[key].append((tname, tid))
        pref_full = _preference_share_full_key(raw_upper)
        if pref_full and pref_full != key:
            by_key[pref_full].append((tname, tid))
        for variant in _series_combination_lookup_variants(key) or ():
            if variant != key:
                by_key[variant].append((tname, tid))

    exact: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    matched_variant: str | None = None
    for variant in _lookup_variants(normalized, deal_maps=deal_maps):
        variant_hits: list[tuple[str, str]] = []
        for pair in by_key.get(variant, []):
            if pair not in seen:
                seen.add(pair)
                variant_hits.append(pair)
        if variant_hits:
            exact = variant_hits
            matched_variant = variant
            break

    if len(exact) == 1:
        msg = None
        if (
            normalized in ("INC", "INCOME")
            and matched_variant == "PS"
            and deal_maps is not None
            and not deal_maps.has_inc_tranche_mapping()
        ):
            msg = "income notes matched via PS (no INC row in EMS)"
        return exact[0][1], exact[0][0], "ok", msg
    if len(exact) > 1:
        ids = {tid for _, tid in exact}
        if len(ids) == 1:
            return exact[0][1], exact[0][0], "ok", "multiple names, same tranche_id"
        if normalized in _SUB_LOOKUP_KEYS or _SUB_TIER_KEY.fullmatch(normalized):
            picked, note = _resolve_sub_alias_collision(exact)
            if picked is not None:
                return picked[1], picked[0], "ok", note
        return None, None, "ambiguous", f"exact name collision: {exact!r}"

    return None, None, "unmapped", f"no trustee_tranche_name match for {normalized!r}"


def resolve_tranche(
    maps: DealTrancheMaps,
    *,
    cusip: str | None = None,
    cusips: list[str] | None = None,
    class_name: str | None = None,
    map_class: str | None = None,
    peer_class_names: list[str] | None = None,
    deal_name: str | None = None,
) -> MapResult:
    """Tier 1 (CDOnet CUSIP) when any CUSIP present; tier 2 (EMS name map) only when not."""
    candidates: list[str] = []
    for raw in cusips or ([] if cusip is None else [cusip]):
        nc = normalize_cusip(raw)
        if nc and nc not in candidates:
            candidates.append(nc)

    if candidates:
        ambiguous_notes: list[str] = []
        for nc in candidates:
            ids = maps.cusip_index.get(nc, set())
            if len(ids) == 1:
                tid = next(iter(ids))
                return MapResult(
                    moodystrancheid=tid,
                    map_tier="cusip",
                    map_status="ok",
                    map_message=(
                        f"matched via cusip {nc}"
                        if len(candidates) > 1
                        else None
                    ),
                    matched_cusip=nc,
                )
            if len(ids) > 1:
                ambiguous_notes.append(f"cusip {nc} ambiguous in CDOnet: {sorted(ids)}")

        if ambiguous_notes:
            return MapResult(
                moodystrancheid=None,
                map_tier="cusip",
                map_status="ambiguous",
                map_message="; ".join(ambiguous_notes),
            )
        # All CUSIPs were not found in CDOnet — fall through to name-based tier 2
        # so that non-standard identifiers (e.g. ISSUER172, ISSUER173 on Woodmont SUB/PS)
        # still resolve via noteval_tranche_mapping when a class name is available.
        _cusip_miss_msg = (
            f"no cusip in CDOnet CUSTOM_CDONET_TRANCHE_DATA for deal {maps.deal_id} "
            f"(tried: {', '.join(candidates)})"
        )
    else:
        _cusip_miss_msg = None

    norm = (map_class or "").strip()
    if not norm:
        norm = normalize_class_label(
            class_name,
            deal_maps=maps,
            peer_class_names=peer_class_names,
            deal_name=deal_name,
        )
    tid, tname, status, msg = match_trustee_tranche_name(
        norm, maps.name_index, deal_maps=maps
    )
    if status == "ok" and tid:
        # Resolved via name; annotate when CUSIPs were tried first and missed.
        combined_msg = msg
        if _cusip_miss_msg:
            combined_msg = (
                f"{_cusip_miss_msg}; resolved via name instead"
                if not combined_msg
                else f"{_cusip_miss_msg}; {combined_msg}; resolved via name"
            )
        return MapResult(
            moodystrancheid=str(tid),
            map_tier="cusip+name" if _cusip_miss_msg else "name",
            map_status="ok",
            trustee_tranche_name=tname,
            map_message=combined_msg,
        )
    if _cusip_miss_msg and not norm:
        return MapResult(
            moodystrancheid=None,
            map_tier="cusip",
            map_status="unmapped",
            map_message=_cusip_miss_msg,
        )
    if not norm:
        return MapResult(
            moodystrancheid=None,
            map_tier=None,
            map_status="unmapped",
            map_message="no cusip and no class name to match",
        )
    # Name lookup also failed; if CUSIPs were tried first, report the CUSIP miss as primary.
    if _cusip_miss_msg:
        return MapResult(
            moodystrancheid=None,
            map_tier="cusip",
            map_status="unmapped",
            map_message=_cusip_miss_msg,
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
        tid_to_names: dict[str, set[str]] = defaultdict(set)
        ems = _ems_db()
        cur.execute(_TIER2_SQL.format(ems_db=ems), (deal_id,))
        for tname, tranche_id in cur.fetchall():
            if tname is None or tranche_id is None:
                continue
            n = str(tname).strip()
            tid = str(tranche_id).strip()
            if not n or not tid:
                continue
            name_index.append((n, tid))
            tid_to_names[tid].add(n)
            # numeric moodystrancheid is itself a join key in cdo_noteval_tranches
            tid_to_names[tid].add(tid)
        name_index.sort(key=lambda x: len(x[0]), reverse=True)

        return DealTrancheMaps(
            deal_id=deal_id,
            cusip_index=dict(cusip_index),
            name_index=name_index,
            tranche_id_to_names={k: set(v) for k, v in tid_to_names.items()},
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


@dataclass
class DealNotevalTranches:
    """cdo_noteval_tranches rows for one (deal_id, payment_date), keyed by tranche_name."""

    deal_id: str
    payment_date: str
    by_name: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass
class DealTrancheMaster:
    """cdo_tranche_master rows for one deal_id, keyed by tranche_id (moodystrancheid)."""

    deal_id: str
    by_tranche_id: dict[str, dict[str, Any]] = field(default_factory=dict)


def _normalize_payment_date(payment_date: str | None) -> str:
    """Return YYYY-MM-DD; accepts ISO or YYYYMMDD."""
    if not payment_date:
        return ""
    s = payment_date.strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2}).*", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return s


def load_db_tranche_data(
    deal_id: str,
    payment_date: str,
    *,
    connection: Any | None = None,
) -> DealNotevalTranches:
    """Load cdo_noteval_tranches rows for (deal_id, payment_date) from EMS."""
    pd_iso = _normalize_payment_date(payment_date)
    if not pd_iso:
        return DealNotevalTranches(deal_id=str(deal_id), payment_date="")
    own_conn = connection is None
    conn = connection or _connect_pyodbc()
    try:
        ems = _ems_db()
        cur = conn.cursor()
        cur.execute(_NOTEVAL_TRANCHES_SQL.format(ems_db=ems), (str(deal_id).strip(), pd_iso))
        cols = [d[0] for d in cur.description]
        out: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            rec = dict(zip(cols, row))
            tname = rec.get("tranche_name")
            if tname is None:
                continue
            out[str(tname).strip()] = rec
        return DealNotevalTranches(
            deal_id=str(deal_id).strip(),
            payment_date=pd_iso,
            by_name=out,
        )
    finally:
        if own_conn:
            conn.close()


def load_tranche_master_data(
    deal_id: str,
    *,
    connection: Any | None = None,
) -> DealTrancheMaster:
    """Load ``cdo_tranche_master`` rows for ``deal_id`` keyed by ``tranche_id``."""
    own_conn = connection is None
    conn = connection or _connect_pyodbc()
    try:
        ems = _ems_db()
        cur = conn.cursor()
        cur.execute(_TRANCHE_MASTER_SQL.format(ems_db=ems), (str(deal_id).strip(),))
        cols = [d[0] for d in cur.description]
        out: dict[str, dict[str, Any]] = {}
        for row in cur.fetchall():
            rec = dict(zip(cols, row))
            tid = rec.get("tranche_id")
            if tid is None:
                continue
            out[str(tid).strip()] = rec
        return DealTrancheMaster(deal_id=str(deal_id).strip(), by_tranche_id=out)
    finally:
        if own_conn:
            conn.close()


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _to_float(value: Any) -> float | None:
    """Parse a money / rate cell into a float; ignores $, commas, and trailing %."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s.upper() in ("N/A", "NA", "—", "-", "--"):
        return None
    s = s.replace(",", "").replace("$", "").strip()
    is_pct = s.endswith("%")
    if is_pct:
        s = s[:-1].strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        v = float(s)
    except ValueError:
        m = _NUM_RE.search(s)
        if not m:
            return None
        try:
            v = float(m.group(0))
        except ValueError:
            return None
    if is_pct:
        v = v / 100.0
    return v


def _diff_amount(
    extracted: Any,
    db_value: Any,
    *,
    tolerance: float = 0.01,
    is_rate: bool = False,
) -> str:
    """Return '' if either side missing, 'match' if within tolerance, else signed delta.

    For ``is_rate=True``, the trustee value (e.g. ``5.06802%``) is parsed as a
    fraction and the DB value (e.g. ``5.06802``) is treated as a percent number;
    we align them before comparing.
    """
    e = _to_float(extracted)
    d = _to_float(db_value)
    # Treat a missing side as 0 when the other side is exactly 0 (within tolerance).
    # Common case: trustee prints 0.00 for deferred interest while DB stores NULL.
    if e is None and d is not None and abs(d) <= tolerance:
        return "match"
    if d is None and e is not None and abs(e) <= tolerance:
        return "match"
    if e is None or d is None:
        return ""
    if is_rate:
        # Trustee text with '%' was divided by 100; DB column stores percent number.
        # Re-scale extracted back to percent if the DB value looks like percent.
        if abs(e) < 1.5 and abs(d) > 1.5:
            e = e * 100.0
        elif abs(d) < 1.5 and abs(e) > 1.5:
            d = d * 100.0
        tolerance = max(tolerance, 0.001)
    delta = e - d
    if abs(delta) <= tolerance:
        return "match"
    return f"{delta:+.4f}" if abs(delta) < 1 else f"{delta:+.2f}"


def compare_tranche_to_db(
    extracted: dict[str, Any],
    db_row: dict[str, Any] | None,
) -> dict[str, str]:
    """Return diff_<field> + db_<field> values for one class row."""
    out: dict[str, str] = {}
    for field_name in DB_COMPARE_FIELDS:
        if db_row is None:
            out[f"db_{field_name}"] = ""
            out[f"diff_{field_name}"] = ""
            continue
        db_col = _DB_FIELD_FROM_SQL[field_name]
        db_val = db_row.get(db_col)
        out[f"db_{field_name}"] = "" if db_val is None else str(db_val)
        out[f"diff_{field_name}"] = _diff_amount(
            extracted.get(field_name),
            db_val,
            is_rate=(field_name == "interest_rate"),
        )
    return out


def compare_tranche_to_master(
    extracted: dict[str, Any],
    master_row: dict[str, Any] | None,
) -> dict[str, str]:
    """Compare export ``original_balance`` to ``cdo_tranche_master.orig_balance``."""
    if master_row is None:
        return {
            "db_orig_balance": "",
            "diff_original_balance": "",
        }
    db_val = master_row.get("orig_balance")
    return {
        "db_orig_balance": "" if db_val is None else str(db_val),
        "diff_original_balance": _diff_amount(
            extracted.get("original_balance"),
            db_val,
        ),
    }


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
        self._tranche_data: dict[tuple[str, str], DealNotevalTranches] = {}
        self._master_data: dict[str, DealTrancheMaster] = {}

    def maps_for_deal(self, deal_id: str) -> DealTrancheMaps:
        did = str(deal_id).strip()
        if did in self._deal_maps:
            return self._deal_maps[did]
        if self._use_db:
            self._deal_maps[did] = load_deal_maps_from_db(did, connection=self._connection)
            return self._deal_maps[did]
        return DealTrancheMaps(deal_id=did, cusip_index={}, name_index=[])

    def tranche_data_for(self, deal_id: str, payment_date: str) -> DealNotevalTranches:
        did = str(deal_id).strip()
        pd_iso = _normalize_payment_date(payment_date)
        key = (did, pd_iso)
        cached = self._tranche_data.get(key)
        if cached is not None:
            return cached
        if not self._use_db or not pd_iso:
            empty = DealNotevalTranches(deal_id=did, payment_date=pd_iso)
            self._tranche_data[key] = empty
            return empty
        data = load_db_tranche_data(did, pd_iso, connection=self._connection)
        self._tranche_data[key] = data
        return data

    def db_row_for(
        self,
        deal_id: str,
        payment_date: str,
        *,
        moodystrancheid: str | None,
    ) -> tuple[dict[str, Any] | None, str]:
        """Return (cdo_noteval_tranches row, matched_name) for the mapped tranche.

        Tries every name registered for ``moodystrancheid`` in
        ``noteval_tranche_mapping`` (and the moodystrancheid itself) until one
        appears as ``cdo_noteval_tranches.tranche_name`` for that
        (deal_id, payment_date).
        """
        if not moodystrancheid:
            return None, ""
        data = self.tranche_data_for(deal_id, payment_date)
        if not data.by_name:
            return None, ""
        maps = self.maps_for_deal(deal_id)
        candidates = maps.names_for_tranche_id(moodystrancheid)
        if str(moodystrancheid).strip() not in candidates:
            candidates.append(str(moodystrancheid).strip())
        for name in candidates:
            row = data.by_name.get(name)
            if row is not None:
                return row, name
        return None, ""

    def tranche_master_for(self, deal_id: str) -> DealTrancheMaster:
        did = str(deal_id).strip()
        cached = self._master_data.get(did)
        if cached is not None:
            return cached
        if not self._use_db:
            empty = DealTrancheMaster(deal_id=did)
            self._master_data[did] = empty
            return empty
        data = load_tranche_master_data(did, connection=self._connection)
        self._master_data[did] = data
        return data

    def master_row_for(
        self,
        deal_id: str,
        *,
        moodystrancheid: str | None,
    ) -> tuple[dict[str, Any] | None, str]:
        """Return (``cdo_tranche_master`` row, tranche_id) for the mapped tranche."""
        if not moodystrancheid:
            return None, ""
        tid = str(moodystrancheid).strip()
        if not tid:
            return None, ""
        data = self.tranche_master_for(deal_id)
        row = data.by_tranche_id.get(tid)
        if row is not None:
            return row, tid
        return None, ""

    def resolve(
        self,
        deal_id: str,
        *,
        cusip: str | None = None,
        cusips: list[str] | None = None,
        class_name: str | None = None,
        map_class: str | None = None,
        peer_class_names: list[str] | None = None,
        deal_name: str | None = None,
    ) -> MapResult:
        return resolve_tranche(
            self.maps_for_deal(deal_id),
            cusip=cusip,
            cusips=cusips,
            class_name=class_name,
            map_class=map_class,
            peer_class_names=peer_class_names,
            deal_name=deal_name,
        )

    def enrich_class_row(
        self,
        row: list[Any],
        *,
        deal_id_col: int = 0,
        payment_date_col: int = 1,
        class_name_col: int = 2,
        cusip_col: int = 3,
        cusips: list[str] | None = None,
        peer_class_names: list[str] | None = None,
        deal_name: str | None = None,
        extracted: dict[str, Any] | None = None,
        compare_db: bool = False,
    ) -> list[Any]:
        """Append mapping columns (and optional DB-compare columns) to a class export row."""
        if len(row) <= class_name_col:
            base = row + ["", "", "", "", ""]
            if compare_db:
                base += [""] * len(DB_COMPARE_HEADERS)
            return base
        deal_id = str(row[deal_id_col] or "").strip()
        class_name = str(row[class_name_col] or "").strip()
        cusip = str(row[cusip_col] or "").strip()
        listing_cusips = list(cusips) if cusips else []
        if not listing_cusips and cusip:
            listing_cusips = [cusip]
        r = self.resolve(
            deal_id,
            cusips=listing_cusips or None,
            cusip=None if listing_cusips else (cusip or None),
            class_name=class_name,
            peer_class_names=peer_class_names,
            deal_name=deal_name,
        )
        out = list(row)
        if r.matched_cusip:
            while len(out) <= cusip_col:
                out.append("")
            out[cusip_col] = r.matched_cusip
        out = out + [
            r.moodystrancheid or "",
            r.trustee_tranche_name or "",
            r.map_tier or "",
            r.map_status or "",
            r.map_message or "",
        ]
        if not compare_db:
            return out
        payment_date = (
            str(row[payment_date_col] or "").strip()
            if payment_date_col < len(row)
            else ""
        )
        db_row, matched_name = self.db_row_for(
            deal_id, payment_date, moodystrancheid=r.moodystrancheid
        )
        diffs = compare_tranche_to_db(extracted or {}, db_row)
        db_status = (
            "ok"
            if db_row is not None
            else ("no_data" if not payment_date else "no_match")
        )
        for f in DB_COMPARE_FIELDS:
            out.append(diffs.get(f"db_{f}", ""))
        out.append(matched_name)
        out.append(db_status)
        for f in DB_COMPARE_FIELDS:
            out.append(diffs.get(f"diff_{f}", ""))
        return out


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
