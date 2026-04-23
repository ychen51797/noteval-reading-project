# Note Balance and Deferred Interest

## Extracted Data

### Section present?
| Field | Value |
|-------|-------|
| Section present (Y/N) | Y |

### Note balance table
| Line item | Amount | Notes |
|-----------|--------|-------|
| Interest Collection Account — balance after Payment Date | 0.00 | p.16; deposits 197,044.46 |
| Principal Collection Account — balance after Payment Date | 0.00 | deposits 3,994,397.78 |
| Payment Account — balance after Payment Date | 0.00 | withdrawals 4,191,442.24 |

### Deferred / accrued interest (issuer or aggregate — not per tranche)
| Description | Amount | Notes |
|-------------|--------|-------|
| N/A | | Per-tranche **Deferred interest** on the class table is in **`02_tranche_class_balances.md`** only. Sub note interest paid totals appear in **`02`**; not duplicated as a per-class ladder here. |

## Completeness Checklist
- [x] Section exists or marked absent
- [x] Note balance lines match report labels
- [x] Issuer-level / aggregate deferred or fee-deferral mechanics captured if shown (per-tranche deferred interest is **not** duplicated here — see **`02`**)
- [x] Totals agree or variance explained

## Source Text

**Page 3**
```
 45,500,000.00  3,836,500.73 0.00  0.00 0.00  0.00 0.00  0.00SUB-144A
Total  49,250,000.00  4,152,695.84 0.00  0.00 0.00  0.00 0.00  0.00
```

**Page 16**
```
Interest Collection Account 197,044.46 0.00 197,044.46 0.00
Principal Collection Account 3,994,397.78 0.00 3,994,397.78 0.00
Payment Account 0.00 4,191,442.24 4,191,442.24 0.00
```
