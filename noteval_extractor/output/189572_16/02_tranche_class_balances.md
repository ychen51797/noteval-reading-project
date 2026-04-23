# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | 9 (8 rated classes + Subordinated Notes) |
| Table name(s) as printed | “The following amounts represent balances and payments for the entire issue” (p.5); aggregate table (a)(i) on p.1 |
| Currency | US$ |

### Class balance table (primary)
| Class | ISIN or CUSIP | Original balance | Beginning balance | Interest payment | Principal payment | Deferred interest | Dividend | Ending balance | Notes |
|-------|---------------|------------------|-------------------|------------------|-------------------|-------------------|----------|----------------|-------|
| Class X-R Notes | 04009GAN7; G3333XAG7; 04009GAP2 | 5,500,000.00 | 3,666,666.64 | 23,498.12 | 3,666,666.64 | 0.00 | 0.00 | 0.00 | **Beginning balance** = Principal balance column; **Interest payment** = Accrued Interest; **Deferred interest** from PDF column; p.5 |
| Class A-1-R Notes | 04009GAQ0; G3333XAH5; 04009GAR8 | 352,000,000.00 | 352,000,000.00 | 2,314,291.08 | 352,000,000.00 | 0.00 | 0.00 | 0.00 | |
| Class A-2-R Notes | 04009GAS6; G3333XAJ1; 04009GAT4 | 16,500,000.00 | 16,500,000.00 | 113,120.73 | 16,500,000.00 | 0.00 | 0.00 | 0.00 | |
| Class B-R Notes | 04009GAU1; G3333XAK8; 04009GAV9 | 49,500,000.00 | 49,500,000.00 | 352,012.18 | 49,500,000.00 | 0.00 | 0.00 | 0.00 | |
| Class C-R Notes | 04009GAW7; G3333XAL6; 04009GAX5 | 33,000,000.00 | 33,000,000.00 | 247,324.79 | 33,000,000.00 | 0.00 | 0.00 | 0.00 | |
| Class D-1-R Notes | 04009GAY3; G3333XAM4; 04009GAZ0 | 27,500,000.00 | 27,500,000.00 | 244,756.77 | 27,500,000.00 | 0.00 | 0.00 | 0.00 | |
| Class D-2-R Notes | 04009GBA4; G3333XAN2; 04009GBB2 | 11,000,000.00 | 11,000,000.00 | 101,131.25 | 11,000,000.00 | 0.00 | 0.00 | 0.00 | |
| Class E-R Notes | 04015YAE0; G3333YAC4; 04015YAF7 | 16,500,000.00 | 16,500,000.00 | 229,079.06 | 16,500,000.00 | 0.00 | 0.00 | 0.00 | |
| Subordinated Notes | 04015YAC4; G3333YAB6; 04015YAD2 | 57,200,000.00 | 57,200,000.00 | 0.00 | 0.00 | 0.00 | 0.00 | 57,200,000.00 | No interest / principal payable on p.5 issue table this period |
| **TOTALS** | | 568,700,000.00 | 566,866,666.64 | 3,625,213.98 | 509,666,666.64 | 0.00 | 0.00 | 57,200,000.00 | p.5 TOTALS row |

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| Interest Distribution Amount (excl. Sub) — Schedule G (b) | 3,625,213.98 | p.1 — matches sum of per-class **Interest payment** in **(b)** |
| Administrative Expenses (next Payment Date) — Schedule G (c) | 705,936.12 | p.1–2; itemized block |

### Distribution grid (optional — e.g. “Distribution in US$”, prior/current principal, interest paid)
| Class | Prior principal balance | Current principal balance | Principal paid | Interest paid | Other columns (name + value) | Notes |
|-------|------------------------|---------------------------|----------------|----------------|------------------------------|-------|
| N/A | | | | | | No separate **Distribution in US$** grid; issue totals on **p.5** |

### Cross-checks (distribution grid, if used)
| Check | Value |
|-------|-------|
| Sum of principal paid (detail) | 509,666,666.64 |
| Stated total (if any) | 509,666,666.64 on **TOTALS** (Principal Payable column) |
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

**Page 5** (issue dollar table — excerpt)
```
The following amounts represent balances and payments for the entire issue:  
TOTAL ENDING
ORIGINAL PRINCIPAL PRINCIPAL  ACCRUED DEFERRED AMOUNT PRINCIPAL
CLASS BALANCE BALANCE PAYABLE DIVIDENDS INTEREST INTEREST PAYABLE BALANCE
Class X-R Notes $5,500,000.00 $3,666,666.64 $3,666,666.64 $0.00 $23,498.12 $0.00 $3,690,164.76 $0.00
...
TOTALS $568,700,000.00 $566,866,666.64 $509,666,666.64 $0.00 $3,625,213.98 $0.00 $513,291,880.62 $57,200,000.00
```

**Page 5** (CUSIP / ISIN lines — excerpt)
```
Class X-R Notes ... 04009GAN7 G3333XAG7 04009GAP2
Class A-1-R Notes ... 04009GAQ0 G3333XAH5 04009GAR8
```
