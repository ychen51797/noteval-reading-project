# Extraction Summary

## Extracted Data

### Deal / report overview
| Field | Value |
|-------|-------|
| Deal name | ICG Euro CLO 2023-2 DAC |
| Payment / distribution date | Next payment **July 28, 2025**; as-of **July 10, 2025** |
| Currency | EUR (waterfalls labeled **Payments (EUR)**) |

### Key counts
| Item | Count |
|------|-------|
| Classes in 02 | 11 |
| Waterfall lines in 04 | 28 representative rows (interest + principal; full ladders pp.4–11) |
| Logical disbursement rows in 06 | 0 (section N/A) |
| Fee rows (approx) | 6+ in waterfall + fee mirror (trustee, admin, senior/sub management fees) |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | Y | **Distribution Summary** on p.3 folded into **`02`** (primary + optional distribution grid); **no `03`** |
| Has waterfall / proceeds table? | Y | **Interest Priority of Payments** pp.4–7; **Principal Priority of Payments** pp.8–11 |
| Has deferred interest section? | Partial | Deferred-interest **steps** in interest waterfall at **0.00**; no separate note-balance / deferred ledger |
| Has logical disbursements (11.1-style)? | N | Tabular priority-of-payments only — captured in **`04`**, not **`06`** |

### Deal layout (see `extraction-templates.md`)
| Family | Applies? |
|--------|------------|
| Grid / table waterfall | Y — U.S. Bank CLO payment summary |
| Indenture-style Section 11.1 | N |
| Logical disbursement style | N |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | Principal paid column sums to **312,500.00**; matches totals row **312,500.00** |
| Waterfall paid vs class/distribution totals in `02` | Sum of per-class **Interest payment** in **`02`** = **4,642,162.43**; matches p.3 totals row; interest waterfall ends at **0.00** available after **(DD)** |
| Internal consistency | **As of 7/10/2025** and **Next Payment 7/28/2025** consistent on pp.1–3 and section headers |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | complete |
| 02_tranche_class_balances.md | complete — includes optional distribution grid from p.3 |
| 04_interest_principal_waterfall.md | partial — representative rows + opening/closing pools; full ladders on pp.4–11 |
| 05_note_balance_deferred_interest.md | N/A — no standalone note balance section |
| 06_logical_disbursements.md | N/A — no Section 11.1-style ladder |

## Completeness Checklist
- [x] All applicable files **01**, **02**, **04**, **05**, **06** exist or N/A documented here (no `03`)
- [x] Counts and flags match body extractions
- [x] Cross-checks run; discrepancies explained in **Notes**

## Source Text

See per-file Source Text.
