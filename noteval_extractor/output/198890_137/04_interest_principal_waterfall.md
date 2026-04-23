# Interest and Principal Waterfall

## Extracted Data

### Section identification
| Field | Value |
|-------|-------|
| Section title(s) as printed | Waterfall Payment Per **Section 11.1** — Disbursements of Monies from Payment Account; **Per Section 10.6 (b)(iv)** of the Indenture |
| Funds type (interest / principal / combined) | **Interest Proceeds** priority (pp.4–5) then **Principal Proceeds** priority (pp.6–8) |

### Waterfall table
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| INT-HDR | Interest Proceeds applied per **Priority of Interest Proceeds** (opening context) | | | 8,163,247.48 | | Pool lines: **REGATTA XX FDG - INTEREST COLL** 8,163,247.48; RSV 0.00 — p.4 |
| (A)(1) | **Taxes**, governmental fees, registered office fees (CAP) | 21,796.53 | | 8,141,450.95 | | PDF shows **Amount** 45,575.28 and **Paid** 21,796.53 ×2 then **Running Total** 8,141,450.95 |
| (A)(2)-4(i) | **Administrative Expenses** — tier 4(i) | 90,005.85 | | 8,117,672.20 | | Paid 23,778.75 also shown on adjacent line — use primary **Amount** line 90,005.85 per PDF layout |
| (B) | **Senior Management Fee** (Collateral Manager) | 186,827.41 | | 7,930,844.79 | | |
| (C) | Hedge Counterparty amounts (pro rata bucket) | 0.00 | | 7,930,844.79 | | |
| (D)-1 | Class X — current interest | 39,790.20 | | 7,891,054.59 | | |
| (D)-2 | Class A-R — current interest | 3,881,752.00 | | 4,009,302.59 | | |
| (D)-3 | Class X — **Principal Amortization** | 857,142.86 | | 3,152,159.73 | | |
| (E) | Class B-R — interest | 783,328.50 | | 2,368,831.23 | | |
| (G) | Class C-R — interest | 406,664.25 | | 1,962,166.98 | | |
| (I) | Class D-1-R / D-2-R — interest | 470,414.25; 94,027.38 | | 1,397,725.35 | | Combined step (I): two paid lines on p.5 |
| (K) | Class E-R — interest | 321,457.13 | | 1,076,268.23 | | |
| (Q) | **Subordinated Management Fee** (accrued/unpaid) | 435,930.62 | | 640,337.61 | | |
| (R)(ii) | **Administrative Expenses** not paid under (A)(2) cap — sub-tier (ii) | 66,227.10 | | 574,110.51 | | |
| (V) | Subordinated Notes — **Target Return** distribution | 574,110.51 | | 0.00 | | |
| PR-HDR | **Principal Proceeds** — opening available (after interest diversion line) | | | 2,774,745.48 | | p.5–6 |
| PR-(L) | Reinvestment Period — **Collection Account** / collateral purchase | 2,774,745.48 | | 0.00 | | Principal **Paid** exhausts pool this period — p.6 |

> **Column semantics:** PDF header **Amount | Paid | Running Total** — mapped **Paid** → **Amount paid**; **Running Total** → **Amount available / running**. Long legal **Item** text truncated in some rows; see **`06_logical_disbursements.md`** for clause text.

### Fees extracted separately (optional mirror)
| Fee name | Rate or basis (if stated) | Paid | Notes |
|----------|----------------------------|------|-------|
| Senior Management Fee | Clause (B) | 186,827.41 | p.4 |
| Subordinated Management Fee | Clause (Q) | 435,930.62 | p.5 |
| Administrative Expenses (4(i) tier) | Administrative Expense Cap | 90,005.85 | p.4 |
| Administrative Expenses (R)(ii) | Post-cap / clause (R) | 66,227.10 | p.5 |

## Completeness Checklist
- [x] Full waterfall section captured in table form (or multi-table with clear headings)
- [x] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [x] All fee lines that affect note valuation captured
- [x] Subtotals / totals match detail or variance explained

## Source Text

**Page 4** (opening + taxes + admin + senior fee + start of note interest)
```
Waterfall Payment Per Section 11.1 As of Date: 4/15/2026
Per Section 10.6 (b)(iv) of the Indenture Amount  Paid Running Total
...
REGATTA XX FDG - INTEREST COLL 8,163,247.48
...
(A) (1) first, to the payment of Taxes, governmental fees and registered CAP 45,575.28$                                 
office fees ... 21,796.53 21,796.53 8,141,450.95
...
4(i) 90,005.85$             23,778.75 8,117,672.20 23,778.75$     
(B) to pay to the Collateral Manager ... Senior Management Fee 186,827.41 186,827.41 7,930,844.79
...
(D) ... Class X - Int 39,790.20$             39,790.20 7,891,054.59
Class AR $3,881,752.00 3,881,752.00 4,009,302.59
Class X - Amort $857,142.86 857,142.86 3,152,159.73
(E) ... Class BR 783,328.50$           783,328.50$           $2,368,831.23
```

**Page 5** (tail of interest waterfall)
```
(G) ... Class CR 406,664.25$           406,664.25 1,962,166.98
(I) ... Class D1R 470,414.25$           470,414.25 1,491,752.73
Class D2R 94,027.38$             94,027.38 1,397,725.35
(K) ... Class ER $321,457.13 321,457.13 1,076,268.23
(Q) ... Subordinated 435,930.62 435,930.62 640,337.61
(R) ... (ii) 66,227.10 66,227.10 574,110.51
(V) ... Subordinated Notes ... 574,110.51 574,110.51 0.00
```

**Page 6** (principal priority)
```
Principal Proceeds ... 2,774,745.48
(L) (i) during the Reinvestment Period, to the Collection Account as 2,774,745.48$        2,774,745.48 0.00
```
