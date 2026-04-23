# Extraction Summary

## Extracted Data

### Deal / report overview
| Field | Value |
|-------|-------|
| Deal name | 522 Funding CLO 2021-7, LTD. |
| Payment / distribution date | March 27, 2026 |
| Currency | US$ |

### Key counts
| Item | Count |
|------|-------|
| Classes in 02 | 7 |
| Waterfall lines in 04 | 14 (representative; full ladder pp.1–8) |
| Logical disbursement rows in 06 | 15 |
| Fee rows (approx) | 3 in fee mirror |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | N | No separate **Distribution in US$** page; class totals on p.9 in **`02`** |
| Has waterfall / proceeds table? | Y | Section 11.1 — **indenture / logical disbursement** layout; also summarized in **`04`** as paid vs running |
| Has deferred interest section? | Y | Clauses in 11.1; trustee TOTALS show `$0.00` deferred |
| Has logical disbursements (11.1-style)? | Y | pp.1–8 primary content |

### Deal layout (see `extraction-templates.md`)
| Family | Applies? |
|--------|------------|
| Grid / table waterfall | Partial — two `$` per line, not full Deutsche-style column headers |
| Indenture-style Section 11.1 | Y |
| Logical disbursement style | Y |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | Original principals total `$407,900,000.00` on p.9 |
| Waterfall paid vs header | Interest: `$10,000 + $1,722.20 + $2,870.33 + $32,307.39 = $46,899.92`; Principal `(R)` `$756,001.79` matches header |
| Internal consistency | Payment date March 27, 2026 across 01 and p.9 |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | complete |
| 02_tranche_class_balances.md | complete — includes **Original balance** column |
| 04_interest_principal_waterfall.md | partial — representative waterfall rows |
| 05_note_balance_deferred_interest.md | complete |
| 06_logical_disbursements.md | complete — primary ladder |

## Completeness Checklist
- [x] All applicable files **01**, **02**, **04**, **05**, **06** exist or N/A documented here (no `03`)
- [x] Counts and flags match body extractions
- [x] Cross-checks run; discrepancies explained in **Notes**

## Source Text

See per-file Source Text.
