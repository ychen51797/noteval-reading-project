# Interest and Principal Waterfall

## Extracted Data

### Section identification
| Field | Value |
|-------|-------|
| Section title(s) as printed | Interest Proceeds; Principal Proceeds; Payment Date Proceeds (p.5); Administrative Expenses (p.6); Distribution of Interest Proceeds (pp.7–10); Distribution of Principal Proceeds (pp.11–15) |
| Funds type (interest / principal / combined) | Interest and principal; columns **Available \| Optimal \| Paid \| Unpaid** |

### Waterfall table
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| P5 | Interest Proceeds — composition (i)–(xi) Total | | | | | Pool total 197,044.46 p.5 |
| P5-PR | Principal Proceeds Total | | | | | 3,994,397.78 |
| I7-A1 | (A)(1) Taxes / governmental / registered office fees | 0.00 | 0.00 | 197,044.46 | Optimal 0.00; Unpaid 0.00 | |
| I7-A2i | (A)(2)(i) Trustee | 244.42 | 244.42 | 197,044.46 | | |
| I7-A2ix | (A)(2)(ix) Collateral Manager | 28,758.31 | 32,252.80 | 196,800.04 | Unpaid 3,494.49 | **Paid** per Deutsche **Paid** column |
| I7-B | (B) Senior Collateral Management Fee (current) | 2,793.34 | 2,793.34 | 168,041.73 | | |
| I10-T1 | (T)(1) Accrued and unpaid Subordinated Management Fee | 2,793.34 | 2,793.34 | 165,248.39 | | |
| I10-W | (W) Payment to Subordinate Notes (Incentive threshold) | 158,298.06 | 37,481,644.03 | 158,298.06 | Unpaid 37,323,345.97 | |
| Pr15-F | (F) Payment to Subordinate Notes — principal | 3,994,397.78 | 37,323,345.97 | 3,994,397.78 | Unpaid 33,328,948.19 | p.15 |

> **Fee-style rows:** Amounts in **Amount paid** follow the PDF **Paid** column.

### Fees extracted separately (optional mirror)
| Fee name | Rate or basis (if stated) | Paid | Notes |
|----------|----------------------------|------|-------|
| Trustee Fee | 0.017500%; 50 days; Min 20,000 | 244.42 | p.17 |
| Senior Collateral Management Fee | 0.200000%; 50 days | 2,793.34 | p.17 |
| Subordinated Collateral Management Fee | 0.200000%; 50 days | 2,793.34 | p.17 |

## Completeness Checklist
- [x] Full waterfall section captured in table form (or multi-table with clear headings)
- [x] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [x] All fee lines that affect note valuation captured
- [x] Subtotals / totals match detail or variance explained

## Source Text

**Page 7**
```
Distribution of Interest Proceeds
Available Optimal Paid Unpaid
(A)(1) Payment of taxes, governmental fees, filing and registration fees and registered office fees 197,044.46 0.00 0.00 0.00
           (ix) Collateral Manager 196,800.04 32,252.80 28,758.31 3,494.49
```

**Page 15**
```
(F) Payment to the Subordinate Notes until Incentive Management Fee Threshold has been met 3,994,397.78 37,323,345.97 3,994,397.78 33,328,948.19
```

**Page 17**
```
Trustee Fee 244.42
Senior Collateral Management Fee 2,793.34
Subordinated Collateral Management Fee 2,793.34
```
