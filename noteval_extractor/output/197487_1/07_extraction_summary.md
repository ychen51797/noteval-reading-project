# Extraction Summary

## Extracted Data

### Deal / report overview
| Field | Value |
|-------|-------|
| Deal name | CIFC Funding 2016-1. Ltd. |
| Payment / distribution date | March 26, 2026 |
| Currency | US$ |

### Key counts
| Item | Count |
|------|-------|
| Classes in 02 | 22 |
| Waterfall lines in 04 | 9 (representative; full grids pp.7–15) |
| Logical disbursement rows in 06 | 0 (**file omitted**) |
| Fee rows (approx) | 3 in fee mirror |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | Y | **Distribution in US$** on p.2 folded into **`02`** (no `03`) |
| Has waterfall / proceeds table? | Y | Available / Optimal / Paid / Unpaid |
| Has deferred interest section? | Y | p.3 interest detail |
| Has logical disbursements (11.1-style)? | N | No Section 11.1 ladder; **grid waterfall** only → **`06` omitted** |

### Deal layout (see `extraction-templates.md`)
| Family | Applies? |
|--------|------------|
| Grid / table waterfall | Y |
| Indenture-style Section 11.1 | N |
| Logical disbursement style | N |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | Distribution **Total** current `$49,250,000.00` on p.2; NVR interest **Total** `$49,250,000.00` on p.3 |
| Waterfall paid vs proceeds | Interest pool 197,044.46 on p.5; principal pool 3,994,397.78 |
| Internal consistency | Determination 25-Mar-2026; payment 26-Mar-2026 |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | complete |
| 02_tranche_class_balances.md | complete — includes **Distribution in US$** / cross-checks in **`02`** |
| 04_interest_principal_waterfall.md | partial — representative rows |
| 05_note_balance_deferred_interest.md | complete |
| 06_logical_disbursements.md | **omitted** — not logical-disbursement ladder layout |

## Completeness Checklist
- [x] All applicable files **01**, **02**, **04**, **05**, **06** exist or N/A documented here (no `03`)
- [x] Counts and flags match body extractions
- [x] Cross-checks run; discrepancies explained in **Notes**

## Source Text

See per-file Source Text.
