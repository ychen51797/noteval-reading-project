# Extraction Summary

## Extracted Data

### Deal / report overview
| Field | Value |
|-------|-------|
| Deal name | Regatta XX Funding, LTD. |
| Payment / distribution date | **Payment date 4/15/2026**; determination **4/3/2026** |
| Currency | US$ |

### Key counts
| Item | Count |
|------|-------|
| Classes in 02 | 8 |
| Waterfall lines in 04 | 18 (interest + principal highlights; full ladder pp.4–8) |
| Logical disbursement rows in 06 | 16 (Section 11.1 clause mapping) |
| Fee rows (approx) | 4+ (taxes, admin, senior / sub management fees) |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | N | Class economics on **p.2** NVR table only (**no `03`**) |
| Has waterfall / proceeds table? | Y | **Section 10.6(b)(iv)** Amount / Paid / Running Total |
| Has deferred interest section? | Y | Small **default/deferred** amounts on D-2-R / E-R; senior fee block **10.6(b)(v)** on p.3 |
| Has logical disbursements (11.1-style)? | Y | Full **Section 11.1** priority text with embedded numbers |

### Deal layout (see `extraction-templates.md`)
| Family | Applies? |
|--------|------------|
| Grid / table waterfall | Y — **Paid** vs **Running Total** columns |
| Indenture-style Section 11.1 | Y |
| Logical disbursement style | Partial — same pages as **`04`**, structured as clause ladder in **`06`** |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | Principal payable **857,142.86** (Class X); matches **TOTAL** row |
| Waterfall paid vs class/distribution totals in `02` | Interest / dividend totals align with **Section 11.1** paid lines (e.g. Class A-R interest **3,881,752.00**; Subordinated **(V)** **574,110.51**) |
| Internal consistency | **p.9** Interest Collection: paid out **8,163,247.48** matches interest pool; Principal **2,774,745.48** remains after payment per **p.9** |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | complete |
| 02_tranche_class_balances.md | complete — ISIN cells not legible as discrete values in chunk |
| 04_interest_principal_waterfall.md | partial — representative + closing balances; full text on pp.4–8 |
| 05_note_balance_deferred_interest.md | partial — **10.6(b)(v)** fee block + NVR deferred snippets |
| 06_logical_disbursements.md | partial — major clauses; continuations summarized |

## Completeness Checklist
- [x] All applicable files **01**, **02**, **04**, **05**, **06** exist or N/A documented here (no `03`)
- [x] Counts and flags match body extractions
- [x] Cross-checks run; discrepancies explained in **Notes**

## Source Text

See per-file Source Text.
