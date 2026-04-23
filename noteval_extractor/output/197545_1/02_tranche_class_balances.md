# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | 7 |
| Table name(s) as printed | TRUSTEE REPORT TO NOTE HOLDERS — TOTALS (ORIGINAL PRINCIPAL BALANCE / …) |
| Currency | US$ |

### Class balance table (primary)
| Class | ISIN or CUSIP | Original balance | Beginning balance | Interest payment | Principal payment | Deferred interest | Dividend | Ending balance | Notes |
|-------|---------------|------------------|-------------------|------------------|-------------------|-------------------|----------|----------------|-------|
| Class A Notes | 33833VAA3; G3660UAA9; 33833VAB1 | 85,400,000.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | TOTALS row p.9; **Beginning balance** = second currency column (principal balance); senior classes fully paid down. |
| Class A-L Loans | 33833VAC9; G3660UAB7; 33833VAD7 | 162,600,000.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | |
| Class B Notes | 33833VAE5; G3660UAC5; 33833VAF2 | 56,000,000.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | |
| Class C Notes | 33833VAG0; G3660UAD3; 33833VAH8 | 26,000,000.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | |
| Class D Notes | 33833VAJ4; G3660UAE1; 33833VAK1 | 22,000,000.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | |
| Class E Notes | 33834UAA4; G3661NAA4; 33834UAB2 | 14,000,000.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | |
| Subordinated Notes | 33834UAC0; G3661NAB2; 33834UAD8 | 41,900,000.00 | 41,900,000.00 | 788,309.18 | 0.00 | 0.00 | 0.00 | 41,900,000.00 | **Interest payment** from DIVIDENDS column `$788,309.18` in source TOTALS; reconcile to trustee labels if automating. |

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| TOTALS — Original principal (all classes) | 407,900,000.00 | p.9 |
| TOTALS — Dividends column (issue) | 788,309.18 | Aligns with SUB interest line above |

## Completeness Checklist
- [x] Every class row from the main table captured (or explicitly listed as omitted with reason)
- [x] **Class** and **ISIN or CUSIP** (when printed) for each line
- [x] **Original balance** when the report prints it (or N/A with reason)
- [x] **Beginning balance** and **ending balance** (or mapped from report labels such as prior/current principal)
- [x] **Interest payment**, **principal payment**, **Deferred interest**, and **dividend** captured when the report includes them (or marked N/A with reason)
- [x] Totals row matches sum of detail rows (or discrepancy noted)

## Source Text

**Page 9** (TOTALS)
```
ORIGINAL PRINCIPA L PRINCIPAL  ACCRUE D DEFERRED AMOUNT PRINCIPAL
CLASS BALANCE BALANCE PAYABLE DIVIDENDS INTEREST INTEREST PAYABL E BALANCE
Class A Notes $85,400,000.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00
Class A-L Loans $162,600,000.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00
Class B Notes $56,000,000.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00
Class C Notes $26,000,000.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00
Class D Notes $22,000,000.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00
Class E Notes $14,000,000.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00 $0.00
Subordinated Notes $41,900,000.00 $41,900,000.00 $0.00 $788,309.18 $0.00 $0.00 $0.00 $41,900,000.00
TOTALS $407,900,000.00 $41,900,000.00 $0.00 $788,309.18 $0.00 $0.00 $0.00 $41,900,000.00
```
