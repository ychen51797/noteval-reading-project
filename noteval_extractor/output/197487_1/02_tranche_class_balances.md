# Tranche and Class Balances

## Extracted Data

### Summary
| Metric | Value |
|--------|-------|
| Number of classes / tranches listed | 22 (rated notes + SUB variants; excludes Total row) |
| Table name(s) as printed | Distribution in US$; Note Valuation Report (interest detail p.3; CUSIP/factors p.4) |
| Currency | US$ |

### Class balance table (primary)
| Class | ISIN or CUSIP | Original balance | Beginning balance | Interest payment | Principal payment | Deferred interest | Dividend | Ending balance | Notes |
|-------|---------------|------------------|-------------------|------------------|-------------------|-------------------|----------|----------------|-------|
| A-RRR-144A | 17180TBL5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | p.2 Distribution row + p.4 CUSIP |
| A-RRR-REGS | G21910AT4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| A-RRR-AI | 17180TBM3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| B-RRR-144A | 17180TBN1 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| B-RRR-REGS | G21910AU1 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| B-RRR-AI | 17180TBP6 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| C-RRR-144A | 17180TBQ4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| C-RRR-REGS | G21910AV9 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| C-RRR-AI | 17180TBR2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| D-1-RRR-144A | 17180TBS0 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| D-1-RRR-REGS | G21910AW7 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| D-1-RRR-AI | 17180TBT8 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| D-2-RRR-144A | 17180TBU5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| D-2-RRR-REGS | G21910AX5 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| D-2-RRR-AI | 17180TBV3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| E-RRR-144A | 17180UAL3 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| E-RRR-REGS | G2140BAF2 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| E-RRR-AI | 17180UAM1 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| F-R-144A | 17180UAG4 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| F-R-REGS | G2140BAD7 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| F-R-AI | DE18C2060 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |
| SUB-144A | 17180UAB5 | 45,500,000.00 | 45,500,000.00 | 3,836,500.73 | 0.00 | 0.00 | | 45,500,000.00 | Balances/interest from p.2; CUSIP p.4 |
| SUB-REGS | G2140BAB1 | 3,750,000.00 | 3,750,000.00 | 316,195.11 | 0.00 | 0.00 | | 3,750,000.00 | |
| SUB-AI | 17180UAD1 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | | 0.00 | |

### Supplementary lines (if present)
| Line description | Amount | Notes |
|------------------|--------|-------|
| Total (Distribution in US$) | Original 49,250,000.00; Interest 4,152,695.84; Principal paid 0.00; Paid interest 4,152,695.84; Ending 49,250,000.00 | p.2 |

### Cross-checks (p.2 distribution grid, folded into `02`)
| Check | Value |
|-------|-------|
| Sum of principal paid (detail) | 0.00 |
| Stated total (if any) | 0.00 (Total row p.2) |
| Match? (Y/N / partial) | Y |

## Completeness Checklist
- [x] Every class row from the main table captured (or explicitly listed as omitted with reason)
- [x] **Class** and **ISIN or CUSIP** (when printed) for each line
- [x] **Original balance** when the report prints it (or N/A with reason)
- [x] **Beginning balance** and **ending balance** (or mapped from report labels such as prior/current principal)
- [x] **Interest payment**, **principal payment**, **Deferred interest**, and **dividend** captured when the report includes them (or marked N/A with reason)
- [x] Totals row matches sum of detail rows (or discrepancy noted)
- [x] Optional **Distribution grid** / cross-checks when a separate distribution page exists

## Source Text

**Page 2** (excerpt)
```
  Distribution in US$
...
 45,500,000.00  45,500,000.00  3,836,500.73  0.00  3,836,500.73  45,500,000.00 ... SUB-144A
 3,750,000.00  3,750,000.00  316,195.11  0.00  316,195.11  3,750,000.00 ... SUB-REGS
Total  49,250,000.00  49,250,000.00  4,152,695.84  0.00  4,152,695.84  0.00  49,250,000.00 ...
```
