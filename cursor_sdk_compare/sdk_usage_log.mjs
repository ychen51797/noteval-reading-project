/**
 * Append JSONL usage lines for Cursor SDK noteval extractions (tokens + estimated USD).
 *
 * Default log: <repo>/logs/noteval_sdk_usage.log
 * Disable: NOTEVAL_SDK_USAGE_LOG=0|off|false
 * Override path: NOTEVAL_SDK_USAGE_LOG=/path/to/file.log
 * Rates: NOTEVAL_SDK_PRICE_*_PER_1M, NOTEVAL_SDK_CURSOR_TOKEN_RATE_PER_1M (default 0.25)
 */

import { appendFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "..");

/** @type {[string, number, number, number | null, number | null][]} prefix, input, output, cacheWrite, cacheRead */
const MODEL_USD_PER_1M = [
  ["composer-2.5", 0.5, 2.5, null, 0.2],
  ["composer-2", 0.5, 2.5, null, 0.2],
  ["composer-1.5", 3.5, 17.5, null, 0.35],
  ["composer-1", 1.25, 10, null, 0.125],
];

const DEFAULT_CURSOR_TOKEN_RATE_PER_1M = 0.25;

export function resolveSdkUsageLogPath() {
  const raw = (process.env.NOTEVAL_SDK_USAGE_LOG ?? "").trim().toLowerCase();
  if (raw === "0" || raw === "off" || raw === "false" || raw === "no") {
    return null;
  }
  if (raw) {
    return resolve(raw);
  }
  return resolve(REPO_ROOT, "logs", "noteval_sdk_usage.log");
}

function tableRates(modelId) {
  const m = String(modelId ?? "").trim().toLowerCase();
  for (const [prefix, inp, out, cw, cr] of MODEL_USD_PER_1M) {
    if (m === prefix || m.startsWith(`${prefix}-`)) {
      return { input: inp, output: out, cacheWrite: cw ?? inp, cacheRead: cr ?? inp * 0.4 };
    }
  }
  return null;
}

function envRate(name) {
  const v = (process.env[name] ?? "").trim();
  if (!v) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function cursorTokenRatePerM() {
  const v = envRate("NOTEVAL_SDK_CURSOR_TOKEN_RATE_PER_1M");
  return v ?? DEFAULT_CURSOR_TOKEN_RATE_PER_1M;
}

/**
 * @param {string} modelId
 * @param {{ inputTokens: number; outputTokens: number; cacheReadTokens: number; cacheWriteTokens: number }} t
 */
export function estimateSdkCostUsd(modelId, t) {
  const inp = Math.max(0, t.inputTokens ?? 0);
  const out = Math.max(0, t.outputTokens ?? 0);
  const cr = Math.max(0, t.cacheReadTokens ?? 0);
  const cw = Math.max(0, t.cacheWriteTokens ?? 0);

  const envIn = envRate("NOTEVAL_SDK_PRICE_INPUT_PER_1M");
  const envOut = envRate("NOTEVAL_SDK_PRICE_OUTPUT_PER_1M");
  const envCr = envRate("NOTEVAL_SDK_PRICE_CACHE_READ_PER_1M");
  const envCw = envRate("NOTEVAL_SDK_PRICE_CACHE_WRITE_PER_1M");

  let rates;
  let pricingNote;
  if (envIn != null && envOut != null) {
    rates = {
      input: envIn,
      output: envOut,
      cacheRead: envCr ?? envIn * 0.4,
      cacheWrite: envCw ?? envIn,
    };
    pricingNote = "env_rates_plus_ctr";
  } else {
    rates = tableRates(modelId);
    if (!rates) {
      return { cost_usd: null, cost_model_usd: null, cost_ctr_usd: null, pricing_note: "unknown_model_set_NOTEVAL_SDK_PRICE_*_PER_1M" };
    }
    pricingNote = "cursor_list_plus_ctr_approx";
  }

  const modelUsd =
    (inp * rates.input + out * rates.output + cr * rates.cacheRead + cw * rates.cacheWrite) / 1_000_000;
  const totalTok = inp + out + cr + cw;
  const ctrUsd = (totalTok * cursorTokenRatePerM()) / 1_000_000;
  const cost = modelUsd + ctrUsd;
  return {
    cost_usd: Math.round(cost * 1_000_000) / 1_000_000,
    cost_model_usd: Math.round(modelUsd * 1_000_000) / 1_000_000,
    cost_ctr_usd: Math.round(ctrUsd * 1_000_000) / 1_000_000,
    pricing_note: pricingNote,
  };
}

export function createUsageAccumulator() {
  return {
    inputTokens: 0,
    outputTokens: 0,
    cacheReadTokens: 0,
    cacheWriteTokens: 0,
    turnCount: 0,
  };
}

/**
 * @param {ReturnType<typeof createUsageAccumulator>} acc
 * @param {{ inputTokens?: number; outputTokens?: number; cacheReadTokens?: number; cacheWriteTokens?: number }} u
 */
export function addTurnUsage(acc, u) {
  if (!u) return;
  acc.inputTokens += u.inputTokens ?? 0;
  acc.outputTokens += u.outputTokens ?? 0;
  acc.cacheReadTokens += u.cacheReadTokens ?? 0;
  acc.cacheWriteTokens += u.cacheWriteTokens ?? 0;
  acc.turnCount += 1;
}

/**
 * @param {Record<string, unknown>} record
 */
export function appendSdkUsageLog(record) {
  const path = resolveSdkUsageLogPath();
  if (!path) return null;
  mkdirSync(dirname(path), { recursive: true });
  appendFileSync(path, `${JSON.stringify(record)}\n`, "utf8");
  return path;
}

/**
 * @param {string} sdkDir absolute path to *_sdk output folder
 */
export function dealFolderFromSdkDir(sdkDir) {
  const parts = sdkDir.replace(/\\/g, "/").split("/");
  return parts[parts.length - 1] || sdkDir;
}
