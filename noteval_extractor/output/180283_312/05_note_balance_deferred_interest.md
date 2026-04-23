# Note Balance and Deferred Interest

## Extracted Data

### Section present?
| Field | Value |
|-------|-------|
| Section present (Y/N) | N |

### Note balance table
| Line item | Amount | Notes |
|-----------|--------|-------|
| N/A | | No standalone “Note Balance” / cumulative note balance schedule in this 11-page Payment Summary. Class balances and interest appear on **Distribution Summary** (`02`). |

### Deferred / accrued interest (issuer or aggregate — not per tranche)
| Description | Amount | Notes |
|-------------|--------|-------|
| N/A | | Class-level **Deferred interest** (if any) belongs in **`02`**; this PDF has no separate note-balance ledger. Waterfall **Deferred Interest** clause lines at **0.00** (pp.5–6) are procedural, not a tranche table in **`05`**. |

## Completeness Checklist
- [x] Section exists or marked absent
- [x] Note balance lines match report labels
- [x] Issuer-level / aggregate deferred or fee-deferral mechanics captured if shown (per-tranche deferred interest is **not** duplicated here — see **`02`**)
- [x] Totals agree or variance explained

## Source Text

**Page 5** (deferred-interest lines in interest waterfall — all zero this payment)
```
(L)Deferred Interest on the Class C Notes0.002,998,231.90
...
(O)Deferred Interest on the Class D Notes0.002,492,122.26
```

**Page 6**
```
(R)Deferred Interest on the Class E Notes0.002,051,131.71
(U)Deferred Interest on the Class F Notes0.001,700,923.77
```
