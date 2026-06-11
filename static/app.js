const form = document.getElementById("lookupForm");
const locateLineInput = document.getElementById("locate_deal_line");
const locateSegmentBtn = document.getElementById("locateSegmentBtn");
const checkEligibilityBtn = document.getElementById("checkEligibilityBtn");
const segmentStatusLine = document.getElementById("segmentStatusLine");
const segmentLogToolbar = document.getElementById("segmentLogToolbar");
const segmentLogToggleBtn = document.getElementById("segmentLogToggleBtn");
const segmentLogBox = document.getElementById("segmentLogBox");

const cockpitOutputDir = document.getElementById("cockpitOutputDir");
const cockpitCopyPathBtn = document.getElementById("cockpitCopyPathBtn");
const cockpitCopyAllPathsBtn = document.getElementById("cockpitCopyAllPathsBtn");
const cockpitRememberPathBtn = document.getElementById("cockpitRememberPathBtn");
const cockpitClearPathsBtn = document.getElementById("cockpitClearPathsBtn");
const cockpitOutputPathsList = document.getElementById("cockpitOutputPathsList");
const cockpitPathsEmptyHint = document.getElementById("cockpitPathsEmptyHint");

const pipelineSdkBtn = document.getElementById("pipelineSdkBtn");
const pipelineStatus = document.getElementById("pipelineStatus");
const pipelineLog = document.getElementById("pipelineLog");
const pipelineExtractionHint = document.getElementById("pipelineExtractionHint");
/** @deprecated SDK compare UI removed; uses pipelineStatus / pipelineLog */
const sdkCompareHint = null;
const sdkCompareStartBtn = null;
const sdkCompareDiffBtn = null;
const sdkCompareStatus = null;
const sdkCompareLog = null;

/** @type {readonly ("01"|"02"|"03"|"04")[]} */
const PIPELINE_TARGET_ORDER = ["01", "02", "03", "04"];

/** @type {readonly ("01"|"02")[]} */
const EXTRACT_0102_ONLY_TARGETS = ["01", "02"];

/** @type {readonly ("03"|"04")[]} */
const EXTRACT_0304_ONLY_TARGETS = ["03", "04"];

/** @type {Record<string, string>} */
const PIPELINE_TARGET_FILES = {
  "01": "01_report_metadata.md",
  "02": "02_tranche_class_balances.md",
  "03": "03_interest_principal_waterfall.md",
  "04": "04_extraction_summary.md",
};

/**
 * When checked, SDK agent drafts only metadata + tranche/class balances.
 * @returns {boolean}
 */
function isExtract0102Only() {
  const el = document.getElementById("extractDeliverables0102Only");
  return el instanceof HTMLInputElement && el.checked;
}

/**
 * When checked, SDK agent drafts only waterfall + summary (existing 01/02 kept).
 * @returns {boolean}
 */
function isExtract0304Only() {
  const el = document.getElementById("extractDeliverables0304Only");
  return el instanceof HTMLInputElement && el.checked;
}

/**
 * When checked, skip the "already extracted" check and overwrite existing deliverables.
 * @returns {boolean}
 */
function isForceReextract() {
  const el = document.getElementById("forceReextractCheck");
  return el instanceof HTMLInputElement && el.checked;
}

/**
 * Checked sections for pipeline / SDK (respects scope presets).
 * @returns {("01"|"02"|"03"|"04")[]}
 */
function getEffectivePipelineTargets() {
  if (isExtract0102Only()) return [...EXTRACT_0102_ONLY_TARGETS];
  if (isExtract0304Only()) return [...EXTRACT_0304_ONLY_TARGETS];
  const selected = getSelectedPipelineTargets();
  return selected.length > 0 ? selected : [...PIPELINE_TARGET_ORDER];
}

/**
 * @param {string} outputDir
 * @param {("01"|"02"|"03"|"04")[]} targets
 * @param {{ force?: boolean }} [opts]
 * @returns {Promise<{ complete: boolean; missing: string[]; detail: string; error?: string }>}
 */
async function checkDealExtractionComplete(outputDir, targets, { force = false } = {}) {
  const dir = String(outputDir || "").trim();
  if (!dir) {
    return { complete: false, missing: [], detail: "", error: "empty output_dir" };
  }
  try {
    const { res, data } = await apiPostJson("/api/extraction/check-extraction-complete", {
      output_dir: dir,
      targets,
      force,
    });
    if (!res.ok) {
      return {
        complete: false,
        missing: [],
        detail: "",
        error: formatDetail(data.detail) || res.statusText,
      };
    }
    return {
      complete: !!data.complete,
      missing: Array.isArray(data.missing) ? data.missing.map(String) : [],
      detail: typeof data.detail === "string" ? data.detail : "",
    };
  } catch (e) {
    return {
      complete: false,
      missing: [],
      detail: "",
      error: e instanceof Error ? e.message : String(e),
    };
  }
}

/**
 * @param {string} dealDir
 * @param {("01"|"02"|"03"|"04")[]} targets
 * @param {string} label
 * @param {string} logPrefix
 */
function appendExtractionSkipLog(dealDir, targets, label, logPrefix = "") {
  if (!pipelineLog) return;
  const files = targets.map((t) => PIPELINE_TARGET_FILES[t] || t).join(", ");
  pipelineLog.textContent =
    (pipelineLog.textContent || "") +
    `${logPrefix}Skipped ${label}: deliverables already present (${files}).\n`;
  pipelineLog.scrollTop = pipelineLog.scrollHeight;
}

/** Sync scope cards and deliverable checkboxes when presets (01&02 / 03&04) change. */
function applyExtractScopeUi() {
  const on0102 = isExtract0102Only();
  const on0304 = isExtract0304Only();
  const locked = batchRunning;

  for (const cardId of ["extractScopeCard0102", "extractScopeCard0304"]) {
    const card = document.getElementById(cardId);
    if (card) card.classList.toggle("is-disabled", locked);
  }

  for (const id of ["01", "02"]) {
    const el = document.getElementById(`pipelineTarget${id}`);
    if (el instanceof HTMLInputElement) {
      if (on0304) {
        el.checked = false;
        el.disabled = true;
      } else if (!batchRunning) {
        el.disabled = false;
      }
    }
  }
  for (const id of ["03", "04"]) {
    const el = document.getElementById(`pipelineTarget${id}`);
    if (el instanceof HTMLInputElement) {
      if (on0102) {
        el.checked = false;
        el.disabled = true;
      } else if (on0304) {
        el.checked = true;
        el.disabled = true;
      } else if (!batchRunning) {
        el.disabled = false;
      }
    }
  }
}

/**
 * Checked deliverable sections for SDK extraction (subset preserves canonical order).
 * @returns {("01"|"02"|"03"|"04")[]}
 */
function getSelectedPipelineTargets() {
  /** @type {("01"|"02"|"03"|"04")[]} */
  const out = [];
  for (const id of PIPELINE_TARGET_ORDER) {
    const el = document.getElementById(`pipelineTarget${id}`);
    if (el instanceof HTMLInputElement && el.checked) {
      out.push(id);
    }
  }
  return out;
}

const mapValuationFeesBtn = document.getElementById("mapValuationFeesBtn");
const validationRunBtn = document.getElementById("validationRunBtn");
const xmlExportBtn = document.getElementById("xmlExportBtn");
const compareXmlDbBtn = document.getElementById("compareXmlDbBtn");
const xmlExportStatus = document.getElementById("xmlExportStatus");
const validationReportStatus = document.getElementById("validationReportStatus");
const validationReportPre = document.getElementById("validationReportPre");
const validationReportToggleBtn = document.getElementById("validationReportToggleBtn");
const batchValidateRunBtn = document.getElementById("batchValidateRunBtn");
const batchExportXmlBtn = document.getElementById("batchExportXmlBtn");
const batchCompareXmlDbBtn = document.getElementById("batchCompareXmlDbBtn");
const batchValidateQueueOnly = document.getElementById("batchValidateQueueOnly");
const batchValidateStrict = document.getElementById("batchValidateStrict");
const batchValidationSummaryBtn = document.getElementById("batchValidationSummaryBtn");
const batchValidationSummaryStatus = document.getElementById("batchValidationSummaryStatus");
const batchValidationSummaryPre = document.getElementById("batchValidationSummaryPre");
const batchValidationSummaryToggleBtn = document.getElementById("batchValidationSummaryToggleBtn");
const wrapupRefreshBtn = document.getElementById("wrapupRefreshBtn");
const wrapupCopyBothBtn = document.getElementById("wrapupCopyBothBtn");
const wrapupDealSelect = document.getElementById("wrapupDealSelect");
const wrapupDealMeta = document.getElementById("wrapupDealMeta");
const wrapupStatus = document.getElementById("wrapupStatus");
const wrapupTranchePanel = document.getElementById("wrapupTranchePanel");
const wrapupFeesPanel = document.getElementById("wrapupFeesPanel");
const wrapupAdminPanel = document.getElementById("wrapupAdminPanel");

const WRAPUP_TRANCHE_FILE = "02_tranche_class_balances.md";
const WRAPUP_FEES_FILE = "03_interest_principal_waterfall.md";
const WRAPUP_VALUATION_FEES_FILE = "05_valuation_relevant_fees.md";
const WRAPUP_METADATA_FILE = "01_report_metadata.md";
const WRAPUP_VALUATION_FEES_HEADING = "### Valuation-relevant fees";
const WRAPUP_CLASS_PRIMARY_HEADING = "### Class balance table (primary)";
const WRAPUP_WATERFALL_HEADING = "### Waterfall table";
const WRAPUP_ADMIN_GRID_HEADING = "### Administrative Expenses grid";

/** @type {string} */
let lastWrapupFeesMarkdownExport = "";
/** @type {string} */
let lastWrapupTrancheMarkdownExport = "";
/** @type {string} */
let lastWrapupAdminMarkdownExport = "";
const batchQueueBody = document.getElementById("batchQueueBody");
const batchAddRowBtn = document.getElementById("batchAddRowBtn");
const batchContinueOnError = document.getElementById("batchContinueOnError");
const batchRunBtn = document.getElementById("batchRunBtn");
const batchSdkRunBtn = document.getElementById("batchSdkRunBtn");
/** @type {NodeListOf<HTMLButtonElement>} */
const batchStopBtns = document.querySelectorAll(".batch-stop-btn");
const batchRunStatus = document.getElementById("batchRunStatus");
const batchPasteDialog = document.getElementById("batchPasteDialog");
const batchPasteTextarea = document.getElementById("batchPasteTextarea");
const batchPasteOpenBtn = document.getElementById("batchPasteOpenBtn");
const batchPasteApplyBtn = document.getElementById("batchPasteApplyBtn");
const batchPasteCancelBtn = document.getElementById("batchPasteCancelBtn");
const batchPasteFoldersDialog = document.getElementById("batchPasteFoldersDialog");
const batchPasteFoldersTextarea = document.getElementById("batchPasteFoldersTextarea");
const batchPasteFoldersOpenBtn = document.getElementById("batchPasteFoldersOpenBtn");
const batchPasteFoldersApplyBtn = document.getElementById("batchPasteFoldersApplyBtn");
const batchPasteFoldersCancelBtn = document.getElementById("batchPasteFoldersCancelBtn");

let batchRunning = false;
/** @type {Record<number, ReturnType<typeof setTimeout>>} */
const batchRowProbeTimers = {};
let batchRunAbort = false;

/** @type {Record<string, string> | null} */
let lastResolved = null;

/** @type {string[]} */
const outputPathHistory = [];
const OUTPUT_PATH_HISTORY_MAX = 32;
/** Empty rows shown on load / after reset. */
const BATCH_QUEUE_DEFAULT_ROWS = 5;
/** Max deals in the batch queue (segment / SDK / Excel export). */
const BATCH_QUEUE_MAX_ROWS = 50;

/** Grow the queue to at least ``minCount`` rows (never below default, never above max). */
function ensureBatchQueueMinRows(minCount) {
  const target = Math.min(
    Math.max(Number(minCount) || 0, BATCH_QUEUE_DEFAULT_ROWS),
    BATCH_QUEUE_MAX_ROWS,
  );
  while (batchQueueRows.length < target) {
    batchQueueRows.push(makeEmptyBatchRow());
  }
}

/**
 * Strip BOM / zero-width chars and normalize spaces (paste from Excel/Teams often adds these).
 * @param {string} raw
 */
function normalizeDealPaymentLine(raw) {
  return String(raw || "")
    .replace(/^\uFEFF/, "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/\u00A0/g, " ")
    .trim();
}

/** Split one line: first token = deal ID, remainder = payment date (spaces in date preserved). */
function parseDealPaymentLine(raw) {
  const s = normalizeDealPaymentLine(raw);
  if (!s) return { deal_id: "", payment_date: "" };
  const parts = s.split(/\s+/);
  if (parts.length === 1) return { deal_id: parts[0], payment_date: "" };
  return { deal_id: parts[0], payment_date: parts.slice(1).join(" ") };
}

/**
 * Human label from output folder basename like 825275100_20260316 (matches batch_segment naming).
 * @param {string} base
 */
function labelFromFolderBasename(base) {
  const b = String(base || "").trim();
  if (!b) return "Output folder";
  const m = /^(\d+)_(\d{8})$/.exec(b);
  if (m) {
    const y = m[2].slice(0, 4);
    const mo = m[2].slice(4, 6);
    const d = m[2].slice(6, 8);
    return `${m[1]} — ${y}-${mo}-${d}`;
  }
  return b;
}

/**
 * Infer batch deal line from folder basename ``824048437_20260422`` or ``*_sdk``.
 * @param {string} base
 */
function inferDealLineFromFolderBasename(base) {
  const b = String(base || "")
    .trim()
    .replace(/_sdk$/i, "");
  const m = /^(\d+)_(\d{8})$/.exec(b);
  if (!m) return "";
  const mo = parseInt(m[2].slice(4, 6), 10);
  const d = parseInt(m[2].slice(6, 8), 10);
  const y = m[2].slice(0, 4);
  if (!mo || !d) return "";
  return `${m[1]} ${mo}/${d}/${y}`;
}

/**
 * @param {string} raw
 */
function normalizePastedOutputFolderLine(raw) {
  return String(raw || "")
    .replace(/^\uFEFF/, "")
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/\u00A0/g, " ")
    .trim()
    .replace(/^["']|["']$/g, "");
}

/**
 * @param {string} resolvedDir
 * @param {{ segmented?: boolean; detail?: string; deal_id?: string; payment_date?: string }} chk
 */
function applyLinkedOutputFolderToRow(row, resolvedDir, chk) {
  row.output_dir = resolvedDir;
  if (!row.line.trim()) {
    const fromApi =
      chk.deal_id && chk.payment_date ? `${chk.deal_id} ${chk.payment_date}` : "";
    row.line = fromApi || inferDealLineFromFolderBasename(outputPathBasename(resolvedDir));
  }
  if (chk.segmented) {
    row.status = "Ready";
    row.detail = chk.detail || "Segmented folder linked — run SDK extraction.";
  } else {
    row.status = "Warn";
    row.detail = chk.detail || "Folder linked but _chunks/ missing — segment first.";
  }
}

/**
 * @param {string} pathLine
 * @returns {Promise<{ resolvedDir: string; chk: Record<string, unknown> } | { error: string }>}
 */
async function resolveAndCheckOutputFolder(pathLine) {
  const line = normalizePastedOutputFolderLine(pathLine);
  if (!line) return { error: "empty path" };
  try {
    const { res, data } = await apiPostJson("/api/extraction/check-output-folder", {
      output_dir: line,
    });
    if (!res.ok) {
      return { error: formatDetail(data.detail) || res.statusText };
    }
    const resolvedDir = String(data.output_dir || line).trim();
    if (!resolvedDir) return { error: "server returned no output_dir" };
    return {
      resolvedDir,
      chk: {
        segmented: !!data.segmented,
        detail: typeof data.detail === "string" ? data.detail : "",
        deal_id: typeof data.deal_id === "string" ? data.deal_id : "",
        payment_date: typeof data.payment_date === "string" ? data.payment_date : "",
      },
    };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
}

/**
 * @param {BatchRow} row
 * @param {string} resolvedDir
 * @param {{ segmented?: boolean; detail?: string; deal_id?: string; payment_date?: string }} chk
 */
function linkOutputFolderToBatchRow(row, resolvedDir, chk) {
  applyLinkedOutputFolderToRow(row, resolvedDir, chk);
  addOutputPathToHistory(resolvedDir);
}

/** @param {string} pdfPath */
function pdfStemFromPath(pdfPath) {
  const base = outputPathBasename(String(pdfPath || "").replace(/\\/g, "/"));
  if (!base) return "deal";
  return base.replace(/\.pdf$/i, "") || "deal";
}

/**
 * @param {string} dealId
 * @param {string} paymentDate
 * @param {string} [pdfStem]
 * @returns {Promise<
 *   | { output_dir: string; folder: string; exists: boolean; segmented: boolean; detail: string }
 *   | { error: string }
 * >}
 */
async function lookupSegmentedFolderForDeal(dealId, paymentDate, pdfStem = "") {
  try {
    const { res, data } = await apiPostJson("/api/lookup-segmented-folder", {
      deal_id: dealId,
      payment_date: paymentDate,
      pdf_stem: pdfStem || "deal",
    });
    if (!res.ok) {
      return { error: formatDetail(data.detail) || res.statusText };
    }
    return {
      output_dir: String(data.output_dir || "").trim(),
      folder: String(data.folder || "").trim(),
      exists: !!data.exists,
      segmented: !!data.segmented,
      detail: typeof data.detail === "string" ? data.detail : "",
    };
  } catch (e) {
    return { error: e instanceof Error ? e.message : String(e) };
  }
}

/**
 * @param {BatchRow} row
 * @param {{ output_dir: string; exists: boolean; segmented: boolean; detail: string }} lookup
 */
function applyLookupToBatchRow(row, lookup) {
  if (lookup.segmented) {
    row.output_dir = lookup.output_dir;
    row.status = "Ready";
    row.detail = lookup.detail || "Already segmented — run SDK extraction.";
    return;
  }
  if (lookup.exists) {
    row.output_dir = lookup.output_dir;
    row.status = "Warn";
    row.detail = lookup.detail || "Folder exists but not segmented — run batch segmentation.";
    return;
  }
  row.output_dir = "";
  row.status = "—";
  row.detail = "";
}

/** @param {number} rowIdx */
async function probeBatchRowSegmentedFolder(rowIdx) {
  if (batchRunning) return;
  syncBatchRowsFromDom();
  const row = batchQueueRows[rowIdx];
  if (!row) return;
  const { deal_id, payment_date } = parseDealPaymentLine(row.line);
  if (!deal_id || !payment_date) {
    if (!row.line.trim()) {
      row.output_dir = "";
      row.status = "—";
      row.detail = "";
      renderBatchTable();
    }
    return;
  }
  const lookup = await lookupSegmentedFolderForDeal(deal_id, payment_date);
  if ("error" in lookup) {
    row.status = "Error";
    row.detail = lookup.error;
    renderBatchTable();
    return;
  }
  applyLookupToBatchRow(row, lookup);
  renderBatchTable();
}

async function applyPastedOutputFoldersMultiline(raw) {
  if (batchRunning) return;
  syncBatchRowsFromDom();
  const lines = String(raw || "")
    .split(/\r?\n/)
    .map(normalizePastedOutputFolderLine)
    .filter(Boolean);
  if (lines.length === 0) {
    window.alert("Paste at least one output folder path (one per line).");
    return;
  }

  let folderLines = lines;
  let folderCapped = 0;
  if (folderLines.length > BATCH_QUEUE_MAX_ROWS) {
    folderCapped = folderLines.length - BATCH_QUEUE_MAX_ROWS;
    folderLines = folderLines.slice(0, BATCH_QUEUE_MAX_ROWS);
  }
  ensureBatchQueueMinRows(folderLines.length);

  /** @type {number[]} */
  const emptyIndices = [];
  for (let i = 0; i < batchQueueRows.length; i++) {
    if (!String(batchQueueRows[i].output_dir || "").trim()) emptyIndices.push(i);
  }

  let applied = 0;
  let ei = 0;
  const failures = [];

  if (batchRunStatus) {
    batchRunStatus.textContent = `Checking ${folderLines.length} folder path(s)…`;
  }

  for (const line of folderLines) {
    const result = await resolveAndCheckOutputFolder(line);
    if ("error" in result) {
      failures.push(`${line}: ${result.error}`);
      continue;
    }
    let rowIdx = -1;
    if (ei < emptyIndices.length) {
      rowIdx = emptyIndices[ei++];
    } else if (batchQueueRows.length < BATCH_QUEUE_MAX_ROWS) {
      batchQueueRows.push(makeEmptyBatchRow());
      rowIdx = batchQueueRows.length - 1;
      emptyIndices.push(rowIdx);
      ei++;
    } else {
      failures.push(`${line}: no free batch row (max ${BATCH_QUEUE_MAX_ROWS})`);
      continue;
    }
    linkOutputFolderToBatchRow(batchQueueRows[rowIdx], result.resolvedDir, result.chk);
    applied++;
  }

  renderBatchTable();
  if (applied > 0) {
    const lastRow = batchQueueRows.find((r) => String(r.output_dir || "").trim());
    if (lastRow?.output_dir) {
      setActiveOutputDirectory(lastRow.output_dir, { refreshWrapup: true });
    }
  }

  let msg = `Linked ${applied} folder(s) to the batch table.`;
  if (failures.length) msg += ` ${failures.length} failed.`;
  if (folderCapped) msg += ` ${folderCapped} not applied (max ${BATCH_QUEUE_MAX_ROWS} rows).`;
  if (batchRunStatus) batchRunStatus.textContent = msg;
  if (failures.length || folderCapped) {
    window.alert(`${msg}\n\n${failures.slice(0, 8).join("\n")}`);
  }
}

/**
 * Paths to show in Tranche & fees deal picker (batch rows with output_dir, then recent folders).
 * @returns {{ label: string, fullPath: string }[]}
 */
function collectWrapupDealPickerEntries() {
  if (!batchRunning) syncBatchRowsFromDom();
  /** @type {Map<string, { label: string, fullPath: string }>} */
  const byNorm = new Map();

  for (const row of batchQueueRows) {
    const p = String(row.output_dir || "").trim();
    if (!p) continue;
    const n = normalizeOutputPath(p);
    const { deal_id, payment_date } = parseDealPaymentLine(row.line);
    const label =
      deal_id && payment_date
        ? `${deal_id} — ${payment_date}`
        : labelFromFolderBasename(outputPathBasename(p));
    byNorm.set(n, { label, fullPath: p });
  }

  for (const full of outputPathHistory) {
    const raw = String(full || "").trim();
    if (!raw) continue;
    const n = normalizeOutputPath(raw);
    if (byNorm.has(n)) continue;
    byNorm.set(n, {
      label: labelFromFolderBasename(outputPathBasename(raw)),
      fullPath: raw,
    });
  }

  const activeRaw = cockpitOutputDir?.value.trim() || "";
  if (activeRaw) {
    const n = normalizeOutputPath(activeRaw);
    if (!byNorm.has(n)) {
      byNorm.set(n, {
        label: labelFromFolderBasename(outputPathBasename(activeRaw)),
        fullPath: activeRaw,
      });
    }
  }

  return Array.from(byNorm.values());
}

function populateWrapupDealSelect() {
  const sel = wrapupDealSelect;
  if (!sel) return;
  const active = normalizeOutputPath(cockpitOutputDir?.value || "");
  const entries = collectWrapupDealPickerEntries();
  entries.sort((a, b) =>
    a.label.localeCompare(b.label, undefined, { numeric: true, sensitivity: "base" }),
  );

  sel.innerHTML = "";

  const opt0 = document.createElement("option");
  opt0.value = "";
  if (entries.length === 0) {
    opt0.textContent = "No segmented folders yet (run Segment or batch segmentation)";
    opt0.disabled = true;
    sel.appendChild(opt0);
    return;
  }
  opt0.textContent = "Choose deal & payment date…";
  sel.appendChild(opt0);

  let matched = false;
  for (const { label, fullPath } of entries) {
    const opt = document.createElement("option");
    opt.value = fullPath;
    opt.textContent = label;
    if (normalizeOutputPath(fullPath) === active) {
      opt.selected = true;
      matched = true;
    }
    sel.appendChild(opt);
  }
  if (!matched) {
    opt0.selected = true;
  }
}

/** @typedef {{ line: string; status: string; detail: string; output_dir: string }} BatchRow */
/** @type {BatchRow[]} */
let batchQueueRows = [];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** @param {string} p */
function normalizeOutputPath(p) {
  return String(p || "")
    .trim()
    .replace(/\\/g, "/");
}

/** @param {string} fullPath */
function outputPathBasename(fullPath) {
  const n = normalizeOutputPath(fullPath);
  if (!n) return "";
  const parts = n.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : n;
}

function renderOutputPathHistory() {
  if (!cockpitOutputPathsList) return;
  cockpitOutputPathsList.innerHTML = "";
  const active = normalizeOutputPath(cockpitOutputDir?.value || "");
  for (const p of outputPathHistory) {
    const li = document.createElement("li");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "cockpit-path-row";
    if (normalizeOutputPath(p) === active) row.classList.add("selected");
    const nameEl = document.createElement("span");
    nameEl.className = "cockpit-path-name";
    nameEl.textContent = outputPathBasename(p) || p;
    const fullEl = document.createElement("span");
    fullEl.className = "cockpit-path-full";
    fullEl.textContent = p;
    fullEl.title = p;
    row.appendChild(nameEl);
    row.appendChild(fullEl);
    row.addEventListener("click", () => {
      setActiveOutputDirectory(p, { refreshWrapup: true });
    });
    li.appendChild(row);
    cockpitOutputPathsList.appendChild(li);
  }
  if (cockpitPathsEmptyHint) {
    cockpitPathsEmptyHint.hidden = outputPathHistory.length > 0;
  }
  populateWrapupDealSelect();
}

/** @param {string} fullPath */
function addOutputPathToHistory(fullPath) {
  const n = normalizeOutputPath(fullPath);
  if (!n) return;
  const idx = outputPathHistory.findIndex((x) => normalizeOutputPath(x) === n);
  if (idx >= 0) outputPathHistory.splice(idx, 1);
  outputPathHistory.unshift(fullPath.trim());
  while (outputPathHistory.length > OUTPUT_PATH_HISTORY_MAX) {
    outputPathHistory.pop();
  }
  renderOutputPathHistory();
}

/**
 * Set the active output folder for Extraction agent, Validate, and Tranche & fees.
 * @param {string} fullPath
 * @param {{ refreshWrapup?: boolean }} [opts] Pass refreshWrapup: false during batch between segment and extraction to avoid extra reads.
 */
function setActiveOutputDirectory(fullPath, opts = {}) {
  const p = String(fullPath || "").trim();
  if (!p || !cockpitOutputDir) return;
  cockpitOutputDir.value = p;
  addOutputPathToHistory(p);
  if (opts.refreshWrapup !== false) {
    void refreshWrapUpPanel({ quiet: true });
  }
}

function makeEmptyBatchRow() {
  return { line: "", status: "—", detail: "", output_dir: "" };
}

function initBatchQueue() {
  batchQueueRows = [];
  for (let k = 0; k < BATCH_QUEUE_DEFAULT_ROWS; k++) batchQueueRows.push(makeEmptyBatchRow());
  renderBatchTable();
}

function syncBatchRowsFromDom() {
  const tb = batchQueueBody;
  if (!tb) return;
  const attrRows = tb.querySelectorAll("tr[data-batch-idx]");
  if (attrRows.length > 0) {
    for (const tr of attrRows) {
      const i = Number(tr.getAttribute("data-batch-idx"));
      if (!Number.isInteger(i) || i < 0 || i >= batchQueueRows.length) continue;
      const ln = tr.querySelector(".batch-line-input");
      if (ln) batchQueueRows[i].line = ln.value;
    }
    return;
  }
  [...tb.querySelectorAll("tr")].forEach((tr, i) => {
    if (!batchQueueRows[i]) return;
    const ln = tr.querySelector(".batch-line-input");
    if (ln) batchQueueRows[i].line = ln.value;
  });
}

function renderBatchTable() {
  const tb = batchQueueBody;
  if (!tb) return;
  tb.innerHTML = "";
  batchQueueRows.forEach((row, i) => {
    const tr = document.createElement("tr");
    tr.setAttribute("data-batch-idx", String(i));

    const tdIdx = document.createElement("td");
    tdIdx.className = "batch-col-idx";
    tdIdx.textContent = String(i + 1);

    const tdLine = document.createElement("td");
    tdLine.className = "batch-col-line";
    const inLine = document.createElement("input");
    inLine.type = "text";
    inLine.className = "batch-line-input";
    inLine.autocomplete = "off";
    inLine.value = row.line;
    inLine.placeholder = "825275100  3/16/2026";
    inLine.disabled = batchRunning;
    const rowIdx = i;
    inLine.addEventListener("blur", () => {
      if (batchRunning) return;
      const prev = batchRowProbeTimers[rowIdx];
      if (prev) clearTimeout(prev);
      batchRowProbeTimers[rowIdx] = setTimeout(() => {
        delete batchRowProbeTimers[rowIdx];
        void probeBatchRowSegmentedFolder(rowIdx);
      }, 350);
    });
    tdLine.appendChild(inLine);

    const tdOut = document.createElement("td");
    tdOut.className = "batch-col-output";
    const od = String(row.output_dir || "").trim();
    if (od) {
      const useBtn = document.createElement("button");
      useBtn.type = "button";
      useBtn.className = "batch-output-path batch-output-use-btn";
      useBtn.textContent = od;
      useBtn.title =
        "Use this folder as the active output directory (Extraction agent, Validate, Tranche & fees)";
      useBtn.addEventListener("click", () => {
        setActiveOutputDirectory(od, { refreshWrapup: true });
      });
      tdOut.appendChild(useBtn);
    } else {
      const outEl = document.createElement("div");
      outEl.className = "batch-output-path";
      outEl.textContent = "—";
      tdOut.appendChild(outEl);
    }

    const tdStatus = document.createElement("td");
    const st = document.createElement("div");
    st.className = "batch-status-cell";
    if (row.status === "Done" || row.status === "Ready" || row.status === "Skipped") st.classList.add("ok");
    if (row.status === "Warn") st.classList.add("warn");
    if (row.status === "Error" || row.status === "Stopped") st.classList.add("err");
    st.textContent = row.status || "—";
    tdStatus.appendChild(st);
    if (row.detail) {
      const det = document.createElement("div");
      det.className = "batch-detail-cell";
      if (row.status === "Error" || row.status === "Stopped") {
        det.classList.add("err-detail");
      }
      det.textContent = row.detail;
      det.title = row.detail;
      tdStatus.appendChild(det);
    }

    const tdRm = document.createElement("td");
    const rm = document.createElement("button");
    rm.type = "button";
    rm.className = "primary secondary small";
    rm.textContent = "Clear";
    rm.title = "Clear this row (deal line, output folder, status). Row count stays the same.";
    rm.disabled = batchRunning;
    const idx = i;
    rm.addEventListener("click", () => {
      syncBatchRowsFromDom();
      if (!batchQueueRows[idx]) return;
      batchQueueRows[idx] = makeEmptyBatchRow();
      renderBatchTable();
    });
    tdRm.appendChild(rm);

    tr.appendChild(tdIdx);
    tr.appendChild(tdLine);
    tr.appendChild(tdOut);
    tr.appendChild(tdStatus);
    tr.appendChild(tdRm);
    tb.appendChild(tr);
  });
  populateWrapupDealSelect();
}

function applyPastedDealsMultiline(raw) {
  if (batchRunning) return;
  syncBatchRowsFromDom();
  const lines = String(raw || "")
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  const valid = [];
  const bad = [];
  for (const line of lines) {
    const norm = normalizeDealPaymentLine(line);
    const { deal_id, payment_date } = parseDealPaymentLine(norm);
    if (deal_id && payment_date) valid.push(norm);
    else bad.push(line);
  }
  if (valid.length === 0) {
    window.alert(
      bad.length
        ? "No valid lines. Each line needs: deal ID, space, then payment date."
        : "Paste at least one non-empty line."
    );
    return;
  }

  let capped = 0;
  if (valid.length > BATCH_QUEUE_MAX_ROWS) {
    capped = valid.length - BATCH_QUEUE_MAX_ROWS;
    valid.length = BATCH_QUEUE_MAX_ROWS;
  }
  ensureBatchQueueMinRows(valid.length);

  let vi = 0;
  for (let i = 0; i < batchQueueRows.length && vi < valid.length; i++) {
    if (!batchQueueRows[i].line.trim()) {
      batchQueueRows[i].line = valid[vi++];
      batchQueueRows[i].status = "—";
      batchQueueRows[i].detail = "";
      batchQueueRows[i].output_dir = "";
    }
  }
  while (vi < valid.length && batchQueueRows.length < BATCH_QUEUE_MAX_ROWS) {
    batchQueueRows.push({ line: valid[vi++], status: "—", detail: "", output_dir: "" });
  }
  const skippedForCap = valid.length - vi;
  const applied = valid.length - skippedForCap;
  renderBatchTable();
  for (let i = 0; i < batchQueueRows.length; i++) {
    if (batchQueueRows[i].line.trim()) void probeBatchRowSegmentedFolder(i);
  }

  if (batchRunStatus) {
    if (bad.length || skippedForCap || capped) {
      let s = `Pasted ${applied} deal(s).`;
      if (bad.length) s += ` Skipped ${bad.length} invalid line(s).`;
      if (capped) s += ` ${capped} not applied (max ${BATCH_QUEUE_MAX_ROWS} rows).`;
      if (skippedForCap) s += ` ${skippedForCap} not applied (table full).`;
      batchRunStatus.textContent = s;
      const detail =
        bad.length && bad.length <= 6 ? `${s}\n\nInvalid lines:\n${bad.slice(0, 6).join("\n")}` : s;
      window.alert(detail);
    } else {
      batchRunStatus.textContent = `Pasted ${applied} deal(s) into the queue.`;
    }
  }
}

function setBatchUiLocked(locked) {
  if (locateSegmentBtn) locateSegmentBtn.disabled = locked;
  if (locateLineInput) locateLineInput.disabled = locked;
  if (checkEligibilityBtn) checkEligibilityBtn.disabled = locked;
  if (pipelineSdkBtn) pipelineSdkBtn.disabled = locked;
  for (const id of PIPELINE_TARGET_ORDER) {
    const el = document.getElementById(`pipelineTarget${id}`);
    if (el instanceof HTMLInputElement) el.disabled = locked;
  }
  if (validationRunBtn) validationRunBtn.disabled = locked;
  if (mapValuationFeesBtn) mapValuationFeesBtn.disabled = locked;
  if (batchAddRowBtn) batchAddRowBtn.disabled = locked;
  if (batchPasteOpenBtn) batchPasteOpenBtn.disabled = locked;
  if (batchPasteFoldersOpenBtn) batchPasteFoldersOpenBtn.disabled = locked;
  if (batchContinueOnError) batchContinueOnError.disabled = locked;
  if (batchRunBtn) batchRunBtn.disabled = locked;
  if (batchSdkRunBtn) batchSdkRunBtn.disabled = locked;
  if (batchValidateRunBtn) batchValidateRunBtn.disabled = locked;
  if (batchValidationSummaryBtn) batchValidationSummaryBtn.disabled = locked;
  if (batchValidateQueueOnly instanceof HTMLInputElement) batchValidateQueueOnly.disabled = locked;
  if (batchValidateStrict instanceof HTMLInputElement) batchValidateStrict.disabled = locked;
  if (batchExportXmlBtn) batchExportXmlBtn.disabled = locked;
  if (xmlExportBtn) xmlExportBtn.disabled = locked;
  const extract0102El = document.getElementById("extractDeliverables0102Only");
  if (extract0102El instanceof HTMLInputElement) extract0102El.disabled = locked;
  const extract0304El = document.getElementById("extractDeliverables0304Only");
  if (extract0304El instanceof HTMLInputElement) extract0304El.disabled = locked;
  if (!locked) applyExtractScopeUi();
  for (const btn of batchStopBtns) btn.disabled = !locked;
  renderBatchTable();
}

async function runBatchQueue() {
  if (batchRunning) return;
  syncBatchRowsFromDom();
  for (const row of batchQueueRows) {
    const c = normalizeDealPaymentLine(row.line);
    if (c !== row.line) row.line = c;
  }
  const contOnErr = !!batchContinueOnError?.checked;

  /** @type {number[]} */
  const indices = [];
  for (let i = 0; i < batchQueueRows.length; i++) {
    const { deal_id: d, payment_date: p } = parseDealPaymentLine(batchQueueRows[i].line);
    if (!d && !p) continue;
    if (!d || !p) {
      window.alert(
        `Row ${i + 1}: use deal ID, a space, then payment date on one line (example: 825275100 3/16/2026), or leave blank to skip.`
      );
      return;
    }
    indices.push(i);
  }
  if (indices.length === 0) {
    window.alert("Add at least one row: deal ID, space, then payment date.");
    return;
  }

  /** One line per queued row, frozen at batch start (avoids DOM re-read clearing lines mid-run). */
  const queuedDealLines = indices.map((idx) =>
    normalizeDealPaymentLine(batchQueueRows[idx].line),
  );

  let stoppedByUser = false;
  batchRunning = true;
  batchRunAbort = false;
  setBatchUiLocked(true);
  if (batchRunBtn) batchRunBtn.disabled = true;
  for (const btn of batchStopBtns) btn.disabled = false;
  if (batchRunStatus) batchRunStatus.textContent = `Starting batch segmentation (${indices.length} deal(s))…`;

  try {
    for (let j = 0; j < indices.length; j++) {
      if (batchRunAbort) {
        stoppedByUser = true;
        if (batchRunStatus) batchRunStatus.textContent = "Batch segmentation stopped by user.";
        break;
      }
      const i = indices[j];
      const row = batchQueueRows[i];
      const lineForDeal = queuedDealLines[j];
      row.line = lineForDeal;
      const { deal_id, payment_date } = parseDealPaymentLine(lineForDeal);
      row.detail = "";
      row.status = "Resolving…";
      renderBatchTable();
      if (batchRunStatus) {
        batchRunStatus.textContent = `Batch segmentation ${j + 1} of ${indices.length}: ${deal_id} — looking up path…`;
      }

      let resolveRes;
      let resolveData = {};
      try {
        resolveRes = await fetch("/api/resolve-path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            deal_id,
            payment_date,
          }),
        });
        resolveData = await resolveRes.json().catch(() => ({}));
      } catch (e) {
        row.status = "Error";
        row.detail = e instanceof Error ? e.message : String(e);
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      if (!resolveRes.ok) {
        row.status = "Error";
        row.detail = formatDetail(resolveData.detail) || resolveRes.statusText;
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      const pdfPath = String(resolveData.pdf_path || "").trim();
      const st = String(resolveData.status || "").toLowerCase();
      if (st !== "ok" || !pdfPath) {
        row.status = "Error";
        const srv = String(resolveData.status || "").trim();
        if (!pdfPath) {
          row.detail = srv ? `No PDF path (ARD: ${srv})` : "No PDF path.";
        } else {
          row.detail = srv ? `Unexpected ARD status: ${srv}` : "File path not found.";
        }
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      const wfPath = String(resolveData.waterfall_path || "").trim();
      row.status = "Checking path…";
      renderBatchTable();
      if (batchRunStatus) {
        batchRunStatus.textContent = `Batch segmentation ${j + 1} of ${indices.length}: ${deal_id} — checking PDF on disk…`;
      }

      const { res: chkRes, data: chkData } = await apiPostJson("/api/check-report-paths", {
        pdf_path: pdfPath,
        waterfall_path: wfPath,
        run_primary_pdf_gate: true,
      });
      if (!chkRes.ok) {
        row.status = "Error";
        row.detail = formatDetail(chkData.detail) || chkRes.statusText;
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }
      if (!chkData.ok) {
        const errs = Array.isArray(chkData.errors) ? chkData.errors.join("; ") : "";
        row.status = "Error";
        row.detail = errs || "Report file path check failed.";
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }
      const gate = interpretPrimaryPdfGate(chkData.primary_pdf_gate);
      if (gate.blocked) {
        row.status = "Error";
        row.detail = gate.text;
        renderBatchTable();
        if (batchRunStatus) {
          batchRunStatus.textContent = `Batch segmentation ${j + 1} of ${indices.length}: ${deal_id} — skipped (not noteval).`;
        }
        if (!contOnErr) break;
        continue;
      }

      const lookup = await lookupSegmentedFolderForDeal(
        String(resolveData.deal_id ?? deal_id),
        String(resolveData.payment_date ?? payment_date),
        pdfStemFromPath(pdfPath),
      );
      if (!("error" in lookup) && lookup.segmented) {
        row.output_dir = lookup.output_dir;
        row.status = "Ready";
        row.detail = "Already segmented — skipped re-segment.";
        setActiveOutputDirectory(lookup.output_dir, { refreshWrapup: false });
        renderBatchTable();
        if (batchRunStatus) {
          batchRunStatus.textContent = `Batch segmentation ${j + 1} of ${indices.length}: ${deal_id} — already segmented.`;
        }
        continue;
      }

      row.status = "Segmenting…";
      renderBatchTable();
      if (batchRunStatus) {
        batchRunStatus.textContent = `Batch segmentation ${j + 1} of ${indices.length}: ${deal_id} — segmenting…`;
      }

      let segRes;
      let segData = {};
      try {
        segRes = await fetch("/api/segment", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            deal_id: resolveData.deal_id ?? deal_id,
            payment_date: resolveData.payment_date ?? payment_date,
            pdf_path: resolveData.pdf_path,
            waterfall_path: resolveData.waterfall_path || "",
            status: resolveData.status || "",
          }),
        });
        segData = await segRes.json().catch(() => ({}));
      } catch (e) {
        row.status = "Error";
        row.detail = e instanceof Error ? e.message : String(e);
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      if (!segRes.ok) {
        row.status = "Error";
        row.detail = formatDetail(segData.detail) || segRes.statusText;
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      const outputDir = String(segData.output_dir || segData.folder || "").trim();
      if (outputDir) {
        setActiveOutputDirectory(outputDir, { refreshWrapup: false });
      }

      row.output_dir = outputDir;
      row.status = "Done";
      row.detail = outputDir ? "Segmented — run SDK extraction when ready." : "";
      renderBatchTable();
      if (batchRunStatus) {
        batchRunStatus.textContent = `Batch segmentation ${j + 1} of ${indices.length}: ${deal_id} — segmented.`;
      }
    }
  } finally {
    batchRunning = false;
    batchRunAbort = false;
    setBatchUiLocked(false);
    if (batchRunBtn) batchRunBtn.disabled = false;
    for (const btn of batchStopBtns) btn.disabled = true;
    if (batchRunStatus && !stoppedByUser) {
      let ok = 0;
      for (const ii of indices) {
        const st = batchQueueRows[ii]?.status;
        if (st === "Done" || st === "Ready") ok++;
      }
      if (indices.length > 1) {
        batchRunStatus.textContent =
          ok === indices.length
            ? `Batch segmentation finished — ${ok}/${indices.length} deals segmented. Run SDK extraction per folder as needed.`
            : `Batch segmentation ended — ${ok}/${indices.length} deals segmented. Check the Status column for Error/Stopped rows.`;
      } else {
        batchRunStatus.textContent = "Batch segmentation finished — deal segmented.";
      }
    }
  }
}

function formatDetail(detail) {
  if (detail == null) return "Unknown error";
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && !Array.isArray(detail)) {
    const o = /** @type {Record<string, unknown>} */ (detail);
    if (String(o.error || "") === "primary_pdf_gate_failed") {
      const msg = typeof o.message === "string" ? o.message : "";
      const meta = o.meta && typeof o.meta === "object" ? o.meta : {};
      return humanNotevalGateMessage(false, msg, meta);
    }
  }
  if (Array.isArray(detail)) {
    return detail.map((d) => d.msg || JSON.stringify(d)).join("; ");
  }
  return JSON.stringify(detail);
}

/**
 * @param {boolean} pass
 * @param {string} message
 * @param {Record<string, unknown>} [meta]
 */
function humanNotevalGateMessage(pass, message, meta = {}) {
  if (pass) return "";
  const head = "Not enough noteval-style data in this primary PDF for segmentation / extraction.";
  const m = String(message || "").trim();
  const bits = [head];
  if (m) bits.push(m);
  const pages = typeof meta.pages === "number" ? meta.pages : null;
  const maxp = typeof meta.max_pages === "number" ? meta.max_pages : null;
  if (pages != null && maxp != null && pages > maxp) {
    bits.push(`This file has ${pages} pages (gate max is ${maxp}).`);
  }
  return bits.join(" ");
}

/**
 * @param {unknown} gate — `primary_pdf_gate` from `/api/check-report-paths`
 * @returns {{ blocked: boolean; text: string }}
 */
function interpretPrimaryPdfGate(gate) {
  if (!gate || typeof gate !== "object") return { blocked: false, text: "" };
  const g = /** @type {Record<string, unknown>} */ (gate);
  if (g.pass !== false) return { blocked: false, text: "" };
  const msg = typeof g.message === "string" ? g.message : "";
  const meta = g.meta && typeof g.meta === "object" ? /** @type {Record<string, unknown>} */ (g.meta) : {};
  return { blocked: true, text: humanNotevalGateMessage(false, msg, meta) };
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    window.prompt("Copy path:", text);
  }
}

/**
 * @param {unknown} cfg — `/api/extraction/sdk-config` JSON
 */
function applyExtractionHints(cfg) {
  const el = pipelineExtractionHint;
  if (!el) return;
  if (!cfg || typeof cfg !== "object") {
    el.textContent = "Could not load extraction status.";
    return;
  }
  const d = /** @type {Record<string, unknown>} */ (cfg);
  const lines = [];

  if (d.configured === true) {
    lines.push("SDK: ready (writes 01–04 in the deal folder).");
  } else {
    const bits = [];
    if (!d.api_key_set) bits.push("CURSOR_API_KEY missing");
    if (d.node_ok === false) bits.push("Node.js/npm not on server PATH");
    if (d.sdk_package_installed === false) bits.push("npm install in cursor_sdk_compare/");
    const note = typeof d.note === "string" ? d.note.trim() : "";
    const apiHint = typeof d.api_key_hint === "string" ? d.api_key_hint.trim() : "";
    lines.push(
      bits.length > 0
        ? `SDK: not ready — ${bits.join("; ")}.${note ? ` ${note}` : ""}`
        : note || apiHint || "SDK: not ready.",
    );
  }

  if (isExtract0102Only()) {
    lines.push("Scope: 01 & 02 only.");
  } else if (isExtract0304Only()) {
    lines.push("Scope: 03 & 04 only (existing 01 & 02 kept).");
  }

  el.textContent = lines.join(" ");
}

async function refreshExtractionHints() {
  try {
    const r = await fetch("/api/extraction/sdk-config");
    const d = await r.json().catch(() => ({}));
    applyExtractionHints(d);
  } catch {
    applyExtractionHints(null);
  }
}

/**
 * @param {string} jobId
 */
/**
 * Estimated USD from SDK job result or log tail (``cost_usd≈`` line).
 * @param {Record<string, unknown> | null | undefined} result
 * @param {string} [logText]
 * @returns {number | null}
 */
function sdkCostUsdFromJob(result, logText = "") {
  const u = result && typeof result === "object" ? result.sdk_usage : null;
  if (u && typeof u === "object") {
    const raw = /** @type {{ cost_usd?: unknown }} */ (u).cost_usd;
    if (typeof raw === "number" && Number.isFinite(raw)) return raw;
    if (raw != null) {
      const n = Number(raw);
      if (Number.isFinite(n)) return n;
    }
  }
  const m = String(logText || "").match(/cost_usd≈([\d.]+)/);
  if (m) {
    const n = Number(m[1]);
    if (Number.isFinite(n)) return n;
  }
  return null;
}

/**
 * @param {number} usd
 */
function formatBatchCostUsd(usd) {
  return `$${usd.toFixed(4)}`;
}

/** @returns {string} */
function newExtractionBatchId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `batch-${Date.now()}`;
}

/** @param {"llm"|"sdk"|"all"} source */
function rememberExtractionBatchId(source, batchId) {
  try {
    sessionStorage.setItem(`noteval_batch_id_${source}`, batchId);
  } catch {
    /* ignore */
  }
}

/** @param {"llm"|"sdk"|"all"} source */
function lastExtractionBatchId(source) {
  try {
    return sessionStorage.getItem(`noteval_batch_id_${source}`) || "";
  } catch {
    return "";
  }
}

/**
 * @param {"llm"|"sdk"} source
 * @param {string} batchId
 * @param {Record<string, number>} costsByFolder
 * @param {string[]} folderNames
 */
async function persistBatchCostManifest(source, batchId, costsByFolder, folderNames) {
  const keys = Object.keys(costsByFolder);
  if (!batchId || keys.length === 0) return;
  try {
    await apiPostJson("/api/extraction/batch-cost-manifest", {
      batch_id: batchId,
      source,
      costs: costsByFolder,
      folder_names: folderNames,
    });
    rememberExtractionBatchId(source, batchId);
  } catch {
    /* manifest is optional; validation falls back to no costs */
  }
}

/**
 * @param {string} jobId
 * @param {{ shouldAbort?: () => boolean; logPrefix?: string }} [opts]
 */
async function waitForSdkJobComplete(jobId, opts = {}) {
  const { shouldAbort, logPrefix = "", suppressFinishStatus = false } = opts;
  if (!pipelineLog || !pipelineStatus) {
    return { ok: false, error: "Missing extraction UI", finalLogs: "" };
  }
  let lastLogs = "";
  while (true) {
    if (shouldAbort?.()) {
      pipelineStatus.textContent = "Stopped.";
      return { ok: false, error: "aborted", aborted: true, finalLogs: logPrefix + lastLogs };
    }
    const r = await fetch(`/api/extraction/sdk/${encodeURIComponent(jobId)}`, { cache: "no-store" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = formatDetail(j.detail) || r.statusText;
      pipelineStatus.textContent = msg;
      return { ok: false, error: msg, finalLogs: logPrefix + lastLogs };
    }
    const logs = Array.isArray(j.logs) ? j.logs : [];
    lastLogs = logs.join("\n");
    pipelineLog.textContent = logPrefix + lastLogs;
    pipelineLog.scrollTop = pipelineLog.scrollHeight;
    if (j.status === "done" || j.status === "error") {
      if (j.status === "done") {
        const res = j.result && typeof j.result === "object" ? j.result : {};
        const outDir = typeof res.sdk_dir === "string" ? res.sdk_dir : "";
        const vrc =
          res.validation && typeof res.validation === "object"
            ? res.validation.returncode
            : null;
        const fm =
          res.fee_mapping && typeof res.fee_mapping === "object" ? res.fee_mapping : null;
        const fmTail =
          fm && fm.mapped_count != null
            ? ` map_valuation_fees: ${fm.mapped_count} fee row(s).`
            : "";
        const tail =
          (typeof vrc === "number"
            ? ` validate_noteval exit ${vrc} (see validation_report.md).`
            : "") + fmTail;
        if (!suppressFinishStatus) {
          pipelineStatus.textContent = outDir
            ? `SDK extraction finished.${tail} Output: ${outDir}`
            : `SDK extraction finished.${tail}`;
        }
        if (outDir) {
          addOutputPathToHistory(outDir);
          if (!suppressFinishStatus) {
            setActiveOutputDirectory(outDir, { refreshWrapup: true });
          }
        }
        if (!suppressFinishStatus) {
          void refreshWrapUpPanel({ quiet: true });
          const val = res.validation;
          if (val && typeof val === "object") {
            applyValidationUiFromApiData(val);
          }
        }
        const costUsd = sdkCostUsdFromJob(res, lastLogs);
        return {
          ok: true,
          result: res,
          finalLogs: logPrefix + lastLogs,
          costUsd,
        };
      }
      if (!suppressFinishStatus) {
        pipelineStatus.textContent = `SDK extraction failed: ${j.error || "unknown error"}`;
      }
      return { ok: false, error: j.error || "unknown error", finalLogs: logPrefix + lastLogs, costUsd: null };
    }
    if (!suppressFinishStatus) {
      pipelineStatus.textContent = `Job ${jobId} — Cursor agent running…`;
    }
    await sleep(3000);
  }
}

/**
 * Deal folder path (no ``_sdk`` suffix) from a batch row output path.
 * @param {string} outputDir
 */
function batchRowDealDir(outputDir) {
  const p = String(outputDir || "").trim();
  if (!p) return "";
  return p.replace(/_sdk\/?$/i, "");
}

async function runBatchSdkQueue() {
  if (batchRunning) return;
  syncBatchRowsFromDom();

  /** @type {number[]} */
  const indices = [];
  for (let i = 0; i < batchQueueRows.length; i++) {
    if (String(batchQueueRows[i].output_dir || "").trim()) {
      indices.push(i);
    }
  }
  if (indices.length === 0) {
    window.alert(
      "No output folders in the queue. Run batch segmentation first, or click a row's output path after segmenting a deal.",
    );
    return;
  }

  const contOnErr = !!batchContinueOnError?.checked;

  try {
    const cfgR = await fetch("/api/extraction/sdk-config");
    const cfg = await cfgR.json().catch(() => ({}));
    if (!cfg.configured) {
      window.alert(formatDetail(cfg.note) || "Cursor SDK not configured (CURSOR_API_KEY, npm install).");
      return;
    }
  } catch (e) {
    window.alert(e instanceof Error ? e.message : String(e));
    return;
  }

  let stoppedByUser = false;
  batchRunning = true;
  batchRunAbort = false;
  setBatchUiLocked(true);
  if (batchRunBtn) batchRunBtn.disabled = true;
  if (batchSdkRunBtn) batchSdkRunBtn.disabled = true;
  for (const btn of batchStopBtns) btn.disabled = false;
  if (pipelineLog) pipelineLog.textContent = "";
  if (batchRunStatus) {
    batchRunStatus.textContent = `Starting batch SDK extraction (${indices.length} deal(s))…`;
  }

  let okCount = 0;
  let skipCount = 0;
  let batchCostUsd = 0;
  let batchCostDeals = 0;
  const batchId = newExtractionBatchId();
  /** @type {Record<string, number>} */
  const batchCostsByFolder = {};
  const sdkTargets = getEffectivePipelineTargets();

  try {
    for (let j = 0; j < indices.length; j++) {
      if (batchRunAbort) {
        stoppedByUser = true;
        if (batchRunStatus) batchRunStatus.textContent = "Batch SDK extraction stopped by user.";
        break;
      }

      const i = indices[j];
      const row = batchQueueRows[i];
      const sourceDir = String(row.output_dir || "").trim();
      const dealDir = batchRowDealDir(sourceDir) || sourceDir;
      const label =
        row.line.trim() ||
        labelFromFolderBasename(outputPathBasename(dealDir)) ||
        dealDir;

      row.detail = "";
      const forceReBatchSdk = isForceReextract();
      const extCheck = await checkDealExtractionComplete(dealDir, sdkTargets, { force: forceReBatchSdk });
      if (extCheck.complete) {
        row.status = "Skipped";
        row.detail = `${dealDir} — already extracted (${sdkTargets.join(", ")}).`;
        skipCount++;
        renderBatchTable();
        appendExtractionSkipLog(
          dealDir,
          sdkTargets,
          label,
          `\n=== Batch SDK ${j + 1}/${indices.length}: ${label} ===\n`,
        );
        if (batchRunStatus) {
          batchRunStatus.textContent = `Batch SDK ${j + 1} of ${indices.length}: ${label} — skipped (already extracted).`;
        }
        continue;
      }

      row.status = "SDK running…";
      renderBatchTable();
      if (batchRunStatus) {
        batchRunStatus.textContent = `Batch SDK ${j + 1} of ${indices.length}: ${label} — Cursor agent…`;
      }
      if (pipelineStatus) {
        pipelineStatus.textContent = `Batch SDK ${j + 1}/${indices.length}: ${label}`;
      }

      let startRes;
      let startData = {};
      try {
        ({ res: startRes, data: startData } = await apiPostJson(
          "/api/extraction/sdk/start",
          {
            output_dir: dealDir,
            prepare: false,
            run_validate: false,
            targets: sdkTargets,
          },
          { timeoutMs: 120_000 },
        ));
      } catch (e) {
        row.status = batchRunAbort ? "Stopped" : "Error";
        row.detail = e instanceof Error ? e.message : String(e);
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      if (!startRes.ok) {
        row.status = "Error";
        row.detail = formatDetail(startData.detail) || startRes.statusText;
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      const jobId = startData.job_id;
      if (!jobId) {
        row.status = "Error";
        row.detail = "No job_id from SDK start.";
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      const logPrefix = `\n=== Batch SDK ${j + 1}/${indices.length}: ${label} ===\n`;
      const poll = await waitForSdkJobComplete(jobId, {
        shouldAbort: () => batchRunAbort,
        logPrefix,
        suppressFinishStatus: true,
      });

      if (!poll.ok) {
        row.status = batchRunAbort ? "Stopped" : "Error";
        row.detail = poll.aborted
          ? "Stopped"
          : String(poll.error || "SDK extraction failed").slice(0, 240);
        renderBatchTable();
        if (!contOnErr) break;
        continue;
      }

      const outDir = dealDir;
      if (typeof poll.costUsd === "number" && Number.isFinite(poll.costUsd)) {
        batchCostUsd += poll.costUsd;
        batchCostDeals += 1;
        const folderKey = outputPathBasename(outDir);
        if (folderKey) batchCostsByFolder[folderKey] = poll.costUsd;
        if (pipelineLog) {
          pipelineLog.textContent =
            (pipelineLog.textContent || "") +
            `\nDeal cost (estimated): ${formatBatchCostUsd(poll.costUsd)}\n`;
          pipelineLog.scrollTop = pipelineLog.scrollHeight;
        }
      }

      const mapFeesAfter = !isExtract0102Only();
      if (mapFeesAfter) {
        row.status = "Map fees…";
        renderBatchTable();
        try {
          let mapRes;
          let mapData = {};
          ({ res: mapRes, data: mapData } = await apiPostJson("/api/extraction/map-valuation-fees", {
            output_dir: outDir,
          }));
          if (!mapRes.ok) {
            row.status = "SDK done (fees failed)";
            row.detail = `${outDir} — ${formatDetail(mapData.detail) || mapRes.statusText}`.slice(
              0,
              280,
            );
          } else {
            const n = mapData.mapped_count ?? "?";
            row.status = "SDK done";
            row.detail = `${outDir} — mapped ${n} fee row(s)`;
            okCount++;
          }
        } catch (e) {
          row.status = "SDK done (fees failed)";
          row.detail = `${outDir} — ${e instanceof Error ? e.message : String(e)}`.slice(0, 280);
          okCount++;
        }
      } else {
        row.status = "SDK done";
        row.detail = `${outDir} — 01 & 02 only (fees skipped)`;
        okCount++;
      }

      row.output_dir = outDir;
      addOutputPathToHistory(outDir);
      if (j === indices.length - 1 || !batchRunAbort) {
        setActiveOutputDirectory(outDir, { refreshWrapup: j === indices.length - 1 });
      }
      renderBatchTable();
      if (batchRunStatus) {
        batchRunStatus.textContent = `Batch SDK ${j + 1} of ${indices.length}: ${label} — done.`;
      }
    }
  } finally {
    await persistBatchCostManifest(
      "sdk",
      batchId,
      batchCostsByFolder,
      Object.keys(batchCostsByFolder),
    );
    const batchCostSuffix =
      batchCostDeals > 0
        ? ` Total batch cost (estimated): ${formatBatchCostUsd(batchCostUsd)} (${batchCostDeals} deal(s) with usage).`
        : "";
    if (batchCostDeals > 0 && pipelineLog) {
      pipelineLog.textContent =
        (pipelineLog.textContent || "") +
        `\n=== Batch SDK total (estimated) ===\nTotal batch cost: ${formatBatchCostUsd(batchCostUsd)} USD (${batchCostDeals} deal(s) with usage logged)\n`;
      pipelineLog.scrollTop = pipelineLog.scrollHeight;
    }
    batchRunning = false;
    batchRunAbort = false;
    setBatchUiLocked(false);
    if (batchRunBtn) batchRunBtn.disabled = false;
    if (batchSdkRunBtn) batchSdkRunBtn.disabled = false;
    for (const btn of batchStopBtns) btn.disabled = true;
    if (batchRunStatus && !stoppedByUser) {
      const skipSuffix =
        skipCount > 0 ? ` ${skipCount} skipped (already extracted).` : "";
      if (indices.length > 1) {
        const doneTotal = okCount + skipCount;
        batchRunStatus.textContent =
          (doneTotal === indices.length && okCount === indices.length
            ? `Batch SDK extraction finished — ${okCount}/${indices.length} deals. Validate each deal folder as needed.`
            : doneTotal === indices.length
              ? `Batch SDK extraction finished — ${okCount} extracted, ${skipCount} skipped.${skipSuffix}`
              : `Batch SDK extraction ended — ${okCount} extracted, ${skipCount} skipped, ${indices.length - doneTotal} failed. Check Status for errors.`) +
          batchCostSuffix;
      } else if (skipCount === 1) {
        batchRunStatus.textContent = `Batch SDK extraction skipped — deliverables already present.${batchCostSuffix}`;
      } else if (okCount === 1) {
        batchRunStatus.textContent = `Batch SDK extraction finished.${batchCostSuffix}`;
      } else {
        batchRunStatus.textContent = `Batch SDK extraction finished with errors.${batchCostSuffix}`;
      }
    }
    void refreshWrapUpPanel({ quiet: true });
  }
}

async function startSdkExtraction() {
  if (!pipelineStatus || !pipelineLog || batchRunning) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    pipelineStatus.textContent = "Set active output directory first (segment a deal).";
    return;
  }
  const sdkTargets = getEffectivePipelineTargets();
  pipelineStatus.textContent = "Checking existing deliverables…";
  pipelineLog.textContent = "";
  if (pipelineSdkBtn) pipelineSdkBtn.disabled = true;
  try {
    const cfgR = await fetch("/api/extraction/sdk-config");
    const cfg = await cfgR.json().catch(() => ({}));
    if (!cfg.configured) {
      pipelineStatus.textContent = formatDetail(cfg.note) || "Cursor SDK not configured.";
      return;
    }
    const forceReSdk = isForceReextract();
    const extCheck = await checkDealExtractionComplete(out, sdkTargets, { force: forceReSdk });
    if (extCheck.complete) {
      pipelineStatus.textContent = `Skipped — deliverables already present (${sdkTargets.join(", ")}).`;
      appendExtractionSkipLog(out, sdkTargets, outputPathBasename(out));
      return;
    }
    pipelineStatus.textContent = "Starting Cursor SDK extraction…";
    const { res, data } = await apiPostJson("/api/extraction/sdk/start", {
      output_dir: out,
      prepare: false,
      run_validate: false,
      targets: sdkTargets,
      force_reextract: forceReSdk,
    });
    if (!res.ok) {
      pipelineStatus.textContent = formatDetail(data.detail) || res.statusText;
      return;
    }
    const jobId = data.job_id;
    if (!jobId) {
      pipelineStatus.textContent = "No job_id returned.";
      return;
    }
    pipelineStatus.textContent = `Job ${jobId} — Cursor agent extracting ${sdkTargets.join(", ")}…`;
    await waitForSdkJobComplete(jobId);
  } catch (e) {
    pipelineStatus.textContent = e instanceof Error ? e.message : String(e);
  } finally {
    if (pipelineSdkBtn) pipelineSdkBtn.disabled = false;
  }
}

function resetSegmentLogPanel() {
  if (!segmentLogBox) return;
  segmentLogBox.hidden = true;
  segmentLogBox.textContent = "";
  if (segmentLogToolbar) segmentLogToolbar.hidden = true;
  if (segmentLogToggleBtn) {
    segmentLogToggleBtn.textContent = "Show segment log";
    segmentLogToggleBtn.setAttribute("aria-expanded", "false");
  }
}

/** @param {string} text */
function storeSegmentLog(text) {
  if (!segmentLogBox) return;
  segmentLogBox.textContent = text;
  segmentLogBox.hidden = true;
  const has = String(text || "").trim().length > 0;
  if (segmentLogToolbar) segmentLogToolbar.hidden = !has;
  if (segmentLogToggleBtn) {
    segmentLogToggleBtn.textContent = "Show segment log";
    segmentLogToggleBtn.setAttribute("aria-expanded", "false");
  }
}

/** @param {string} message @param {"ok"|"bad"|"warn"|"muted"} [tone] */
function setSegmentStatus(message, tone = "muted") {
  if (!segmentStatusLine) return;
  segmentStatusLine.className = `hint resolve-status ${tone === "muted" ? "muted" : tone}`;
  segmentStatusLine.textContent = message;
}

/**
 * Resolve ARD path, run noteval gate, then segment PDF into output folder.
 * @returns {Promise<boolean>}
 */
async function locateAndSegmentPdf() {
  if (!segmentStatusLine) return false;
  const { deal_id, payment_date } = parseDealPaymentLine(locateLineInput?.value || "");
  if (!deal_id || !payment_date) {
    setSegmentStatus(
      "Enter deal ID, a space, then payment date on one line (example: 825275100 3/16/2026).",
      "bad",
    );
    return false;
  }

  lastResolved = null;
  resetSegmentLogPanel();
  if (cockpitOutputDir) cockpitOutputDir.value = "";
  renderOutputPathHistory();

  if (locateSegmentBtn) locateSegmentBtn.disabled = true;
  if (checkEligibilityBtn) checkEligibilityBtn.disabled = true;
  setSegmentStatus("Looking up file path…", "muted");

  try {
    const res = await fetch("/api/resolve-path", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ deal_id, payment_date }),
    });
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      setSegmentStatus(formatDetail(data.detail) || res.statusText, "bad");
      return false;
    }

    lastResolved = data;
    const p = String(data.pdf_path || "").trim();
    const st = String(data.status || "").toLowerCase();
    if (st !== "ok" || !p) {
      const stRaw = String(data.status || "").trim();
      setSegmentStatus(
        stRaw && stRaw !== "ok"
          ? `No usable primary path (ARD status: ${stRaw}).`
          : "No PDF path in ARD response for this deal and payment date.",
        "bad",
      );
      return false;
    }

    setSegmentStatus(`Path found. Checking noteval eligibility…\n${p}`, "muted");

    const gateResult = await evaluateReportPathsAndNotevalGate(lastResolved);
    if (!gateResult.pass) {
      setSegmentStatus(gateResult.userMessage, "bad");
      return false;
    }

    const lookup = await lookupSegmentedFolderForDeal(
      String(lastResolved.deal_id ?? deal_id),
      String(lastResolved.payment_date ?? payment_date),
      pdfStemFromPath(p),
    );
    if (!("error" in lookup) && lookup.segmented) {
      setSegmentStatus(`Already segmented. Output: ${lookup.output_dir}`, "ok");
      setActiveOutputDirectory(lookup.output_dir, { refreshWrapup: true });
      return true;
    }

    setSegmentStatus("Segmenting PDF…", "muted");

    const segRes = await fetch("/api/segment", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        deal_id: lastResolved.deal_id,
        payment_date: lastResolved.payment_date,
        pdf_path: lastResolved.pdf_path,
        waterfall_path: lastResolved.waterfall_path || "",
        status: lastResolved.status || "",
      }),
    });
    const segData = await segRes.json().catch(() => ({}));

    if (!segRes.ok) {
      setSegmentStatus(formatDetail(segData.detail) || segRes.statusText, "bad");
      if (typeof segData.detail === "string" && segData.detail.length > 200) {
        storeSegmentLog(segData.detail);
      }
      return false;
    }

    const outDir = String(segData.output_dir || segData.folder || "").trim();
    setSegmentStatus(`Done. Output: ${outDir}`, "ok");
    storeSegmentLog(segData.log || "(no log output)");
    if (outDir) {
      setActiveOutputDirectory(outDir, { refreshWrapup: true });
    }
    return true;
  } catch (err) {
    setSegmentStatus(err instanceof Error ? err.message : String(err), "bad");
    return false;
  } finally {
    if (locateSegmentBtn) locateSegmentBtn.disabled = false;
    if (checkEligibilityBtn) checkEligibilityBtn.disabled = false;
  }
}

/**
 * @param {string} url
 * @param {unknown} body
 * @param {{ timeoutMs?: number }} [opts]
 */
async function apiPostJson(url, body, opts = {}) {
  const timeoutMs = typeof opts.timeoutMs === "number" && opts.timeoutMs > 0 ? opts.timeoutMs : 0;
  /** @type {RequestInit} */
  const init = {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
  if (timeoutMs) {
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      init.signal = AbortSignal.timeout(timeoutMs);
    } else {
      const ctrl = new AbortController();
      const tid = window.setTimeout(() => ctrl.abort(), timeoutMs);
      init.signal = ctrl.signal;
      try {
        const res = await fetch(url, init);
        const data = await res.json().catch(() => ({}));
        return { res, data };
      } finally {
        window.clearTimeout(tid);
      }
    }
  }
  const res = await fetch(url, init);
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

/**
 * File on disk + primary PDF noteval gate (same checks as the start of Segment).
 * @param {{ pdf_path?: string; waterfall_path?: string }} resolved
 * @returns {Promise<{ pass: boolean; userMessage: string }>}
 */
async function evaluateReportPathsAndNotevalGate(resolved) {
  const pdfPath = String(resolved?.pdf_path ?? "").trim();
  if (!pdfPath) {
    return { pass: false, userMessage: "No primary pdf_path on the resolved row — run Find file path again." };
  }
  let chkRes;
  let chkData;
  try {
    ({ res: chkRes, data: chkData } = await apiPostJson(
      "/api/check-report-paths",
      {
        pdf_path: pdfPath,
        waterfall_path: String(resolved?.waterfall_path ?? "").trim(),
        run_primary_pdf_gate: true,
      },
      { timeoutMs: 180_000 },
    ));
  } catch (e) {
    const name = e && typeof e === "object" && "name" in e ? String(/** @type {{ name?: string }} */ (e).name) : "";
    if (name === "AbortError" || name === "TimeoutError") {
      return {
        pass: false,
        userMessage:
          "Eligibility check timed out (server took too long reading the PDF). Try again, or run Segment after confirming the file opens locally.",
      };
    }
    throw e;
  }
  if (!chkRes.ok) {
    return { pass: false, userMessage: formatDetail(chkData.detail) || chkRes.statusText };
  }
  if (!chkData.ok) {
    const errs = Array.isArray(chkData.errors) ? chkData.errors.join("; ") : "";
    return { pass: false, userMessage: errs || "Report file path check failed." };
  }
  const gate = interpretPrimaryPdfGate(chkData.primary_pdf_gate);
  if (gate.blocked) {
    return { pass: false, userMessage: gate.text };
  }
  return {
    pass: true,
    userMessage:
      "Noteval eligibility: passed. Primary PDF exists on this server and meets the noteval gate. You can run Segment PDF.",
  };
}

/**
 * @param {string} line
 */
function isMarkdownTableSeparatorLine(line) {
  return /^\|[\s\-:|]+\|$/.test(line.trim());
}

/**
 * @param {string} sectionText
 * @returns {{ headers: string[]; rows: string[][] } | null}
 */
function parseFirstPipeTableInSection(sectionText) {
  const lines = sectionText.split(/\r?\n/);
  const pipeLines = [];
  for (const row of lines) {
    const line = row.trim();
    if (line.startsWith("|")) {
      pipeLines.push(line);
    } else if (pipeLines.length > 0) {
      break;
    }
  }
  return parsePipeTableFromLines(pipeLines);
}

/**
 * All consecutive pipe tables in a section (e.g. interest + principal blocks under ### Waterfall table).
 * @param {string} sectionText
 * @returns {{ headers: string[]; rows: string[][] }[]}
 */
function parseAllPipeTablesInSection(sectionText) {
  const lines = String(sectionText || "").split(/\r?\n/);
  /** @type {{ headers: string[]; rows: string[][] }[]} */
  const tables = [];
  let i = 0;
  while (i < lines.length) {
    if (!lines[i].trim().startsWith("|")) {
      i += 1;
      continue;
    }
    const pipeLines = [];
    while (i < lines.length && lines[i].trim().startsWith("|")) {
      pipeLines.push(lines[i].trim());
      i += 1;
    }
    const parsed = parsePipeTableFromLines(pipeLines);
    if (parsed) tables.push(parsed);
  }
  return tables;
}

/**
 * @param {string[]} pipeLines
 * @returns {{ headers: string[]; rows: string[][] } | null}
 */
function parsePipeTableFromLines(pipeLines) {
  if (pipeLines.length < 3) return null;
  const splitRow = (s) =>
    s
      .replace(/^\|/, "")
      .replace(/\|\s*$/, "")
      .split("|")
      .map((c) => String(c || "").trim());
  const header = splitRow(pipeLines[0]);
  if (!header.length || !isMarkdownTableSeparatorLine(pipeLines[1])) {
    return null;
  }
  const rows = [];
  for (let k = 2; k < pipeLines.length; k++) {
    let cells = splitRow(pipeLines[k]);
    if (!cells.some((c) => c)) continue;
    while (cells.length < header.length) cells.push("");
    if (cells.length > header.length) cells = cells.slice(0, header.length);
    rows.push(cells);
  }
  return { headers: header, rows };
}

/**
 * @param {string[]} lines
 * @param {string} headingStartsWith
 */
function findMarkdownHeadingLineIndex(lines, headingStartsWith) {
  const sw = String(headingStartsWith);
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trimStart();
    if (t.startsWith(sw)) return i;
  }
  return -1;
}

/**
 * Body lines after a markdown heading until the next `##` / `###` heading.
 * @param {string} md
 * @param {string} headingStartsWith e.g. "### Waterfall table"
 */
function extractSubsectionBodyAfterHeading(md, headingStartsWith) {
  const lines = String(md || "").split(/\r?\n/);
  const hi = findMarkdownHeadingLineIndex(lines, headingStartsWith);
  if (hi === -1) {
    return { error: `No heading starting with «${headingStartsWith}».`, content: "" };
  }
  const out = [];
  for (let j = hi + 1; j < lines.length; j++) {
    if (/^#{2,3}\s/.test(lines[j])) break;
    out.push(lines[j]);
  }
  return { error: "", content: out.join("\n") };
}

/**
 * True when a money cell parses as **numeric zero** (used for valuation-fee roll-up display only).
 * @param {string} cell
 */
function isParsableZeroPaidCellForWrapupUi(cell) {
  const t = String(cell ?? "").trim();
  if (!t || /^n\/?a$/i.test(t)) return false;
  if (t === "—" || t === "-" || t === "--") return false;
  const cleaned = t
    .replace(/,/g, "")
    .replace(/[$€£]\s*/g, "")
    .replace(/^\(([\d.,]+)\)$/, "-$1");
  const n = Number.parseFloat(cleaned);
  if (!Number.isFinite(n)) return false;
  return Math.abs(n) < 1e-9;
}

/**
 * Waterfall UI: all rows from `03` ### Waterfall table (including **0.00** paid).
 * @param {string[]} headers
 * @param {string[][]} rows
 */
function projectWaterfallPriorityItemPaid(headers, rows) {
  const iPaid = findColumnIndexFlexible(headers, "amount paid");
  if (iPaid < 0) {
    return { error: "Waterfall table has no «Amount paid» column.", displayHeaders: [], data: [] };
  }
  const iPayable = findColumnIndexFlexible(headers, "amount payable");
  const iPri = findColumnIndexFlexible(headers, "priority");
  let iItem = findColumnIndexFlexible(
    headers,
    "item / payee description",
    "item / payee",
    "item description",
    "clause / step",
  );
  if (iItem < 0 && headers.length > 1) {
    const tryIdx = iPaid <= 1 ? Math.min(2, headers.length - 1) : 1;
    if (tryIdx >= 0 && tryIdx < headers.length && tryIdx !== iPaid && tryIdx !== iPri) {
      iItem = tryIdx;
    }
  }
  /** @type {string[]} */
  const dispH = ["Priority", "Item / payee description", "Amount paid"];
  if (iPayable >= 0) dispH.push("Amount payable");
  const data = [];
  for (const raw of rows) {
    const row = [...raw];
    while (row.length < headers.length) row.push("");
    const pri = iPri >= 0 && iPri < row.length ? String(row[iPri] ?? "").trim() : "";
    const item =
      iItem >= 0 && iItem < row.length ? String(row[iItem] ?? "").trim() : "";
    const paid = iPaid < row.length ? String(row[iPaid] ?? "").trim() : "";
    const payable =
      iPayable >= 0 && iPayable < row.length ? String(row[iPayable] ?? "").trim() : "";
    if (!pri && !item && !paid && !payable) continue;
    const out = [pri, item, paid];
    if (iPayable >= 0) out.push(payable);
    data.push(out);
  }
  return { error: "", displayHeaders: dispH, data };
}

/**
 * Admin expense grid UI: item name + paid amount only.
 * @param {string[]} headers
 * @param {string[][]} rows
 */
function adminGridPaidColumnIndex(headers) {
  const keys = [
    "paid on the distribution date",
    "paid on the distribution",
    "paid during the period",
    "paid during",
  ];
  for (const k of keys) {
    const ix = findColumnIndexFlexible(headers, k);
    if (ix < 0) continue;
    const hl = String(headers[ix] || "").toLowerCase();
    if (hl.includes("unpaid")) continue;
    return ix;
  }
  const ix = findColumnIndexFlexible(headers, "amount paid");
  if (ix >= 0) {
    const hl = String(headers[ix] || "").toLowerCase();
    if (!hl.includes("payable") && !hl.includes("due from") && !hl.includes("unpaid")) return ix;
  }
  return -1;
}

/**
 * @param {string[]} headers
 * @param {string[][]} rows
 */
function projectAdminGridItemAndPaid(headers, rows) {
  const iItem = findColumnIndexFlexible(
    headers,
    "expense / fee type",
    "expense / fee",
    "fee type",
    "description",
  );
  const iPaid = adminGridPaidColumnIndex(headers);
  if (iItem < 0 || iPaid < 0) {
    return {
      error: "Admin grid: could not find item and paid columns (see template **Paid on the Distribution Date** / **Expense / fee type**).",
      displayHeaders: ["Item", "Amount paid"],
      data: [],
    };
  }
  const dispH = ["Item", "Amount paid"];
  const data = [];
  for (const raw of rows) {
    const row = [...raw];
    while (row.length < headers.length) row.push("");
    data.push([
      iItem < row.length ? String(row[iItem] ?? "").trim() : "",
      iPaid < row.length ? String(row[iPaid] ?? "").trim() : "",
    ]);
  }
  const filtered = data.filter((r) => !isParsableZeroPaidCellForWrapupUi(String(r[1] ?? "")));
  return { error: "", displayHeaders: dispH, data: filtered };
}

/**
 * @param {HTMLElement} parent
 * @param {string[]} displayHeaders
 * @param {string[][]} data
 * @param {string} tableClass
 * @param {number[]} numericColIndices
 */
function appendDataTable(parent, displayHeaders, data, tableClass, numericColIndices = []) {
  const numSet = new Set(numericColIndices);
  const tbl = document.createElement("table");
  tbl.className = tableClass;
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  displayHeaders.forEach((h, i) => {
    const th = document.createElement("th");
    th.textContent = h;
    if (numSet.has(i)) th.classList.add("num");
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  tbl.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of data) {
    const tr = document.createElement("tr");
    row.forEach((cell, i) => {
      const td = document.createElement("td");
      td.textContent = cell;
      if (numSet.has(i)) td.classList.add("num");
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
  tbl.appendChild(tbody);
  parent.appendChild(tbl);
}

/**
 * @param {string[]} headers
 */
function isClassBalanceLikeTable(headers) {
  const h = headers.join(" | ").toLowerCase();
  return h.includes("class") && h.includes("beginning balance");
}

/**
 * @param {string} cell
 */
function isTotalLikeClassLabel(cell) {
  const t = String(cell || "").trim().toLowerCase();
  if (!t) return false;
  return (
    t.includes("total") ||
    t.includes("aggregate") ||
    t.includes("subtotal") ||
    t.includes("sum") ||
    t.includes("combined") ||
    t.includes("all classes")
  );
}

/**
 * Admin grid item column: explicit total / subtotal style labels (trustee voucher wording).
 * @param {string} item
 */
function isAdminGridTotalLikeItemLabel(item) {
  if (isTotalLikeClassLabel(item)) return true;
  const t = String(item || "").trim().toLowerCase();
  if (!t) return false;
  if (t.includes("total administrative") || t.includes("administrative expenses total")) return true;
  if (t.includes("total") && t.includes("expense")) return true;
  return false;
}

/**
 * CLO grids often use a single bundle line spelled exactly «Administrative Expenses» for the rolled-up admin cash.
 * @param {string} item
 */
function isAdminBundleExpensesLabel(item) {
  return String(item || "").trim().toLowerCase() === "administrative expenses";
}

/**
 * @param {string} paid
 */
function adminGridPaidCellHasContent(paid) {
  const t = String(paid || "").trim();
  if (!t) return false;
  if (/^n\/?a$/i.test(t)) return false;
  if (t === "—" || t === "-" || t === "--") return false;
  return true;
}

/**
 * Pick a printed total / rollup row from projected [[Item, Amount paid], ...] (bottom-up; no summing).
 * @param {string[][]} itemPaidRows
 * @returns {{ item: string; paid: string } | null}
 */
function pickAdminGridPrintedTotalRow(itemPaidRows) {
  const rows = Array.isArray(itemPaidRows) ? itemPaidRows : [];
  if (!rows.length) return null;

  for (let i = rows.length - 1; i >= 0; i--) {
    const item = String(rows[i]?.[0] ?? "").trim();
    const paid = String(rows[i]?.[1] ?? "").trim();
    if (!adminGridPaidCellHasContent(paid)) continue;
    if (isAdminGridTotalLikeItemLabel(item)) return { item, paid };
  }
  for (let i = rows.length - 1; i >= 0; i--) {
    const item = String(rows[i]?.[0] ?? "").trim();
    const paid = String(rows[i]?.[1] ?? "").trim();
    if (!adminGridPaidCellHasContent(paid)) continue;
    if (isAdminBundleExpensesLabel(item)) return { item, paid };
  }
  return null;
}

/**
 * Trustees sometimes print the voucher **gross** total as a **lone amount line** after the pipe
 * table in markdown (LLM omitted a **Total** row). Scan subsection body after the first `|…|` table.
 * @param {string} sectionBody
 * @returns {string | null} matched amount string (trimmed) or null
 */
function extractAdminExpenseVoucherFooterTotalAfterPipeTable(sectionBody) {
  const lines = String(sectionBody || "").split(/\r?\n/);
  let seenPipe = false;
  let inTable = false;
  const lone = /^(?:€|\$|£)?\s*\d{1,3}(?:,\d{3})*\.\d{2}\s*$/;
  const candidates = [];
  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].trim();
    if (!seenPipe && t.startsWith("|")) {
      seenPipe = true;
      inTable = true;
      continue;
    }
    if (inTable) {
      if (t.startsWith("|")) continue;
      inTable = false;
    }
    if (!seenPipe) continue;
    if (!t) continue;
    if (/^#{2,3}\s/.test(t)) break;
    if (lone.test(t)) candidates.push(t);
  }
  return candidates.length ? candidates[candidates.length - 1] : null;
}

/**
 * @param {string[]} headers
 * @param {...string} needles
 */
function findColumnIndexFlexible(headers, ...needles) {
  const lowered = headers.map((x) => String(x || "").trim().toLowerCase());
  for (const needle of needles) {
    const n = String(needle).toLowerCase();
    for (let i = 0; i < lowered.length; i++) {
      if (lowered[i] === n) return i;
    }
  }
  for (const needle of needles) {
    const n = String(needle).toLowerCase();
    for (let i = 0; i < lowered.length; i++) {
      if (lowered[i].includes(n)) return i;
    }
  }
  return -1;
}

/** Prefer exact «Class» header so we do not match «Classification». */
function findClassColumnIndex(headers) {
  const lowered = headers.map((x) => String(x || "").trim().toLowerCase());
  for (let i = 0; i < lowered.length; i++) {
    if (lowered[i] === "class") return i;
  }
  return -1;
}

/**
 * @param {string} md
 * @returns {{ headers: string[]; rows: string[][] } | null}
 */
function fallbackFindClassBalanceTable(md) {
  const lines = String(md || "").split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const ln = lines[i].trim();
    if (!ln.startsWith("### ")) continue;
    const low = ln.toLowerCase();
    if (low.includes("tranche by listing")) continue;
    if (low.includes("distribution grid")) continue;
    if (low.includes("cross-checks")) continue;
    const sectionLines = [];
    for (let j = i + 1; j < lines.length; j++) {
      if (/^#{2,3}\s/.test(lines[j])) break;
      sectionLines.push(lines[j]);
    }
    const parsed = parseFirstPipeTableInSection(sectionLines.join("\n"));
    if (!parsed || !isClassBalanceLikeTable(parsed.headers)) continue;
    const hb = parsed.headers.join(" | ").toLowerCase();
    if (hb.includes("cusip line id")) continue;
    if (hb.includes("prior principal") && !hb.includes("beginning balance")) continue;
    return parsed;
  }
  return null;
}

/**
 * @param {string} md
 * @returns {{ error: string; headers: string[] | null; rows: string[][] | null }}
 */
function extractPrimaryClassTableFrom02(md) {
  const text = String(md || "");
  const idx = text.indexOf(WRAPUP_CLASS_PRIMARY_HEADING);
  let parsed = null;
  if (idx !== -1 && (idx === 0 || text[idx - 1] === "\n" || text[idx - 1] === "\r")) {
    const lineEnd = text.indexOf("\n", idx);
    const afterHeading = lineEnd === -1 ? "" : text.slice(lineEnd + 1);
    const next = afterHeading.search(/^#{2,3}\s/m);
    const section = next === -1 ? afterHeading : afterHeading.slice(0, next);
    parsed = parseFirstPipeTableInSection(section);
    if (parsed && !isClassBalanceLikeTable(parsed.headers)) parsed = null;
  }
  if (!parsed) parsed = fallbackFindClassBalanceTable(text);
  if (!parsed) {
    return {
      error:
        "No primary class balance table in 02 — expected «### Class balance table (primary)» or a table with Class + Beginning balance.",
      headers: null,
      rows: null,
    };
  }
  return { error: "", headers: parsed.headers, rows: parsed.rows };
}

/** Display columns for the Tranche & fees panel (subset of 02 primary table). */
const WRAPUP_TRANCHE_GRID_SCHEMA = [
  { label: "Class name", sources: ["class"], numeric: false },
  { label: "Beginning balance", sources: ["beginning balance"], numeric: true },
  { label: "Interest rate", sources: ["interest rate"], numeric: true },
  { label: "Interest payment", sources: ["interest payment"], numeric: true },
  { label: "Deferred interest", sources: ["deferred interest"], numeric: true },
  { label: "Principal payment", sources: ["principal payment"], numeric: true },
  { label: "Ending balance", sources: ["ending balance"], numeric: true },
];

/**
 * @param {string[]} headers
 * @param {string[][]} rows
 * @returns {{ error: string; displayHeaders: string[] | null; data: string[][] | null }}
 */
function projectTrancheGridForWrapup(headers, rows) {
  const idxClass = findClassColumnIndex(headers);
  if (idxClass === -1) {
    return { error: "Primary table has no Class column.", displayHeaders: null, data: null };
  }
  const colIdx = WRAPUP_TRANCHE_GRID_SCHEMA.map((spec) =>
    findColumnIndexFlexible(headers, ...spec.sources)
  );
  const displayHeaders = WRAPUP_TRANCHE_GRID_SCHEMA.map((s) => s.label);
  const data = [];
  for (const raw of rows) {
    const row = [...raw];
    while (row.length < headers.length) row.push("");
    const className = String(row[idxClass] ?? "").trim();
    if (!className) continue;
    if (isTotalLikeClassLabel(className)) continue;
    const out = [];
    for (let c = 0; c < colIdx.length; c++) {
      const ii = colIdx[c];
      out.push(ii >= 0 && ii < row.length ? String(row[ii] ?? "").trim() : "");
    }
    data.push(out);
  }
  if (!data.length) {
    return {
      error: "No class rows to show (after skipping totals / blank Class).",
      displayHeaders,
      data: [],
    };
  }
  return { error: "", displayHeaders, data };
}

/** Wrap-up panel: valuation fee table — Main category, Sub category, Amount paid only. */
const WRAPUP_FEES_DISPLAY_HEADERS = ["Main category", "Sub category", "Amount paid"];

/**
 * @param {string[]} headers
 * @param {string[][]} rows
 * @returns {{ error: string; displayHeaders: string[]; data: string[][] }}
 */
function projectValuationFeesForWrapup(headers, rows) {
  const iMain = findColumnIndexFlexible(headers, "main category");
  const iLeaf = findColumnIndexFlexible(headers, "sub category", "fee_type", "standard fee type");
  const iPaid = findColumnIndexFlexible(headers, "amount paid");
  if (iMain < 0 || iLeaf < 0 || iPaid < 0) {
    return {
      error:
        "Fee table missing expected columns (need Main category, Sub category or fee_type, Amount paid).",
      displayHeaders: [...WRAPUP_FEES_DISPLAY_HEADERS],
      data: [],
    };
  }
  const data = [];
  for (const raw of rows) {
    const row = [...raw];
    while (row.length < headers.length) row.push("");
    const main = String(row[iMain] ?? "").trim();
    const leaf = String(row[iLeaf] ?? "").trim();
    const paid = String(row[iPaid] ?? "").trim();
    if (!main && !leaf && !paid) continue;
    if (isParsableZeroPaidCellForWrapupUi(paid)) continue;
    data.push([main, leaf, paid]);
  }
  return { error: "", displayHeaders: [...WRAPUP_FEES_DISPLAY_HEADERS], data };
}

/**
 * @param {string} md
 * @returns {{ error: string; headers: string[] | null; rows: string[][] | null }}
 */
/**
 * @param {string} md
 * @param {string} [sourceLabel]
 */
function extractValuationFeesSection(md, sourceLabel = "05") {
  const text = String(md || "");
  const idx = text.indexOf(WRAPUP_VALUATION_FEES_HEADING);
  if (idx === -1) {
    return {
      error:
        sourceLabel === "05"
          ? "No «### Valuation-relevant fees» in 05 — click Map valuation fees or open the file on disk."
          : "No «### Valuation-relevant fees» in 03 (legacy) — run Map valuation fees for 05.",
      headers: null,
      rows: null,
    };
  }
  if (idx > 0 && text[idx - 1] !== "\n" && text[idx - 1] !== "\r") {
    return {
      error: "Could not locate valuation fees section (heading not at line start).",
      headers: null,
      rows: null,
    };
  }
  const lineEnd = text.indexOf("\n", idx);
  const afterHeading = lineEnd === -1 ? "" : text.slice(lineEnd + 1);
  const next = afterHeading.search(/^#{2,3}\s/m);
  const section = next === -1 ? afterHeading : afterHeading.slice(0, next);
  const parsed = parseFirstPipeTableInSection(section);
  if (!parsed) {
    return {
      error: "No valid markdown table found under «Valuation-relevant fees».",
      headers: null,
      rows: null,
    };
  }
  const headBlob = parsed.headers.join(" | ").toLowerCase();
  if (!headBlob.includes("main category")) {
    return {
      error:
        "First table under this section is not the fee summary (missing «Main category» — expected Main category | Sub category | Amount paid per extraction-templates.md).",
      headers: null,
      rows: null,
    };
  }
  if (
    !headBlob.includes("sub category") &&
    !headBlob.includes("fee_type") &&
    !headBlob.includes("standard fee type")
  ) {
    return {
      error:
        "First table under this section is not the fee summary (missing «Sub category» or «fee_type» column — use allowed literals per extraction-templates.md).",
      headers: null,
      rows: null,
    };
  }
  return { error: "", headers: parsed.headers, rows: parsed.rows };
}

/** @param {string} md */
function extractValuationFeesFrom03(md) {
  return extractValuationFeesSection(md, "03");
}

/**
 * Fallback: `administrator_expenses` row in «### Valuation-relevant fees» (prefer 05).
 * @param {string} md
 * @returns {{ paid: string | null; error: string }}
 */
function extractAdministratorExpensesPaidFromValuation03(md) {
  const ext = extractValuationFeesSection(md, "05");
  if (ext.error || !ext.headers || !ext.rows) {
    return { paid: null, error: ext.error || "no valuation fees table" };
  }
  const h = ext.headers;
  const iLeaf = findColumnIndexFlexible(h, "sub category", "fee_type", "standard fee type");
  const iPaid = findColumnIndexFlexible(h, "amount paid");
  if (iLeaf < 0 || iPaid < 0) {
    return { paid: null, error: "valuation fees: missing Sub category/fee_type or Amount paid" };
  }
  /** @type {string | null} */
  let last = null;
  for (const raw of ext.rows) {
    const row = [...raw];
    while (row.length < h.length) row.push("");
    const leaf = String(row[iLeaf] ?? "").trim().toLowerCase();
    const paid = String(row[iPaid] ?? "").trim();
    if (leaf !== "administrator_expenses") continue;
    if (paid) last = paid;
  }
  return { paid: last, error: "" };
}

/**
 * @param {string[]} headers
 * @param {string[][]} rows
 */
function pipeTableToMarkdown(headers, rows) {
  const esc = (c) => String(c ?? "").replace(/\|/g, "\\|");
  const line = (cells) => `| ${cells.map(esc).join(" | ")} |`;
  const sep = `| ${headers.map(() => "---").join(" | ")} |`;
  const body = rows.map((r) => {
    const padded = [...r];
    while (padded.length < headers.length) padded.push("");
    return line(padded.slice(0, headers.length));
  });
  return [line(headers), sep, ...body].join("\n");
}

/**
 * @param {HTMLElement | null} panelEl
 * @param {{ ok: boolean; error: string | null; exists: boolean; content: string; truncated: boolean }} fe03
 * @param {{ ok: boolean; error: string | null; exists: boolean; content: string; truncated: boolean }} fe05
 */
function renderWrapupFeesPanel(panelEl, fe03, fe05) {
  lastWrapupFeesMarkdownExport = "";
  if (!panelEl) return;
  panelEl.innerHTML = "";

  const hint = (msg, cls = "") => {
    const p = document.createElement("p");
    p.className = `wrapup-fees-hint${cls ? ` ${cls}` : ""}`;
    p.textContent = msg;
    panelEl.appendChild(p);
  };

  if (!fe03.ok) {
    hint(`(03: could not load — ${fe03.error || "error"})`, "warn");
    return;
  }
  if (!fe03.exists) {
    hint("(03 not in this folder yet.)");
    return;
  }
  if (!String(fe03.content || "").trim()) {
    hint("(03 file is empty.)");
    return;
  }

  const md = fe03.content;
  const exportParts = [];

  const wfSec = extractSubsectionBodyAfterHeading(md, WRAPUP_WATERFALL_HEADING);
  if (wfSec.error) {
    hint(wfSec.error, "warn");
  } else {
    const wfTables = parseAllPipeTablesInSection(wfSec.content.trim());
    if (!wfTables.length) {
      hint("«### Waterfall table» has no pipe table yet (logical-only 03, or section not filled).", "warn");
    } else {
      const hWf = document.createElement("h4");
      hWf.className = "wrapup-subsection-title";
      hWf.textContent =
        "### Waterfall table (`03` — all rows, incl. 0.00 paid)";
      panelEl.appendChild(hWf);
      /** @type {string[]} */
      let dispH = [];
      /** @type {string[][]} */
      const allRows = [];
      for (const tbl of wfTables) {
        const wfProj = projectWaterfallPriorityItemPaid(tbl.headers, tbl.rows);
        if (wfProj.error) {
          hint(wfProj.error, "warn");
          continue;
        }
        if (!dispH.length && wfProj.displayHeaders.length) {
          dispH = wfProj.displayHeaders;
        }
        allRows.push(...wfProj.data);
      }
      if (!allRows.length) {
        hint("Waterfall table has no data rows.", "");
      } else {
        const numCols = new Set([2, dispH.length - 1]);
        appendDataTable(panelEl, dispH, allRows, "wrapup-waterfall-table", [...numCols]);
        exportParts.push(`## ${hWf.textContent}\n\n${pipeTableToMarkdown(dispH, allRows)}`);
      }
    }
  }

  const hVf = document.createElement("h4");
  hVf.className = "wrapup-subsection-title";
  hVf.textContent = "### Valuation-relevant fees (roll-up)";
  panelEl.appendChild(hVf);

  let parsedV = { error: "", headers: null, rows: null };
  if (fe05?.ok && fe05.exists && String(fe05.content || "").trim()) {
    parsedV = extractValuationFeesSection(fe05.content, "05");
  } else {
    parsedV = extractValuationFeesFrom03(md);
  }
  if (parsedV.error) {
    hint(parsedV.error, "warn");
  } else if (!parsedV.headers || !parsedV.rows) {
    hint("Could not parse valuation fees table.", "warn");
  } else {
    const proj = projectValuationFeesForWrapup(parsedV.headers, parsedV.rows);
    if (proj.error) {
      hint(proj.error, "warn");
    } else if (!proj.data.length) {
      hint("No valuation fee roll-up rows to display.", "");
    } else {
      appendDataTable(panelEl, proj.displayHeaders, proj.data, "wrapup-fees-table", [2]);
      exportParts.push(`## ${hVf.textContent}\n\n${pipeTableToMarkdown(proj.displayHeaders, proj.data)}`);
    }
  }

  lastWrapupFeesMarkdownExport = exportParts.filter(Boolean).join("\n\n");

  if (fe03.truncated) {
    const p = document.createElement("p");
    p.className = "wrapup-fees-trunc";
    p.textContent =
      "03 response was truncated by the server — if tables look incomplete, raise max_bytes or open the file on disk.";
    panelEl.appendChild(p);
  }
}

/**
 * @param {HTMLElement | null} panelEl
 * @param {{ ok: boolean; error: string | null; exists: boolean; content: string; truncated: boolean }} fe03
 * @param {{ ok: boolean; error: string | null; exists: boolean; content: string; truncated: boolean }} [fe05]
 */
function renderWrapupAdminPanel(panelEl, fe03, fe05) {
  lastWrapupAdminMarkdownExport = "";
  if (!panelEl) return;
  panelEl.innerHTML = "";

  const hint = (msg, cls = "") => {
    const p = document.createElement("p");
    p.className = `wrapup-fees-hint${cls ? ` ${cls}` : ""}`;
    p.textContent = msg;
    panelEl.appendChild(p);
  };

  if (!fe03.ok) {
    hint(`(03: could not load — ${fe03.error || "error"})`, "warn");
    return;
  }
  if (!fe03.exists) {
    hint("(03 not in this folder yet.)");
    return;
  }
  if (!String(fe03.content || "").trim()) {
    hint("(03 file is empty.)");
    return;
  }

  const sec = extractSubsectionBodyAfterHeading(fe03.content, WRAPUP_ADMIN_GRID_HEADING);
  if (sec.error) {
    return;
  }
  const parsed = parseFirstPipeTableInSection(sec.content.trim());
  if (!parsed) {
    hint("No pipe table under «### Administrative Expenses grid».", "warn");
    return;
  }
  const h0 = String(parsed.headers[0] || "").trim().toLowerCase();
  const h1 = String(parsed.headers[1] || "").trim().toLowerCase();
  if (h0 === "field" && h1 === "value") {
    hint("First table under admin section is not the expense grid (Field | Value table).", "warn");
    return;
  }

  const adm = projectAdminGridItemAndPaid(parsed.headers, parsed.rows);
  /** @type {string[]} */
  const exportMdParts = [];

  if (adm.error) {
    hint(adm.error, "warn");
    appendDataTable(panelEl, parsed.headers, parsed.rows, "wrapup-admin-table", []);
    exportMdParts.push(pipeTableToMarkdown(parsed.headers, parsed.rows));
  } else {
    appendDataTable(panelEl, adm.displayHeaders, adm.data, "wrapup-admin-table", [1]);
    exportMdParts.push(pipeTableToMarkdown(adm.displayHeaders, adm.data));

    const footerTotRaw = extractAdminExpenseVoucherFooterTotalAfterPipeTable(sec.content.trim());
    const totalRow = pickAdminGridPrintedTotalRow(adm.data);
    const normMoney = (s) => String(s || "").replace(/[\s€$£,]/g, "");

    if (totalRow) {
      const pTot = document.createElement("p");
      pTot.className = "wrapup-admin-total-line";
      pTot.textContent = `Total (from grid): ${totalRow.paid} (${totalRow.item})`;
      panelEl.appendChild(pTot);
      exportMdParts.push(`**Total (from grid):** ${totalRow.paid} (${totalRow.item})`);
    } else if (footerTotRaw) {
      const pFb0 = document.createElement("p");
      pFb0.className = "wrapup-admin-total-line";
      pFb0.textContent = `Total (voucher footer, as printed): ${footerTotRaw}`;
      panelEl.appendChild(pFb0);
      exportMdParts.push(`**Total (voucher footer, as printed):** ${footerTotRaw}`);
    } else {
      const vfMd =
        fe05?.ok && fe05.exists && String(fe05.content || "").trim()
          ? fe05.content
          : fe03.content;
      const vf = extractAdministratorExpensesPaidFromValuation03(vfMd);
      if (vf.paid) {
        const pFb = document.createElement("p");
        pFb.className = "wrapup-admin-total-line wrapup-admin-total-line--fallback";
        pFb.textContent = `Roll-up (valuation fees, administrator_expenses): ${vf.paid}`;
        panelEl.appendChild(pFb);
        exportMdParts.push(`**Roll-up (valuation fees, administrator_expenses):** ${vf.paid}`);
      }
    }

    if (totalRow && footerTotRaw && normMoney(totalRow.paid) && normMoney(footerTotRaw) !== normMoney(totalRow.paid)) {
      const p2 = document.createElement("p");
      p2.className = "wrapup-admin-total-line wrapup-admin-total-line--fallback";
      p2.textContent = `Voucher footer (prose after table): ${footerTotRaw}`;
      panelEl.appendChild(p2);
      exportMdParts.push(`**Voucher footer (prose after table):** ${footerTotRaw}`);
    }
  }

  lastWrapupAdminMarkdownExport = exportMdParts.filter(Boolean).join("\n\n");

  if (fe03.truncated) {
    const p = document.createElement("p");
    p.className = "wrapup-fees-trunc";
    p.textContent =
      "03 response was truncated — if the admin grid looks incomplete, open the markdown file on disk.";
    panelEl.appendChild(p);
  }
}

/**
 * @param {HTMLElement | null} panelEl
 * @param {{ ok: boolean; error: string | null; exists: boolean; content: string; truncated: boolean }} tr
 */
function renderWrapupTranchePanel(panelEl, tr) {
  lastWrapupTrancheMarkdownExport = "";
  if (!panelEl) return;
  panelEl.innerHTML = "";

  const hint = (msg, cls = "") => {
    const p = document.createElement("p");
    p.className = `wrapup-fees-hint${cls ? ` ${cls}` : ""}`;
    p.textContent = msg;
    panelEl.appendChild(p);
  };

  if (!tr.ok) {
    hint(`(02: could not load — ${tr.error || "error"})`, "warn");
    return;
  }
  if (!tr.exists) {
    hint("(02 not in this folder yet.)");
    return;
  }
  if (!String(tr.content || "").trim()) {
    hint("(02 file is empty.)");
    return;
  }

  const ext = extractPrimaryClassTableFrom02(tr.content);
  if (ext.error) {
    hint(ext.error, "warn");
    return;
  }
  if (!ext.headers || !ext.rows) {
    hint("Could not parse primary class table.", "warn");
    return;
  }

  const proj = projectTrancheGridForWrapup(ext.headers, ext.rows);
  if (proj.error) {
    hint(proj.error, "warn");
    return;
  }
  if (!proj.displayHeaders || !proj.data || proj.data.length === 0) {
    hint("No rows to display in tranche grid.", "warn");
    return;
  }

  lastWrapupTrancheMarkdownExport = pipeTableToMarkdown(proj.displayHeaders, proj.data);

  const tbl = document.createElement("table");
  tbl.className = "wrapup-tranche-table";
  const thead = document.createElement("thead");
  const hr = document.createElement("tr");
  proj.displayHeaders.forEach((h, i) => {
    const th = document.createElement("th");
    th.textContent = h;
    if (WRAPUP_TRANCHE_GRID_SCHEMA[i]?.numeric) th.classList.add("num");
    else th.classList.add("class-col");
    hr.appendChild(th);
  });
  thead.appendChild(hr);
  tbl.appendChild(thead);
  const tbody = document.createElement("tbody");
  for (const row of proj.data) {
    const trEl = document.createElement("tr");
    row.forEach((cell, i) => {
      const td = document.createElement("td");
      td.textContent = cell;
      if (WRAPUP_TRANCHE_GRID_SCHEMA[i]?.numeric) td.classList.add("num");
      else td.classList.add("class-col");
      trEl.appendChild(td);
    });
    tbody.appendChild(trEl);
  }
  tbl.appendChild(tbody);
  panelEl.appendChild(tbl);

  if (tr.truncated) {
    const p = document.createElement("p");
    p.className = "wrapup-fees-trunc";
    p.textContent =
      "02 response was truncated by the server — open the file on disk if the grid looks incomplete.";
    panelEl.appendChild(p);
  }
}

async function fetchWrapupDeliverable(outputDir, relativePath) {
  const { res, data } = await apiPostJson("/api/extraction/file", {
    output_dir: outputDir,
    relative_path: relativePath,
    allow_missing: true,
  });
  if (!res.ok) {
    return {
      ok: false,
      error: formatDetail(data.detail) || res.statusText,
      exists: false,
      content: "",
      truncated: false,
    };
  }
  return {
    ok: true,
    error: null,
    exists: data.exists !== false,
    content: typeof data.content === "string" ? data.content : "",
    truncated: !!data.truncated,
  };
}

/**
 * @param {string} v
 */
function isWrapupMetaEmptyValue(v) {
  const t = String(v || "").trim();
  if (!t) return true;
  return /^n\/?a$/i.test(t) || t === "—" || t === "-";
}

/**
 * @param {string} v
 */
function formatWrapupMetaDisplayValue(v) {
  if (isWrapupMetaEmptyValue(v)) return "—";
  return String(v).trim();
}

/**
 * @param {string} md
 * @param {string} headingStartsWith
 * @returns {Record<string, string>}
 */
function parseMarkdownKvTableFromSection(md, headingStartsWith) {
  const sec = extractSubsectionBodyAfterHeading(md, headingStartsWith);
  if (sec.error) return {};
  const tbl = parseFirstPipeTableInSection(sec.content.trim());
  if (!tbl) return {};
  /** @type {Record<string, string>} */
  const out = {};
  for (const row of tbl.rows) {
    const key = String(row[0] || "").trim();
    if (!key || key.toLowerCase() === "field") continue;
    out[key.toLowerCase()] = String(row[1] || "").trim();
  }
  return out;
}

/**
 * @param {Record<string, string>} routing
 */
function dealIdFrom01RoutingTable(routing) {
  for (const [k, v] of Object.entries(routing || {})) {
    if (k.includes("other deal id") && !isWrapupMetaEmptyValue(v)) return v;
  }
  return "";
}

/**
 * @param {string} outputDir
 */
function resolveWrapupDealLineForOutputDir(outputDir) {
  const n = normalizeOutputPath(outputDir);
  if (!batchRunning) syncBatchRowsFromDom();
  for (const row of batchQueueRows) {
    const rowDir = normalizeOutputPath(String(row.output_dir || ""));
    if (rowDir === n && row.line.trim()) {
      return parseDealPaymentLine(row.line);
    }
  }
  const inferred = inferDealLineFromFolderBasename(
    outputPathBasename(outputDir).replace(/_sdk$/i, "").replace(/_llm$/i, ""),
  );
  return parseDealPaymentLine(inferred);
}

/**
 * @param {string} outputDir
 * @param {string} md01
 */
function buildWrapupDealMeta(outputDir, md01) {
  const queued = resolveWrapupDealLineForOutputDir(outputDir);
  let dealId = queued.deal_id || "";
  let paymentDate = "";
  let determinationDate = "";

  if (isWrapupMetaEmptyValue(dealId)) {
    const base = outputPathBasename(outputDir).replace(/_sdk$/i, "").replace(/_llm$/i, "");
    const m = /^(\d+)_/.exec(base);
    if (m) dealId = m[1];
  }

  if (String(md01 || "").trim()) {
    const dates = parseMarkdownKvTableFromSection(md01, "### Key dates");
    const routing = parseMarkdownKvTableFromSection(md01, "### Document routing (if stated)");
    if (!Object.keys(routing).length) {
      Object.assign(routing, parseMarkdownKvTableFromSection(md01, "### Document routing"));
    }
    paymentDate = dates["payment date"] || "";
    determinationDate = dates["determination date"] || "";
    if (isWrapupMetaEmptyValue(dealId)) {
      dealId = dealIdFrom01RoutingTable(routing);
    }
  }

  if (isWrapupMetaEmptyValue(paymentDate)) {
    paymentDate = queued.payment_date || "";
  }

  return {
    deal_id: formatWrapupMetaDisplayValue(dealId),
    payment_date: formatWrapupMetaDisplayValue(paymentDate),
    determination_date: formatWrapupMetaDisplayValue(determinationDate),
  };
}

/**
 * @param {{ deal_id?: string; payment_date?: string; determination_date?: string }} meta
 */
function renderWrapupDealMetaBox(meta) {
  if (!wrapupDealMeta) return;
  const set = (field, val) => {
    const el = wrapupDealMeta.querySelector(`[data-field="${field}"]`);
    if (el) el.textContent = val || "—";
  };
  set("deal_id", meta.deal_id || "—");
  set("payment_date", meta.payment_date || "—");
  set("determination_date", meta.determination_date || "—");
  wrapupDealMeta.hidden = false;
}

function clearWrapupDealMetaBox() {
  if (!wrapupDealMeta) return;
  renderWrapupDealMetaBox({
    deal_id: "—",
    payment_date: "—",
    determination_date: "—",
  });
  wrapupDealMeta.hidden = true;
}

/**
 * Load 02 (tranche grid) and 03 (fees table) for the active output directory.
 * @param {{ quiet?: boolean }} [options]
 */
async function refreshWrapUpPanel(options = {}) {
  const quiet = !!options.quiet;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!wrapupTranchePanel || !wrapupFeesPanel) return;

  if (!out) {
    if (wrapupStatus) {
      wrapupStatus.textContent = "Set active output directory above to load 02 and 03.";
    }
    lastWrapupTrancheMarkdownExport = "";
    lastWrapupFeesMarkdownExport = "";
    lastWrapupAdminMarkdownExport = "";
    wrapupTranchePanel.innerHTML = "";
    wrapupFeesPanel.innerHTML = "";
    if (wrapupAdminPanel) wrapupAdminPanel.innerHTML = "";
    clearWrapupDealMetaBox();
    return;
  }

  if (wrapupStatus && !quiet) {
    wrapupStatus.textContent = "Loading 01, 02 and 03…";
  }

  const [meta01, tr, fe03, fe05] = await Promise.all([
    fetchWrapupDeliverable(out, WRAPUP_METADATA_FILE),
    fetchWrapupDeliverable(out, WRAPUP_TRANCHE_FILE),
    fetchWrapupDeliverable(out, WRAPUP_FEES_FILE),
    fetchWrapupDeliverable(out, WRAPUP_VALUATION_FEES_FILE),
  ]);

  renderWrapupDealMetaBox(
    buildWrapupDealMeta(
      out,
      meta01.ok && meta01.exists ? meta01.content : "",
    ),
  );

  renderWrapupTranchePanel(wrapupTranchePanel, tr);
  renderWrapupFeesPanel(wrapupFeesPanel, fe03, fe05);
  renderWrapupAdminPanel(wrapupAdminPanel, fe03, fe05);

  if (!wrapupStatus) return;

  const msgs = [];
  if (!tr.ok && tr.error) msgs.push(`02: ${tr.error}`);
  if (!fe03.ok && fe03.error) msgs.push(`03: ${fe03.error}`);
  if (!fe05.ok && fe05.error) msgs.push(`05: ${fe05.error}`);
  if (tr.ok && !tr.exists) msgs.push("02 missing");
  if (fe03.ok && !fe03.exists) msgs.push("03 missing");
  if (fe05.ok && !fe05.exists) msgs.push("05 missing (run Map valuation fees)");
  if (msgs.length) {
    wrapupStatus.textContent = msgs.join(" · ");
  } else {
    wrapupStatus.textContent = quiet
      ? "Tranche, waterfall & admin panels updated."
      : "Loaded tranche grid, waterfall / fees, and admin expenses grid.";
  }
}

/** Preview existing segmented folder when deal line is complete (single-deal form). */
async function probeSingleDealSegmentedFolder() {
  if (batchRunning || !segmentStatusLine) return;
  const { deal_id, payment_date } = parseDealPaymentLine(locateLineInput?.value || "");
  if (!deal_id || !payment_date) return;
  const lookup = await lookupSegmentedFolderForDeal(deal_id, payment_date);
  if ("error" in lookup || !lookup.segmented) return;
  setSegmentStatus(`Already segmented. Output: ${lookup.output_dir}`, "ok");
  setActiveOutputDirectory(lookup.output_dir, { refreshWrapup: true });
}

if (locateLineInput) {
  locateLineInput.addEventListener("blur", () => {
    void probeSingleDealSegmentedFolder();
  });
}

if (form) {
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    void locateAndSegmentPdf();
  });
}

if (checkEligibilityBtn) {
  checkEligibilityBtn.addEventListener("click", async () => {
    if (!segmentStatusLine) return;
    const { deal_id, payment_date } = parseDealPaymentLine(locateLineInput?.value || "");
    if (!deal_id || !payment_date) {
      setSegmentStatus(
        "Enter deal ID, a space, then payment date on one line (example: 825275100 3/16/2026).",
        "bad",
      );
      return;
    }

    checkEligibilityBtn.disabled = true;
    if (locateSegmentBtn) locateSegmentBtn.disabled = true;
    setSegmentStatus("Resolving path for eligibility check…", "muted");

    try {
      if (
        !lastResolved ||
        String(lastResolved.deal_id) !== deal_id ||
        String(lastResolved.payment_date) !== payment_date
      ) {
        const res = await fetch("/api/resolve-path", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ deal_id, payment_date }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setSegmentStatus(formatDetail(data.detail) || res.statusText, "bad");
          return;
        }
        lastResolved = data;
      }

      const p = String(lastResolved?.pdf_path || "").trim();
      if (!p) {
        setSegmentStatus("No PDF path — cannot check eligibility.", "bad");
        return;
      }

      setSegmentStatus("Checking primary PDF for noteval content…", "muted");
      const gateResult = await evaluateReportPathsAndNotevalGate(lastResolved);
      setSegmentStatus(gateResult.userMessage, gateResult.pass ? "ok" : "bad");
    } catch (err) {
      setSegmentStatus(err instanceof Error ? err.message : String(err), "bad");
    } finally {
      checkEligibilityBtn.disabled = false;
      if (locateSegmentBtn) locateSegmentBtn.disabled = false;
    }
  });
}

if (segmentLogToggleBtn && segmentLogBox) {
  segmentLogToggleBtn.addEventListener("click", () => {
    const show = segmentLogBox.hidden;
    segmentLogBox.hidden = !show;
    segmentLogToggleBtn.textContent = show ? "Hide segment log" : "Show segment log";
    segmentLogToggleBtn.setAttribute("aria-expanded", show ? "true" : "false");
  });
}

if (cockpitCopyPathBtn && cockpitOutputDir) {
  cockpitCopyPathBtn.addEventListener("click", () => {
    const p = cockpitOutputDir.value.trim();
    if (!p) {
      window.alert("Active output directory is empty.");
      return;
    }
    void copyText(p);
  });
}

if (cockpitCopyAllPathsBtn) {
  cockpitCopyAllPathsBtn.addEventListener("click", () => {
    const lines =
      outputPathHistory.length > 0
        ? outputPathHistory.map((x) => String(x).trim()).filter(Boolean)
        : cockpitOutputDir
          ? [cockpitOutputDir.value.trim()].filter(Boolean)
          : [];
    if (lines.length === 0) {
      window.alert("No paths to copy — segment deals, Remember path, or paste a path first.");
      return;
    }
    void copyText(lines.join("\n"));
  });
}

if (cockpitRememberPathBtn && cockpitOutputDir) {
  cockpitRememberPathBtn.addEventListener("click", () => {
    const p = cockpitOutputDir.value.trim();
    if (!p) {
      window.alert("Paste or select an output path first.");
      return;
    }
    addOutputPathToHistory(p);
  });
}

if (cockpitClearPathsBtn) {
  cockpitClearPathsBtn.addEventListener("click", () => {
    outputPathHistory.length = 0;
    renderOutputPathHistory();
  });
}

if (cockpitOutputDir) {
  cockpitOutputDir.addEventListener("blur", () => {
    renderOutputPathHistory();
  });
}

if (pipelineSdkBtn) {
  pipelineSdkBtn.addEventListener("click", () => void startSdkExtraction());
}
if (batchAddRowBtn) {
  batchAddRowBtn.addEventListener("click", () => {
    syncBatchRowsFromDom();
    if (batchQueueRows.length >= BATCH_QUEUE_MAX_ROWS) {
      window.alert(`At most ${BATCH_QUEUE_MAX_ROWS} rows.`);
      return;
    }
    batchQueueRows.push(makeEmptyBatchRow());
    renderBatchTable();
  });
}

if (batchPasteOpenBtn && batchPasteDialog) {
  batchPasteOpenBtn.addEventListener("click", () => {
    if (batchRunning) return;
    if (typeof batchPasteDialog.showModal !== "function") {
      window.alert("Your browser does not support modal dialogs; use one row at a time in the table.");
      return;
    }
    batchPasteDialog.showModal();
    if (batchPasteTextarea) {
      batchPasteTextarea.focus();
      batchPasteTextarea.select();
    }
  });
}

if (batchPasteCancelBtn && batchPasteDialog) {
  batchPasteCancelBtn.addEventListener("click", () => {
    if (batchPasteTextarea) batchPasteTextarea.value = "";
    batchPasteDialog.close();
  });
}

if (batchPasteApplyBtn && batchPasteDialog && batchPasteTextarea) {
  batchPasteApplyBtn.addEventListener("click", () => {
    applyPastedDealsMultiline(batchPasteTextarea.value);
    batchPasteTextarea.value = "";
    batchPasteDialog.close();
  });
}

if (batchPasteFoldersOpenBtn && batchPasteFoldersDialog) {
  batchPasteFoldersOpenBtn.addEventListener("click", () => {
    if (batchRunning) return;
    if (typeof batchPasteFoldersDialog.showModal !== "function") {
      window.alert("Your browser does not support modal dialogs.");
      return;
    }
    batchPasteFoldersDialog.showModal();
    if (batchPasteFoldersTextarea) {
      batchPasteFoldersTextarea.focus();
      batchPasteFoldersTextarea.select();
    }
  });
}

if (batchPasteFoldersCancelBtn && batchPasteFoldersDialog) {
  batchPasteFoldersCancelBtn.addEventListener("click", () => {
    if (batchPasteFoldersTextarea) batchPasteFoldersTextarea.value = "";
    batchPasteFoldersDialog.close();
  });
}

if (batchPasteFoldersApplyBtn && batchPasteFoldersDialog && batchPasteFoldersTextarea) {
  batchPasteFoldersApplyBtn.addEventListener("click", () => {
    void applyPastedOutputFoldersMultiline(batchPasteFoldersTextarea.value).then(() => {
      batchPasteFoldersTextarea.value = "";
      batchPasteFoldersDialog.close();
    });
  });
}

if (batchRunBtn) {
  batchRunBtn.addEventListener("click", () => void runBatchQueue());
}

if (batchSdkRunBtn) {
  batchSdkRunBtn.addEventListener("click", () => void runBatchSdkQueue());
}

for (const btn of batchStopBtns) {
  btn.addEventListener("click", () => {
    batchRunAbort = true;
  });
}

/**
 * @param {string} report
 * @param {number | null} returncode
 * @returns {{ headline: string; tone: "ok" | "warn" | "fail" | "muted" }}
 */
function validationSummaryFromReport(report, returncode) {
  const t = String(report || "");
  if (/\*\*STATUS:\s*FAIL\*\*/i.test(t)) {
    return { headline: "Validation failed.", tone: "fail" };
  }
  if (/\*\*STATUS:\s*PASS WITH WARNINGS\*\*/i.test(t)) {
    return { headline: "Validation passed with warnings.", tone: "warn" };
  }
  if (/\*\*STATUS:\s*PASS\*\*/i.test(t)) {
    return { headline: "Validation passed.", tone: "ok" };
  }
  if (returncode === 0) {
    return { headline: "Validation passed.", tone: "ok" };
  }
  if (typeof returncode === "number" && returncode !== 0) {
    return { headline: "Validation did not pass.", tone: "fail" };
  }
  return { headline: "Validation finished.", tone: "muted" };
}

/**
 * @param {string} headline
 * @param {"ok" | "warn" | "fail" | "muted"} tone
 */
function setValidationReportSummary(headline, tone) {
  if (!validationReportStatus) return;
  validationReportStatus.textContent = headline;
  validationReportStatus.className = "hint validation-summary";
  if (tone === "ok") validationReportStatus.classList.add("ok");
  else if (tone === "warn") validationReportStatus.classList.add("warn");
  else if (tone === "fail") validationReportStatus.classList.add("bad");
  else validationReportStatus.classList.add("muted");
}

function collapseValidationReportDetail() {
  if (validationReportPre) {
    validationReportPre.hidden = true;
    validationReportPre.textContent = "";
  }
  if (validationReportToggleBtn) {
    validationReportToggleBtn.hidden = true;
    validationReportToggleBtn.textContent = "Show full validation report";
    validationReportToggleBtn.setAttribute("aria-expanded", "false");
  }
}

/**
 * Update Validation panel from API or pipeline result (same shape as /api/extraction/validate).
 * @param {{ returncode?: number; report?: string; log_tail?: string }} data
 */
function applyValidationUiFromApiData(data) {
  if (!validationReportStatus || !validationReportPre) return;
  const rc = typeof data.returncode === "number" ? data.returncode : null;
  const report = typeof data.report === "string" ? data.report : "";
  const tail = typeof data.log_tail === "string" ? data.log_tail.trim() : "";
  const { headline, tone } = validationSummaryFromReport(report, rc);
  setValidationReportSummary(headline, tone);

  const parts = [];
  if (report) parts.push(report);
  else parts.push("(no validation_report.md content — check output folder and script errors.)");
  if (tail) parts.push("\n---\n\n**Process output (tail)**\n\n" + tail);
  validationReportPre.textContent = parts.join("\n");
  validationReportPre.hidden = true;
  if (validationReportToggleBtn) {
    validationReportToggleBtn.hidden = false;
  }
}

/**
 * @param {string} headline
 * @param {"ok" | "warn" | "fail" | "muted"} tone
 */
function setXmlExportStatus(headline, tone) {
  if (!xmlExportStatus) return;
  xmlExportStatus.textContent = headline;
  xmlExportStatus.className = "hint validation-summary";
  if (tone === "ok") xmlExportStatus.classList.add("ok");
  else if (tone === "warn") xmlExportStatus.classList.add("warn");
  else if (tone === "fail") xmlExportStatus.classList.add("bad");
  else xmlExportStatus.classList.add("muted");
}

async function runXmlExport() {
  if (batchRunning) return;
  if (!xmlExportStatus) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    setXmlExportStatus("Set output directory first.", "fail");
    return;
  }
  setXmlExportStatus("Running export_noteval_xml…", "muted");
  if (xmlExportBtn) xmlExportBtn.disabled = true;
  try {
    const { res, data } = await apiPostJson("/api/extraction/export-xml", {
      output_dir: out,
    });
    if (!res.ok) {
      setXmlExportStatus(formatDetail(data.detail) || res.statusText, "fail");
      return;
    }
    const path = typeof data.xml_path === "string" ? data.xml_path : "";
    const exists = !!data.xml_exists;
    if (exists && path) {
      setXmlExportStatus(`Wrote XML: ${path}`, "ok");
    } else if (path) {
      setXmlExportStatus(`Exporter finished but file not found at ${path}`, "warn");
    } else {
      setXmlExportStatus("Export returned no path.", "warn");
    }
  } catch (e) {
    setXmlExportStatus(e instanceof Error ? e.message : String(e), "fail");
  } finally {
    if (xmlExportBtn) xmlExportBtn.disabled = false;
  }
}

/**
 * @param {{ batch?: boolean }} [opts]
 */
async function runCompareXmlDb(opts = {}) {
  const batch = !!opts.batch;
  if (batchRunning && !batch) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    const msg = "Set output directory first.";
    if (batch) setBatchValidationSummaryStatus(msg, "fail");
    else setXmlExportStatus(msg, "fail");
    return;
  }

  /** @type {string[]} */
  let folderNames = [];
  if (batch) {
    folderNames = batchQueueDealFolderNames();
    if (folderNames.length === 0) {
      window.alert(
        "No output folders in the batch queue. Run batch extraction and Export batch to XML first.",
      );
      return;
    }
  }

  const statusFn = batch ? setBatchValidationSummaryStatus : setXmlExportStatus;
  const btn = batch ? batchCompareXmlDbBtn : compareXmlDbBtn;
  statusFn(
    batch
      ? `Comparing export XML to DB${folderNames.length ? ` (${folderNames.length} deal(s))` : ""}…`
      : "Comparing export XML to database…",
    "muted",
  );
  if (btn) btn.disabled = true;
  if (batch) {
    batchRunning = true;
    setBatchUiLocked(true);
  }

  try {
    const healthRes = await fetch("/api/health");
    const health = await healthRes.json().catch(() => ({}));
    if (
      healthRes.ok &&
      health.capabilities &&
      health.capabilities.compare_xml_db !== true
    ) {
      statusFn(
        "Compare with DB unavailable (openpyxl / batch_tranche_mapping — restart server from repo root).",
        "fail",
      );
      return;
    }

    const res = await fetch("/api/extraction/compare-xml-db", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        output_dir: out,
        folder_names: folderNames,
      }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      statusFn(formatDetail(data.detail) || res.statusText, "fail");
      return;
    }

    const compared = res.headers.get("X-Noteval-Compared") || "?";
    const missing = parseInt(res.headers.get("X-Noteval-Missing-Xml") || "0", 10) || 0;
    const fallback =
      folderNames.length === 1
        ? `xml_db_compare_${folderNames[0]}.xlsx`
        : folderNames.length > 1
          ? `xml_db_compare_${folderNames.length}deals.xlsx`
          : "xml_db_compare.xlsx";
    const filename = await downloadBlobResponse(res, fallback);
    let msg = `Compared ${compared} deal(s) — downloaded ${filename}. See Match rates sheet.`;
    if (missing > 0) {
      msg += ` (${missing} queue folder(s) had no export XML — run Export batch to XML first.)`;
    }
    statusFn(msg, missing > 0 ? "warn" : "ok");
  } catch (e) {
    statusFn(e instanceof Error ? e.message : String(e), "fail");
  } finally {
    if (btn) btn.disabled = false;
    if (batch) {
      batchRunning = false;
      setBatchUiLocked(false);
    }
  }
}

async function runMapValuationFees() {
  if (batchRunning) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    setXmlExportStatus("Set output directory first.", "fail");
    return;
  }
  if (mapValuationFeesBtn) mapValuationFeesBtn.disabled = true;
  setXmlExportStatus("Running map_valuation_fees.py…", "muted");
  try {
    const healthRes = await fetch("/api/health");
    const health = await healthRes.json().catch(() => ({}));
    if (
      healthRes.ok &&
      health.capabilities &&
      health.capabilities.map_valuation_fees !== true
    ) {
      setXmlExportStatus(
        "This server is too old for Map valuation fees (missing API). Stop it and restart: py -3 server.py — then hard-refresh the browser.",
        "fail",
      );
      return;
    }
    let { res, data } = await apiPostJson("/api/extraction/map-valuation-fees", {
      output_dir: out,
    });
    if (res.status === 404) {
      ({ res, data } = await apiPostJson("/api/extraction/map_valuation_fees", {
        output_dir: out,
      }));
    }
    if (!res.ok) {
      const msg = formatDetail(data.detail) || res.statusText;
      if (res.status === 404) {
        setXmlExportStatus(
          `${msg} — route not found. Restart noteval server (py -3 server.py from repo root) and hard-refresh the page.`,
          "fail",
        );
      } else {
        setXmlExportStatus(msg, "fail");
      }
      return;
    }
    const n = data.mapped_count ?? "?";
    const outFile = data.output_file ? ` (${data.output_file})` : "";
    setXmlExportStatus(`Mapped ${n} fee row(s) → 05_valuation_relevant_fees.md${outFile}`, "ok");
    await refreshWrapUpPanel({ quiet: true });
  } catch (e) {
    setXmlExportStatus(e instanceof Error ? e.message : String(e), "fail");
  } finally {
    if (mapValuationFeesBtn) mapValuationFeesBtn.disabled = false;
  }
}

async function runValidationReport() {
  if (batchRunning) return;
  if (!validationReportStatus || !validationReportPre) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    setValidationReportSummary("Set output directory first.", "fail");
    collapseValidationReportDetail();
    return;
  }
  setValidationReportSummary("Running validate_noteval…", "muted");
  collapseValidationReportDetail();
  if (validationRunBtn) validationRunBtn.disabled = true;
  try {
    const { res, data } = await apiPostJson("/api/extraction/validate", { output_dir: out });
    if (!res.ok) {
      setValidationReportSummary(formatDetail(data.detail) || res.statusText, "fail");
      collapseValidationReportDetail();
      return;
    }
    applyValidationUiFromApiData(data);
  } catch (e) {
    setValidationReportSummary(e instanceof Error ? e.message : String(e), "fail");
    collapseValidationReportDetail();
  } finally {
    if (validationRunBtn) validationRunBtn.disabled = false;
  }
}

function collapseBatchValidationSummaryDetail() {
  if (batchValidationSummaryPre) {
    batchValidationSummaryPre.hidden = true;
    batchValidationSummaryPre.textContent = "";
  }
  if (batchValidationSummaryToggleBtn) {
    batchValidationSummaryToggleBtn.hidden = true;
    batchValidationSummaryToggleBtn.textContent = "Show full batch summary";
    batchValidationSummaryToggleBtn.setAttribute("aria-expanded", "false");
  }
}

/**
 * @param {string} headline
 * @param {"ok" | "warn" | "fail" | "muted"} tone
 */
function setBatchValidationSummaryStatus(headline, tone) {
  if (!batchValidationSummaryStatus) return;
  batchValidationSummaryStatus.textContent = headline;
  batchValidationSummaryStatus.className = "hint validation-summary";
  if (tone === "ok") batchValidationSummaryStatus.classList.add("ok");
  else if (tone === "warn") batchValidationSummaryStatus.classList.add("warn");
  else if (tone === "fail") batchValidationSummaryStatus.classList.add("bad");
  else batchValidationSummaryStatus.classList.add("muted");
}

/**
 * @param {{ found?: boolean; path?: string; content?: string; truncated?: boolean; hint?: string }} data
 */
function applyBatchValidationSummaryUi(data) {
  if (!batchValidationSummaryStatus || !batchValidationSummaryPre) return;
  const found = !!data.found;
  const content = typeof data.content === "string" ? data.content : "";
  const hint = typeof data.hint === "string" ? data.hint : "";
  const path = typeof data.path === "string" ? data.path : "";

  if (!found) {
    const missing = path ? path.replace(/^.*[/\\]/, "") : "batch validation summary";
    setBatchValidationSummaryStatus(`No ${missing} on this output root.`, "warn");
    batchValidationSummaryPre.textContent = hint || path || "";
    batchValidationSummaryPre.hidden = false;
    if (batchValidationSummaryToggleBtn) batchValidationSummaryToggleBtn.hidden = true;
    return;
  }

  let tone = "muted";
  if (/\*\*Batch STATUS: FAIL\*\*/i.test(content)) tone = "fail";
  else if (/\*\*Batch STATUS: PASS\*\*/i.test(content)) tone = "ok";
  else if (/\*\*Batch STATUS: N\/A\*\*/i.test(content)) tone = "warn";
  const trunc = data.truncated ? " (file truncated in UI)" : "";
  setBatchValidationSummaryStatus(`Loaded batch summary${trunc}.`, tone);

  batchValidationSummaryPre.textContent = content;
  batchValidationSummaryPre.hidden = true;
  if (batchValidationSummaryToggleBtn) {
    batchValidationSummaryToggleBtn.hidden = false;
    batchValidationSummaryToggleBtn.textContent = "Show full batch summary";
    batchValidationSummaryToggleBtn.setAttribute("aria-expanded", "false");
  }
}

/** Deal folder basenames from batch queue rows (strips legacy ``*_sdk`` / ``*_llm`` suffixes). */
function batchQueueDealFolderNames() {
  syncBatchRowsFromDom();
  /** @type {string[]} */
  const names = [];
  for (const row of batchQueueRows) {
    const raw = String(row.output_dir || "").trim();
    if (!raw) continue;
    let base = outputPathBasename(raw);
    if (!base) continue;
    base = base.replace(/_sdk$/i, "").replace(/_llm$/i, "");
    names.push(base);
  }
  return [...new Set(names)];
}

async function runBatchValidation() {
  if (batchRunning) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    setBatchValidationSummaryStatus(
      "Set active output directory first (any folder under noteval_extractor/output).",
      "fail",
    );
    collapseBatchValidationSummaryDetail();
    return;
  }

  const queueOnly = batchValidateQueueOnly instanceof HTMLInputElement && batchValidateQueueOnly.checked;
  const strict = batchValidateStrict instanceof HTMLInputElement && batchValidateStrict.checked;

  /** @type {string[]} */
  let folderNames = [];
  if (queueOnly) {
    folderNames = batchQueueDealFolderNames();
    if (folderNames.length === 0) {
      window.alert(
        "No output folders in the batch queue. Run batch segmentation and extraction first, or uncheck “Only batch queue rows”.",
      );
      return;
    }
  }

  batchRunning = true;
  setBatchUiLocked(true);
  setBatchValidationSummaryStatus(
    `Running batch validation${queueOnly ? ` (${folderNames.length} queued folder(s))` : ""}…`,
    "muted",
  );
  collapseBatchValidationSummaryDetail();
  if (batchValidateRunBtn) batchValidateRunBtn.disabled = true;

  const extractionBatchId = lastExtractionBatchId("sdk") || lastExtractionBatchId("all");
  const validationSource = "sdk";

  try {
    const { res, data } = await apiPostJson(
      "/api/extraction/batch-validate",
      {
        output_dir: out,
        source: validationSource,
        strict,
        max_deals: 0,
        folder_names: folderNames,
        inventory_segmented: true,
        all_log_costs: false,
        extraction_batch_id: extractionBatchId,
      },
      { timeoutMs: 3_600_000 },
    );
    if (!res.ok) {
      setBatchValidationSummaryStatus(formatDetail(data.detail) || res.statusText, "fail");
      if (data.log_tail && batchValidationSummaryPre) {
        batchValidationSummaryPre.textContent = String(data.log_tail);
        batchValidationSummaryPre.hidden = false;
      }
      return;
    }
    applyBatchValidationSummaryUi({
      found: !!data.summary_found,
      path: data.summary_path,
      content: data.content || "",
      truncated: !!data.truncated,
      hint: data.log_tail || "",
    });
    const rc = typeof data.returncode === "number" ? data.returncode : null;
    const tone = data.ok ? (rc === 0 ? "ok" : "warn") : "fail";
    setBatchValidationSummaryStatus(
      data.ok
        ? "Batch validation finished. See summary below."
        : "Batch validation completed with failures. See summary.",
      tone,
    );
    if (data.log_tail && batchValidationSummaryPre) {
      const existing = batchValidationSummaryPre.textContent || "";
      batchValidationSummaryPre.textContent = `${existing}\n\n---\n\n**Process log (tail)**\n\n${data.log_tail}`.trim();
    }
  } catch (e) {
    setBatchValidationSummaryStatus(e instanceof Error ? e.message : String(e), "fail");
  } finally {
    batchRunning = false;
    setBatchUiLocked(false);
    if (batchValidateRunBtn) batchValidateRunBtn.disabled = false;
  }
}

/**
 * @param {Response} res
 * @param {string} fallbackName
 */
function downloadBlobResponse(res, fallbackName) {
  const cd = res.headers.get("Content-Disposition") || "";
  let filename = fallbackName;
  const m = /filename\*?=(?:UTF-8'')?"?([^";\n]+)"?/i.exec(cd);
  if (m && m[1]) filename = m[1].trim();
  return res.blob().then((blob) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.style.display = "none";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    return filename;
  });
}

async function runBatchExportXml() {
  if (batchRunning) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    setBatchValidationSummaryStatus(
      "Set active output directory first (any folder under noteval_extractor/output).",
      "fail",
    );
    return;
  }

  const queueOnly = batchValidateQueueOnly instanceof HTMLInputElement && batchValidateQueueOnly.checked;

  /** @type {string[]} */
  let folderNames = [];
  if (queueOnly) {
    folderNames = batchQueueDealFolderNames();
    if (folderNames.length === 0) {
      window.alert(
        "No output folders in the batch queue. Run batch extraction first, or uncheck “Only batch queue rows”.",
      );
      return;
    }
  }

  batchRunning = true;
  setBatchUiLocked(true);
  setBatchValidationSummaryStatus(
    `Exporting XML${queueOnly ? ` (${folderNames.length} folder(s))` : ""}…`,
    "muted",
  );
  if (batchExportXmlBtn) batchExportXmlBtn.disabled = true;

  try {
    const healthRes = await fetch("/api/health");
    const health = await healthRes.json().catch(() => ({}));
    if (
      healthRes.ok &&
      health.capabilities &&
      health.capabilities.batch_export_xml !== true
    ) {
      setBatchValidationSummaryStatus(
        "Batch XML export unavailable (export_noteval_xml.py missing — restart server from repo root).",
        "fail",
      );
      return;
    }

    const { res, data } = await apiPostJson("/api/extraction/batch-export-xml", {
      output_dir: out,
      source: "sdk",
      folder_names: folderNames,
      max_deals: 0,
    });
    if (!res.ok) {
      setBatchValidationSummaryStatus(formatDetail(data.detail) || res.statusText, "fail");
      return;
    }
    const exported = typeof data.exported === "number" ? data.exported : 0;
    const total = typeof data.total === "number" ? data.total : exported;
    const xmlRoot = typeof data.xml_root === "string" ? data.xml_root : "noteval_extractor/xml";
    const failed = Array.isArray(data.results)
      ? data.results.filter((r) => r && r.ok === false)
      : [];
    let msg = `Exported ${exported}/${total} deal(s) to ${xmlRoot}.`;
    if (failed.length > 0) {
      const names = failed
        .slice(0, 4)
        .map((r) => String(r.folder || "?"))
        .join(", ");
      msg += ` Failed: ${names}${failed.length > 4 ? "…" : ""}.`;
    }
    setBatchValidationSummaryStatus(msg, exported === total && failed.length === 0 ? "ok" : "warn");
  } catch (e) {
    setBatchValidationSummaryStatus(e instanceof Error ? e.message : String(e), "fail");
  } finally {
    batchRunning = false;
    setBatchUiLocked(false);
    if (batchExportXmlBtn) batchExportXmlBtn.disabled = false;
  }
}

async function runBatchValidationSummary() {
  if (batchRunning) return;
  if (!batchValidationSummaryStatus || !batchValidationSummaryPre) return;
  const out = cockpitOutputDir?.value.trim() || "";
  if (!out) {
    setBatchValidationSummaryStatus("Set output directory first (any deal folder under the output root).", "fail");
    collapseBatchValidationSummaryDetail();
    return;
  }
  setBatchValidationSummaryStatus("Loading batch_validation_summary_sdk.md…", "muted");
  collapseBatchValidationSummaryDetail();
  if (batchValidationSummaryBtn) batchValidationSummaryBtn.disabled = true;
  try {
    const { res, data } = await apiPostJson("/api/extraction/batch-validation-summary", {
      output_dir: out,
      source: "sdk",
    });
    if (!res.ok) {
      setBatchValidationSummaryStatus(formatDetail(data.detail) || res.statusText, "fail");
      collapseBatchValidationSummaryDetail();
      return;
    }
    applyBatchValidationSummaryUi(data);
  } catch (e) {
    setBatchValidationSummaryStatus(e instanceof Error ? e.message : String(e), "fail");
    collapseBatchValidationSummaryDetail();
  } finally {
    if (batchValidationSummaryBtn) batchValidationSummaryBtn.disabled = false;
  }
}

if (validationReportToggleBtn && validationReportPre) {
  validationReportToggleBtn.addEventListener("click", () => {
    const show = validationReportPre.hidden;
    validationReportPre.hidden = !show;
    validationReportToggleBtn.textContent = show
      ? "Hide full validation report"
      : "Show full validation report";
    validationReportToggleBtn.setAttribute("aria-expanded", show ? "true" : "false");
  });
}

if (mapValuationFeesBtn) {
  mapValuationFeesBtn.addEventListener("click", () => void runMapValuationFees());
}

if (validationRunBtn) {
  validationRunBtn.addEventListener("click", () => void runValidationReport());
}

if (xmlExportBtn) {
  xmlExportBtn.addEventListener("click", () => void runXmlExport());
}

if (compareXmlDbBtn) {
  compareXmlDbBtn.addEventListener("click", () => void runCompareXmlDb());
}

if (batchValidationSummaryToggleBtn && batchValidationSummaryPre) {
  batchValidationSummaryToggleBtn.addEventListener("click", () => {
    const show = batchValidationSummaryPre.hidden;
    batchValidationSummaryPre.hidden = !show;
    batchValidationSummaryToggleBtn.textContent = show
      ? "Hide full batch summary"
      : "Show full batch summary";
    batchValidationSummaryToggleBtn.setAttribute("aria-expanded", show ? "true" : "false");
  });
}

if (batchValidateRunBtn) {
  batchValidateRunBtn.addEventListener("click", () => void runBatchValidation());
}

if (batchExportXmlBtn) {
  batchExportXmlBtn.addEventListener("click", () => void runBatchExportXml());
}

if (batchCompareXmlDbBtn) {
  batchCompareXmlDbBtn.addEventListener("click", () => void runCompareXmlDb({ batch: true }));
}

if (batchValidationSummaryBtn) {
  batchValidationSummaryBtn.addEventListener("click", () => void runBatchValidationSummary());
}

if (wrapupRefreshBtn) {
  wrapupRefreshBtn.addEventListener("click", () => void refreshWrapUpPanel({ quiet: false }));
}

if (wrapupDealSelect) {
  wrapupDealSelect.addEventListener("change", () => {
    const v = String(wrapupDealSelect.value || "").trim();
    if (!v) return;
    setActiveOutputDirectory(v, { refreshWrapup: true });
  });
}

if (wrapupCopyBothBtn && wrapupTranchePanel && wrapupFeesPanel) {
  wrapupCopyBothBtn.addEventListener("click", () => {
    const tMd = lastWrapupTrancheMarkdownExport.trim();
    const t =
      tMd !== ""
        ? `# Tranche grid (from ${WRAPUP_TRANCHE_FILE})\n\n${tMd}\n`
        : (wrapupTranchePanel.innerText || "").trim();
    const fMd = lastWrapupFeesMarkdownExport.trim();
    const f =
      fMd !== ""
        ? `# Waterfall & fees (from ${WRAPUP_FEES_FILE})\n\n${fMd}\n`
        : (wrapupFeesPanel.innerText || "").trim();
    const aMd = lastWrapupAdminMarkdownExport.trim();
    const a =
      aMd !== ""
        ? `# Administrative Expenses grid (from ${WRAPUP_FEES_FILE})\n\n${aMd}\n`
        : (wrapupAdminPanel?.innerText || "").trim();
    const block = [t, f, a].filter((x) => x.trim()).join("\n\n---\n\n");
    if (!block.trim()) {
      window.alert("Nothing to copy — refresh after setting an output folder with 02/03.");
      return;
    }
    void copyText(block + "\n");
    if (wrapupStatus) {
      wrapupStatus.textContent =
        tMd && fMd && aMd
          ? "Copied tranche + waterfall/fees + admin grid (markdown)."
          : tMd && fMd
            ? "Copied tranche + waterfall/fees (markdown); admin grid empty or unavailable."
            : "Copied panel content to clipboard.";
    }
  });
}

function onExtractScopePresetChange(which) {
  const otherId =
    which === "0102" ? "extractDeliverables0304Only" : "extractDeliverables0102Only";
  const selfId =
    which === "0102" ? "extractDeliverables0102Only" : "extractDeliverables0304Only";
  const selfEl = document.getElementById(selfId);
  const otherEl = document.getElementById(otherId);
  if (
    selfEl instanceof HTMLInputElement &&
    selfEl.checked &&
    otherEl instanceof HTMLInputElement
  ) {
    otherEl.checked = false;
  }
  applyExtractScopeUi();
  void refreshExtractionHints();
}

applyExtractScopeUi();
const extract0102El = document.getElementById("extractDeliverables0102Only");
if (extract0102El instanceof HTMLInputElement) {
  extract0102El.addEventListener("change", () => onExtractScopePresetChange("0102"));
}
const extract0304El = document.getElementById("extractDeliverables0304Only");
if (extract0304El instanceof HTMLInputElement) {
  extract0304El.addEventListener("change", () => onExtractScopePresetChange("0304"));
}
void refreshExtractionHints();
initBatchQueue();
renderOutputPathHistory();
