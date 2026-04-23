# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | 8 (Class X, Class A-R through E-R, Subordinated Notes) |
| Table name(s) as printed | Note Valuation Report — dollar balances (p.2); per-unit table above uses “units of 1,000” |
| Currency | US$ |

### Class balance table (primary)
| Class | ISIN or CUSIP | Original balance | Beginning balance | Interest payment | Principal payment | Deferred interest | Dividend | Ending balance | Notes |
|-------|---------------|------------------|-------------------|------------------|-------------------|-------------------|----------|----------------|-------|
| Class X Notes | N/A in chunk | N/A | 3,428,571.42 | 39,790.20 | 857,142.86 | 0.00 | 0.00 | 2,571,428.56 | **Interest payment** = Interest Payable; **Deferred interest** = Interest Deferred Payable (“-” → **0.00**) plus any default/deferred interest column |
| Class A-R Notes | N/A in chunk | N/A | 320,000,000.00 | 3,881,752.00 | 0.00 | 0.00 | 0.00 | 320,000,000.00 | |
| Class B-R Notes | N/A in chunk | N/A | 60,000,000.00 | 783,328.50 | 0.00 | 0.00 | 0.00 | 60,000,000.00 | |
| Class C-R Notes | N/A in chunk | N/A | 30,000,000.00 | 406,664.25 | 0.00 | 0.00 | 0.00 | 30,000,000.00 | |
| Class D-1-R Notes | N/A in chunk | N/A | 30,000,000.00 | 470,414.25 | 0.00 | 0.00 | 0.00 | 30,000,000.00 | |
| Class D-2-R Notes | N/A in chunk | N/A | 5,000,000.00 | 94,027.38 | 0.00 | 1.00 | 0.00 | 5,000,000.00 | **Deferred interest** = Default / Deferred Interest Payable **$1.00** (PDF column) |
| Class E-R Notes | N/A in chunk | N/A | 15,000,000.00 | 321,457.13 | 0.00 | 2.00 | 0.00 | 15,000,000.00 | Default / Deferred Interest Payable **$2.00** |
| Subordinated Notes | N/A in chunk | N/A | 54,000,000.00 | 0.00 | 0.00 | 0.00 | 574,110.51 | 54,000,000.00 | **Dividend** = Dividend Payable **574,110.51**; Interest Payable shown “-” in PDF |
| **TOTAL** | | N/A | 517,428,571.42 | 5,997,433.70 | 857,142.86 | 3.00 | 574,110.51 | 516,571,428.56 | PDF **TOTAL** row |

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| Total Amount Payable (footer column) | 7,428,690.07 | PDF **TOTAL** row — reconciliation line across interest/dividend/principal |

### Distribution grid (optional — e.g. “Distribution in US$”, prior/current principal, interest paid)
| Class | Prior principal balance | Current principal balance | Principal paid | Interest paid | Other columns (name + value) | Notes |
|-------|------------------------|---------------------------|----------------|----------------|------------------------------|-------|
| N/A | | | | | | No separate **Distribution in US$** grid; class economics are in the NVR table on **p.2** only |

### Cross-checks (distribution grid, if used)
| Check | Value |
|-------|-------|
| Sum of principal paid (detail) | 857,142.86 (Class X only) |
| Stated total (if any) | 857,142.86 on **TOTAL** row |
| Match? (Y/N / partial) | Y |

## Completeness Checklist
- [x] Every class row from the main table captured (or explicitly listed as omitted with reason)
- [x] **Class** and **ISIN or CUSIP** (when printed) for each line
- [x] **Original balance** when the report prints it (or N/A with reason)
- [x] **Beginning balance** and **ending balance** (or mapped from report labels such as prior/current principal)
- [x] **Interest payment**, **principal payment**, **Deferred interest**, and **dividend** captured when the report includes them (or marked N/A with reason)
- [x] Totals row matches sum of detail rows (or discrepancy noted)
- [x] Optional **Distribution grid** filled or marked N/A when the PDF has a separate class-distribution page

## Source Text

**Page 2** (dollar table)
```
The following amounts represent balances and payments in units of 1,000:
...
CLASS ISIN   BALANCE PAYABLE ACCRUED PAYABLE DEFERRED PAYABLE INTEREST PAYABLE PAYABLE    BALANCE
Class X Notes 3,428,571.42$               $857,142.86 39,790.20$                 39,790.20$                 -$                     -$                      $0.00 896,933.06$                2,571,428.56$                   
Class A-R Notes 320,000,000.00$           $0.00 3,881,752.00$            3,881,752.00$            -$                     -$                      $0.00 3,881,752.00$             320,000,000.00$               
...
Subordinated Notes 54,000,000.00$             $0.00 -$                            -$                            -$                     574,110.51$         $0.00 574,110.51$                54,000,000.00$                 
TOTAL 517,428,571.42$           $857,142.86 5,997,433.70$            5,997,433.70$            $574,110.51 $3.00 7,428,690.07$             516,571,428.56$               
```
