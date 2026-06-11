---
marp: true
theme: default
paginate: true
header: "Noteval Extraction — Agents & Skills"
footer: "Internal knowledge share · May 2026"
style: |
  section { font-size: 28px; }
  section.lead h1 { font-size: 46px; }
  table { font-size: 21px; }
  blockquote { font-size: 24px; }
  pre { font-size: 20px; }
---

<!-- _class: lead -->

# Agents & Skills

### How we turn trustee PDFs into structured data

**Knowledge share for non-technical colleagues** · May 2026

---

## What we’re solving

- Monthly **CLO / ABS payment reports** arrive as PDFs — layouts differ by **trustee and vintage**.
- Valuation needs **class balances, waterfall cash, and fees** with a **page-level audit trail**.
- Downstream systems need **stable field names**, not ad hoc spreadsheets.

**Today’s approach:** Prepare the PDF → an **agent** drafts structured files → **rules** validate and map fees.

---

## One sentence to remember

> **The agent is the worker. The skill is the job manual.**

Without a skill, the agent improvises.  
With a skill + templates, output stays **consistent and auditable**.

---

## What is an **agent**?

An **agent** is an AI assistant that can:

1. Take a **goal** (“extract this payment report”)
2. **Read** materials (page list, PDF text, templates)
3. **Decide** what to open next
4. **Write** deliverables in a fixed format

| Human analyst | AI agent |
|---------------|----------|
| Opens the deal folder | Opens segmented text + page index |
| Finds the right pages | Navigates via index / tools |
| Fills a standard worksheet | Writes **01–04** markdown files |
| Checks work | Validation report (we run after) |

**Not magic OCR** — it needs prepared text, a playbook, and quality gates.

---

## What is a **skill**?

A **skill** is a **written playbook** (SOP) that tells the agent **how to do this job correctly**.

| Real world | In our project |
|------------|----------------|
| Standard Operating Procedure | **`SKILL.md`** (`noteval_extractor`) |
| “When to use you” job brief | **`noteval-extractor-agent.md`** |
| Blank form with column headers | **`extraction-templates.md`** |
| Compliance checker | **`validate_noteval.py`** |
| Fee category rules | **`map_valuation_fees.py`** → **05** |

Skills capture **tribal knowledge** so every run follows the same business rules.

---

## What goes inside a skill?

1. **When to use it** — e.g. “segmented deal folder exists”
2. **Workflow** — segment → read page index → write 01, 02, 03, 04 → validate
3. **Domain rules** — “Paid column only, not Due”; dual-PDF routing; multi-listing tranches
4. **Output shape** — exact filenames, table columns, checklist
5. **Edge cases** — Wells Fargo waterfall PDF; 144A + REGS → one class row

**Updating a skill = updating our process** (like revising an SOP).

---

## Agent + Skill — how they fit together

```
┌──────────────────────────────────────────┐
│  SKILL (playbook)                        │
│  Workflow + business rules               │
└─────────────────┬────────────────────────┘
                  │ guides
                  ▼
┌──────────────────────────────────────────┐
│  AGENT (worker)                          │
│  Reads text, navigates, drafts 01–04     │
└─────────────────┬────────────────────────┘
                  │ produces
                  ▼
┌──────────────────────────────────────────┐
│  DELIVERABLES + CHECKS                   │
│  Validation → fee mapping (05) → export  │
└──────────────────────────────────────────┘
```

---

## Three layers of quality

| Layer | What it does | Who owns it |
|-------|----------------|-------------|
| **Skill + templates** | Defines *what good looks like* | Domain / ops + playbook |
| **Agent** | *Drafts* structured files from PDF text | AI (LLM or SDK) |
| **Scripts** | *Hard gates* — validate, fee roll-up | Engineering rules |

**Example:** Agents draft **03** waterfall; **Python** maps fees to **05** so DB categories never drift.

---

## Shared starting point (all paths)

Before any agent runs, we **segment** the PDF:

| Artifact | Plain name | Purpose |
|----------|------------|---------|
| `_page_index.md` | **Page list** | “Page 2 = Distribution in US$” |
| `_manifest.md` | **File map** | “Pages 1–16 in this text file” |
| `_chunks/` | **Chunk text** | Actual PDF words, page by page |

**All extraction paths use the same prepared folder.**  
They differ only in **who picks pages** and **how many round-trips** happen.

---

## What we produce (per deal)

| File | Business content |
|------|------------------|
| **01** | Deal ID, payment / determination dates, trustee |
| **02** | Tranche / class balances |
| **03** | Interest & principal waterfall |
| **04** | Summary, gaps, routing notes |
| **05** | Valuation-relevant fees (mapped categories) |

Plus **`validation_report.md`** and **Source Text** on every file for audit.

---

## Two agents, one skill

We use **two execution environments** — both follow the **same playbook**:

| | **UI LLM agent** | **SDK agent** |
|--|------------------|---------------|
| **Where** | Web server + OpenAI | Cursor Agent API |
| **Freedom** | Limited tools (ask for pages) | Full read / search / write |
| **Jobs** | Four (one per file 01–04) | One long multi-step job |
| **Output folder** | Main deal folder | `*_sdk` (for comparison) |
| **Best for** | Batch, cost control | Hard layouts, quality benchmark |

**Same skill — different “building access.”**

---

## Three extraction modes (UI)

| Mode | Analogy | In one line |
|------|---------|-------------|
| **LLM bundle** | Pre-packed envelope | System picks pages; one shot per file |
| **LLM + tools** | Call the filing cabinet | Model asks for specific pages (UI default) |
| **SDK agent** | Analyst in the office | Full playbook + project access |

```
PDF → Segment → ┬→ LLM bundle
                ├→ LLM + tools  → 01–04 → Validate → 05
                └→ SDK agent
```

---

## Skills vs templates vs scripts

| Term | Role |
|------|------|
| **Skill** | End-to-end *procedure* for the agent |
| **Agent profile** | *Who* to invoke + “read the skill first” |
| **Template** | Exact *schema* (columns, filenames) |
| **Tool** | Single action (e.g. “open pages 4–8”) |
| **Script** | Deterministic logic after drafting |

**Fee mapping (05) stays in Python** — stable DB literals, not free-form AI labels.

---

## Why skills matter for the business

- **Consistency** — Same columns and fee types every deal
- **Trainability** — New trustee quirk → update skill, re-run
- **Audit** — Skill + template + Source Text = traceable decisions
- **Fair comparison** — LLM vs SDK uses the **same standard**; differences are navigation, not rules

---

## Improvement loop

1. Segment PDF  
2. Agent runs with **skill + templates**  
3. **Validation** flags gaps  
4. Human review (UI: tranche, waterfall, fees)  
5. **Update skill / template** when we learn a new pattern  
6. Re-run on problem deals  

---

## When to use which agent

| Situation | Suggestion |
|-----------|------------|
| High volume, standard layouts | UI LLM (bundle or tools) in batch |
| New trustee, dual PDF, validation fails | SDK agent → compare to LLM |
| Production after sign-off | Validated folder + mapped **05** |
| Fee taxonomy / DB load | Always **Python** fee mapper |

---

## Live artifacts (where to look)

| Artifact | Location |
|----------|----------|
| Skill (playbook) | `noteval_extractor/SKILL.md` |
| Agent brief | `noteval_extractor/agents/noteval-extractor-agent.md` |
| Templates | `noteval_extractor/references/extraction-templates.md` |
| Plain-language comparison | `docs/LLM_vs_Agent_Comparison_Plain_Language.md` |
| Deal outputs | `noteval_extractor/output/<deal>_<date>/` |

---

## Q&A — common questions

- **Can the agent ignore the skill?** It shouldn’t — validation and review catch drift.
- **Do we need both?** Agent = capability; skill = **your** standard.
- **Is a skill just a prompt?** No — it’s a **persistent, versioned playbook**.
- **Who maintains skills?** Domain rules in playbook; engineering for scripts.

---

<!-- _class: lead -->

# Thank you

**Deck:** `noteval_extractor/docs/Agents_and_Skills_Concepts.md`  
**Deep dive:** `LLM_vs_Agent_Comparison_Plain_Language.md`

*Questions welcome*
