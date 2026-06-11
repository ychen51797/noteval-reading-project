# File 02 — Tranche / class balance domain rules

Read this when filling **`02_tranche_class_balances.md`**. Canonical table headers and checklist items are in **`extraction-templates.md`** File **02**.

## Distribution in US$ — fixed column layouts

Trustee PDFs often scramble column order in **`_chunks/`** linear text. For known layouts, apply the **fixed column order** mechanically — do not reconstruct camel-jammed headers by splitting tokens.

### Deutsche Bank only

| As printed | Template field |
|------------|----------------|
| Class | Notes only |
| Ccy | Notes only |
| Original Face Value | `Original balance` |
| Prior Principal Balance | `Beginning balance` |
| Percent of Original Face Value (prior) | Notes only |
| Optimal Interest | Notes only |
| **Interest Paid** | **`Interest payment`** |
| **Principal Paid** | **`Principal payment`** |
| Total Payment | Notes only (cross-check: = Interest Paid + Principal Paid) |
| Defaulted Interest | Notes only |
| Cumulative Deferred/Defaulted Interest | Notes only |
| **Current Principal Balance** | **`Ending balance`** |
| Percent of Original Face Value (current) | Notes only |

**Critical:** pypdf linearization puts **Interest Paid** at stream position 3 (after Original Face Value and Prior Principal Balance), before percentage columns. Do **not** label it “Deferred/Cumulative” or “not period cash.” **Known error — deal 825275100:** Interest Paid (3,836,500.73 SUB-144A + 316,195.11 SUB-REGS) misread as deferred → SUB Interest payment = 0.00. **Do not** apply this layout to other trustees.

### Other trustees (identify trustee first)

**US Bank — Distribution in US$ (wide voucher):**
`Original Face Value` | `Beginning Principal Balance` | `Principal Paid` → `Principal payment` | `Interest Paid` → `Interest payment` | `Ending/Current Principal Balance` → `Ending balance` | `Total Payment` (cross-check). Known deals: 825578539, 825594251, 830246667, 831182614, 867049059.

**US Bank — Notes Information / Section 3 grid (BNY-style):**
`Original Principal Outstanding` | `Beginning Principal Outstanding` → `Beginning balance` | `All In Rate` → `Interest rate` | `Interest Due` → `Interest payable` | `Deferred Interest Due` → `Deferred interest` | `Interest Paid` → `Interest payment` | `Principal Paid` → `Principal payment` | `Ending Principal Outstanding` → `Ending balance`. Known deals: 825288561, 824976105, 830947388, 831268599, 867302616, 867555158.

**Computershare — PDD/IDD:**
`Original Face` | `Period Beginning Balance` → `Beginning balance` | `Principal Distribution` → `Principal payment` | `Deferred Interest` | `Ending Balance` → `Ending balance` | `Coupon Rate` → `Interest rate`. Known deals: 500020237, 823904788, 824910826, 867424755, 868776484.

**Opening/Closing Balance (Citibank and similar):**
`Original Face Value` | `Opening Balance` → `Beginning balance` | `Repayment of Principal` → `Principal payment` | `Closing Balance` → `Ending balance` | `Accrued Interest Due` → `Interest payable` | `Deferred Interest`. Known deals: 831358226, 867046842, 867325679.

**Unknown trustee:** Read headers **verbatim** from the printed page. Record **`### Column mapping`** in **`## Extracted Data`**. Escalate if ambiguous — do not invent a mapping.

### Self-validation loop (required after every `02` save)

Run `validate_noteval.py` and read **`validation_report.md`**. Any Rule 5 **principal roll-forward** warning on a **Distribution in US$** row is usually a column mis-map (signature: delta = that class's **`Interest payment`** — **Total Payment** copied into **`Ending balance`**). Re-open the chunk, re-apply the trustee layout, re-map by column title, save, re-validate until Rule 5 passes or document in **Notes**.

## Class names — same vs different (string equality only)

1. **Strip whitespace** from both names.
2. If `strip(A) == strip(B)` → same class, one primary row. Else → separate primary rows. **Stop. No judgment** about similarity.
3. **Program slices:** Remove suffix (`-144A`, `-REGS`, `-REG S`, `-AI`, `-RegS`), compare base names. Match → one primary + listing rows.
4. Multiple CUSIPs under one economic class → **`### Tranche by listing`**; set **`Multi-listing tranches? = Y`** in **`04`**.

**Never merge:** `Subordinated Notes` ≠ `Subordinated Preferred Return Notes`; `A2L-R2` ≠ `AL1-R2`; `D-R` ≠ `D-RR`.

## Class labels (Note Class / Class, not CUSIP)

**`Class`** and **`Economic class`** follow the trustee's **printed** tranche name — **not** CUSIP. CUSIP/ISIN only in **listing** columns when **`Multi-listing = Y`**.

**Computershare PDD/IDD:** Each **Note Class** section ends with **Sub Totals:** = aggregate for all CUSIPs in that section (use for **primary**). **Sub Totals** ≠ tranche **SUB**. **Refinance:** **-R** once, **-RR** twice (**CR2** = **CRR** role). Latest line (**CRR**, **D-RR**, …) usually carries payment; older lines often paid down.

**SUB interest cash:** Map from **SUB** **Sub Totals** / footer **Interest Distribution** — not 0.00 just because coupon is 0. When class table shows 0 but **`03`** waterfall pays subordinated holders (U.S. Bank **(V)**), fill **`Interest payment`** from waterfall **Payment** — see **`extraction-templates.md`** (*`02` class table ≠ `03` waterfall Paid*).

## Computershare PDD/IDD — pdfplumber-first CUSIP→class (required)

pypdf linearizes **(1)** CUSIP strip, **(2)** Note Class labels, **(3)** Sub Totals bands — **independently ordered**. Never assign by nth-position pairing.

1. **Open `_chunks_structured/pdd_idd_pdfplumber.md` first** — authoritative CUSIP → Note Class mapping.
2. **Sub Totals $ from pdfplumber** for primary balances. **Arithmetic check:** `sum(CUSIP beginning balances in section) = Sub Totals beginning balance`.
3. **Fallback** (pdfplumber absent only): assign by arithmetic match to Sub Totals — not by position.
4. **One primary row per distinct Note Class** section.
5. **Never collapse pdfplumber sections** — N sections → N primary rows. **Known — deal 867151089:** collapsing `A2L-R2` into `AL1-R2` shifted entire chain, inflated SUB by 22M.

**Known nth-band failures:** 824431650, 824169432, 825519711. Full procedure: **`extraction-templates.md`** *Computershare PDD/IDD — refinance-chain Sub Totals alignment*.

### pdfplumber tail-label direction

The glued token after **`Sub Totals:`** on a CUSIP row names the **next** section's class — **not** the current row's class. Assign CUSIP to the class from the **preceding** row's tail or the section header above.

**Example — deal 867151089 `BCC3N3Y39`:** col0 ends with `... AL3-R2` — that is the **following** section; CUSIP belongs to **AL2-R2** (preceding tail).

### Never override pdfplumber with linearized label stack

Once pdfplumber assigns CUSIP X → class Y, that mapping **stands**. A CUSIP "missing" from the linearized strip is **not** evidence the class has no balance.

**Known — deal 869770740 D1:** pdfplumber correct; follow-up from linearized strip shifted D2/E/F/SUB by one class.

## Multi-CUSIP sections — Sub Totals is the aggregate

When a section has **two or more CUSIPs**, **Sub Totals = sum of ALL CUSIPs** → use for **primary beginning balance**. Every CUSIP (including 0.00 paid-down) goes in **listing** under the same **`Economic class`**.

**Known — deal 825519711 E-RR:** QBJ2 (0) + QBK9 (60M); Sub Totals = 60M; "SUB" after Sub Totals is **next section header**.

## SUB / F footer — multiple CUSIPs

**One listing row per CUSIP**; **`Economic class`** from **that** CUSIP's Sub Totals only. Do not assign both to SUB because of footer. **824169432:** NAN4 → **F** 12M; NAQ7 → **SUB** 34.2M.

## Waterfall-only `02` + SUB IRR hurdle

When **no** class / PDD / IDD table exists, fill **`02`** from **Section 11.1** only (**first `$`** = paid). **Subordinated Notes … Internal Rate of Return** on **Principal Proceeds (T)** → **`Interest payment`**, not **`Principal payment`** (**830482172**).

## Amount mapping principles (all trustees)

- Map by **printed column or section title** — not horizontal position, template column order, or “nth decimal after CUSIP.”
- **All In Rate 0%** on subordinated notes does **not** mean zero interest cash.
- **Day counts** (360, 968, …) are accrual metadata — never in money or rate columns.
- **`Principal payment`** = **Principal Distribution** / **Principal Paid** column only — **never** Ending/Current/Beginning balance. Computershare PDD five-band: third = principal payment, fifth = ending balance.
- Non-numeric placeholders (**Residual**, **Nil**, **N/A**, …) → **`N/A`** or blank in Extracted Data; keep verbatim in Source Text.
