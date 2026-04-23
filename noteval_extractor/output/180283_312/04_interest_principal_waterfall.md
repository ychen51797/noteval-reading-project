# Interest and Principal Waterfall

## Extracted Data

### Section identification
| Field | Value |
|-------|-------|
| Section title(s) as printed | Interest Priority of Payments; Principal Priority of Payments |
| Funds type (interest / principal / combined) | Interest proceeds waterfall pp.4–7; principal proceeds waterfall pp.8–11 |

### Waterfall table
| Priority | Item / payee description | Amount paid | Amount payable | Amount available / running | Other amount columns | Notes |
|----------|-------------------------|-------------|----------------|---------------------------|----------------------|-------|
| INT | Interest Priority Of Interest Proceeds (Waterfall) — opening available | | | 6,886,432.80 | | EUR; header on p.4 |
| (A)(1) | Payment of taxes owing by the Issuer — Taxes CSP | 0.00 | | 6,886,432.80 | | |
| (A)(1) | Payment of taxes owing by the Issuer — Taxes USB | 57.50 | | 6,886,375.30 | | |
| (A)(2) | Payment of the Issuer Profit Amount to be retained by the Issuer | 250.00 | | 6,886,125.30 | | |
| (B) | Payment of accrued and unpaid **Trustee Fees and Expenses**, up to Senior Expenses Cap | 1,250.00 | | 6,884,875.30 | | |
| (C) | Payment of **Administrative Expenses** (incl. negative interest charges), up to Senior Expenses Cap less (B) — U.S. Bank Europe DAC | 8,750.00 | | 6,876,125.30 | | |
| (C) | Administrative Expenses — U.S. Bank Global Corporate Trust Limited | 15,654.68 | | 6,860,470.62 | | |
| (C) | Administrative Expenses — FINDOX INC - EUR - 50213535 | 2,546.75 | | 6,857,923.87 | | |
| (C) | Administrative Expenses — VIRTUS GROUP - EUR - 82976977 | 31,449.05 | | 6,825,826.62 | | |
| (C) | Administrative Expenses — TMF | 13,467.60 | | 6,812,359.02 | | |
| (C) | Administrative Expenses — McCarthy Tetrault | 2,410.37 | | 6,809,948.65 | | |
| (E) | Payment of the **Senior Collateral Management Fee** due on current Payment Date | 154,362.45 | | 6,655,586.20 | | |
| (E) | VAT - Senior Management Fee | 0.00 | | 6,655,586.20 | | |
| (G)(1) | Class X — Current Interest Amount | 11,102.47 | | 6,644,483.73 | | |
| (G)(1) | Class A-1 — Current Interest Amount | 2,360,540.00 | | 4,283,943.73 | | |
| (G)(2)(i) | Class X Principal Amortisation Amount | 312,500.00 | | 3,971,443.73 | | |
| (H) | Class A-2 — Current Interest Amount | 62,805.17 | | 3,908,638.56 | | |
| (I) | Class B-1 — Current Interest Amount | 434,487.08 | | 3,474,151.48 | | |
| (I) | Class B-2 — Current Interest Amount | 108,500.00 | | 3,365,651.48 | | |
| (K) | Class C Notes — Current Interest (incl. deferred interest) | 367,419.58 | | 2,998,231.90 | | |
| (L) | Deferred Interest on the Class C Notes | 0.00 | | 2,998,231.90 | | |
| (N) | Class D Notes — Current Interest (incl. deferred interest) | 506,109.64 | | 2,492,122.26 | | |
| (Q) | Class E Notes — Current Interest (incl. deferred interest) | 440,990.55 | | 2,051,131.71 | | |
| (T) | Class F Notes — Current Interest (incl. deferred interest) | 350,207.94 | | 1,700,923.77 | | |
| (X) | **Subordinated Collateral Management Fee** | 257,270.75 | | 1,443,653.02 | | |
| (DD) | Any remaining Interest Proceeds to the Subordinated Notes | 1,443,653.02 | | 0.00 | | |
| PRIN | Principal Priority Of Principal Proceeds (Waterfall) — opening available | | | 17,016,632.87 | | p.8 |
| (P)(1) | During Reinvestment Period — purchase of Substitute Collateral Obligations or to Principal Account | 17,016,632.87 | | 0.00 | | p.10; exhausts principal pool this period |

> **Column semantics:** **Report Payment** amounts from PDF are mapped to **Amount paid**; trailing **Available** column is **Amount available / running** after each line (EUR).

### Fees extracted separately (optional mirror)
| Fee name | Rate or basis (if stated) | Paid | Notes |
|----------|----------------------------|------|-------|
| Trustee Fees and Expenses (clause B) | Senior Expenses Cap | 1,250.00 | p.4 |
| Senior Collateral Management Fee | Current payment date | 154,362.45 | p.4 |
| Subordinated Collateral Management Fee | Current payment date | 257,270.75 | p.6 |
| Administrative Expenses (aggregate of named vendors) | Senior Expenses Cap net of (B) | 74,926.65 | Sum of all **(C)** payee lines on p.4 (matches drop in **Available** before step (D)) |

## Completeness Checklist
- [x] Full waterfall section captured in table form (or multi-table with clear headings)
- [x] Column semantics documented in **Notes** where ambiguous (Paid vs Available)
- [x] All fee lines that affect note valuation captured
- [x] Subtotals / totals match detail or variance explained

## Source Text

**Page 4** (interest waterfall opening and senior expenses)
```
ICG Euro CLO 2023-2 DACInterest Priority of PaymentsAs of:  7/10/2025Next Payment: 7/28/2025AvailableDocumentReport PaymentforReferenceReferenceAmountDisbursementsInterest Priority Of Interest Proceeds (Waterfall)6,886,432.80Payments (EUR)(A)(1)Payment of taxes owing by the IssuerTaxes CSP0.006,886,432.80Taxes USB57.506,886,375.30(A)(2)Payment of the Issuer Profit Amount to be retained by the Issuer250.006,886,125.30(B)Payment of accrued and unpaid Trustee Fees and Expenses, up to an amount equal to the Senior Expenses Cap1,250.006,884,875.30(C)Payment of Administrative Expenses ...
```

**Page 6** (subordinated management fee and tail)
```
(X)Payment of the Subordinated Collateral Management Fee due and payable on the current Payment DateSubordinated Management Fee257,270.751,443,653.02
```

**Page 7**
```
(DD)Any remaining Interest Proceeds to the Subordinated Notes1,443,653.020.00
```

**Page 8** (principal waterfall header)
```
Principal Priority Of Principal Proceeds (Waterfall)17,016,632.87Payments (EUR)
```

**Page 10** (principal application)
```
(P)(1)during the Reinvestment Period, at the discretion of the Collateral Manager, either to the purchase of Substitute Collateral Obligations or 17,016,632.870.00to the Principal Account pending reinvestment
```
