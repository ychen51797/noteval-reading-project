# Interest and Principal Waterfall

## Extracted Data

### Section identification
| Field | Value |
|-------|-------|
| Section title(s) as printed | Section 11.1 — Disbursements of Cash from Payment Account; Interest Proceeds (11.1(a)(i)); Principal Proceeds (11.1(a)(ii)) |
| Funds type (interest / principal / combined) | Interest then principal; separate running-balance pairs on each line |

### Waterfall table
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| INT-HDR | Interest Proceeds pool (header) | | | 46,899.92 | | |
| I-A1 | (A)(1) Taxes and governmental fees | 0.00 | | 46,899.92 | | Trailing pair: **paid** then **running** per line |
| I-A2-first | (A)(2) first — Collateral Trustee / Bank (Section 6.7) | 10,000.00 | | 36,899.92 | | |
| I-B | (B) Senior Collateral Management Fee | 1,722.20 | | 35,177.72 | | |
| I-C | (C) Hedge Counterparty | 0.00 | | 35,177.72 | | |
| I-D | (D) Class A / A-L interest | 0.00 | | 35,177.72 | | |
| I-E | (E) Class B interest | 0.00 | | 35,177.72 | | |
| I-S | (S) Subordinated Collateral Management Fee | 2,870.33 | | 32,307.39 | | |
| I-W | (W) Subordinated Notes (Incentive Fee Threshold) | 32,307.39 | | 0.00 | | |
| PR-HDR | Principal Proceeds (less holdback) | | | 756,001.79 | | p.5 |
| P-R | (R) Subordinated Notes — principal | 756,001.79 | | 0.00 | | p.8 |

> **Fee-style rows:** Trustee / admin and **Collateral Management Fee** lines included above.

### Fees extracted separately (optional mirror)
| Fee name | Rate or basis (if stated) | Paid | Notes |
|----------|----------------------------|------|-------|
| Senior Collateral Management Fee | Clause (B) | 1,722.20 | p.2 |
| Subordinated Collateral Management Fee | Clause (S) | 2,870.33 | p.4 |
| Collateral Trustee / Bank (admin) | Clause (A)(2) first tier | 10,000.00 | p.1 |

## Completeness Checklist
- [x] Full waterfall section captured in table form (or multi-table with clear headings)
- [x] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [x] All fee lines that affect note valuation captured
- [x] Subtotals / totals match detail or variance explained

## Source Text

**Page 1**
```
Section 11.1     Disbursements of Cash from Payment Account Interest Proceeds $46,899.92
(A) (1) first, to the payment of taxes and governmental fees owing by the $0.00 $46,899.92
...
first, to the Collateral Trustee pursuant to Section 6.7 ... $10,000.00 $36,899.92
```

**Page 2**
```
(B) to the payment of the Senior Collateral Management Fee ... $1,722.20 $35,177.72
```

**Page 4**
```
(S) to the payment of the accrued and unpaid Subordinated Collateral
Management Fee ... $2,870.33 $32,307.39
(W) to the Holders of the Subordinated Notes until the Incentive Collateral 32,307.39 $0.00
```

**Page 8**
```
(R) to the Holders of the Subordinated Notes until the Incentive Collateral $756,001.79 $0.00
```
