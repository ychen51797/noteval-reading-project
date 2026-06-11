#!/usr/bin/env node
/**
 * Run a local Cursor Agent to extract noteval 01–04 directly into a segmented deal folder.
 *
 * Prerequisites:
 *   1. Segment a deal (UI or batch_segment) → noteval_extractor/output/<deal>/
 *   2. CURSOR_API_KEY in env or cursor_sdk_compare/.env (not committed)
 *   3. npm install in cursor_sdk_compare/
 *
 * Usage (from repo root):
 *   cd cursor_sdk_compare && npm run extract -- ../noteval_extractor/output/<deal>
 *
 * After extraction (when 03 is in targets), map_valuation_fees.py runs automatically.
 * Optional validate: pass without --no-validate (off by default; UI runs validate separately).
 *
 * Usage / estimated cost: logs/noteval_sdk_usage.log (JSONL). Disable with NOTEVAL_SDK_USAGE_LOG=off.
 */

import { spawnSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Agent, CursorAgentError } from "@cursor/sdk";
import {
  addTurnUsage,
  appendSdkUsageLog,
  createUsageAccumulator,
  dealFolderFromSdkDir,
  estimateSdkCostUsd,
  resolveSdkUsageLogPath,
} from "./sdk_usage_log.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");

function loadDotEnvFile(envPath) {
  if (!existsSync(envPath)) return;
  for (const line of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const t = line.trim();
    if (!t || t.startsWith("#")) continue;
    const i = t.indexOf("=");
    if (i < 1) continue;
    const key = t.slice(0, i).trim();
    let val = t.slice(i + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (!(key in process.env)) process.env[key] = val;
  }
}

/** Same search order as server.py / get_file_path (later files do not override set keys). */
function loadDotEnv() {
  for (const envPath of [
    join(__dirname, ".env"),
    join(REPO_ROOT, ".env"),
    join(REPO_ROOT, "noteval_extractor", ".env"),
    join(REPO_ROOT, "noteval_extractor", "scripts", ".env"),
  ]) {
    loadDotEnvFile(envPath);
  }
}

const DEFAULT_TARGETS = ["01", "02", "03", "04"];
const TARGET_FILES = {
  "01": "01_report_metadata.md",
  "02": "02_tranche_class_balances.md",
  "03": "03_interest_principal_waterfall.md",
  "04": "04_extraction_summary.md",
};

function usage() {
  console.error(`Usage:
  node run-extract.mjs <output-dir> [--model MODEL] [--no-validate]
    [--targets 01,02,03,04]

Examples:
  node run-extract.mjs ../noteval_extractor/output/195084_249
  node run-extract.mjs ../noteval_extractor/output/824237876_20260427 --targets 01,02
`);
  process.exit(1);
}

function parseTargets(raw) {
  if (!raw || !String(raw).trim()) return [...DEFAULT_TARGETS];
  const out = String(raw)
    .split(",")
    .map((x) => x.trim())
    .filter((x) => /^0[1-4]$/.test(x));
  return out.length ? out : [...DEFAULT_TARGETS];
}

/** @param {import("@cursor/sdk").SDKRun} run */
async function logRunFailureDetails(run, result, { sdkDir, targets, agentId }) {
  console.error(
    `\nAgent run failed (status=error). agent_id=${agentId ?? "n/a"} run_id=${result.id}`
  );
  const msg = result.result;
  if (typeof msg === "string" && msg.trim()) {
    console.error(`Cursor error: ${msg.trim()}`);
  } else if (msg != null && typeof msg === "object") {
    console.error(`Cursor error: ${JSON.stringify(msg)}`);
  } else {
    console.error(
      "Cursor error: (no message from API — open the Cursor dashboard for this agent/run)"
    );
  }

  if (typeof run.supports === "function" && run.supports("conversation")) {
    try {
      const conv = await run.conversation();
      const tail = conv.slice(-8);
      if (tail.length) {
        console.error("\nLast conversation steps:");
        for (const step of tail) {
          if (step.type === "assistantMessage") {
            const t = step.message?.text?.trim();
            if (t) {
              console.error(
                `  assistant: ${t.slice(0, 500)}${t.length > 500 ? "…" : ""}`
              );
            }
          } else if (step.type === "toolCall") {
            const m = step.message;
            const toolType = m?.type ?? "tool";
            const exit = m?.result?.exitCode;
            const err = m?.result?.error ?? m?.error;
            const stderr = m?.result?.stderr;
            if (err || (exit != null && exit !== 0)) {
              console.error(
                `  tool ${toolType}: exit=${exit ?? "?"} error=${String(err ?? "").slice(0, 300)}`
              );
              if (stderr) {
                console.error(`    stderr: ${String(stderr).slice(0, 400)}`);
              }
            }
          }
        }
      }
    } catch (e) {
      const note = e instanceof Error ? e.message : String(e);
      console.error(`(Could not load conversation: ${note})`);
    }
  }

  const missing = targets.filter((t) => {
    const f = TARGET_FILES[t];
    return f && !existsSync(join(sdkDir, f));
  });
  if (missing.length) {
    console.error(
      `\nMissing deliverables: ${missing.map((t) => TARGET_FILES[t]).join(", ")}`
    );
  }
}

function parseArgs(argv) {
  const positional = [];
  let validate = false;
  let model = process.env.CURSOR_MODEL || "composer-2.5";
  let targets = [...DEFAULT_TARGETS];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--no-validate") validate = false;
    else if (a === "--help" || a === "-h") usage();
    else if (a.startsWith("--model=")) model = a.slice("--model=".length);
    else if (a === "--model") {
      model = argv[++i] ?? model;
    } else if (a.startsWith("--targets=")) {
      targets = parseTargets(a.slice("--targets=".length));
    } else if (a === "--targets") {
      targets = parseTargets(argv[++i]);
    } else positional.push(a);
  }
  return { positional, validate, model, targets };
}


function buildPrompt(sdkDir, targets = DEFAULT_TARGETS) {
  const rel = sdkDir.replace(/\\/g, "/");
  const agentPath = "noteval_extractor/agents/noteval-extractor-agent.md";
  const hasWf = existsSync(join(sdkDir, "_chunks_waterfall"));
  const hasStructuredPdd = existsSync(
    join(sdkDir, "_chunks_structured", "pdd_idd_pdfplumber.md")
  );
  const hasStructuredPdr = existsSync(
    join(sdkDir, "_chunks_structured", "payment_date_report_pdfplumber.md")
  );

  const wfNote = hasWf
    ? `
- **03 waterfall / fees:** \`_page_index_waterfall.md\` + only the \`_chunks_waterfall/pages_*.txt\` files that cover your mapped pages. **Also** read note-val \`_chunks/\` only for a **separate Administrative Expenses** grid if \`_page_index.md\` shows one — not for waterfall fee \`Amount paid\`.
- **01 / 02:** use unsuffixed \`_page_index.md\` + \`_chunks/\` only — do **not** read \`_chunks_waterfall/\` for 01 or 02.`
    : `
- **03:** map pages from \`_page_index.md\`; read only the \`_chunks/pages_*.txt\` files that cover waterfall / Section 11.1 / fee pages. **Admin voucher grid:** often **Administrative Cap and Expenses** — populate \`### Administrative Expenses grid\` from **Administrative Expenses** line items only (**not** **Administrative Expenses Cap** formula rows).`;

  const structuredNote =
    hasStructuredPdd || hasStructuredPdr
      ? `
- **02 only (when present):** you may read \`_chunks_structured/pdd_idd_pdfplumber.md\`${
          hasStructuredPdr ? " and/or `_chunks_structured/payment_date_report_pdfplumber.md`" : ""
        } once for column alignment — still quote **Source Text** from \`_chunks/*.txt\`. Do **not** open structured files for 01, 03, or 04.`
      : "";

  return `You are executing a **token-efficient** noteval extraction (Cursor SDK). Quality rules still apply; minimize file reads and context size.

Repository root (agent cwd): ${REPO_ROOT.replace(/\\/g, "/")}
**Write deliverables ONLY here:** ${rel}

Segmentation already exists under that folder. **Do not modify** \`_chunks/\`, \`_chunks_waterfall/\`, \`_manifest*.md\`, or index files.

## Token / context rules (required)

1. **Plan from indexes first** — Read \`${rel}/_page_index.md\` (and \`_manifest.md\` for chunk filenames). ${
    hasWf ? "If dual segmentation exists, read `_page_index_waterfall.md` only when working on 03." : ""
  } Record **page ranges per deliverable** before opening any \`pages_*.txt\` file.
2. **Read each repo reference at most once** — Open \`${agentPath}\` and \`noteval_extractor/SKILL.md\` **one time each** at the start (skim; do not paste into chat). For templates, read **only** the matching \`## File NN\` section from \`noteval_extractor/references/extraction-templates.md\` when drafting that file — **not** the full templates doc repeatedly.
3. **Chunk files: open only what you need** — Never read every \`pages_*.txt\` in a folder. Open **only** chunks that contain your mapped pages. Prefer **partial reads** (search within a chunk for \`--- Page N ---\`) over loading whole multi-hundred-page chunks when the manifest shows a smaller slice would suffice.
4. **Do not re-read** a chunk or reference file you already used in this run unless a deliverable is incomplete.
5. **Do not run validate_noteval.py or map_valuation_fees.py** — both run automatically after this job when **03** is in targets. Note any obvious gaps in \`04_extraction_summary.md\`.

## References (order)

1. \`${agentPath}\` — procedure (read once)
2. \`noteval_extractor/SKILL.md\` — boundaries (read once)
3. \`noteval_extractor/references/extraction-templates.md\` — **per-file section only** when writing each deliverable

## Per-deliverable read scope

| File | Read |
|------|------|
| **01** | Index + chunks for **metadata** pages only (title, dates, deal name, report type). |
| **02** | Index + chunks for **class / PDD / IDD / Distribution in US$ / consolidated payment-date** pages only.${structuredNote} |
| **03** |${wfNote} |
| **04** | **No new chunk reads** unless a cross-check requires one page — synthesize from the **01–03** you already wrote plus brief index notes. |

## Write (in order — this run only)

${targets
  .map((t, i) => `${i + 1}. \`${TARGET_FILES[t]}\``)
  .join("\n")}

Do **not** create deliverable files outside this list.

Each file: **Extracted Data → Completeness Checklist → Source Text** (exact template headers).

Quality rules (for extraction; formal validate runs later): **Map by printed column headers only — never guess position** (no nth-$ after All In Rate/CUSIP; **0% All In Rate on SUB is normal**). PDD/IDD mapping, waterfall **Amount paid** from columns whose **headers** say paid/payment/settled — **never** from due/payable columns; **column order varies by trustee** — fill **\`### Column mapping\`** from **this** PDF's headers (not a fixed 1st/2nd dollar-column position rule); when **Paid** is **0.00**, **Amount paid** = **0.00**, no invented amounts. **\`02\` Interest rate:** numeric accrual only (**Coupon** / **Spread** / **%** / SOFR+margin) — **never** map **Interest type** / **Rate type** cells that are only **Floating**, **Variable**, or **Fixed**. **Do not** write \`### Valuation-relevant fees\` in \`03\` — run \`map_valuation_fees.py\` after extraction for \`05_valuation_relevant_fees.md\`.

**\`02\` Distribution in US$ → primary (when present):** If the PDF has **Distribution in US$** / **NVR $** class economics **and** a separate **Factor per 1000** / PDD page, **primary** balances and interest/principal **$** come **only** from the **$** table (subtotal / **Total** or sum listing with **Notes**) — **never** from **~1000** factor cells. **Primary** = **one row per economic class** (**A**, **SUB**, …). **Program slices** (**SUB-144A**, **A-REGS**, …) → **\`### Tranche by listing\`** with **$** from the **$** exhibit. **Multi-listing** = **Y** when **>1** slice/CUSIP. **Deutsche Bank NVR:** **Interest rate** = **Current Coupon** on **Distribution in US$** (or **Coupon Rates** when labeled **Current Coupon**) — **not** **Index % + Spread %** concat. Factor page: coupon/rate only — not balances.

**\`02\` Deutsche — Interest Detail:** **Interest Paid** column → **Interest payment** only. **Prior Cumulative** leading **$** on **SUB** lines is **not** period cash (keep **Interest payment** **0.00** when **Interest Paid** is **0.00**). **Accrued Dividends** rule applies only when **Interest paid** is **0** but a **separate** dividend/accrual **cash** column is non-zero — **not** for prior cumulative balances.

**\`02\` SUB / M / Income Notes — Accrued Dividends → Interest payment:** On the **class / trustee summary** table, when **Accrued Dividends** / **Dividend** shows **non-zero** **$** and **Interest paid** is **0.00**, map that cash to **Interest payment**; leave **Dividend** blank. **Exception — SUB with 0 Interest paid but interest-waterfall cash:** When **Interest payment** on the class table is **0.00** and **\`03\`** **interest-proceeds** waterfall shows **non-zero Payment** to **Holders of the Subordinated Notes** (e.g. U.S. Bank **(V)**), **fill \`Interest payment\`** from that waterfall **$** — **required**. **\`Interest payable\`** may still come from **Amount Current Payable** / **TOTAL PAYABLE**. **Do not** use **principal-waterfall** sub **(R)** for **Interest payment**.

**\`02\` Preference Share / Preferred Shares — primary row (required):** When the **class / tranche summary** lists **Preference Share** or **Preferred Shares** **with note classes**, add **one row** in **\`### Class balance table (primary)\`** (printed label verbatim; same balance / interest / principal columns as notes). **Do not** put those lines in **\`### Supplementary lines\`** only — supplementary is for **issuer-level aggregates not on the class summary**, not for skipping equity when tranches are in the report.

**\`02\` DISTRIBUTION REPORT Section 10.5(b):** **(C) interest payable** on secured → **Interest payable**; **(D) payments on Subordinated Notes** → **Interest payment**. Read **Applicable Periodic Rate** page **(v)** for **Interest rate**.

**\`02\` NOTE VALUATION REPORT — Interest payable to [Class] Notes (indenture subsection (2)):** Per-class lines **Interest payable to Class … Notes** / **Interest payable to the Subordinated Notes** with **\$** and **no** separate **interest paid** column → map that **\$** to **Interest payment** **and** **Interest payable** (same value). **Do not** leave **Interest payment** **N/A** on this layout — payable-to wording **is** the period interest cash (e.g. deal **825089106**-style indenture NVR). Distinct from aggregate **(C) interest payable in respect of each Class** blocks on some Distribution Report covers.

**\`02\` Notes Information (BNY Payment Date Report):** **Interest Paid** → **Interest payment**; **Deferred Interest Paid** / **Deferred Interest Due** → **Deferred interest** only. **SUB** with **0% All In Rate** still uses **Interest Paid** for **Interest payment** when non-zero — do not mis-map to **Deferred interest**.

**\`02\` Computershare PDD/IDD — refinance-chain (required):** On **Principal / Interest Distribution Detail**, **\`_chunks/\`** prints **CUSIP strip → label stack → Sub Totals bands** as **three separate blocks**. Pair **nth Note Class label ↔ nth Sub Totals \$ block** for **Original balance** — **not** nth CUSIP **Original Face**. **Verify:** single-CUSIP classes — **Original balance** = that CUSIP's **Original Face**; use **\`_chunks_structured/pdd_idd_pdfplumber.md\`** when present. **Every** **A-R** / **B-R** / **-RR** label gets a **primary** row; capture page-break orphan CUSIPs in **listing**. Off-by-one often hits **mid-stack** (**824431650**: **B-R** **21M** vs **72M**). Quote label stack + **Sub Totals** in Source Text.

**\`02\` SUB / F footer — multiple CUSIPs (required):** When **two or more CUSIPs** appear near a **SUB** or **F** footer, **do not** assign **both** to **SUB** because of the footer or glued tail token — **one listing row per CUSIP**, **Economic class** from **that** CUSIP's **Sub Totals** / **Original Face** only. **Primary SUB** = SUB CUSIPs only (e.g. **824169432**: **31679NAN4** = **F** **12M**, **31679NAQ7** = **SUB** **34.2M** — not both **SUB**).

**\`03\` waterfall vs \`05\` fee mapping (required):** \`map_valuation_fees.py\` (run after extraction) reads **\`### Waterfall table\`** first (then **\`### Disbursement ladder\`**). **Only fee/vendor lines** get non-zero **Amount paid**: taxes, trustee, collateral administrator, rating/counsel, explicit **management fee** labels, **(R)** unpaid admin after cap. **Do not** put class interest/principal, subordinated **noteholder** distributions, reinvestment/purchase-of-collateral, coverage-test PASS, or account opening balances in **\`### Waterfall table\`** — use **\`### Other waterfall lines\`** + **Notes: see \`02\`**. **Do not** write \`### Valuation-relevant fees\` in \`03\` — \`05\` is script-built.

**\`03\` Citibank / clause-only Section 11.1 (required when no column headers):** When the PDF prints **Section 11.1** priority text with a trailing **\$** per clause (no **Amount Due / Paid / Available** grid), you **must** still fill **\`### Waterfall table\`** — one row per priority step with **Priority**, **Item / payee description**, **Amount paid** (trailing **\$** on that clause), and **Notes**. Set **Layout in this file** to **Both** (not **Logical only**). Also fill **\`### Disbursement ladder\`** when helpful. **Never** mark **\`### Waterfall table\`** **N/A** when Source Text lists disbursement amounts. Example fee rows: **Trustee**, **Collateral Administrator**, **Senior / Subordinated Management Fee**, **(R)** admin not paid under **(A)(2)** cap.`;
}

async function main() {
  loadDotEnv();
  const apiKey = process.env.CURSOR_API_KEY?.trim();
  if (!apiKey) {
    console.error(
      "Missing CURSOR_API_KEY. Set it in noteval_extractor/.env, cursor_sdk_compare/.env, or the environment."
    );
    process.exit(1);
  }

  const rawArgv = process.argv.slice(2);
  let { positional, validate, model, targets } = parseArgs(rawArgv);
  if (positional.length < 1) usage();

  const sdkDir = resolve(positional[0]);

  if (!existsSync(join(sdkDir, "_chunks"))) {
    console.error(`Missing _chunks/ in ${sdkDir}. Segment the PDF first (pdf_workflow.py or batch_segment.py).`);
    process.exit(1);
  }

  const prompt = buildPrompt(sdkDir, targets);
  console.error(`Repo: ${REPO_ROOT}`);
  console.error(`SDK output: ${sdkDir}`);
  console.error(`Targets: ${targets.join(", ")}`);
  const usageLogPath = resolveSdkUsageLogPath();
  if (usageLogPath) {
    console.error(`Usage log: ${usageLogPath}`);
  }
  console.error(`Model: ${model}`);
  console.error("Starting local Cursor agent…\n");

  const startedAt = new Date().toISOString();
  const usageAcc = createUsageAccumulator();
  let agent;
  let agentId;

  try {
    agent = await Agent.create({
      apiKey,
      model: { id: model },
      local: { cwd: REPO_ROOT, settingSources: [] },
    });
    agentId = agent.agentId;

    const run = await agent.send(prompt, {
      onDelta: ({ update }) => {
        if (update.type === "turn-ended" && update.usage) {
          addTurnUsage(usageAcc, update.usage);
        }
      },
    });
    console.error(`Run id: ${run.id}`);

    if (run.supports("stream")) {
      for await (const event of run.stream()) {
        if (event.type === "assistant") {
          for (const block of event.message.content) {
            if (block.type === "text") process.stdout.write(block.text);
          }
        }
      }
    }

    const result = await run.wait();
    const resolvedModel = result.model?.id ?? model;
    const cost = estimateSdkCostUsd(resolvedModel, usageAcc);
    const record = {
      ts: new Date().toISOString(),
      started_at: startedAt,
      source: "cursor_sdk_compare/run-extract.mjs",
      deal_folder: dealFolderFromSdkDir(sdkDir),
      sdk_output_dir: sdkDir.replace(/\\/g, "/"),
      model: resolvedModel,
      agent_id: agentId ?? null,
      run_id: result.id,
      run_status: result.status,
      duration_ms: result.durationMs ?? null,
      turn_count: usageAcc.turnCount,
      input_tokens: usageAcc.inputTokens,
      output_tokens: usageAcc.outputTokens,
      cache_read_tokens: usageAcc.cacheReadTokens,
      cache_write_tokens: usageAcc.cacheWriteTokens,
      total_tokens:
        usageAcc.inputTokens +
        usageAcc.outputTokens +
        usageAcc.cacheReadTokens +
        usageAcc.cacheWriteTokens,
      cost_usd: cost.cost_usd,
      cost_model_usd: cost.cost_model_usd,
      cost_ctr_usd: cost.cost_ctr_usd,
      pricing_note: cost.pricing_note,
    };
    const loggedPath = appendSdkUsageLog(record);

    console.error(`\n\nRun finished: status=${result.status} id=${result.id}`);
    if (usageAcc.turnCount > 0) {
      console.error(
        `Tokens (turn-ended sum): in=${usageAcc.inputTokens} out=${usageAcc.outputTokens} ` +
          `cache_r=${usageAcc.cacheReadTokens} cache_w=${usageAcc.cacheWriteTokens}`
      );
    } else {
      console.error(
        "Tokens: no turn-ended usage deltas captured (check SDK version); see dashboard for token counts."
      );
    }
    if (cost.cost_usd != null) {
      console.error(
        `Estimated cost USD: ${cost.cost_usd} (model ${cost.cost_model_usd} + CTR ${cost.cost_ctr_usd}; ${cost.pricing_note})`
      );
    }
    if (loggedPath) {
      console.error(`Appended usage line: ${loggedPath}`);
    }

    if (result.status === "error") {
      await logRunFailureDetails(run, result, { sdkDir, targets, agentId });
      process.exit(2);
    }

    if (targets.includes("03")) {
      const rel = sdkDir.replace(/\\/g, "/");
      console.error("\nRunning map_valuation_fees.py …");
      const m = spawnSync(
        process.platform === "win32" ? "py" : "python3",
        [
          "-3",
          join(REPO_ROOT, "noteval_extractor", "scripts", "map_valuation_fees.py"),
          rel,
        ],
        { cwd: REPO_ROOT, stdio: "inherit", shell: process.platform === "win32" }
      );
      if (m.status !== 0) {
        process.exit(m.status === null ? 4 : m.status);
      }
    }

    if (validate) {
      const rel = sdkDir.replace(/\\/g, "/");
      console.error("\nRe-running validate_noteval.py …");
      const v = spawnSync(
        process.platform === "win32" ? "py" : "python3",
        ["-3", join(REPO_ROOT, "noteval_extractor", "scripts", "validate_noteval.py"), rel],
        { cwd: REPO_ROOT, stdio: "inherit", shell: process.platform === "win32" }
      );
      process.exit(v.status === 0 ? 0 : 3);
    }
  } catch (err) {
    if (err instanceof CursorAgentError) {
      console.error(`Agent startup failed: ${err.message} (retryable=${err.isRetryable})`);
      process.exit(1);
    }
    throw err;
  } finally {
    await disposeAgent(agent);
  }
}

/** @param {import("@cursor/sdk").SDKAgent | undefined} agent */
async function disposeAgent(agent) {
  if (!agent) return;
  const sym = Symbol.asyncDispose;
  if (typeof agent[sym] === "function") {
    await agent[sym]();
    return;
  }
  if (typeof agent.close === "function") {
    agent.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
