# Extraction Summary

## Extracted Data

### Deal / report overview
| Field | Value |
|-------|-------|
| Deal name | KKR CLO 36 Ltd. |
| Payment / distribution date | **September 3, 2025**; determination **September 2, 2025** |
| Currency | US$ |

### Key counts
| Item | Count |
|------|-------|
| Classes in 02 (primary) | 6 (+ **Totals**) — consolidated **p.4** |
| Listing rows in 02 (`### Tranche by listing`) | 18 (6 economic classes × 3 programs: **Reg S**, **Rule 144A**, **Accredited Investor**) |
| Waterfall lines in 04 | 4 (redemption / collection lines on **p.3**) |
| Logical disbursement rows in 06 | 0 (section N/A) |
| Fee rows (approx) | 0 in chunk (admin report referenced off-PDF) |

### Critical flags
| Flag | Value | Notes |
|------|-------|-------|
| Per-class distribution grid in 02? | N | No **Distribution in US$** grid; **primary + listing** tables |
| Multi-listing tranches? | **Y** | Same economics under **Reg S** / **144A** / **AI** with **different ISINs and/or CUSIPs** (this PDF: **CUSIPs** in **`02`** listing rows; **ISIN** blank) |
| Has waterfall / proceeds table? | Partial | **p.3** redemption proceeds bullets; full waterfall likely **p.9** per TOC (not in file) |
| Has deferred interest section? | Y | **$0.00** in schedule excerpt; primary **p.4** class lines use **0.00** for deferred-style column |
| Has logical disbursements (11.1-style)? | N |

### Deal layout (see `extraction-templates.md`)
| Family | Applies? |
|--------|------------|
| Grid / table waterfall | Partial |
| Indenture-style Section 11.1 | N |
| Logical disbursement style | N |

### Cross-checks
| Check | Result |
|-------|--------|
| Sum of class principals vs report totals | **410,000,000.00** principal payable = **p.4 Totals**; **395,000,000.00** = **p.6** 144A-only sub-total (see **`02`** supplementary) |
| Multi-listing: sum of **Tranche by listing** vs primary **`02`** / PDF | **Y** — e.g. Class A listing principal **15M + 300M + 0 = 315M**; listing interest **119,982.50 + 2,399,650.00 = 2,519,632.50** (matches **p.4** Class A) |
| Waterfall paid vs class/distribution totals in `02` | **p.3** **Re-Pricing Proceeds Principal** **410,000,000.00** aligns with **p.4 Totals** principal payable |
| Internal consistency | Payment **3-Sep-25** / Record **19-Aug-25** consistent on **pp.4–7** |

### Extraction files status
| File | Status (complete / partial / N/A) |
|------|-----------------------------------|
| 01_report_metadata.md | complete |
| 02_tranche_class_balances.md | complete — **primary (p.4)** + **`### Tranche by listing`** (pp.5–7) |
| 04_interest_principal_waterfall.md | partial — **p.3** only |
| 05_note_balance_deferred_interest.md | partial |
| 06_logical_disbursements.md | N/A |

## Completeness Checklist
- [x] All applicable files **01**, **02**, **04**, **05**, **06** exist or N/A documented here (no `03`)
- [x] Counts and flags match body extractions
- [x] Cross-checks run; discrepancies explained in **Notes**

## Source Text

See per-file Source Text.
