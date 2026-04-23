# Note Balance and Deferred Interest

## Extracted Data

### Section present?
| Field | Value |
|-------|-------|
| Section present (Y/N) | Y |

### Note balance table
| Line item | Amount | Notes |
|-----------|--------|-------|
| Class A through E — ending balance (issue) | 0.00 | p.9 TOTALS |
| Subordinated Notes — ending balance | 41,900,000.00 | |
| Subordinated Notes — DIVIDENDS column (issue total) | 788,309.18 | Mapped to interest in `02` |

### Deferred / accrued interest (issuer or aggregate — not per tranche)
| Description | Amount | Notes |
|-------------|--------|-------|
| N/A | | Per-tranche **Deferred interest** from the NVR class table is captured in **`02`** only; not repeated here. |

## Completeness Checklist
- [x] Section exists or marked absent
- [x] Note balance lines match report labels
- [x] Issuer-level / aggregate deferred or fee-deferral mechanics captured if shown (per-tranche deferred interest is **not** duplicated here — see **`02`**)
- [x] Totals agree or variance explained

## Source Text

**Page 9**
```
Subordinated Notes $41,900,000.00 $41,900,000.00 $0.00 $788,309.18 $0.00 $0.00 $0.00 $41,900,000.00
TOTALS $407,900,000.00 $41,900,000.00 $0.00 $788,309.18 $0.00 $0.00 $0.00 $41,900,000.00
```
