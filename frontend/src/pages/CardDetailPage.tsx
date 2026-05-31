import { Crop, Minus, Play, Plus, RefreshCw, RotateCcw, Save, Trash2, Upload, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PointerEvent, ReactNode, WheelEvent } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, mediaUrl } from "../api/client";
import type {
  AnalysisAsset,
  AIGradingPipelineStatus,
  AnalysisFinding,
  AnalysisImagePayload,
  AnalysisReport,
  AnalysisRun,
  Card,
  CardMedia,
  CenteringMeasurement,
  LocalAIDryRun,
  LocalAIDebugSingleImageResponse,
  LocalAIStatus,
  OwnedCard,
  PriceFetchResponse,
  PriceHistoryEntry,
  PriceObservation,
  PriceProviderStatus,
  ProcessedImagesResponse,
  ProcessedSide,
  RemoteAIGradeResponse,
  RemoteAIWorkerResult,
  RecognitionResponse,
} from "../api/types";
import { AIGradingModal } from "../components/AIGradingModal";
import { EmptyState } from "../components/EmptyState";
import { GlobalLoadingOverlay } from "../components/GlobalLoadingOverlay";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { SegmentedControl } from "../components/SegmentedControl";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";
import { formatDate, formatHuf, formatNumber } from "../utils/format";

const mediaLabels = [
  "front",
  "back",
  "corner_tl",
  "corner_tr",
  "corner_bl",
  "corner_br",
  "edge_top",
  "edge_right",
  "edge_bottom",
  "edge_left",
];
const statuses = ["raw_owned", "graded_owned", "sent_to_grading", "listed_for_sale", "sold", "kept_long_term"];
const sources = ["pack", "blister", "single_purchase", "trade", "unknown"];
const processedVariantOptions = [
  ["perspective_corrected", "Normalized", "Perspective corrected grading view."],
  ["original_normalized", "Original", "Original uploaded image."],
  ["grayscale_clahe", "CLAHE", "Contrast-enhanced grayscale."],
  ["sobel_edges", "Sobel", "Edge and line emphasis."],
  ["emboss_surface", "Emboss", "Surface texture visualization."],
  ["highpass_texture", "High Pass", "Micro texture and scratch enhancement."],
  ["canny_edges", "Canny", "Contour detection."],
  ["centering_debug", "Centering Debug", "Measurement overlay."],
] as const;

type CardDetailPageProps = {
  ownedCardId: number;
  debugMode: boolean;
  onDeleted: () => void;
};

type PriceForm = {
  raw_price: string;
  market_price: string;
  psa_7: string;
  psa_8: string;
  psa_9: string;
  psa_10: string;
  currency: string;
  price_confidence: string;
  condition_hint: string;
  source_url: string;
};

type OwnedEditForm = {
  copy_label: string;
  status: string;
  acquired_price_huf: string;
  acquired_source: string;
  storage_location: string;
  personal_notes: string;
};

type NoticeScope = "details" | "media" | "price" | "analysis" | "report";

type InlineNoticeState = {
  scope: NoticeScope;
  tone: "success" | "error";
  text: string;
};

type WorkOverlayState = {
  title: string;
  subtitle: string;
  steps?: string[];
};

const emptyPriceForm: PriceForm = {
  raw_price: "",
  market_price: "",
  psa_7: "",
  psa_8: "",
  psa_9: "",
  psa_10: "",
  currency: "HUF",
  price_confidence: "manual",
  condition_hint: "",
  source_url: "",
};

function editFormFromOwnedCard(ownedCard: OwnedCard | null): OwnedEditForm {
  return {
    copy_label: ownedCard?.copy_label ?? "",
    status: ownedCard?.status ?? "raw_owned",
    acquired_price_huf: ownedCard?.acquired_price_huf?.toString() ?? "",
    acquired_source: ownedCard?.acquired_source ?? "unknown",
    storage_location: ownedCard?.storage_location ?? "",
    personal_notes: ownedCard?.personal_notes ?? "",
  };
}

function formFromPrice(price: PriceHistoryEntry | null): PriceForm {
  if (!price) return emptyPriceForm;
  return {
    raw_price: price.raw_price?.toString() ?? "",
    market_price: price.market_price?.toString() ?? "",
    psa_7: price.psa_7?.toString() ?? "",
    psa_8: price.psa_8?.toString() ?? "",
    psa_9: price.psa_9?.toString() ?? "",
    psa_10: price.psa_10?.toString() ?? "",
    currency: price.currency ?? "HUF",
    price_confidence: price.confidence ?? "manual",
    condition_hint: price.condition_hint ?? "",
    source_url: price.source_url ?? "",
  };
}

function priceValueHuf(price: PriceHistoryEntry | null, key: "raw" | "market" | "psa_7" | "psa_8" | "psa_9" | "psa_10"): number | null {
  if (!price) return null;
  const convertedKey = key === "raw" || key === "market" ? `converted_${key}_price` : `converted_${key}`;
  const converted = price[convertedKey as keyof PriceHistoryEntry];
  if (typeof converted === "number") return converted;
  if (price.currency === "HUF") {
    const value = key === "raw" ? price.raw_price : key === "market" ? price.market_price : price[key];
    return value ?? null;
  }
  return null;
}

function sourcePriceValue(price: PriceHistoryEntry | null, key: "raw" | "market" | "psa_7" | "psa_8" | "psa_9" | "psa_10"): number | null {
  if (!price) return null;
  if (key === "raw") return price.raw_price ?? null;
  if (key === "market") return price.market_price ?? null;
  return price[key] ?? null;
}

function formatSourceCurrency(value: number | null, currency?: string | null): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("hu-HU", {
    style: "currency",
    currency: currency || "HUF",
    maximumFractionDigits: currency === "HUF" ? 0 : 2,
  }).format(value);
}

function fxMetadata(price: PriceHistoryEntry | null): { provider?: string; rateDate?: string; source?: string; warning?: string } | null {
  if (!price?.debug_metadata_json) return null;
  try {
    const parsed = JSON.parse(price.debug_metadata_json) as { fx?: Record<string, unknown> };
    const fx = parsed.fx;
    if (!fx) return null;
    return {
      provider: typeof fx.fx_provider === "string" ? fx.fx_provider : undefined,
      rateDate: typeof fx.fx_rate_date === "string" ? fx.fx_rate_date : undefined,
      source: typeof fx.fx_source === "string" ? fx.fx_source : undefined,
      warning: typeof fx.fx_warning === "string" ? fx.fx_warning : undefined,
    };
  } catch {
    return null;
  }
}

function legacyPriceToHistory(price: PriceObservation, ownedCardId: number): PriceHistoryEntry {
  return {
    id: -price.id,
    card_id: price.card_id,
    owned_card_id: ownedCardId,
    source: price.source_name ?? "legacy",
    raw_price: price.raw_price_huf,
    market_price: price.raw_price_huf,
    psa_7: price.psa_7_price_huf,
    psa_8: price.psa_8_price_huf,
    psa_9: price.psa_9_price_huf,
    psa_10: price.psa_10_price_huf,
    currency: "HUF",
    converted_currency: "HUF",
    converted_raw_price: price.raw_price_huf,
    converted_market_price: price.raw_price_huf,
    converted_psa_7: price.psa_7_price_huf,
    converted_psa_8: price.psa_8_price_huf,
    converted_psa_9: price.psa_9_price_huf,
    converted_psa_10: price.psa_10_price_huf,
    confidence: price.price_confidence?.toString() ?? null,
    condition_hint: price.notes ?? null,
    fetched_at: price.observed_at,
    created_at: price.observed_at,
    updated_at: price.observed_at,
  };
}

function priceProviderLabel(provider: string): string {
  return {
    auto: "Auto/provider chain",
    manual: "Manual",
    local_json: "Local JSON",
    poketrace: "PokeTrace",
    tcgdex: "TCGdex",
    pokemontcg: "Pokemon TCG API",
  }[provider] ?? provider;
}

function providerFetchErrorMessage(error?: string | null, fallback?: string | null): string {
  if (error === "price_source_not_configured") return "Az árforrás nincs beállítva.";
  if (error === "price_source_disabled") return "Az árforrás ki van kapcsolva.";
  if (error === "provider_rate_limited") return "Rate limit elérve. Próbáld később.";
  if (error === "provider_no_reliable_match") return "Nem találtunk elég biztos egyezést.";
  if (error === "provider_no_price_available") return "Nem találtunk használható árat ennél a forrásnál.";
  if (error === "provider_auth_failed") return "Az API kulcs elutasítva.";
  return fallback || "Nem érkezett használható árforrásból adat.";
}

const marketPriceSources = new Set(["poketrace", "tcgdex", "pokemontcg", "local_json"]);

function isMarketPrice(price: PriceHistoryEntry | null): boolean {
  if (!price) return false;
  return marketPriceSources.has((price.source ?? "").toLowerCase());
}

function priceHistoryMatchesFilter(price: PriceHistoryEntry, filter: string): boolean {
  const source = (price.source ?? "").toLowerCase();
  if (filter === "all") return true;
  if (filter === "market") return marketPriceSources.has(source);
  if (filter === "manual") return source === "manual";
  return source === filter;
}

function sourcePriceDisplay(price: PriceHistoryEntry | null): string {
  if (!price) return "-";
  const value = price.market_price ?? price.raw_price ?? price.psa_10 ?? price.psa_9 ?? price.psa_8 ?? price.psa_7 ?? null;
  return formatSourceCurrency(value, price.currency);
}

function fetchSuccessMessage(result: PriceFetchResponse): string {
  const success = result.results.find((item) => item.ok && !item.skipped && item.source !== "manual") ?? result.results.find((item) => item.ok);
  const value = success?.market_price ?? success?.raw_price ?? null;
  if (success && value !== null) {
    return `${priceProviderLabel(success.source)} sikeres: ${formatSourceCurrency(value, success.currency)}`;
  }
  return `Árfrissítés kész: ${result.fetched_count} sikeres forrás.`;
}

function optionalNumber(value: string): number | null {
  const normalized = value.trim().replace(",", ".");
  if (!normalized) return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
}

function FieldLabel({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-1.5 text-xs font-medium text-slate-400">
      <span>{label}</span>
      {children}
    </label>
  );
}

function PriceValueCard({ label, price, field }: { label: string; price: PriceHistoryEntry; field: "raw" | "market" | "psa_7" | "psa_8" | "psa_9" | "psa_10" }) {
  const sourceValue = sourcePriceValue(price, field);
  const hufValue = priceValueHuf(price, field);
  const isConverted = price.currency !== "HUF";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-4">
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-50">{isConverted ? formatSourceCurrency(sourceValue, price.currency) : formatHuf(hufValue)}</div>
      {isConverted && hufValue !== null && (
        <div className="mt-1 text-sm text-emerald-200">≈ {formatHuf(hufValue)}</div>
      )}
      {isConverted && sourceValue !== null && hufValue === null && (
        <div className="mt-1 text-xs text-amber-200">{price.currency} ár elérhető, de HUF konverzió még nincs.</div>
      )}
    </div>
  );
}

function displayRemoteValue(value?: number | string | null): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return formatNumber(value);
  return value;
}

function displayGrade(value?: number | string | null): string {
  if (value === null || value === undefined || value === "") return "N/A";
  if (typeof value === "number") return formatNumber(value);
  return value;
}

function parseDisplayGradeScore(value?: number | string | { score?: number | string | null; label?: string | null } | null): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "object") return parseDisplayGradeScore(value.score);
  if (typeof value === "number") return Math.max(1, Math.min(10, value));
  const match = value.replace(",", ".").match(/(?<!\d)(10(?:\.0)?|[0-9](?:\.[05])?)(?!\d)/);
  if (match) return Math.max(1, Math.min(10, Number(match[1])));
  const lowered = value.toLowerCase();
  if (lowered.includes("gem") && lowered.includes("mint")) return 10;
  if (lowered === "nm" || lowered.includes("near mint")) return 9;
  if (lowered.includes("mint")) return 9.5;
  if (lowered === "ex" || lowered.includes("excellent")) return 7;
  if (lowered === "vg" || lowered.includes("very good")) return 5;
  if (lowered.includes("good")) return 3;
  if (lowered.includes("poor")) return 1;
  return null;
}

function labelForGradeScore(score: number | null): string {
  if (score === null) return "";
  if (score >= 10) return "Gem Mint";
  if (score >= 9.5) return "Mint";
  if (score >= 9) return "Near Mint";
  if (score >= 7) return "Excellent";
  if (score >= 5) return "Very Good";
  if (score >= 3) return "Good";
  return "Poor";
}

function displaySubgrade(value?: number | string | { score?: number | string | null; label?: string | null } | null): string {
  const score = parseDisplayGradeScore(value);
  const label = typeof value === "object" && value?.label ? value.label : labelForGradeScore(score);
  if (score === null) return "N/A";
  return `${formatNumber(score)}${label ? ` ${label}` : ""}`;
}

function displayFinalGrade(final?: { overall_score?: number | null; estimated_grade?: string | null; estimated_grade_label?: string | null } | null): string {
  const score = parseDisplayGradeScore(final?.overall_score ?? final?.estimated_grade);
  if (score === null) return displayGrade(final?.estimated_grade);
  return final?.estimated_grade_label ? `${formatNumber(score)} ${final.estimated_grade_label}` : formatNumber(score);
}

function displayGradeRangeValue(value?: string | { min?: number | string | null; max?: number | string | null; label?: string | null } | null): string {
  if (!value) return "N/A";
  if (typeof value === "object") {
    if (value.label) return value.label;
    const low = parseDisplayGradeScore(value.min);
    const high = parseDisplayGradeScore(value.max);
    return low !== null && high !== null ? `${formatNumber(low)} - ${formatNumber(high)}` : "N/A";
  }
  return value;
}

function aiWarningText(warning: string): string {
  if (warning === "model_reported_issue_for_unprovided_area" || warning === "invalid_issues_filtered") {
    return "A modell olyan területre jelzett hibát, amelyről nem kapott képet. Ez a jelzés el lett vetve.";
  }
  if (warning === "limited_image_set") {
    return "Csak egy kép vagy hiányos képsor alapján készült, ezért nem teljes grading.";
  }
  if (warning === "repeated_template_issue_warning") {
    return "A válasz sablonos hibaleírásra hasonlít; érdemes kézzel ellenőrizni.";
  }
  if (warning === "model_grade_low_without_visible_evidence") {
    return "A modell alacsonyabb grade-et jelzett látható indok nélkül, ezért a bizalom csökkentve lett.";
  }
  if (warning === "possible_stale_image_payload") {
    return "Figyelem: ez az AI futás ugyanazt a képet kapta, mint egy korábbi másik kártya elemzése.";
  }
  return warning;
}

function ImagePayloadDebug({ payload }: { payload?: AnalysisImagePayload[] }) {
  if (!payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-xs text-slate-300">
      <div className="mb-2 font-semibold text-slate-200">Image payload</div>
      <div className="space-y-2">
        {payload.map((item, index) => (
          <div key={`${item.asset_id ?? index}-${item.image_hash_short ?? index}`} className="rounded border border-slate-800 p-2">
            <div className="font-medium text-slate-100">{item.image_label ?? item.asset_label ?? "image"} · {item.image_hash_short ?? "-"}</div>
            <div className="mt-1 text-slate-400">
              asset #{item.asset_id ?? "-"} · media #{item.media_id ?? "-"} · {item.width ?? "-"}x{item.height ?? "-"} · {item.file_size ?? "-"} bytes
            </div>
            <div className="mt-1 break-all text-slate-500">{item.relative_path ?? item.filename ?? "-"}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RemoteAIGradePanel({ response }: { response: RemoteAIGradeResponse }) {
  const result = response.worker_result as RemoteAIWorkerResult;
  const issues = Array.isArray(result.detected_issues) ? result.detected_issues : [];
  const metaWarnings = (response.worker_meta as { warnings?: unknown } | undefined)?.warnings;
  const warnings = response.warnings ?? (Array.isArray(metaWarnings) ? metaWarnings.map(String) : []);
  const metaPayload = (response.worker_meta as { image_payload?: unknown } | undefined)?.image_payload;
  const imagePayload = response.image_payload ?? (Array.isArray(metaPayload) ? metaPayload as AnalysisImagePayload[] : []);
  const isPartial = response.analysis_scope === "partial" || response.analysis_run?.analysis_scope === "partial";
  return (
    <div className={response.ok ? "mt-4 rounded-lg border border-emerald-500/25 bg-emerald-500/10 p-4 text-sm text-emerald-50" : "mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100"}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-semibold">{response.ok ? "Remote AI grading" : "Remote AI worker hiba"}</div>
          {isPartial && <div className="mt-2 inline-flex rounded-full border border-amber-500/40 px-2 py-0.5 text-xs text-amber-100">Részleges elemzés</div>}
          <div className="mt-1 text-xs opacity-80">
            Képek: {response.images_sent ?? "-"} · {response.image_labels_sent?.join(", ") || "-"}
          </div>
        </div>
        <div className="text-right">
          <div className="text-2xl font-semibold">{isPartial ? "-" : displayRemoteValue(result.estimated_grade)}</div>
          <div className="text-xs opacity-80">Becslés</div>
        </div>
      </div>
      {response.ok ? (
        <div className="mt-4 space-y-4">
          {warnings.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
              {warnings.map((warning) => <div key={warning}>{aiWarningText(warning)}</div>)}
            </div>
          )}
          <div className="grid grid-cols-2 gap-2">
            <StatCard label="Range" value={isPartial ? "Részleges" : `${displayRemoteValue(result.grade_range?.low)} - ${displayRemoteValue(result.grade_range?.high)}`} />
            <StatCard label="Confidence" value={result.confidence || "-"} />
            <StatCard label="Centering" value={displayRemoteValue(result.subscores?.centering)} />
            <StatCard label="Corners" value={isPartial ? "-" : displayRemoteValue(result.subscores?.corners)} />
            <StatCard label="Edges" value={isPartial ? "-" : displayRemoteValue(result.subscores?.edges)} />
            <StatCard label="Surface" value={isPartial ? "-" : displayRemoteValue(result.subscores?.surface)} />
          </div>
          {result.summary && <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-slate-200">{result.summary}</div>}
          <ImagePayloadDebug payload={imagePayload} />
          {!isPartial && <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">PSA 10 risk</div>
              <div className="mt-1 text-slate-100">{result.psa_10_risk || "-"}</div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">
              <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Ajánlás</div>
              <div className="mt-1 text-slate-100">{result.recommended_action || "-"}</div>
            </div>
          </div>}
          {issues.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">Detected issues</div>
              <div className="space-y-2">
                {issues.map((issue, index) => (
                  <div key={`${issue.area ?? "issue"}-${index}`} className="rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-slate-200">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{issue.area || "unknown"}</span>
                      <FindingBadge tone={severityTone(issue.severity)}>{issue.severity || "unknown"}</FindingBadge>
                    </div>
                    <div className="mt-1 text-slate-300">{issue.description || "-"}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ) : (
        <pre className="mt-3 max-h-56 overflow-auto whitespace-pre-wrap rounded bg-slate-950/70 p-3 text-xs text-rose-100">{JSON.stringify(response.worker_result, null, 2)}</pre>
      )}
    </div>
  );
}

function SmartGradePanel({ pipeline, debugMode, onRetryPhaseB }: { pipeline: AIGradingPipelineStatus | null; debugMode: boolean; onRetryPhaseB: () => void }) {
  if (!pipeline || pipeline.status === "not_started") return null;
  const final = pipeline.final_result;
  const phaseAFinished = pipeline.phase_a_status === "completed";
  const phaseBFinished = pipeline.phase_b_status === "completed";
  const phaseBFailed = pipeline.phase_b_status === "failed" || pipeline.status === "phase_b_failed";
  return (
    <div className="glass-card mt-4 p-4 text-sm text-emerald-50">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="font-semibold">AI grading result</div>
          <div className="mt-1 text-xs opacity-80">Two-step workflow status: {pipeline.status}</div>
        </div>
        <div className="text-right">
          <div className="metric-value text-5xl font-semibold leading-none text-slate-50">{displayFinalGrade(final)}</div>
          <div className="text-xs opacity-80">Final estimate</div>
        </div>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <StatCard label="Visual + centering" value={phaseAFinished ? "Completed" : pipeline.phase_a_status ?? "Pending"} />
        <StatCard label="Surface + final grade" value={phaseBFinished ? "Completed" : pipeline.phase_b_status ?? "Pending"} />
        <StatCard label="Range" value={displayGradeRangeValue(final?.grade_range)} />
        <StatCard label="Confidence" value={final?.confidence !== undefined ? formatNumber(final.confidence, 2) : "-"} />
      </div>
      {final?.subgrades && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <StatCard label="Centering" value={displaySubgrade(final.subgrades.centering)} />
          <StatCard label="Corners" value={displaySubgrade(final.subgrades.corners)} />
          <StatCard label="Edges" value={displaySubgrade(final.subgrades.edges)} />
          <StatCard label="Surface" value={displaySubgrade(final.subgrades.surface)} />
        </div>
      )}
      {final?.reasoning_summary && <div className="mt-3 rounded-2xl border border-white/10 bg-[#0d1117]/38 p-3 text-slate-100">{final.reasoning_summary}</div>}
      {final?.risk_flags?.length ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {final.risk_flags.map((flag) => <StatusBadge key={flag} tone="warning">{flag}</StatusBadge>)}
        </div>
      ) : null}
      {final?.recommended_action && (
        <div className="mt-3 rounded-2xl border border-white/10 bg-[#0d1117]/38 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
          <div className="text-xs font-semibold uppercase text-slate-500">Recommended action</div>
          <div className="mt-1 text-base font-semibold text-slate-50">{final.recommended_action}</div>
        </div>
      )}
      {phaseBFailed && (
        <button className="mt-3 inline-flex items-center justify-center gap-2 rounded-lg border border-amber-500/40 px-3 py-2 text-sm font-medium text-amber-100 hover:bg-amber-500/10" onClick={onRetryPhaseB} type="button">
          <RefreshCw size={16} /> Retry Phase B
        </button>
      )}
      {debugMode && final?.parsing_warnings?.length ? (
        <div className="mt-3 rounded-lg border border-amber-400/25 bg-amber-400/10 p-3 text-xs text-amber-100">
          {final.parsing_warnings.map((warning) => <div key={warning}>{warning}</div>)}
        </div>
      ) : null}
      {debugMode && <details className="mt-3">
        <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-emerald-200">Developer details</summary>
        <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-slate-950/70 p-3 text-xs text-slate-200">{JSON.stringify({
          phase_a: pipeline.phase_a_result,
          final: pipeline.final_result,
          warnings: pipeline.warnings,
          parsing_warnings: pipeline.final_result?.parsing_warnings,
          model_parameters: pipeline.model_parameters,
          error: pipeline.error_message,
        }, null, 2)}</pre>
      </details>}
    </div>
  );
}

function RecognitionPanel({
  result,
  busy,
  onAccept,
}: {
  result: RecognitionResponse;
  busy: boolean;
  onAccept: (catalogCardId: number) => void;
}) {
  const extracted = result.recognition_attempt?.extracted;
  return (
    <div className={result.ok ? "mt-4 rounded-lg border border-blue-500/25 bg-blue-500/10 p-4 text-sm text-blue-50" : "mt-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-100"}>
      <div className="font-semibold">{result.ok ? "Kártya felismerés" : "Felismerési hiba"}</div>
      {result.message && <div className="mt-1 text-sm opacity-90">{result.message}</div>}
      {extracted && (
        <div className="mt-3 grid grid-cols-2 gap-2">
          <StatCard label="Név" value={extracted.name || "-"} />
          <StatCard label="Szám" value={extracted.card_number || "-"} />
          <StatCard label="Set" value={extracted.set_text || extracted.set_code || "-"} />
          <StatCard label="Ritkaság" value={extracted.rarity || "-"} />
        </div>
      )}
      {result.ok && result.candidates.length === 0 && (
        <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-amber-100">
          Nem találtam elég erős katalógus jelöltet. Próbálj élesebb front képet, vagy használd a kézi megadást.
        </div>
      )}
      {result.candidates.length > 0 && (
        <div className="mt-4 space-y-2">
          {result.candidates.map((candidate) => (
            <div key={candidate.id} className="rounded-lg border border-slate-800 bg-slate-950/35 p-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-medium text-slate-50">{candidate.rank}. {candidate.name}</div>
                  <div className="mt-1 text-xs text-slate-400">
                    {[candidate.set_name, candidate.set_code, candidate.card_number, candidate.rarity, candidate.language].filter(Boolean).join(" · ") || "-"}
                  </div>
                </div>
                <div className="rounded-full border border-blue-500/30 px-2 py-0.5 text-xs text-blue-100">{formatNumber(candidate.score, 0)}%</div>
              </div>
              {candidate.match_reasons.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {candidate.match_reasons.map((reason) => (
                    <span key={reason} className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{reason}</span>
                  ))}
                </div>
              )}
              <div className="mt-3 flex flex-wrap gap-2">
                <button className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy} onClick={() => onAccept(candidate.catalog_card_id)} type="button">
                  Ez az
                </button>
                <button className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800/50" onClick={() => { window.location.hash = "#/add"; }} type="button">
                  Manual override
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FindingBadge({ children, tone = "default" }: { children: ReactNode; tone?: "default" | "warn" | "danger" }) {
  const toneClass =
    tone === "danger"
      ? "border-rose-500/30 bg-rose-500/10 text-rose-200"
      : tone === "warn"
        ? "border-amber-500/30 bg-amber-500/10 text-amber-200"
        : "border-slate-700 bg-slate-900 text-slate-300";
  return <span className={`rounded-full border px-2 py-0.5 text-[11px] ${toneClass}`}>{children}</span>;
}

function severityTone(severity?: string | null): "default" | "warn" | "danger" {
  if (severity === "severe" || severity === "moderate") return "danger";
  if (severity === "minor" || severity === "very_minor") return "warn";
  return "default";
}

function newestFirst<T extends { created_at?: string | null; id?: number | null }>(items: T[]): T[] {
  return [...items].sort((a, b) => {
    const byDate = new Date(b.created_at ?? 0).getTime() - new Date(a.created_at ?? 0).getTime();
    if (byDate !== 0) return byDate;
    return (b.id ?? 0) - (a.id ?? 0);
  });
}

function cacheKeyFor(item: { id?: number | null; created_at?: string | null }): string | number | null {
  return item.id ?? item.created_at ?? null;
}

function sideFromLabel(label?: string | null): "front" | "back" | null {
  const normalized = (label ?? "").toLowerCase();
  if (normalized === "front" || normalized.startsWith("front_")) return "front";
  if (normalized === "back" || normalized.startsWith("back_")) return "back";
  return null;
}

function isPhotoQualityFinding(finding: AnalysisFinding): boolean {
  const findingType = (finding.finding_type ?? "unknown").toLowerCase();
  return (
    finding.photo_quality_issue === true ||
    finding.confirmed === false ||
    findingType === "glare_uncertain" ||
    findingType === "image_quality_issue" ||
    findingType === "unknown"
  );
}

function isAutoCropAsset(asset: AnalysisAsset): boolean {
  const label = (asset.label ?? "").toLowerCase();
  return asset.asset_type === "crop" || label.includes("corner") || label.includes("edge");
}

function isDebugAsset(asset: AnalysisAsset): boolean {
  return Boolean(asset.asset_type?.startsWith("local_ai")) || asset.asset_type === "opencv_debug" || asset.asset_type === "normalized_image" || isAutoCropAsset(asset);
}

function annotatedFindingId(asset: AnalysisAsset): number | null {
  const match = (asset.label ?? "").match(/^finding_(\d+)_annotated$/);
  return match ? Number(match[1]) : null;
}

function assetDisplayLabel(asset: AnalysisAsset): string {
  if (isAutoCropAsset(asset)) {
    return `Auto crop - nem használt gradinghez: ${asset.label ?? asset.asset_type ?? "asset"}`;
  }
  return asset.label ?? asset.asset_type ?? "asset";
}

function workOverlayForLabel(label: string | null): WorkOverlayState | null {
  if (!label) return null;
  if (label.includes("Smart AI")) {
    return {
      title: "Smart AI grading running...",
      subtitle: "One request is running deterministic preprocessing, Phase A notes, and Phase B final grading.",
      steps: ["Visual and centering analysis running", "Surface and final grading running", "Final result saved"],
    };
  }
  if (label.includes("preprocess")) {
    return {
      title: "Preprocessing images...",
      subtitle: "OpenCV diagnostic views and centering data are being refreshed.",
      steps: ["Boundary detection", "Diagnostic images", "Centering JSON"],
    };
  }
  if (label.includes("Local AI") || label.includes("Front elemzés") || label.includes("Back elemzés") || label.includes("review")) {
    return {
      title: "Local AI elemzés fut...",
      subtitle: "A lokális modell elemzi a kártyaképeket. Ez eltarthat pár percig.",
      steps: ["front_resized/back_resized kiválasztása", "Lokális modell futtatása", "JSON eredmény mentése"],
    };
  }
  if (label.includes("OpenCV") || label === "Elemzés fut...") {
    return {
      title: "OpenCV elemzés fut...",
      subtitle: "Képek előkészítése és minőségi metrikák számítása.",
      steps: ["Front/back képek beolvasása", "Resized assetek frissítése", "Report előkészítése"],
    };
  }
  if (label.includes("Report") || label.includes("Score") || label.includes("Annot")) {
    return {
      title: "Report generálása...",
      subtitle: "Pontszámok, annotációk és ajánlás frissítése.",
      steps: ["Findingok rendezése", "Score számítása", "Report újratöltése"],
    };
  }
  if (label.includes("Centering")) {
    return {
      title: "Centering mentése...",
      subtitle: "A manuális centering mérés mentése és a pontszámok frissítése.",
    };
  }
  if (label.includes("feltölt")) {
    return {
      title: "Kép feltöltése...",
      subtitle: "A lokális media tár frissítése és az előnézet újratöltése.",
    };
  }
  if (label.includes("szerkeszt") || label.includes("crop")) {
    return {
      title: "Kép szerkesztése...",
      subtitle: "A módosított kép új, lokális derived media assetként mentődik.",
    };
  }
  return {
    title: label,
    subtitle: "Lokális művelet folyamatban.",
  };
}

export function CardDetailPage({ ownedCardId, debugMode, onDeleted }: CardDetailPageProps) {
  const [ownedCard, setOwnedCard] = useState<OwnedCard | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [media, setMedia] = useState<CardMedia[]>([]);
  const [latestPrice, setLatestPrice] = useState<PriceHistoryEntry | null>(null);
  const [latestMarketPrice, setLatestMarketPrice] = useState<PriceHistoryEntry | null>(null);
  const [latestManualOwnedPrice, setLatestManualOwnedPrice] = useState<PriceHistoryEntry | null>(null);
  const [priceHistory, setPriceHistory] = useState<PriceHistoryEntry[]>([]);
  const [lastPriceFetchResult, setLastPriceFetchResult] = useState<PriceFetchResponse | null>(null);
  const [historyFilter, setHistoryFilter] = useState("all");
  const [priceProviders, setPriceProviders] = useState<PriceProviderStatus[]>([]);
  const [selectedPriceSource, setSelectedPriceSource] = useState("auto");
  const [latestCentering, setLatestCentering] = useState<CenteringMeasurement | null>(null);
  const [centeringMeasurements, setCenteringMeasurements] = useState<CenteringMeasurement[]>([]);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [opencvAssets, setOpenCvAssets] = useState<AnalysisAsset[]>([]);
  const [findings, setFindings] = useState<AnalysisFinding[]>([]);
  const [localAI, setLocalAI] = useState<LocalAIStatus | null>(null);
  const [localAIDryRun, setLocalAIDryRun] = useState<LocalAIDryRun | null>(null);
  const [localAIDebug, setLocalAIDebug] = useState<LocalAIDebugSingleImageResponse | null>(null);
  const [remoteAIGrade, setRemoteAIGrade] = useState<RemoteAIGradeResponse | null>(null);
  const [processedImages, setProcessedImages] = useState<ProcessedImagesResponse | null>(null);
  const [gradingPipeline, setGradingPipeline] = useState<AIGradingPipelineStatus | null>(null);
  const [recognitionResult, setRecognitionResult] = useState<RecognitionResponse | null>(null);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<InlineNoticeState | null>(null);
  const [uploadLabel, setUploadLabel] = useState("front");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [priceForm, setPriceForm] = useState<PriceForm>(emptyPriceForm);
  const [ownedEditForm, setOwnedEditForm] = useState<OwnedEditForm>(editFormFromOwnedCard(null));
  const [previewAsset, setPreviewAsset] = useState<AnalysisAsset | CardMedia | null>(null);
  const [selectedPreviewSide, setSelectedPreviewSide] = useState<"front" | "back">("front");
  const [selectedProcessedSide, setSelectedProcessedSide] = useState<"front" | "back">("front");
  const [selectedProcessedVariant, setSelectedProcessedVariant] = useState("perspective_corrected");
  const [boundaryEditorSide, setBoundaryEditorSide] = useState<"front" | "back" | null>(null);
  const [showCenteringEditor, setShowCenteringEditor] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [aiGradingModalOpen, setAIGradingModalOpen] = useState(false);
  const [aiGradingModalError, setAIGradingModalError] = useState<string | null>(null);
  const [fullscreenImage, setFullscreenImage] = useState<{ src: string; label: string; description?: string } | null>(null);

  const busy = busyLabel !== null;
  const workOverlay = workOverlayForLabel(busyLabel);
  const genericWorkOverlay = busyLabel?.includes("Smart AI") ? null : workOverlay;
  const latestAnalysis = analysisRuns[0] ?? null;
  const visibleFindings = report?.findings?.length ? report.findings : findings;
  const hasAnalysisImage = media.some((item) => item.media_type === "image" && sideFromLabel(item.label) !== null);
  const latestOpenCvAnalysis = analysisRuns.find((run) => run.mode === "local_only" && run.status === "completed") ?? null;
  const confirmedFindings = visibleFindings.filter((finding) => !isPhotoQualityFinding(finding));
  const frontFindings = confirmedFindings.filter((finding) => finding.side === "front");
  const backFindings = confirmedFindings.filter((finding) => finding.side === "back");
  const otherConfirmedFindings = confirmedFindings.filter((finding) => finding.side !== "front" && finding.side !== "back");
  const uncertainFindings = visibleFindings.filter(isPhotoQualityFinding);
  const localAIBlockedReason = !latestOpenCvAnalysis
    ? "Előbb futtasd az OpenCV elemzést."
    : !localAI?.enabled
      ? "Local AI nincs bekapcsolva."
      : localAI.mode === "server_local" && !localAI.model_name
        ? "LOCAL_AI_MODEL_NAME nincs beállítva."
        : !localAI.reachable
          ? localAI.mode === "server_local" ? "LM Studio nem érhető el." : "Local AI worker nem érhető el."
          : null;
  const priceChartData = useMemo(
    () =>
      priceHistory
        .filter((item) => !item.error_code)
        .filter((item) => priceHistoryMatchesFilter(item, historyFilter))
        .map((item) => ({
          fetched_at: item.fetched_at,
          raw_market_huf: priceValueHuf(item, "market") ?? priceValueHuf(item, "raw"),
          psa_10_huf: priceValueHuf(item, "psa_10"),
        })),
    [historyFilter, priceHistory],
  );
  const selectablePriceProviders = useMemo(
    () => priceProviders.filter((provider) => ["poketrace", "tcgdex", "pokemontcg", "local_json"].includes(provider.provider)),
    [priceProviders],
  );
  const poketraceStatus = priceProviders.find((provider) => provider.provider === "poketrace") ?? null;

  const setScopedSuccess = (scope: NoticeScope, text: string) => setNotice({ scope, tone: "success", text });
  const setScopedError = (scope: NoticeScope, text: string) => setNotice({ scope, tone: "error", text });

  const loadReport = useCallback(async (analysisRunId: number | null) => {
    if (!analysisRunId) {
      setReport(null);
      setFindings([]);
      return;
    }
    try {
      const nextReport = await api.getAnalysisReport(analysisRunId);
      setReport(nextReport);
      setFindings(nextReport.findings ?? []);
    } catch {
      setReport(null);
      setFindings([]);
    }
  }, []);

  const load = useCallback(async (showPageLoading = true) => {
    if (showPageLoading) setLoading(true);
    try {
      setRemoteAIGrade(null);
      setRecognitionResult(null);
      const owned = await api.getOwnedCard(ownedCardId);
      setOwnedCard(owned);
      setOwnedEditForm(editFormFromOwnedCard(owned));
      const [cardData, mediaData, runsData] = await Promise.all([
        api.getCard(owned.card_id),
        api.getOwnedCardMedia(ownedCardId),
        api.getAnalysisRuns(ownedCardId),
      ]);
      setCard(cardData);
      setMedia(newestFirst(mediaData));
      setAnalysisRuns(runsData);

      try {
        const [price, market, history] = await Promise.all([
          api.getLatestOwnedCardPriceHistory(ownedCardId),
          api.getOwnedCardMarketLatest(ownedCardId),
          api.getPriceHistory(owned.card_id),
        ]);
        let latestAny = price.latest_any ?? price.latest ?? history.latest ?? null;
        let latestManualOwned = price.latest_manual_owned ?? market.latest_manual_owned ?? null;
        let latestMarket = market.latest_market ?? price.latest_market ?? null;
        let historyItems = history.history;
        if (!latestAny && !latestMarket && !latestManualOwned) {
          const legacyPrice = await api.getLatestOwnedCardPrice(ownedCardId);
          if (legacyPrice) {
            const legacyHistory = legacyPriceToHistory(legacyPrice, ownedCardId);
            latestAny = legacyHistory;
            latestManualOwned = legacyHistory;
            historyItems = [legacyHistory];
          }
        }
        setLatestPrice(latestAny);
        setLatestMarketPrice(latestMarket);
        setLatestManualOwnedPrice(latestManualOwned);
        setPriceHistory(historyItems);
        setPriceForm(formFromPrice(latestManualOwned ?? (isMarketPrice(latestAny) ? null : latestAny)));
      } catch {
        setLatestPrice(null);
        setLatestMarketPrice(null);
        setLatestManualOwnedPrice(null);
        setPriceHistory([]);
        setPriceForm(emptyPriceForm);
      }
      try {
        const providerStatus = await api.getPriceProviderStatus();
        setPriceProviders(providerStatus.providers);
      } catch {
        setPriceProviders([]);
      }

      await loadReport(runsData[0]?.id ?? null);
      const latestOpenCvRun = runsData.find((run) => run.mode === "local_only" && run.status === "completed");
      if (latestOpenCvRun) {
        try {
          const detail = await api.getAnalysisRunDetail(latestOpenCvRun.id);
          setOpenCvAssets(detail.assets);
        } catch {
          setOpenCvAssets([]);
        }
      } else {
        setOpenCvAssets([]);
      }
      try {
        const processed = await api.getProcessedImages(ownedCardId);
        setProcessedImages(processed);
        const status = await api.getAIGradingStatus(ownedCardId);
        setGradingPipeline(status);
      } catch {
        setProcessedImages(null);
        setGradingPipeline(null);
      }
      try {
        setLatestCentering(await api.getLatestCentering(ownedCardId));
        setCenteringMeasurements(await api.getCenteringMeasurements(ownedCardId));
      } catch {
        setLatestCentering(null);
        setCenteringMeasurements([]);
      }
      try {
        setLocalAI(await api.getLocalAIStatus());
      } catch {
        setLocalAI(null);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    } finally {
      if (showPageLoading) setLoading(false);
    }
  }, [loadReport, ownedCardId]);

  useEffect(() => {
    load();
  }, [load]);

  const imageMedia = useMemo(() => newestFirst(media.filter((item) => item.media_type === "image")), [media]);
  const latestFrontImage = useMemo(() => imageMedia.find((item) => sideFromLabel(item.label) === "front") ?? null, [imageMedia]);
  const latestBackImage = useMemo(() => imageMedia.find((item) => sideFromLabel(item.label) === "back") ?? null, [imageMedia]);
  const latestUploadedImage = imageMedia[0] ?? null;
  const previewImage = selectedPreviewSide === "front"
    ? latestFrontImage ?? latestBackImage ?? latestUploadedImage
    : latestBackImage ?? latestFrontImage ?? latestUploadedImage;
  const processedSides = processedImages?.sides ?? {};
  const selectedProcessed = processedSides[selectedProcessedSide] ?? processedSides.front ?? processedSides.back ?? null;
  const processedVariantPath = selectedProcessed?.generated_images?.[selectedProcessedVariant]
    ?? selectedProcessed?.generated_images?.perspective_corrected
    ?? selectedProcessed?.generated_images?.original_normalized
    ?? null;

  useEffect(() => {
    if (selectedPreviewSide === "front" && !latestFrontImage && latestBackImage) {
      setSelectedPreviewSide("back");
    }
    if (selectedPreviewSide === "back" && !latestBackImage && latestFrontImage) {
      setSelectedPreviewSide("front");
    }
  }, [latestBackImage, latestFrontImage, selectedPreviewSide]);

  useEffect(() => {
    if (selectedProcessedSide === "front" && !processedSides.front && processedSides.back) {
      setSelectedProcessedSide("back");
    }
    if (selectedProcessedSide === "back" && !processedSides.back && processedSides.front) {
      setSelectedProcessedSide("front");
    }
  if (selectedProcessed && !selectedProcessed.generated_images[selectedProcessedVariant]) {
      setSelectedProcessedVariant(selectedProcessed.generated_images.perspective_corrected ? "perspective_corrected" : "original_normalized");
    }
  }, [processedSides.back, processedSides.front, selectedProcessed, selectedProcessedSide, selectedProcessedVariant]);

  const groupedAssets = useMemo(() => {
    const assets = report?.assets ?? [];
    const uncertainFindingIds = new Set(visibleFindings.filter(isPhotoQualityFinding).map((finding) => finding.id));
    return {
      resized: assets.filter((asset) => asset.asset_type === "resized_image"),
      annotated: assets.filter((asset) => {
        if (asset.asset_type !== "annotated_image") return false;
        const findingId = annotatedFindingId(asset);
        return findingId === null || !uncertainFindingIds.has(findingId);
      }),
      debug: assets.filter(isDebugAsset),
    };
  }, [report, visibleFindings]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!uploadFile) return;
    setBusyLabel("Kép feltöltése...");
    setNotice(null);
    try {
      await api.uploadMedia(ownedCardId, uploadLabel, uploadFile);
      setUploadFile(null);
      await load(false);
      if (uploadLabel === "front" || uploadLabel === "back") setSelectedPreviewSide(uploadLabel);
      setScopedSuccess("media", "Kép feltöltve.");
    } catch (err) {
      setScopedError("media", err instanceof Error ? err.message : "Feltöltési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const saveDerivedMedia = async (sourceMediaId: number, payload: Parameters<typeof api.createDerivedMedia>[1]) => {
    setBusyLabel(payload.edit_type === "manual_crop" ? "Kép crop mentése..." : "Kép szerkesztés mentése...");
    setNotice(null);
    try {
      const saved = await api.createDerivedMedia(sourceMediaId, payload);
      await load(false);
      const side = sideFromLabel(saved.label);
      if (side) setSelectedPreviewSide(side);
      setScopedSuccess("media", "Szerkesztett kép mentve új derived media assetként.");
    } catch (err) {
      setScopedError("media", err instanceof Error ? err.message : "Kép szerkesztési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const recognizeSelectedImage = async () => {
    if (!previewImage) {
      setScopedError("media", "Nincs felismerhető kép.");
      return;
    }
    setBusyLabel("Kártya felismerése...");
    setNotice(null);
    try {
      const result = await api.recognizeCardFromMedia(previewImage.id);
      setRecognitionResult(result);
      if (result.ok) {
        setScopedSuccess("media", `Felismerés kész. Találatok: ${result.candidates.length}.`);
      } else {
        setScopedError("media", result.message || "Nem sikerült felismerni a kártyát.");
      }
    } catch (err) {
      setScopedError("media", err instanceof Error ? err.message : "Kártya felismerési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const acceptRecognitionCandidate = async (catalogCardId: number) => {
    const attemptId = recognitionResult?.recognition_attempt?.id ?? recognitionResult?.recognition_attempt_id;
    if (!attemptId) return;
    setBusyLabel("Felismerés elfogadása...");
    setNotice(null);
    try {
      const accepted = await api.acceptRecognitionCandidate(attemptId, catalogCardId, ownedCardId, false);
      await load(false);
      setScopedSuccess("details", `Kártya kiválasztva: ${accepted.owned_card.name}.`);
    } catch (err) {
      setScopedError("media", err instanceof Error ? err.message : "Felismerés elfogadási hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const handlePriceSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ownedCard) return;
    setBusyLabel("Ár mentése...");
    setNotice(null);
    try {
      const saved = await api.createManualPrice({
        card_id: ownedCard.card_id,
        owned_card_id: ownedCard.id,
        raw_price: optionalNumber(priceForm.raw_price),
        market_price: optionalNumber(priceForm.market_price),
        psa_7: optionalNumber(priceForm.psa_7),
        psa_8: optionalNumber(priceForm.psa_8),
        psa_9: optionalNumber(priceForm.psa_9),
        psa_10: optionalNumber(priceForm.psa_10),
        currency: priceForm.currency.trim().toUpperCase() || "HUF",
        confidence: priceForm.price_confidence.trim() || "manual",
        condition_hint: priceForm.condition_hint.trim() || null,
        source_url: priceForm.source_url.trim() || null,
      });
      setLatestPrice(saved);
      setLatestManualOwnedPrice(saved);
      if (!latestMarketPrice || latestMarketPrice.price_kind === "manual_fallback") {
        setLatestMarketPrice(saved);
      }
      setPriceHistory((current) => [...current, saved].sort((a, b) => new Date(a.fetched_at).getTime() - new Date(b.fetched_at).getTime()));
      setPriceForm(formFromPrice(saved));
      if (latestAnalysis) await loadReport(latestAnalysis.id);
      setScopedSuccess("price", "Ár mentve.");
    } catch (err) {
      setScopedError("price", err instanceof Error ? err.message : "Ár mentési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const fetchLatestPrice = async () => {
    if (!ownedCard) return;
    setBusyLabel("Ár frissítése...");
    setNotice(null);
    try {
      const result = await api.fetchCardPrices(ownedCard.card_id, {
        owned_card_id: ownedCard.id,
        sources: selectedPriceSource === "auto" ? undefined : [selectedPriceSource],
        force: true,
      });
      setLastPriceFetchResult(result);
      await load(false);
      if (result.ok) {
        setScopedSuccess("price", fetchSuccessMessage(result));
      } else {
        const firstError = result.results.find((item) => item.error);
        setScopedError("price", providerFetchErrorMessage(firstError?.error, result.message || firstError?.message));
      }
    } catch (err) {
      setScopedError("price", err instanceof Error ? err.message : "Árfrissítési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const saveProviderMapping = async (
    provider: string,
    candidate: { id?: string | number | null; name?: string | null; score?: number | null },
  ) => {
    if (!ownedCard || candidate.id === null || candidate.id === undefined || candidate.id === "") return;
    setBusyLabel("Provider mapping mentése...");
    setNotice(null);
    try {
      await api.savePriceProviderMapping({
        card_id: ownedCard.card_id,
        provider,
        source_card_id: String(candidate.id),
        confidence: "manual",
        match_score: candidate.score ?? null,
        notes: candidate.name ? `Manual UI mapping: ${candidate.name}` : "Manual UI mapping",
      });
      setScopedSuccess("price", "Provider mapping mentve. A következő frissítés ezt a találatot használja.");
    } catch (err) {
      setScopedError("price", err instanceof Error ? err.message : "Provider mapping mentési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const saveOwnedCardBasics = async (event: FormEvent) => {
    event.preventDefault();
    if (!ownedCard) return;
    setBusyLabel("Adatok mentese...");
    setNotice(null);
    try {
      const updated = await api.updateOwnedCard(ownedCard.id, {
        copy_label: ownedEditForm.copy_label.trim() || null,
        status: ownedEditForm.status,
        acquired_price_huf: optionalNumber(ownedEditForm.acquired_price_huf),
        acquired_source: ownedEditForm.acquired_source,
        storage_location: ownedEditForm.storage_location.trim() || null,
        personal_notes: ownedEditForm.personal_notes.trim() || null,
      });
      setOwnedCard(updated);
      setOwnedEditForm(editFormFromOwnedCard(updated));
      setScopedSuccess("details", "Adatok mentve.");
      setError(null);
    } catch (err) {
      setScopedError("details", err instanceof Error ? err.message : "Adatmentési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const addCopyOfCurrentCard = async () => {
    if (!ownedCard) return;
    setBusyLabel("Uj peldany letrehozasa...");
    setNotice(null);
    try {
      const copy = await api.createOwnedCard({
        card_id: ownedCard.card_id,
        copy_label: `${card?.name ?? "Card"} uj peldany`,
        status: "raw_owned",
        acquired_source: "unknown",
      });
      setScopedSuccess("details", "Új példány hozzáadva.");
      window.location.hash = `#/owned-cards/${copy.id}`;
    } catch (err) {
      setScopedError("details", err instanceof Error ? err.message : "Új példány létrehozási hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const runAnalysis = async () => {
    if (!hasAnalysisImage) {
      setScopedError("analysis", "Tölts fel legalább egy front vagy back képet az OpenCV elemzéshez.");
      return;
    }
    setBusyLabel("Elemzés fut...");
    setNotice(null);
    try {
      const newRun = await api.runOpenCvAnalysis(ownedCardId);
      setBusyLabel("Report frissítése...");
      await api.scoreAnalysisRun(newRun.id);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(newRun.id);
      setScopedSuccess("analysis", "OpenCV elemzés és score elkészült.");
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Elemzési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const refreshProcessedState = async () => {
    try {
      setProcessedImages(await api.getProcessedImages(ownedCardId));
    } catch {
      setProcessedImages(null);
    }
    try {
      setGradingPipeline(await api.getAIGradingStatus(ownedCardId));
    } catch {
      setGradingPipeline(null);
    }
  };

  const pollAIGradingStatus = async () => {
    try {
      const status = await api.getAIGradingStatus(ownedCardId);
      setGradingPipeline(status);
      return status;
    } catch {
      return null;
    }
  };

  const runSmartPreprocessing = async () => {
    if (!hasAnalysisImage) {
      setScopedError("analysis", "Upload at least one front or back image first.");
      return;
    }
    setBusyLabel("Smart preprocess running...");
    setNotice(null);
    try {
      const result = await api.runSmartPreprocessing(ownedCardId);
      setProcessedImages(result);
      setScopedSuccess("analysis", "OpenCV diagnostic images refreshed.");
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Smart preprocessing failed");
    } finally {
      setBusyLabel(null);
    }
  };

  const startSmartAIGrading = async () => {
    if (localAIBlockedReason) {
      setScopedError("analysis", localAIBlockedReason);
      return;
    }
    setBusyLabel("Smart AI grading running...");
    setAIGradingModalOpen(true);
    setAIGradingModalError(null);
    setNotice(null);
    const timer = window.setInterval(() => {
      void pollAIGradingStatus();
    }, 1200);
    try {
      await pollAIGradingStatus();
      const result = await api.startAIGrading(ownedCardId);
      setGradingPipeline(result.pipeline);
      await refreshProcessedState();
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      if (result.analysis_run?.id) {
        await loadReport(result.analysis_run.id);
      }
      setScopedSuccess("analysis", "Two-phase AI grading completed.");
      setError(null);
      window.setTimeout(() => setAIGradingModalOpen(false), 2200);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Two-phase AI grading failed";
      setAIGradingModalError(message);
      setScopedError("analysis", message);
      await refreshProcessedState();
    } finally {
      window.clearInterval(timer);
      setBusyLabel(null);
    }
  };

  const retrySmartPhaseB = async () => {
    if (localAIBlockedReason) {
      setScopedError("analysis", localAIBlockedReason);
      return;
    }
    setBusyLabel("Smart AI Phase B retry...");
    setAIGradingModalOpen(true);
    setAIGradingModalError(null);
    setNotice(null);
    const timer = window.setInterval(() => {
      void pollAIGradingStatus();
    }, 1200);
    try {
      await pollAIGradingStatus();
      const result = await api.retryAIGradingPhaseB(ownedCardId);
      setGradingPipeline(result.pipeline);
      if (result.pipeline.analysis_run_id) {
        await loadReport(result.pipeline.analysis_run_id);
      }
      setScopedSuccess("analysis", "Phase B retry completed.");
      setError(null);
      window.setTimeout(() => setAIGradingModalOpen(false), 2200);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Phase B retry failed";
      setAIGradingModalError(message);
      setScopedError("analysis", message);
      await refreshProcessedState();
    } finally {
      window.clearInterval(timer);
      setBusyLabel(null);
    }
  };

  const refreshScore = async () => {
    if (!latestAnalysis) return;
    setBusyLabel("Report frissítése...");
    setNotice(null);
    try {
      await api.scoreAnalysisRun(latestAnalysis.id);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(latestAnalysis.id);
      setScopedSuccess("report", "Score/report frissítve.");
      setError(null);
    } catch (err) {
      setScopedError("report", err instanceof Error ? err.message : "Score/report hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const runLocalAI = async () => {
    if (localAIBlockedReason) {
      setScopedError("analysis", localAIBlockedReason);
      return;
    }
    setBusyLabel("Local AI elemzés fut...");
    setNotice(null);
    try {
      if (localAI?.mode === "remote_worker") {
        const remoteResult = await api.runRemoteAIGrade(ownedCardId);
        setRemoteAIGrade(remoteResult);
        const runsData = await api.getAnalysisRuns(ownedCardId);
        setAnalysisRuns(runsData);
        if (remoteResult.analysis_run?.id) {
          await loadReport(remoteResult.analysis_run.id);
        }
        if (!remoteResult.ok) {
          setScopedError("analysis", "Remote AI worker hibát adott vissza. Nézd meg a részleteket a panelben.");
        } else {
          setScopedSuccess("analysis", `Remote AI grading elkészült. Küldött képek: ${remoteResult.images_sent ?? "-"}.`);
        }
        setError(null);
        return;
      }
      const aiResult = await api.runLocalAIFullReview(ownedCardId);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(aiResult.aggregate.analysis_run.id);
      setScopedSuccess("analysis", `Local AI elemzés elkészült. Findingok: ${aiResult.aggregate.finding_count}.`);
      setError(null);
    } catch (err) {
      const detail = err instanceof Error ? err.message : "Local AI elemzési hiba";
      if (detail.includes("reasoning-only")) {
        setScopedError("analysis", "A lokális Qwen modell csak reasoning tartalmat adott vissza végleges JSON nélkül. Kapcsold ki a thinking módot (/no_think), vagy növeld a max token értéket.");
      } else if (detail.includes("JSON")) {
        setScopedError("analysis", "A lokális modell válasza nem volt feldolgozható JSON. A debug fájlok a media/reports mappában találhatók.");
      } else {
        setScopedError("analysis", detail);
      }
    } finally {
      setBusyLabel(null);
    }
  };

  const runLocalAIPass = async (passType: "front" | "back") => {
    if (localAIBlockedReason) {
      setScopedError("analysis", localAIBlockedReason);
      return;
    }
    setBusyLabel(passType === "front" ? "Front elemzés fut..." : "Back elemzés fut...");
    setNotice(null);
    try {
      const result = passType === "front"
        ? await api.runLocalAIFrontAnalysis(ownedCardId)
        : await api.runLocalAIBackAnalysis(ownedCardId);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(result.analysis_run.id);
      setScopedSuccess("analysis", `${passType === "front" ? "Front" : "Back"} elemzés elkészült. Findingok: ${result.finding_count}.`);
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Local AI pass hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const runLocalAIFullReview = async () => {
    if (localAIBlockedReason) {
      setScopedError("analysis", localAIBlockedReason);
      return;
    }
    setBusyLabel("Teljes local AI review fut...");
    setNotice(null);
    try {
      const result = await api.runLocalAIFullReview(ownedCardId);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(result.aggregate.analysis_run.id);
      setScopedSuccess("analysis", `Teljes local AI review elkészült. Findingok: ${result.aggregate.finding_count}.`);
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Teljes local AI review hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const runLocalAIDryRun = async () => {
    if (!latestOpenCvAnalysis) {
      setScopedError("analysis", "Előbb futtasd az OpenCV elemzést.");
      return;
    }
    setBusyLabel("Local AI dry-run...");
    setNotice(null);
    try {
      const result = await api.runLocalAIDryRun(ownedCardId);
      setLocalAIDryRun(result);
      setScopedSuccess("analysis", `Dry-run kész. Küldeni tervezett képek: ${result.images_would_send}.`);
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Local AI dry-run hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const runLocalAIDebugSingleImage = async () => {
    if (localAIBlockedReason) {
      setScopedError("analysis", localAIBlockedReason);
      return;
    }
    setBusyLabel("Local AI single-image debug...");
    setNotice(null);
    try {
      const imageLabel = selectedPreviewSide === "back" ? "back_resized" : "front_resized";
      const result = await api.runLocalAIDebugSingleImage(ownedCardId, imageLabel);
      setLocalAIDebug(result);
      setScopedSuccess("analysis", `Single-image debug: ${result.status} (${imageLabel}).`);
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Local AI single-image debug hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const generateAnnotations = async () => {
    if (!latestAnalysis) return;
    setBusyLabel("Annotációk generálása...");
    setNotice(null);
    try {
      const result = await api.annotateAnalysisRun(latestAnalysis.id);
      await loadReport(latestAnalysis.id);
      setScopedSuccess("report", result.message);
      setError(null);
    } catch (err) {
      setScopedError("report", err instanceof Error ? err.message : "Annotációs hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const centeringSources = useMemo(() => {
    const assetSource = (side: "front" | "back") =>
      opencvAssets.find((asset) => asset.label === `${side}_normalized`)
      ?? opencvAssets.find((asset) => asset.label === `${side}_resized`);
    const mediaSource = (side: "front" | "back") =>
      imageMedia.find((item) => sideFromLabel(item.label) === side);
    return {
      front: assetSource("front") ?? mediaSource("front") ?? null,
      back: assetSource("back") ?? mediaSource("back") ?? null,
    };
  }, [imageMedia, opencvAssets]);

  const latestCenteringBySide = useMemo(() => ({
    front: centeringMeasurements.find((measurement) => measurement.side === "front") ?? (latestCentering?.side === "front" ? latestCentering : null),
    back: centeringMeasurements.find((measurement) => measurement.side === "back") ?? (latestCentering?.side === "back" ? latestCentering : null),
  }), [centeringMeasurements, latestCentering]);

  const saveCenteringMeasurement = async (payload: Partial<CenteringMeasurement>) => {
    setBusyLabel("Centering mentése...");
    setNotice(null);
    try {
      const saved = await api.createCenteringMeasurement(ownedCardId, payload);
      setLatestCentering(saved);
      setCenteringMeasurements(await api.getCenteringMeasurements(ownedCardId));
      setShowCenteringEditor(false);
      if (latestAnalysis) {
        await api.scoreAnalysisRun(latestAnalysis.id);
        await loadReport(latestAnalysis.id);
      }
      setScopedSuccess("analysis", "Centering mérés mentve.");
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Centering mentési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const saveManualBoundary = async (side: "front" | "back", corners: number[][]) => {
    setBusyLabel("Smart preprocess boundary save...");
    setNotice(null);
    try {
      await api.saveManualBoundary(ownedCardId, side, corners);
      await refreshProcessedState();
      setBoundaryEditorSide(null);
      setScopedSuccess("analysis", "Manual card boundary saved and centering recalculated.");
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Boundary save failed");
    } finally {
      setBusyLabel(null);
    }
  };

  const recalculateSmartCentering = async (side?: "front" | "back") => {
    setBusyLabel("Smart preprocess centering recalculate...");
    setNotice(null);
    try {
      const result = await api.recalculateSmartCentering(ownedCardId, side);
      setProcessedImages(result);
      setScopedSuccess("analysis", "Centering recalculated from final corners.");
      setError(null);
    } catch (err) {
      setScopedError("analysis", err instanceof Error ? err.message : "Centering recalculation failed");
    } finally {
      setBusyLabel(null);
    }
  };

  const deleteCard = async () => {
    setBusyLabel("Deleting card...");
    try {
      const result = await api.deleteOwnedCard(ownedCardId);
      setNotice({ scope: "details", tone: "success", text: result.message });
      onDeleted();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    } finally {
      setBusyLabel(null);
      setShowDeleteConfirm(false);
    }
  };

  const displayMarketPrice = latestMarketPrice ?? (isMarketPrice(latestPrice) ? latestPrice : null);
  const displayManualPrice = latestManualOwnedPrice ?? (!isMarketPrice(latestPrice) ? latestPrice : null);
  const imageCoverageLabel = latestFrontImage && latestBackImage ? "front + back" : latestFrontImage ? "front only" : latestBackImage ? "back only" : "no images";
  const gradingStepState = [
    { label: "Images", done: Boolean(latestFrontImage || latestBackImage) },
    { label: "Recognition", done: Boolean(card?.name || recognitionResult?.candidates?.length) },
    { label: "Preprocess", done: Boolean(processedImages && Object.keys(processedImages.sides ?? {}).length > 0) },
    { label: "Centering", done: Boolean(latestCentering || latestCenteringBySide.front || latestCenteringBySide.back) },
    { label: "AI grade", done: gradingPipeline?.status === "completed" || Boolean(gradingPipeline?.final_result) },
  ];

  if (loading) return <LoadingState label="Kártya részletek betöltése..." />;
  if (error && !ownedCard) return <EmptyState label={`Nem sikerült betölteni a kártyát: ${error}`} />;
  if (!ownedCard) return <EmptyState label="Owned card nem található." />;

  return (
    <div className="space-y-4">
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

      <section className="glass-surface rounded-2xl p-4 sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={ownedCard.status === "graded_owned" ? "success" : "info"}>{ownedCard.status ?? "raw_owned"}</StatusBadge>
              <StatusBadge tone={latestBackImage ? "success" : "warning"}>{imageCoverageLabel}</StatusBadge>
              {debugMode && <StatusBadge tone="warning">Debug visible</StatusBadge>}
            </div>
            <h2 className="mt-3 truncate text-2xl font-semibold text-slate-50 sm:text-3xl">{card?.name ?? `Card #${ownedCard.card_id}`}</h2>
            <p className="mt-1 text-sm text-slate-400">
              {[card?.set_name, card?.set_code, card?.card_number, card?.rarity, card?.language].filter(Boolean).join(" / ") || "Catalog details are not assigned yet."}
            </p>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:min-w-[360px]">
            <StatCard label="Latest value" value={displayMarketPrice ? sourcePriceDisplay(displayMarketPrice) : "No price"} />
            <StatCard label="AI grade" value={displayGrade(gradingPipeline?.final_result?.estimated_grade ?? report?.estimated_grade_range?.estimated_grade_high)} tone={gradingPipeline?.final_result ? "good" : "default"} />
          </div>
        </div>
        <div className="mt-4 flex flex-wrap justify-end gap-2">
          <button
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-rose-400/35 bg-rose-500/10 px-3 text-sm font-semibold text-rose-100 hover:bg-rose-500/18 disabled:opacity-60"
            disabled={busy}
            onClick={() => setShowDeleteConfirm(true)}
            type="button"
          >
            <Trash2 size={16} />
            Delete Card
          </button>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-5">
          {gradingStepState.map((step) => (
            <div key={step.label} className={`rounded-xl border px-3 py-2 text-xs ${step.done ? "border-emerald-400/30 bg-emerald-400/10 text-emerald-100" : "border-white/10 bg-white/[0.035] text-slate-400"}`}>
              <div className="font-semibold">{step.label}</div>
              <div className="mt-0.5">{step.done ? "Ready" : "Pending"}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[370px_minmax(0,1fr)_430px]">
        <div className="space-y-4">
          <Panel title={card?.name ?? `Card #${ownedCard.card_id}`} subtitle={ownedCard.copy_label ?? "Nincs copy label"}>
            <div className="space-y-3 text-sm text-slate-300">
              <div className="flex justify-between gap-4"><span>Status</span><span>{ownedCard.status ?? "-"}</span></div>
              <div className="flex justify-between gap-4"><span>Bekerülés</span><span>{formatHuf(ownedCard.acquired_price_huf)}</span></div>
              <div className="flex justify-between gap-4"><span>Forrás</span><span>{ownedCard.acquired_source ?? "-"}</span></div>
              <div className="flex justify-between gap-4"><span>Set</span><span>{[card?.set_name, card?.card_number, card?.language].filter(Boolean).join(" · ") || "-"}</span></div>
            </div>
          </Panel>

          <Panel title="Adatok szerkesztése" subtitle="Owned copy alapadatok helyi mentése.">
            <form className="space-y-3" onSubmit={saveOwnedCardBasics}>
              <FieldLabel label="Copy label">
                <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={ownedEditForm.copy_label} onChange={(event) => setOwnedEditForm({ ...ownedEditForm, copy_label: event.target.value })} />
              </FieldLabel>
              <div className="grid grid-cols-2 gap-3">
                <FieldLabel label="Status">
                  <select className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={ownedEditForm.status} onChange={(event) => setOwnedEditForm({ ...ownedEditForm, status: event.target.value })}>
                    {statuses.map((status) => <option key={status}>{status}</option>)}
                  </select>
                </FieldLabel>
                <FieldLabel label="Forrás">
                  <select className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={ownedEditForm.acquired_source} onChange={(event) => setOwnedEditForm({ ...ownedEditForm, acquired_source: event.target.value })}>
                    {sources.map((source) => <option key={source}>{source}</option>)}
                  </select>
                </FieldLabel>
              </div>
              <FieldLabel label="Bekerülési ár">
                <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="numeric" value={ownedEditForm.acquired_price_huf} onChange={(event) => setOwnedEditForm({ ...ownedEditForm, acquired_price_huf: event.target.value })} />
              </FieldLabel>
              <FieldLabel label="Tárolási hely">
                <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={ownedEditForm.storage_location} onChange={(event) => setOwnedEditForm({ ...ownedEditForm, storage_location: event.target.value })} />
              </FieldLabel>
              <FieldLabel label="Személyes megjegyzés">
                <textarea className="min-h-20 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={ownedEditForm.personal_notes} onChange={(event) => setOwnedEditForm({ ...ownedEditForm, personal_notes: event.target.value })} />
              </FieldLabel>
              <div className="grid gap-2 sm:grid-cols-2">
                <button className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60" disabled={busy} type="submit">Mentés</button>
                <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800/50 disabled:opacity-60" disabled={busy} onClick={addCopyOfCurrentCard} type="button">Új példány hozzáadása</button>
              </div>
              <InlineNotice notice={notice} scope="details" />
            </form>
          </Panel>

          <Panel title="Kép preview és feltöltés">
            {(latestFrontImage || latestBackImage) && (
              <div className="mb-3 grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-slate-950/35 p-1">
                <button
                  className={`rounded-md px-3 py-2 text-sm font-medium ${selectedPreviewSide === "front" ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-800/70"} disabled:cursor-not-allowed disabled:opacity-45`}
                  disabled={!latestFrontImage}
                  onClick={() => setSelectedPreviewSide("front")}
                  type="button"
                >
                  Front
                </button>
                <button
                  className={`rounded-md px-3 py-2 text-sm font-medium ${selectedPreviewSide === "back" ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-800/70"} disabled:cursor-not-allowed disabled:opacity-45`}
                  disabled={!latestBackImage}
                  onClick={() => setSelectedPreviewSide("back")}
                  type="button"
                >
                  Back
                </button>
              </div>
            )}
            {previewImage ? (
              <button className="block w-full text-left" onClick={() => setPreviewAsset(previewImage)} type="button">
                <img alt={previewImage.label} className="aspect-[3/4] w-full rounded-xl border border-slate-800 object-cover" src={mediaUrl(previewImage.file_path, cacheKeyFor(previewImage))} />
                <div className="mt-2 flex items-center justify-between gap-3 text-xs text-slate-400">
                  <span>{previewImage.label}</span>
                  <span>{formatDate(previewImage.created_at)}</span>
                </div>
              </button>
            ) : (
              <EmptyState label="Még nincs feltöltött kép." />
            )}
            {latestFrontImage && !latestBackImage && (
              <div className="mt-4 rounded-2xl border border-amber-400/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                Back image is missing. The workflow can continue in front-only mode, but final confidence may be lower.
              </div>
            )}
            {imageMedia.length > 0 && (
              <div className="mt-4">
                <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Uploaded image roles</div>
                <div className="grid grid-cols-2 gap-2">
                  {imageMedia.slice(0, 6).map((item) => {
                    const side = sideFromLabel(item.label);
                    return (
                      <button
                        key={item.id}
                        className="rounded-xl border border-white/10 bg-slate-950/30 p-2 text-left transition hover:border-blue-300/40"
                        onClick={() => {
                          if (side) setSelectedPreviewSide(side);
                          setPreviewAsset(item);
                        }}
                        type="button"
                      >
                        <img className="aspect-[3/4] w-full rounded-lg object-cover" src={mediaUrl(item.file_path, cacheKeyFor(item))} alt={item.label} />
                        <div className="mt-2 flex items-center justify-between gap-2 text-xs">
                          <span className="truncate text-slate-300">{item.label}</span>
                          <StatusBadge tone={side ? "success" : "warning"}>{side ?? "extra"}</StatusBadge>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
            {!hasAnalysisImage && (
              <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                Tölts fel legalább egy front vagy back képet az OpenCV elemzéshez.
              </div>
            )}
            <div className="mt-4 space-y-2">
              <button
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-sm font-medium text-blue-100 hover:bg-blue-500/20 disabled:opacity-50"
                disabled={busy || !previewImage || localAI?.mode !== "remote_worker"}
                onClick={recognizeSelectedImage}
                type="button"
              >
                <Play size={16} /> Kártya felismerése
              </button>
              {localAI?.mode !== "remote_worker" && (
                <div className="text-xs text-slate-500">A felismerés a Windows AI Worker remote_worker módját használja.</div>
              )}
            </div>
            {recognitionResult && (
              <RecognitionPanel result={recognitionResult} busy={busy} onAccept={acceptRecognitionCandidate} />
            )}
            <form className="mt-4 space-y-3" onSubmit={handleUpload}>
              <FieldLabel label="Kép típusa">
                <select className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={uploadLabel} onChange={(event) => setUploadLabel(event.target.value)}>
                  {mediaLabels.map((label) => <option key={label} value={label}>{label}</option>)}
                </select>
              </FieldLabel>
              <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-300" type="file" accept="image/*,video/mp4,video/webm,video/quicktime" onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)} />
              <button className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60" disabled={busy || !uploadFile} type="submit">
                <Upload size={16} /> Kép feltöltése
              </button>
              <InlineNotice notice={notice} scope="media" />
            </form>
          </Panel>

          <ImageEditingPanel
            frontImage={latestFrontImage}
            backImage={latestBackImage}
            selectedSide={selectedPreviewSide}
            busy={busy}
            onSelectSide={setSelectedPreviewSide}
            onSave={saveDerivedMedia}
          />

          <Panel
            title="Ár és értékelés"
            subtitle="Legutóbbi raw/graded árak a backend price_history táblából."
            action={
              <div className="flex flex-wrap items-center gap-2">
                <select
                  className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
                  value={selectedPriceSource}
                  onChange={(event) => setSelectedPriceSource(event.target.value)}
                >
                  <option value="auto">Auto/provider chain</option>
                  {selectablePriceProviders.map((provider) => (
                    <option key={provider.provider} disabled={!provider.enabled || !provider.configured} value={provider.provider}>
                      {priceProviderLabel(provider.provider)}{provider.enabled && provider.configured ? "" : " (missing)"}
                    </option>
                  ))}
                </select>
                <button
                  className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 px-3 py-2 text-sm font-medium text-emerald-100 hover:bg-emerald-500/10 disabled:opacity-60"
                  disabled={busy}
                  onClick={fetchLatestPrice}
                  type="button"
                >
                  <RefreshCw size={16} />
                  Ár frissítése
                </button>
              </div>
            }
          >
            <div className="mb-4 space-y-3">
              <div className="flex flex-wrap gap-2">
                {priceProviders.map((provider) => (
                  <span
                    key={provider.provider}
                    className={
                      provider.enabled && provider.configured
                        ? "rounded-full border border-emerald-500/30 px-2 py-1 text-xs text-emerald-200"
                        : "rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-400"
                    }
                  >
                    {priceProviderLabel(provider.provider)}
                  </span>
                ))}
              </div>
              {poketraceStatus && poketraceStatus.enabled && !poketraceStatus.configured && (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                  PokeTrace API kulcs nincs beállítva. Beállítások → Árforrások.
                </div>
              )}
              {poketraceStatus?.plan === "free" && (
                <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-sm text-slate-400">
                  PokeTrace Free csomagban Cardmarket és graded adat korlátozott lehet.
                </div>
              )}
              <button
                className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800"
                onClick={() => { window.location.hash = "#/settings"; }}
                type="button"
              >
                Árforrások beállítása
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-100">Aktuális piaci ár</h3>
                  {displayMarketPrice && <span className="rounded-full border border-emerald-500/30 px-2 py-0.5 text-xs text-emerald-200">{displayMarketPrice.price_kind ?? "market"}</span>}
                </div>
                {displayMarketPrice ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-2">
                      <PriceValueCard field="raw" label="Raw ár" price={displayMarketPrice} />
                      <PriceValueCard field="market" label="Market ár" price={displayMarketPrice} />
                      <PriceValueCard field="psa_7" label="PSA 7" price={displayMarketPrice} />
                      <PriceValueCard field="psa_8" label="PSA 8" price={displayMarketPrice} />
                      <PriceValueCard field="psa_9" label="PSA 9" price={displayMarketPrice} />
                      <PriceValueCard field="psa_10" label="PSA 10" price={displayMarketPrice} />
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs text-slate-400">
                      <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">Forrás: <span className="text-slate-100">{priceProviderLabel(displayMarketPrice.source)}</span></div>
                      <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">Scope: <span className="text-slate-100">{displayMarketPrice.price_scope ?? "-"}</span></div>
                      <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">Confidence: <span className="text-slate-100">{displayMarketPrice.confidence ?? "-"}</span></div>
                      <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-3">Frissítve: <span className="text-slate-100">{formatDate(displayMarketPrice.fetched_at)}</span></div>
                    </div>
                    {displayMarketPrice.currency !== "HUF" && priceValueHuf(displayMarketPrice, "raw") === null && priceValueHuf(displayMarketPrice, "market") === null && (
                      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                        {displayMarketPrice.currency} ár elérhető, HUF konverzió nincs beállítva.
                      </div>
                    )}
                    {fxMetadata(displayMarketPrice) && (
                      <div className={fxMetadata(displayMarketPrice)?.warning ? "rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100" : "rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-sm text-slate-300"}>
                        FX: {fxMetadata(displayMarketPrice)?.provider || "-"} · {fxMetadata(displayMarketPrice)?.rateDate || "-"} · {fxMetadata(displayMarketPrice)?.source || "-"}
                      </div>
                    )}
                  </div>
                ) : (
                  <EmptyState label="Még nincs piaci ár. Futtasd az árfrissítést vagy adj meg kézi árat." />
                )}
              </div>

              <div className="border-t border-slate-800 pt-4">
                <h3 className="mb-2 text-sm font-semibold text-slate-100">Saját / manuális ár</h3>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-4">
                    <div className="text-xs uppercase text-slate-500">Beszerzési ár</div>
                    <div className="mt-1 text-lg font-semibold text-slate-50">{formatHuf(ownedCard.acquired_price_huf ?? null)}</div>
                    <div className="mt-1 text-xs text-slate-500">{ownedCard.acquired_source ?? "-"}</div>
                  </div>
                  {displayManualPrice ? (
                    <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-4">
                      <div className="text-xs uppercase text-slate-500">Legutóbbi manuális owned ár</div>
                      <div className="mt-1 text-lg font-semibold text-slate-50">{sourcePriceDisplay(displayManualPrice)}</div>
                      <div className="mt-1 text-xs text-slate-500">{formatDate(displayManualPrice.fetched_at)} · {displayManualPrice.price_kind ?? "manual"}</div>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-4 text-sm text-slate-400">Nincs külön manuális owned ár rögzítve.</div>
                  )}
                </div>
              </div>

              {lastPriceFetchResult && (
                <div className="border-t border-slate-800 pt-4">
                  <h3 className="mb-2 text-sm font-semibold text-slate-100">Provider eredmények</h3>
                  <div className="space-y-2">
                    {lastPriceFetchResult.results.map((result) => (
                      <div key={`${result.source}-${result.price_history_id ?? result.error ?? "result"}`} className="rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-medium text-slate-100">{priceProviderLabel(result.source)}</span>
                          <span className={result.ok ? "text-emerald-200" : "text-amber-200"}>{result.ok ? `sikeres · ${formatSourceCurrency(result.market_price ?? result.raw_price ?? null, result.currency)}` : providerFetchErrorMessage(result.error, result.message)}</span>
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {result.match_score !== null && result.match_score !== undefined ? `match_score ${formatNumber(result.match_score, 2)}` : "match_score -"}
                          {result.skipped ? " · cache/skip" : ""}
                          {result.rate_limit_remaining !== null && result.rate_limit_remaining !== undefined ? ` · remaining ${result.rate_limit_remaining}` : ""}
                        </div>
                        {result.candidate_alternatives && result.candidate_alternatives.length > 0 && (
                          <div className="mt-3 space-y-1.5">
                            {result.candidate_alternatives.map((candidate) => (
                              <div key={`${result.source}-${candidate.id ?? candidate.name}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-950/40 px-3 py-2 text-xs text-slate-300">
                                <span>{candidate.name ?? candidate.id ?? "-"} {candidate.number ? `#${candidate.number}` : ""} · {candidate.score ?? "-"}%</span>
                                <button className="rounded-lg border border-blue-500/40 px-2 py-1 text-blue-100 hover:bg-blue-500/10 disabled:opacity-60" disabled={busy || !candidate.id} onClick={() => saveProviderMapping(result.source, candidate)} type="button">
                                  Ezt használd ehhez a kártyához
                                </button>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <InlineNotice notice={notice} scope="price" />
          </Panel>

          <Panel title="Ártörténet" subtitle="Raw/market és PSA 10 trend a mentett price_history alapján.">
            <div className="mb-3 flex flex-wrap items-center gap-2 text-sm">
              <span className="text-slate-400">Szűrő:</span>
              <select
                className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100"
                value={historyFilter}
                onChange={(event) => setHistoryFilter(event.target.value)}
              >
                <option value="all">All</option>
                <option value="market">Market only</option>
                <option value="manual">Manual only</option>
                <option value="poketrace">PokeTrace</option>
                <option value="tcgdex">TCGdex</option>
                <option value="pokemontcg">Pokemon TCG API</option>
              </select>
            </div>
            {priceChartData.length === 0 ? (
              <EmptyState label="Még nincs ártörténet." />
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={priceChartData}>
                    <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                    <XAxis dataKey="fetched_at" tickFormatter={formatDate} stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} />
                    <Tooltip
                      contentStyle={{ background: "#111722", border: "1px solid #334155", borderRadius: 8 }}
                      formatter={(value) => formatHuf(Number(value))}
                      labelFormatter={(value) => formatDate(String(value))}
                    />
                    <Line dataKey="raw_market_huf" name="Raw/market" stroke="#60a5fa" strokeWidth={2} type="monotone" connectNulls />
                    <Line dataKey="psa_10_huf" name="PSA 10" stroke="#34d399" strokeWidth={2} type="monotone" connectNulls />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Panel>

          <Panel title="Manuális ár hozzáadása">
            <form className="space-y-3" onSubmit={handlePriceSubmit}>
              <div className="grid grid-cols-2 gap-3">
                <FieldLabel label="Raw ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 8000" value={priceForm.raw_price} onChange={(event) => setPriceForm({ ...priceForm, raw_price: event.target.value })} /></FieldLabel>
                <FieldLabel label="Market ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 9000" value={priceForm.market_price} onChange={(event) => setPriceForm({ ...priceForm, market_price: event.target.value })} /></FieldLabel>
                <FieldLabel label="PSA 7 ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 14000" value={priceForm.psa_7} onChange={(event) => setPriceForm({ ...priceForm, psa_7: event.target.value })} /></FieldLabel>
                <FieldLabel label="PSA 8 ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 18000" value={priceForm.psa_8} onChange={(event) => setPriceForm({ ...priceForm, psa_8: event.target.value })} /></FieldLabel>
                <FieldLabel label="PSA 9 ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 28000" value={priceForm.psa_9} onChange={(event) => setPriceForm({ ...priceForm, psa_9: event.target.value })} /></FieldLabel>
                <FieldLabel label="PSA 10 ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 65000" value={priceForm.psa_10} onChange={(event) => setPriceForm({ ...priceForm, psa_10: event.target.value })} /></FieldLabel>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <FieldLabel label="Pénznem"><select className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={priceForm.currency} onChange={(event) => setPriceForm({ ...priceForm, currency: event.target.value })}><option>HUF</option><option>EUR</option><option>USD</option></select></FieldLabel>
                <FieldLabel label="Confidence"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" placeholder="manual / medium / high" value={priceForm.price_confidence} onChange={(event) => setPriceForm({ ...priceForm, price_confidence: event.target.value })} /></FieldLabel>
              </div>
              <FieldLabel label="Condition hint"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" placeholder="pl. raw near mint" value={priceForm.condition_hint} onChange={(event) => setPriceForm({ ...priceForm, condition_hint: event.target.value })} /></FieldLabel>
              <FieldLabel label="Source URL"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" placeholder="opcionális" value={priceForm.source_url} onChange={(event) => setPriceForm({ ...priceForm, source_url: event.target.value })} /></FieldLabel>
              <button className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy} type="submit">Manuális ár hozzáadása</button>
              <InlineNotice notice={notice} scope="price" />
            </form>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Képi elemzés" subtitle="OpenCV előfeldolgozás és Local AI elemzés server-local vagy később remote worker módban.">
            <div className="grid gap-3 md:grid-cols-3">
              <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60" disabled={busy} onClick={runAnalysis} type="button">
                <Play size={16} /> {busyLabel === "Elemzés fut..." ? "Elemzés fut..." : "OpenCV elemzés indítása"}
              </button>
              <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm font-medium text-blue-100 hover:bg-blue-500/10 disabled:opacity-50" disabled={busy || !hasAnalysisImage} onClick={runSmartPreprocessing} type="button">
                <RefreshCw size={16} /> Preprocess
              </button>
              <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50" disabled={busy || Boolean(localAIBlockedReason)} onClick={startSmartAIGrading} type="button">
                <Play size={16} /> Start AI Grading
              </button>
              {debugMode && <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50" disabled={busy || Boolean(localAIBlockedReason)} onClick={runLocalAI} type="button">
                <Play size={16} /> Local AI elemzés
              </button>}
              <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-cyan-500/40 px-3 py-2 text-sm font-medium text-cyan-100 hover:bg-cyan-500/10 disabled:opacity-50" disabled={busy || (!centeringSources.front && !centeringSources.back)} onClick={() => setShowCenteringEditor(true)} type="button">
                Centering beállítása
              </button>
            </div>
            {localAIBlockedReason && <p className="mt-3 text-sm text-amber-200">{localAIBlockedReason}</p>}
            {!localAIBlockedReason && !localAI?.enabled && <p className="mt-3 text-sm text-amber-200">Local AI nincs bekapcsolva. Állítsd be az LM Studio/Ollama lokális szervert.</p>}
            {!localAIBlockedReason && localAI?.enabled && !localAI.reachable && <p className="mt-3 text-sm text-amber-200">{localAI.message}</p>}
            {latestAnalysis && (
              <div className="mt-4 grid grid-cols-2 gap-2">
                <StatCard label="Status" value={latestAnalysis.status ?? "-"} />
                <StatCard label="Centering" value={formatNumber(latestAnalysis.centering_score)} />
                <StatCard label="Confidence" value={latestAnalysis.confidence_level ?? "-"} />
                <StatCard label="Version" value={latestAnalysis.analysis_version ?? "-"} />
              </div>
            )}
            <InlineNotice notice={notice} scope="analysis" />
            <SmartGradePanel pipeline={gradingPipeline} debugMode={debugMode} onRetryPhaseB={retrySmartPhaseB} />
            {debugMode && remoteAIGrade && <RemoteAIGradePanel response={remoteAIGrade} />}
            <details className="mt-4 rounded-lg border border-slate-800 bg-slate-950/25 p-3" open={Boolean(processedImages && Object.keys(processedImages.sides).length)}>
              <summary className="cursor-pointer text-sm font-medium text-slate-300">Processed image viewer</summary>
              <ProcessedDiagnosticsPanel
                processed={processedImages}
                selectedSide={selectedProcessedSide}
                selectedVariant={selectedProcessedVariant}
                onSelectSide={setSelectedProcessedSide}
                onSelectVariant={setSelectedProcessedVariant}
                onOpenBoundary={(side) => setBoundaryEditorSide(side)}
                onRecalculate={recalculateSmartCentering}
                debugMode={debugMode}
                centeringMeasurements={centeringMeasurements}
                onOpenImage={(src, label, description) => setFullscreenImage({ src, label, description })}
              />
            </details>
            {debugMode && <details className="mt-4 rounded-lg border border-slate-800 bg-slate-950/25 p-3">
              <summary className="cursor-pointer text-sm font-medium text-slate-300">Fejlesztői / Debug eszközök</summary>
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm font-medium text-blue-200 hover:bg-blue-500/10 disabled:opacity-50" disabled={busy || Boolean(localAIBlockedReason)} onClick={() => runLocalAIPass("front")} type="button">
                  Front elemzés
                </button>
                <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm font-medium text-blue-200 hover:bg-blue-500/10 disabled:opacity-50" disabled={busy || Boolean(localAIBlockedReason)} onClick={() => runLocalAIPass("back")} type="button">
                  Back elemzés
                </button>
                <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-emerald-500/40 px-3 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-50" disabled={busy || Boolean(localAIBlockedReason)} onClick={runLocalAIFullReview} type="button">
                  Teljes local AI review
                </button>
                <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-600 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800/50 disabled:opacity-50" disabled={busy || !latestOpenCvAnalysis} onClick={runLocalAIDryRun} type="button">
                  Local AI dry-run
                </button>
                <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-amber-500/40 px-3 py-2 text-sm font-medium text-amber-200 hover:bg-amber-500/10 disabled:opacity-50 md:col-span-2" disabled={busy || Boolean(localAIBlockedReason)} onClick={runLocalAIDebugSingleImage} type="button">
                  Local AI single-image debug
                </button>
              </div>
            {localAIDryRun && (
              <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-sm text-slate-300">
                <div className="font-medium text-slate-100">Local AI dry-run</div>
                <div className="mt-1">Images: {localAIDryRun.images_would_send}</div>
                <div className="mt-1">Max images: {localAIDryRun.max_images} · Max tokens: {localAIDryRun.max_tokens}</div>
                <div className="mt-1">Model: {localAIDryRun.model_name}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {localAIDryRun.image_labels_would_send.map((label) => (
                    <span key={label} className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-300">{label}</span>
                  ))}
                </div>
                <div className="mt-3">
                  <ImagePayloadDebug payload={localAIDryRun.image_payload_would_send} />
                </div>
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-slate-500">Prompt preview</summary>
                  <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap rounded bg-slate-950 p-3 text-xs text-slate-300">{localAIDryRun.prompt_preview}</pre>
                </details>
              </div>
            )}
            {localAIDebug && (
              <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                <div className="font-medium">Local AI single-image debug: {localAIDebug.status}</div>
                <div className="mt-1">Model: {localAIDebug.model}</div>
                <div className="mt-1">Image: {localAIDebug.image_label_sent ?? "-"}</div>
                <div className="mt-3">
                  <ImagePayloadDebug payload={localAIDebug.image_payload} />
                </div>
                <div className="mt-1">Finish reason: {localAIDebug.finish_reason ?? "-"}</div>
                <div className="mt-1">Reasoning content: {localAIDebug.reasoning_content_present ? "igen" : "nem"}</div>
                <div className={localAIDebug.parsed_json_success ? "mt-1 text-emerald-200" : "mt-1 text-rose-200"}>
                  Parsed JSON: {localAIDebug.parsed_json_success ? "sikeres" : "sikertelen"}
                </div>
                {localAIDebug.error_message && <div className="mt-1 text-rose-200">{localAIDebug.error_message}</div>}
                <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded bg-slate-950/70 p-3 text-xs text-slate-200">{localAIDebug.content}</pre>
                {localAIDebug.reasoning_content_preview && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-amber-200">Reasoning preview</summary>
                    <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-950/70 p-3 text-xs text-slate-200">{localAIDebug.reasoning_content_preview}</pre>
                  </details>
                )}
                {localAIDebug.parsed_json_success && (
                  <details className="mt-3">
                    <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wide text-emerald-200">Parsed JSON</summary>
                    <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-950/70 p-3 text-xs text-slate-200">{JSON.stringify(localAIDebug.parsed_json, null, 2)}</pre>
                  </details>
                )}
              </div>
            )}
            </details>}
          </Panel>

          {debugMode && <Panel title="Analysis run lista">
            {analysisRuns.length === 0 ? (
              <EmptyState label="Még nincs elemzési előzmény." />
            ) : (
              <div className="space-y-2">
                {analysisRuns.slice(0, 6).map((run) => (
                  <div key={run.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/25 px-3 py-2 text-sm">
                    <div>
                      <div className="font-medium text-slate-100">Run #{run.id} - {run.status ?? "-"}</div>
                      <div className="text-xs text-slate-500">{formatDate(run.created_at)} · {run.analysis_version ?? "-"}</div>
                    </div>
                    <div className="text-right text-xs text-slate-400">
                      <div>Overall: {formatNumber(run.overall_score)}</div>
                      <div>{run.confidence_level ?? "-"}</div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>}

          <Panel title="Asset gallery" subtitle="Kattints egy thumbnailre a nagyobb előnézethez.">
            {!report || report.assets.length === 0 ? (
              <EmptyState label="Még nincs megjeleníthető analysis asset." />
            ) : (
              <div className="space-y-5">
                {([
                  ["Annotated", groupedAssets.annotated],
                  ["Resized", groupedAssets.resized],
                ] as const).map(([title, assets]) => (
                  <div key={title}>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
                    {assets.length === 0 ? (
                      <div className="text-xs text-slate-500">Nincs asset ebben a csoportban.</div>
                    ) : (
                      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                        {assets.map((asset) => (
                          <button key={asset.id} className="rounded-lg border border-slate-800 bg-charcoal-900 p-2 text-left transition hover:border-blue-500/50 hover:bg-slate-800/40" onClick={() => setPreviewAsset(asset)} type="button">
                            {asset.asset_type?.startsWith("local_ai") ? (
                              <div className="flex aspect-square w-full items-center justify-center rounded bg-slate-950 p-2 text-center text-xs text-slate-400">debug file</div>
                            ) : (
                              <img className="aspect-square w-full rounded object-cover" src={mediaUrl(asset.file_path, cacheKeyFor(asset))} alt={asset.label ?? "asset"} />
                            )}
                            <div className="mt-2 truncate text-xs text-slate-400">{assetDisplayLabel(asset)}</div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
                {debugMode && <details className="rounded-lg border border-slate-800 bg-slate-950/25 p-3">
                  <summary className="cursor-pointer text-sm font-medium text-slate-300">Fejlesztői / Debug eszközök</summary>
                  <div className="mt-4 space-y-4">
                    <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-sm text-amber-100">
                      Auto crop / debug / unreliable: a régi OpenCV crop assetek csak debug célra látszanak, gradinghez és Local AI-hoz nem használjuk őket.
                    </div>
                    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                      {groupedAssets.debug.map((asset) => (
                        <button key={asset.id} className="rounded-lg border border-slate-800 bg-charcoal-900 p-2 text-left transition hover:border-blue-500/50 hover:bg-slate-800/40" onClick={() => setPreviewAsset(asset)} type="button">
                          {asset.asset_type?.startsWith("local_ai") ? (
                            <div className="flex aspect-square w-full items-center justify-center rounded bg-slate-950 p-2 text-center text-xs text-slate-400">debug file</div>
                          ) : (
                            <img className="aspect-square w-full rounded object-cover opacity-70" src={mediaUrl(asset.file_path, cacheKeyFor(asset))} alt={asset.label ?? "asset"} />
                          )}
                          <div className="mt-2 truncate text-xs text-slate-400">{assetDisplayLabel(asset)}</div>
                        </button>
                      ))}
                    </div>
                  </div>
                </details>}
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Score és report">
            {!latestAnalysis ? (
              <EmptyState label="Még nincs elemzés. Tölts fel legalább egy front vagy back képet, majd indíts OpenCV elemzést." />
            ) : !report ? (
              <EmptyState label="A report még nincs elkészítve. Indíts score/report frissítést." />
            ) : (
              <div className="space-y-4">
                {report.analysis_scope === "partial" && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                    <div className="mb-1 inline-flex rounded-full border border-amber-500/40 px-2 py-0.5 text-xs">Részleges elemzés</div>
                    <div>Csak egy kép vagy hiányos képsor alapján készült, ezért nem teljes grading.</div>
                  </div>
                )}
                {(report.warnings ?? []).length > 0 && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                    {(report.warnings ?? []).map((warning) => <div key={warning}>{aiWarningText(warning)}</div>)}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2">
                  <StatCard label="Overall score" value={displayGrade(report.scores.overall_score)} tone="good" />
                  <StatCard label="Grade range" value={`${displayGrade(report.estimated_grade_range.estimated_grade_low)} - ${displayGrade(report.estimated_grade_range.estimated_grade_high)}`} tone="warn" />
                  <StatCard label="Centering" value={displayGrade(report.scores.centering_score)} />
                  <StatCard label="Corners" value={displayGrade(report.scores.corners_score)} />
                  <StatCard label="Edges" value={displayGrade(report.scores.edges_score)} />
                  <StatCard label="Surface" value={displayGrade(report.scores.surface_score)} />
                </div>
                {(latestCenteringBySide.front || latestCenteringBySide.back || report.latest_centering) && (
                  <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 p-4 text-sm text-cyan-100">
                    <div className="mb-3 font-semibold">Manual centering</div>
                    <div className="grid gap-3">
                      {(["front", "back"] as const).map((measurementSide) => {
                        const measurement = latestCenteringBySide[measurementSide] ?? (report.latest_centering?.side === measurementSide ? report.latest_centering : null);
                        return measurement ? <CenteringMeasurementSummary key={measurementSide} measurement={measurement} /> : null;
                      })}
                    </div>
                  </div>
                )}
                {report.analysis_scope !== "partial" && (
                  <div className="grid grid-cols-2 gap-2">
                    <StatCard label="PSA 10 %" value={formatNumber(report.probabilities.psa_10_probability, 0)} />
                    <StatCard label="PSA 9 %" value={formatNumber(report.probabilities.psa_9_probability, 0)} />
                    <StatCard label="PSA 8 %" value={formatNumber(report.probabilities.psa_8_probability, 0)} />
                    <StatCard label="PSA 7- %" value={formatNumber(report.probabilities.psa_7_or_lower_probability, 0)} />
                  </div>
                )}
                <div className="rounded-lg border border-slate-800 bg-charcoal-900 p-4 text-sm leading-6 text-slate-300">{report.human_summary}</div>
                <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
                  <div className="font-semibold">{report.recommendation ?? "-"}</div>
                  <p className="mt-2 leading-6">{report.recommendation_reason}</p>
                </div>
                {debugMode && <details className="rounded-lg border border-slate-800 bg-slate-950/25 p-3 text-sm text-slate-300">
                  <summary className="cursor-pointer font-medium">AI grading debug</summary>
                  <div className="mt-3 space-y-2 text-xs text-slate-400">
                    <div>Scope: {report.analysis_scope ?? "-"}</div>
                    <div>Images: {(report.image_labels_sent ?? []).join(", ") || "-"}</div>
                    <div>Allowed areas: {(report.allowed_issue_areas ?? []).join(", ") || "-"}</div>
                    <div>Warnings: {(report.warnings ?? []).join(", ") || "-"}</div>
                  </div>
                  <div className="mt-3">
                    <ImagePayloadDebug payload={report.image_payload} />
                  </div>
                </details>}

                <InlineNotice notice={notice} scope="report" />

                {debugMode && <details className="rounded-lg border border-slate-800 bg-slate-950/25 p-3">
                  <summary className="cursor-pointer text-sm font-medium text-slate-300">Fejlesztői / Debug eszközök</summary>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="inline-flex items-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/10 disabled:opacity-60" disabled={busy || !latestAnalysis} onClick={refreshScore} type="button">
                      <RefreshCw size={16} /> Score/report frissítése
                    </button>
                    <button className="inline-flex items-center gap-2 rounded-lg border border-amber-500/40 px-3 py-2 text-sm text-amber-200 hover:bg-amber-500/10 disabled:opacity-60" disabled={busy || !latestAnalysis || visibleFindings.length === 0} onClick={generateAnnotations} type="button">
                      Annotációk generálása
                    </button>
                  </div>
                </details>}

                <FindingSection title="Megerősített hibák - front" findings={frontFindings} />
                <FindingSection title="Megerősített hibák - back" findings={backFindings} />
                <FindingSection title="Megerősített hibák - egyéb" findings={otherConfirmedFindings} />
                <FindingSection title="Bizonytalan / fotóminőségi jelzések" findings={uncertainFindings} />

                {(report.strengths.length > 0 || report.main_grade_limiters.length > 0 || report.manual_review_recommendations.length > 0) && (
                  <div className="grid gap-3">
                    {report.strengths.length > 0 && <ReportList title="Erősségek" items={report.strengths} />}
                    {report.main_grade_limiters.length > 0 && <ReportList title="Fő grade limiterek" items={report.main_grade_limiters} />}
                    {report.manual_review_recommendations.length > 0 && <ReportList title="Manuális review javaslatok" items={report.manual_review_recommendations} />}
                  </div>
                )}

                {report.opportunity_precheck && (
                  <div className="grid grid-cols-2 gap-2">
                    <StatCard label="Opp. raw" value={formatHuf(report.opportunity_precheck.raw_price_huf)} />
                    <StatCard label="Opp. PSA 9" value={formatHuf(report.opportunity_precheck.psa_9_price_huf)} />
                    <StatCard label="Opp. PSA 10" value={formatHuf(report.opportunity_precheck.psa_10_price_huf)} />
                    <StatCard label="Grading cost" value={formatHuf(report.opportunity_precheck.grading_cost_huf)} />
                    <StatCard label="Min. profit grade" value={report.opportunity_precheck.minimum_profitable_grade ?? "-"} />
                    <StatCard label="Opportunity score" value={report.opportunity_precheck.opportunity_score} tone="good" />
                  </div>
                )}
              </div>
            )}
          </Panel>
        </div>
      </div>

      {showCenteringEditor && (
        <CenteringEditor
          sources={centeringSources}
          measurements={centeringMeasurements}
          busy={busy}
          onCancel={() => setShowCenteringEditor(false)}
          onSave={saveCenteringMeasurement}
        />
      )}

      {boundaryEditorSide && processedImages?.sides?.[boundaryEditorSide] && (
        <BoundaryEditor
          side={processedImages.sides[boundaryEditorSide]}
          busy={busy}
          onCancel={() => setBoundaryEditorSide(null)}
          onSave={(corners) => saveManualBoundary(boundaryEditorSide, corners)}
        />
      )}

      <AIGradingModal
        open={aiGradingModalOpen}
        pipeline={gradingPipeline}
        error={aiGradingModalError}
        debugMode={debugMode}
        isRunning={busyLabel?.includes("Smart AI") ?? false}
        onRetry={startSmartAIGrading}
        onClose={() => setAIGradingModalOpen(false)}
      />
      {genericWorkOverlay && <GlobalLoadingOverlay title={genericWorkOverlay.title} subtitle={genericWorkOverlay.subtitle} steps={genericWorkOverlay.steps} />}

      {previewAsset && (
        <FullscreenImageViewer
          src={mediaUrl(previewAsset.file_path, cacheKeyFor(previewAsset))}
          label={previewAsset.label ?? "Preview"}
          onClose={() => setPreviewAsset(null)}
        />
      )}

      {fullscreenImage && (
        <FullscreenImageViewer
          src={fullscreenImage.src}
          label={fullscreenImage.label}
          description={fullscreenImage.description}
          onClose={() => setFullscreenImage(null)}
        />
      )}

      {showDeleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4" onClick={() => setShowDeleteConfirm(false)}>
          <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-slate-950 p-5 shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold text-slate-50">Delete card?</h2>
                <p className="mt-2 text-sm leading-6 text-slate-300">
                  This will remove the owned card record, uploaded images, preprocessing outputs, AI grading results, and associated metadata.
                </p>
              </div>
              <button className="rounded-lg p-2 text-slate-400 hover:bg-white/10 hover:text-slate-100" onClick={() => setShowDeleteConfirm(false)} type="button">
                <X size={18} />
              </button>
            </div>
            <div className="mt-5 grid gap-3 sm:grid-cols-2">
              <button className="min-h-11 rounded-xl border border-white/10 px-4 text-sm font-semibold text-slate-200 hover:bg-white/10" disabled={busy} onClick={() => setShowDeleteConfirm(false)} type="button">
                Cancel
              </button>
              <button className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-rose-500 px-4 text-sm font-semibold text-white hover:bg-rose-400 disabled:opacity-60" disabled={busy} onClick={deleteCard} type="button">
                <Trash2 size={16} />
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function InlineNotice({ notice, scope }: { notice: InlineNoticeState | null; scope: NoticeScope }) {
  if (!notice || notice.scope !== scope) return null;
  const classes = notice.tone === "success"
    ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"
    : "border-rose-500/30 bg-rose-500/10 text-rose-200";
  return <div className={`mt-3 rounded-lg border p-3 text-sm ${classes}`}>{notice.text}</div>;
}

function FullscreenImageViewer({ src, label, description, onClose }: { src: string; label: string; description?: string; onClose: () => void }) {
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [dragStart, setDragStart] = useState<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);
  const clampZoom = (next: number) => Math.max(1, Math.min(4, next));
  const updateZoom = (next: number) => {
    const clamped = clampZoom(next);
    setZoom(clamped);
    if (clamped === 1) setOffset({ x: 0, y: 0 });
  };
  const startDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (zoom <= 1) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragStart({ x: event.clientX, y: event.clientY, offsetX: offset.x, offsetY: offset.y });
  };
  const moveDrag = (event: PointerEvent<HTMLDivElement>) => {
    if (!dragStart || zoom <= 1) return;
    setOffset({
      x: dragStart.offsetX + event.clientX - dragStart.x,
      y: dragStart.offsetY + event.clientY - dragStart.y,
    });
  };
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/88 p-2 backdrop-blur-md sm:p-4" onClick={onClose}>
      <div className="flex h-full w-full max-w-7xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-slate-950/90" onClick={(event) => event.stopPropagation()}>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-3 py-2 sm:px-4">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-slate-100">{label}</div>
            {description && <div className="text-xs text-slate-400">{description}</div>}
          </div>
          <div className="flex items-center gap-2">
            <button className="rounded-lg border border-white/10 p-2 text-slate-200 hover:bg-white/10" onClick={() => updateZoom(zoom - 0.25)} type="button" aria-label="Zoom out"><Minus size={17} /></button>
            <div className="min-w-12 text-center text-xs text-slate-300">{Math.round(zoom * 100)}%</div>
            <button className="rounded-lg border border-white/10 p-2 text-slate-200 hover:bg-white/10" onClick={() => updateZoom(zoom + 0.25)} type="button" aria-label="Zoom in"><Plus size={17} /></button>
            <button className="rounded-lg border border-white/10 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-white/10" onClick={() => { setZoom(1); setOffset({ x: 0, y: 0 }); }} type="button">Reset</button>
            <button className="rounded-lg p-2 text-slate-300 hover:bg-white/10 hover:text-white" onClick={onClose} type="button" aria-label="Close preview"><X size={18} /></button>
          </div>
        </div>
        <div
          className={`flex flex-1 touch-none items-center justify-center overflow-hidden bg-black/35 ${zoom > 1 ? "cursor-grab active:cursor-grabbing" : "cursor-zoom-in"}`}
          onClick={(event) => {
            event.stopPropagation();
            if (zoom === 1) updateZoom(2);
          }}
          onPointerDown={startDrag}
          onPointerMove={moveDrag}
          onPointerUp={() => setDragStart(null)}
          onPointerCancel={() => setDragStart(null)}
        >
          <img
            className="max-h-full max-w-full select-none object-contain transition-transform duration-150"
            src={src}
            alt={label}
            draggable={false}
            style={{ transform: `translate(${offset.x}px, ${offset.y}px) scale(${zoom})` }}
          />
        </div>
      </div>
    </div>
  );
}

function CenteringMeasurementSummary({ measurement }: { measurement: CenteringMeasurement }) {
  const left = measurement.horizontal_left_percent ?? 50;
  const right = measurement.horizontal_right_percent ?? 50;
  const top = measurement.vertical_top_percent ?? 50;
  const bottom = measurement.vertical_bottom_percent ?? 50;
  const shiftX = left > right ? "jobbra tolódik" : right > left ? "balra tolódik" : "középen";
  const shiftY = top > bottom ? "lefelé tolódik" : bottom > top ? "felfelé tolódik" : "középen";
  return (
    <div className="rounded-lg border border-cyan-300/20 bg-slate-950/30 p-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-cyan-200">{measurement.side}</div>
          <div className="mt-1 font-medium text-slate-50">{measurement.estimated_grade_label ?? "-"}</div>
        </div>
        <div className="text-right text-xs text-cyan-100">
          <div>Score {formatNumber(measurement.centering_score)}</div>
          <div>{formatDate(measurement.created_at)}</div>
        </div>
      </div>
      <div className="mt-3 space-y-2">
        <CenteringRatioBar label="L/R" first={left} second={right} />
        <CenteringRatioBar label="T/B" first={top} second={bottom} />
      </div>
      <div className="mt-2 text-xs text-cyan-200">{shiftX} · {shiftY}</div>
    </div>
  );
}

type ImageAdjustments = {
  brightness: number;
  contrast: number;
  saturation: number;
  sharpness: number;
  gamma: number;
  exposure: number;
  rotate_degrees: number;
};

type CropRectPct = {
  x: number;
  y: number;
  width: number;
  height: number;
};

type CropHandle = "move" | "n" | "s" | "e" | "w" | "nw" | "ne" | "sw" | "se";

const defaultAdjustments: ImageAdjustments = {
  brightness: 1,
  contrast: 1,
  saturation: 1,
  sharpness: 1,
  gamma: 1,
  exposure: 0,
  rotate_degrees: 0,
};

const defaultCrop: CropRectPct = { x: 6, y: 5, width: 88, height: 90 };

function clampPct(value: number, min = 0, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function imageFilter(adjustments: ImageAdjustments): string {
  const exposureMultiplier = 2 ** adjustments.exposure;
  const gammaPreview = 1 / Math.sqrt(Math.max(0.2, adjustments.gamma));
  const sharpnessPreview = 1 + (adjustments.sharpness - 1) * 0.08;
  return [
    `brightness(${adjustments.brightness * exposureMultiplier * gammaPreview})`,
    `contrast(${adjustments.contrast * sharpnessPreview})`,
    `saturate(${adjustments.saturation})`,
  ].join(" ");
}

function cropToPixels(crop: CropRectPct, natural: { width: number; height: number }) {
  return {
    crop_x: (crop.x / 100) * natural.width,
    crop_y: (crop.y / 100) * natural.height,
    crop_width: (crop.width / 100) * natural.width,
    crop_height: (crop.height / 100) * natural.height,
  };
}

function AdjustmentSlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="space-y-1.5 text-xs font-medium text-slate-400">
      <div className="flex items-center justify-between gap-3">
        <span>{label}</span>
        <span className="text-slate-500">{formatNumber(value, 2)}</span>
      </div>
      <input
        className="w-full accent-blue-500"
        max={max}
        min={min}
        onChange={(event) => onChange(Number(event.target.value))}
        step={step}
        type="range"
        value={value}
      />
    </label>
  );
}

function ImageEditingPanel({
  frontImage,
  backImage,
  selectedSide,
  busy,
  onSelectSide,
  onSave,
}: {
  frontImage: CardMedia | null;
  backImage: CardMedia | null;
  selectedSide: "front" | "back";
  busy: boolean;
  onSelectSide: (side: "front" | "back") => void;
  onSave: (sourceMediaId: number, payload: Parameters<typeof api.createDerivedMedia>[1]) => Promise<void>;
}) {
  const source = selectedSide === "front" ? frontImage ?? backImage : backImage ?? frontImage;
  const sourceSide = sideFromLabel(source?.label) ?? selectedSide;
  const [adjustments, setAdjustments] = useState<ImageAdjustments>(defaultAdjustments);
  const [crop, setCrop] = useState<CropRectPct>(defaultCrop);
  const [lockAspect, setLockAspect] = useState(false);
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const [drag, setDrag] = useState<{ handle: CropHandle; startX: number; startY: number; start: CropRectPct } | null>(null);
  const editorRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setNatural({ width: 0, height: 0 });
    setCrop(defaultCrop);
    setAdjustments(defaultAdjustments);
  }, [source?.id]);

  const updateAdjustment = (key: keyof ImageAdjustments, value: number) => {
    setAdjustments((current) => ({ ...current, [key]: value }));
  };

  const pointerToPct = (event: PointerEvent<HTMLElement>) => {
    const rect = editorRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: clampPct(((event.clientX - rect.left) / rect.width) * 100),
      y: clampPct(((event.clientY - rect.top) / rect.height) * 100),
    };
  };

  const startCropDrag = (event: PointerEvent<HTMLElement>, handle: CropHandle) => {
    event.preventDefault();
    event.stopPropagation();
    const point = pointerToPct(event);
    setDrag({ handle, startX: point.x, startY: point.y, start: crop });
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const updateCropDrag = (event: PointerEvent<HTMLElement>) => {
    if (!drag) return;
    const point = pointerToPct(event);
    const dx = point.x - drag.startX;
    const dy = point.y - drag.startY;
    const next = { ...drag.start };

    if (drag.handle === "move") {
      next.x = clampPct(drag.start.x + dx, 0, 100 - drag.start.width);
      next.y = clampPct(drag.start.y + dy, 0, 100 - drag.start.height);
    } else {
      const right = drag.start.x + drag.start.width;
      const bottom = drag.start.y + drag.start.height;
      if (drag.handle.includes("w")) {
        next.x = clampPct(drag.start.x + dx, 0, right - 5);
        next.width = right - next.x;
      }
      if (drag.handle.includes("e")) {
        next.width = clampPct(drag.start.width + dx, 5, 100 - drag.start.x);
      }
      if (drag.handle.includes("n")) {
        next.y = clampPct(drag.start.y + dy, 0, bottom - 5);
        next.height = bottom - next.y;
      }
      if (drag.handle.includes("s")) {
        next.height = clampPct(drag.start.height + dy, 5, 100 - drag.start.y);
      }
      if (lockAspect) {
        const aspect = drag.start.width / Math.max(1, drag.start.height);
        if (drag.handle.includes("e") || drag.handle.includes("w")) {
          next.height = clampPct(next.width / aspect, 5, 100 - next.y);
          if (drag.handle.includes("n")) next.y = bottom - next.height;
        } else {
          next.width = clampPct(next.height * aspect, 5, 100 - next.x);
          if (drag.handle.includes("w")) next.x = right - next.width;
        }
      }
    }
    setCrop(next);
  };

  const setPreset = (preset: "full" | "close" | "square") => {
    if (preset === "full") {
      setCrop({ x: 3, y: 3, width: 94, height: 94 });
      return;
    }
    if (preset === "close") {
      setCrop({ x: 12, y: 10, width: 76, height: 80 });
      return;
    }
    const width = natural.width || 1;
    const height = natural.height || 1;
    const sizePx = Math.min(width, height) * 0.86;
    setCrop({
      x: ((width - sizePx) / 2 / width) * 100,
      y: ((height - sizePx) / 2 / height) * 100,
      width: (sizePx / width) * 100,
      height: (sizePx / height) * 100,
    });
  };

  const saveAdjustments = () => {
    if (!source) return;
    onSave(source.id, {
      label: `${sourceSide}_adjusted`,
      edit_type: "manual_adjustment",
      ...adjustments,
      edit_metadata: { source_label: source.label },
    });
  };

  const saveCrop = () => {
    if (!source || natural.width <= 0 || natural.height <= 0) return;
    onSave(source.id, {
      label: `${sourceSide}_crop_manual`,
      edit_type: "manual_crop",
      ...adjustments,
      ...cropToPixels(crop, natural),
      edit_metadata: { source_label: source.label, crop_pct: crop, aspect_ratio_locked: lockAspect },
    });
  };

  return (
    <details className="rounded-xl border border-slate-800 bg-charcoal-850/95 shadow-panel">
      <summary className="cursor-pointer border-b border-slate-800 bg-slate-950/20 px-5 py-4 text-sm font-semibold text-slate-50">
        Kép szerkesztés
      </summary>
      <div className="space-y-4 p-5">
        {!source ? (
          <EmptyState label="Tölts fel front vagy back képet a képszerkesztéshez." />
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-slate-950/35 p-1">
              <button className={`rounded-md px-3 py-2 text-sm font-medium ${selectedSide === "front" ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-800/70"} disabled:opacity-45`} disabled={!frontImage} onClick={() => onSelectSide("front")} type="button">
                Front
              </button>
              <button className={`rounded-md px-3 py-2 text-sm font-medium ${selectedSide === "back" ? "bg-blue-600 text-white" : "text-slate-300 hover:bg-slate-800/70"} disabled:opacity-45`} disabled={!backImage} onClick={() => onSelectSide("back")} type="button">
                Back
              </button>
            </div>

            <div
              ref={editorRef}
              className="relative overflow-hidden rounded-lg border border-slate-800 bg-slate-950"
              onPointerMove={updateCropDrag}
              onPointerUp={() => setDrag(null)}
              onPointerLeave={() => setDrag(null)}
            >
              <img
                alt={source.label}
                className="block aspect-[3/4] w-full object-contain"
                draggable={false}
                onLoad={(event) => setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
                src={mediaUrl(source.file_path, cacheKeyFor(source))}
                style={{
                  filter: imageFilter(adjustments),
                  transform: `rotate(${adjustments.rotate_degrees}deg)`,
                  transition: drag ? "none" : "filter 120ms ease, transform 120ms ease",
                }}
              />
              <div className="absolute inset-0 bg-black/20" />
              <div
                className="absolute border-2 border-emerald-300 bg-emerald-300/10 shadow-[0_0_18px_rgba(110,231,183,0.35)]"
                style={{ left: `${crop.x}%`, top: `${crop.y}%`, width: `${crop.width}%`, height: `${crop.height}%` }}
              >
                <button aria-label="Crop move" className="absolute inset-0 cursor-move" onPointerDown={(event) => startCropDrag(event, "move")} type="button" />
                {(["nw", "ne", "sw", "se", "n", "s", "e", "w"] as CropHandle[]).map((handle) => {
                  const positionClass = {
                    nw: "-left-2 -top-2 cursor-nwse-resize",
                    ne: "-right-2 -top-2 cursor-nesw-resize",
                    sw: "-bottom-2 -left-2 cursor-nesw-resize",
                    se: "-bottom-2 -right-2 cursor-nwse-resize",
                    n: "-top-2 left-1/2 -translate-x-1/2 cursor-ns-resize",
                    s: "-bottom-2 left-1/2 -translate-x-1/2 cursor-ns-resize",
                    e: "-right-2 top-1/2 -translate-y-1/2 cursor-ew-resize",
                    w: "-left-2 top-1/2 -translate-y-1/2 cursor-ew-resize",
                    move: "",
                  }[handle];
                  return (
                    <button
                      key={handle}
                      aria-label={`Crop ${handle}`}
                      className={`absolute h-4 w-4 rounded-full border border-emerald-100 bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.8)] transition hover:scale-125 ${positionClass}`}
                      onPointerDown={(event) => startCropDrag(event, handle)}
                      type="button"
                    />
                  );
                })}
              </div>
            </div>

            <div className="grid gap-3">
              <AdjustmentSlider label="Brightness" min={0.5} max={1.6} step={0.01} value={adjustments.brightness} onChange={(value) => updateAdjustment("brightness", value)} />
              <AdjustmentSlider label="Contrast" min={0.5} max={1.8} step={0.01} value={adjustments.contrast} onChange={(value) => updateAdjustment("contrast", value)} />
              <AdjustmentSlider label="Saturation" min={0} max={1.8} step={0.01} value={adjustments.saturation} onChange={(value) => updateAdjustment("saturation", value)} />
              <AdjustmentSlider label="Sharpness" min={0} max={2.5} step={0.05} value={adjustments.sharpness} onChange={(value) => updateAdjustment("sharpness", value)} />
              <AdjustmentSlider label="Gamma" min={0.5} max={1.8} step={0.01} value={adjustments.gamma} onChange={(value) => updateAdjustment("gamma", value)} />
              <AdjustmentSlider label="Exposure" min={-1.5} max={1.5} step={0.05} value={adjustments.exposure} onChange={(value) => updateAdjustment("exposure", value)} />
              <AdjustmentSlider label="Rotate" min={-180} max={180} step={1} value={adjustments.rotate_degrees} onChange={(value) => updateAdjustment("rotate_degrees", value)} />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <button className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800" onClick={() => setPreset("full")} type="button">Full card</button>
              <button className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800" onClick={() => setPreset("close")} type="button">Close-up</button>
              <button className="rounded-lg border border-slate-700 px-3 py-2 text-xs text-slate-300 hover:bg-slate-800" onClick={() => setPreset("square")} type="button">Square</button>
            </div>
            <label className="flex items-center gap-2 rounded-lg border border-slate-800 bg-slate-950/35 px-3 py-2 text-sm text-slate-300">
              <input checked={lockAspect} className="accent-blue-500" onChange={(event) => setLockAspect(event.target.checked)} type="checkbox" />
              Aspect ratio lock
            </label>

            <div className="grid gap-2 sm:grid-cols-2">
              <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-60" disabled={busy} onClick={() => { setAdjustments(defaultAdjustments); setCrop(defaultCrop); }} type="button">
                <RotateCcw size={16} /> Reset
              </button>
              <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm font-medium text-blue-100 hover:bg-blue-500/10 disabled:opacity-60" disabled={busy} onClick={saveAdjustments} type="button">
                <Save size={16} /> Save adjusted
              </button>
              <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60 sm:col-span-2" disabled={busy || natural.width <= 0} onClick={saveCrop} type="button">
                <Crop size={16} /> Save crop as derived image
              </button>
            </div>
          </>
        )}
      </div>
    </details>
  );
}

function ReportList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-charcoal-900 p-4 text-sm text-slate-300">
      <h3 className="mb-2 font-semibold text-slate-100">{title}</h3>
      <ul className="space-y-1">
        {items.map((item) => <li key={item}>• {item}</li>)}
      </ul>
    </div>
  );
}

function FindingSection({ title, findings }: { title: string; findings: AnalysisFinding[] }) {
  if (findings.length === 0) return null;
  return (
    <div className="rounded-lg border border-slate-800 bg-charcoal-900 p-4">
      <h3 className="text-sm font-semibold text-slate-100">{title}</h3>
      <div className="mt-3 space-y-3">
        {findings.map((finding) => (
          <div key={`${title}-${finding.id}`} className="rounded-lg border border-slate-800 bg-slate-950/25 p-3 text-sm">
            <div className="font-medium text-slate-100">{finding.title ?? "Finding"}</div>
            <div className="mt-2 flex flex-wrap gap-2">
              <FindingBadge>{finding.finding_type ?? "unknown"}</FindingBadge>
              <FindingBadge tone={severityTone(finding.severity)}>{finding.severity ?? "-"}</FindingBadge>
              <FindingBadge>{finding.confirmed === false ? "uncertain" : "confirmed"}</FindingBadge>
              <FindingBadge>confidence {formatNumber(finding.confidence, 2)}</FindingBadge>
              <FindingBadge tone={finding.grade_impact === "high" ? "danger" : "default"}>impact {finding.grade_impact ?? "-"}</FindingBadge>
            </div>
            <p className="mt-2 leading-5 text-slate-300">{finding.description}</p>
            <div className="mt-2 text-xs text-slate-500">{finding.location_label ?? "-"}</div>
            {finding.uncertainty_reason && <div className="mt-2 text-xs text-amber-200">{finding.uncertainty_reason}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

type CenteringSource = AnalysisAsset | CardMedia;
type CenteringLines = {
  outer_left_px: number;
  outer_right_px: number;
  outer_top_px: number;
  outer_bottom_px: number;
  inner_left_px: number;
  inner_right_px: number;
  inner_top_px: number;
  inner_bottom_px: number;
};
type LineKey = keyof CenteringLines;
type PercentLines = Record<LineKey, number>;

function defaultLines(width: number, height: number): CenteringLines {
  return {
    outer_left_px: width * 0.05,
    outer_right_px: width * 0.95,
    outer_top_px: height * 0.04,
    outer_bottom_px: height * 0.96,
    inner_left_px: width * 0.18,
    inner_right_px: width * 0.82,
    inner_top_px: height * 0.16,
    inner_bottom_px: height * 0.84,
  };
}

function linesToPercent(lines: CenteringLines, width: number, height: number): PercentLines {
  return {
    outer_left_px: lines.outer_left_px / Math.max(1, width),
    outer_right_px: lines.outer_right_px / Math.max(1, width),
    outer_top_px: lines.outer_top_px / Math.max(1, height),
    outer_bottom_px: lines.outer_bottom_px / Math.max(1, height),
    inner_left_px: lines.inner_left_px / Math.max(1, width),
    inner_right_px: lines.inner_right_px / Math.max(1, width),
    inner_top_px: lines.inner_top_px / Math.max(1, height),
    inner_bottom_px: lines.inner_bottom_px / Math.max(1, height),
  };
}

function linesFromPercent(percent: PercentLines, width: number, height: number): CenteringLines {
  return {
    outer_left_px: percent.outer_left_px * width,
    outer_right_px: percent.outer_right_px * width,
    outer_top_px: percent.outer_top_px * height,
    outer_bottom_px: percent.outer_bottom_px * height,
    inner_left_px: percent.inner_left_px * width,
    inner_right_px: percent.inner_right_px * width,
    inner_top_px: percent.inner_top_px * height,
    inner_bottom_px: percent.inner_bottom_px * height,
  };
}

function percentFromMeasurement(measurement: CenteringMeasurement): PercentLines {
  return {
    outer_left_px: (measurement.outer_left_pct ?? (measurement.outer_left_px / Math.max(1, measurement.image_width))) / (measurement.outer_left_pct ? 100 : 1),
    outer_right_px: (measurement.outer_right_pct ?? (measurement.outer_right_px / Math.max(1, measurement.image_width))) / (measurement.outer_right_pct ? 100 : 1),
    outer_top_px: (measurement.outer_top_pct ?? (measurement.outer_top_px / Math.max(1, measurement.image_height))) / (measurement.outer_top_pct ? 100 : 1),
    outer_bottom_px: (measurement.outer_bottom_pct ?? (measurement.outer_bottom_px / Math.max(1, measurement.image_height))) / (measurement.outer_bottom_pct ? 100 : 1),
    inner_left_px: (measurement.inner_left_pct ?? (measurement.inner_left_px / Math.max(1, measurement.image_width))) / (measurement.inner_left_pct ? 100 : 1),
    inner_right_px: (measurement.inner_right_pct ?? (measurement.inner_right_px / Math.max(1, measurement.image_width))) / (measurement.inner_right_pct ? 100 : 1),
    inner_top_px: (measurement.inner_top_pct ?? (measurement.inner_top_px / Math.max(1, measurement.image_height))) / (measurement.inner_top_pct ? 100 : 1),
    inner_bottom_px: (measurement.inner_bottom_pct ?? (measurement.inner_bottom_px / Math.max(1, measurement.image_height))) / (measurement.inner_bottom_pct ? 100 : 1),
  };
}

function linesFromMeasurement(measurement: CenteringMeasurement | null, width: number, height: number): CenteringLines {
  if (!measurement) return defaultLines(width, height);
  if (measurement.image_width === width && measurement.image_height === height) {
    return {
      outer_left_px: measurement.outer_left_px,
      outer_right_px: measurement.outer_right_px,
      outer_top_px: measurement.outer_top_px,
      outer_bottom_px: measurement.outer_bottom_px,
      inner_left_px: measurement.inner_left_px,
      inner_right_px: measurement.inner_right_px,
      inner_top_px: measurement.inner_top_px,
      inner_bottom_px: measurement.inner_bottom_px,
    };
  }
  return linesFromPercent(percentFromMeasurement(measurement), width, height);
}

function normalizeLinePayload(lines: CenteringLines, width: number, height: number) {
  const percent = linesToPercent(lines, width, height);
  return {
    ...lines,
    outer_left_pct: percent.outer_left_px * 100,
    outer_right_pct: percent.outer_right_px * 100,
    outer_top_pct: percent.outer_top_px * 100,
    outer_bottom_pct: percent.outer_bottom_px * 100,
    inner_left_pct: percent.inner_left_px * 100,
    inner_right_pct: percent.inner_right_px * 100,
    inner_top_pct: percent.inner_top_px * 100,
    inner_bottom_pct: percent.inner_bottom_px * 100,
  };
}

function liveCentering(lines: CenteringLines) {
  const left = Math.max(0, lines.inner_left_px - lines.outer_left_px);
  const right = Math.max(0, lines.outer_right_px - lines.inner_right_px);
  const top = Math.max(0, lines.inner_top_px - lines.outer_top_px);
  const bottom = Math.max(0, lines.outer_bottom_px - lines.inner_bottom_px);
  const ratio = (a: number, b: number) => {
    const total = a + b || 1;
    const first = (a * 100) / total;
    const second = (b * 100) / total;
    return { first, second, label: `${Math.round(first)}/${Math.round(second)}`, off: Math.abs(first - 50) };
  };
  const horizontal = ratio(left, right);
  const vertical = ratio(top, bottom);
  const limiter = Math.max(horizontal.first, horizontal.second, vertical.first, vertical.second);
  const grade = limiter <= 55 ? "Gem Mint 10" : limiter <= 60 ? "Mint 9" : limiter <= 65 ? "NM-MT 8.5" : limiter <= 70 ? "NM-MT 8" : limiter <= 75 ? "EX-MT 7.5" : "Below 7";
  const score = limiter <= 55 ? 10 : limiter <= 60 ? 9 : limiter <= 65 ? 8.5 : limiter <= 70 ? 8 : limiter <= 75 ? 7.5 : Math.max(1, 7 - ((limiter - 75) / 5));
  const shiftX = horizontal.first > horizontal.second ? "jobbra tolódik" : horizontal.second > horizontal.first ? "balra tolódik" : "középen";
  const shiftY = vertical.first > vertical.second ? "lefelé tolódik" : vertical.second > vertical.first ? "felfelé tolódik" : "középen";
  return { horizontal, vertical, grade, score: Math.round(score * 10) / 10, shiftX, shiftY };
}

function CenteringRatioBar({ label, first, second }: { label: string; first: number; second: number }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-cyan-100">
        <span>{label}</span>
        <span>{Math.round(first)}/{Math.round(second)}</span>
      </div>
      <div className="flex h-2 overflow-hidden rounded-full bg-slate-950">
        <div className="bg-cyan-300" style={{ width: `${first}%` }} />
        <div className="bg-blue-500" style={{ width: `${second}%` }} />
      </div>
    </div>
  );
}

function CenteringResultCard({ side, result }: { side: "front" | "back"; result: ReturnType<typeof liveCentering> }) {
  return (
    <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 p-4 text-sm text-cyan-100">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-cyan-200">{side}</div>
          <div className="mt-1 text-base font-semibold">{result.grade}</div>
        </div>
        <div className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-3 py-1 text-xs">Score {formatNumber(result.score)}</div>
      </div>
      <div className="mt-4 space-y-3">
        <CenteringRatioBar label="L/R" first={result.horizontal.first} second={result.horizontal.second} />
        <CenteringRatioBar label="T/B" first={result.vertical.first} second={result.vertical.second} />
      </div>
      <div className="mt-3 text-xs text-cyan-200">{result.shiftX} · {result.shiftY}</div>
    </div>
  );
}

function ProcessedDiagnosticsPanel({
  processed,
  selectedSide,
  selectedVariant,
  onSelectSide,
  onSelectVariant,
  onOpenBoundary,
  onRecalculate,
  debugMode,
  centeringMeasurements,
  onOpenImage,
}: {
  processed: ProcessedImagesResponse | null;
  selectedSide: "front" | "back";
  selectedVariant: string;
  onSelectSide: (side: "front" | "back") => void;
  onSelectVariant: (variant: string) => void;
  onOpenBoundary: (side: "front" | "back") => void;
  onRecalculate: (side: "front" | "back") => void;
  debugMode: boolean;
  centeringMeasurements: CenteringMeasurement[];
  onOpenImage: (src: string, label: string, description?: string) => void;
}) {
  const sides = processed?.sides ?? {};
  const side = sides[selectedSide] ?? sides.front ?? sides.back ?? null;
  const imagePath = side?.generated_images?.[selectedVariant] ?? side?.generated_images?.perspective_corrected ?? side?.generated_images?.original_normalized;
  const selectedVariantInfo = processedVariantOptions.find(([key]) => key === selectedVariant);
  const sideName = selectedSide === "front" ? "Front" : "Back";
  const imageLabel = `${sideName} ${selectedVariantInfo?.[1] ?? selectedVariant}`;
  const history = centeringMeasurements.filter((measurement) => measurement.side === selectedSide).slice(0, 4);
  if (!processed || Object.keys(sides).length === 0) {
    return <EmptyState label="No Phase 16 processed images yet." />;
  }
  return (
    <div className="mt-4 space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase text-slate-500">Selected side</div>
          <SegmentedControl
            options={(["front", "back"] as const).map((item) => ({ value: item, label: item === "front" ? "Front processed" : "Back processed", disabled: !sides[item] }))}
            value={selectedSide}
            onChange={onSelectSide}
          />
        </div>
        {side && (
          <div className="flex flex-wrap gap-2">
            <button className="rounded-lg border border-cyan-500/40 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/10" onClick={() => onOpenBoundary(side.side as "front" | "back")} type="button">Adjust corners</button>
            <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={() => onRecalculate(side.side as "front" | "back")} type="button">Recalculate</button>
          </div>
        )}
      </div>
      <div className="flex gap-2 overflow-x-auto rounded-2xl border border-white/10 bg-slate-950/35 p-2">
        {processedVariantOptions.map(([key, label]) => (
          <button
            key={key}
            className={`min-h-11 shrink-0 rounded-xl border px-3 py-2 text-xs font-semibold ${selectedVariant === key ? "border-cyan-300/45 bg-cyan-300/15 text-cyan-50 shadow-[0_0_18px_rgba(103,232,249,0.18)]" : "border-white/10 text-slate-300 hover:bg-white/10"} disabled:opacity-35`}
            disabled={!side?.generated_images?.[key]}
            onClick={() => onSelectVariant(key)}
            type="button"
          >
            {label}
          </button>
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 px-4 py-3">
            <div>
              <div className="text-sm font-semibold text-slate-50">{imageLabel}</div>
              {selectedVariantInfo && <p className="text-xs leading-5 text-slate-400">{selectedVariantInfo[2]}</p>}
            </div>
            <div className="text-xs font-medium text-cyan-200">Click image to open fullscreen</div>
          </div>
          {imagePath ? (
            <button className="block h-[58vh] min-h-[360px] w-full bg-black/25 p-3 sm:p-5" onClick={() => onOpenImage(mediaUrl(imagePath, side?.updated_at), imageLabel, selectedVariantInfo?.[2])} type="button">
              <img className="h-full w-full object-contain" src={mediaUrl(imagePath, side?.updated_at)} alt={imageLabel} />
            </button>
          ) : (
            <EmptyState label="Selected diagnostic image is not available." />
          )}
        </div>
        <div className="space-y-3">
          <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
            <div className="text-xs font-semibold uppercase text-slate-500">Image clarity</div>
            <div className="mt-2 text-sm text-slate-200">{imageLabel}</div>
            <div className="mt-1 text-xs text-slate-500">Switching side or tab always changes this labeled image only.</div>
          </div>
          {debugMode && (
            <div className="rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-3 text-xs text-cyan-50">
              <div className="font-semibold uppercase text-cyan-100">AI image usage</div>
              <div className="mt-2 text-cyan-50">Phase A uses: front original, back original, centering JSON.</div>
              <div className="mt-1 text-cyan-50">Phase B uses: emboss, high pass, sobel, working notes.</div>
            </div>
          )}
        </div>
      </div>
      {side && (
        <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-3">
          <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
            <div>
              <div className="text-sm font-semibold text-slate-100">Centering details</div>
              <div className="text-xs text-slate-500">{sideName} processed centering data</div>
            </div>
            <div className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-300">source: {side.card_boundary?.boundary_source ?? "fallback"}</div>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Confidence" value={side.centering?.confidence !== undefined ? formatNumber(side.centering.confidence, 2) : "-"} />
            <StatCard label="Boundary confidence" value={side.card_boundary?.confidence !== undefined ? formatNumber(side.card_boundary.confidence, 2) : "-"} />
            <StatCard label="H ratio" value={side.centering?.horizontal_ratio ?? "-"} />
            <StatCard label="V ratio" value={side.centering?.vertical_ratio ?? "-"} />
          </div>
          {history.length > 0 && (
            <div className="mt-3 rounded-xl border border-white/10 bg-slate-950/35 p-3">
              <div className="mb-2 text-xs font-semibold uppercase text-slate-500">Correction history</div>
              <div className="space-y-2">
                {history.map((measurement) => (
                  <div key={measurement.id} className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-300">
                    <span>{measurement.source || "manual"} · {measurement.horizontal_ratio_label ?? "-"} / {measurement.vertical_ratio_label ?? "-"}</span>
                    <span className="text-slate-500">{formatDate(measurement.updated_at)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
      {side?.warnings?.length ? (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-3 text-xs text-amber-100">
          {side.warnings.map((warning) => <div key={warning}>{warning}</div>)}
        </div>
      ) : null}
    </div>
  );
}

function BoundaryEditor({
  side,
  busy,
  onCancel,
  onSave,
}: {
  side: ProcessedSide;
  busy: boolean;
  onCancel: () => void;
  onSave: (corners: number[][]) => void;
}) {
  const imagePath = side.generated_images.original_normalized;
  const boundary = side.card_boundary ?? {};
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const [corners, setCorners] = useState<number[][]>(() => boundary.manual_corners?.length === 4 ? boundary.manual_corners : boundary.final_corners?.length === 4 ? boundary.final_corners : boundary.auto_corners ?? []);
  const [dragIndex, setDragIndex] = useState<number | null>(null);

  const fallback = (width: number, height: number) => [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]];
  const initialize = (width: number, height: number) => {
    setNatural({ width, height });
    setCorners((current) => current.length === 4 ? current : fallback(width, height));
  };
  const updateCorner = (event: PointerEvent<SVGSVGElement>) => {
    if (dragIndex === null || natural.width <= 0 || natural.height <= 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = Math.max(0, Math.min(natural.width, ((event.clientX - rect.left) / rect.width) * natural.width));
    const y = Math.max(0, Math.min(natural.height, ((event.clientY - rect.top) / rect.height) * natural.height));
    setCorners((current) => current.map((point, index) => index === dragIndex ? [Math.round(x * 100) / 100, Math.round(y * 100) / 100] : point));
  };
  const resetAuto = () => {
    if (boundary.auto_corners?.length === 4) {
      setCorners(boundary.auto_corners);
    } else if (natural.width && natural.height) {
      setCorners(fallback(natural.width, natural.height));
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="max-h-[94vh] w-full max-w-6xl overflow-auto rounded-xl border border-slate-700 bg-charcoal-900/95 p-4 shadow-2xl shadow-black/50">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Card boundary: {side.side}</h2>
            <p className="mt-1 text-sm text-slate-400">Drag the four corners, then save. Coordinates are stored beside the auto-detected corners.</p>
          </div>
          <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={onCancel} type="button"><X size={16} /></button>
        </div>
        {!imagePath ? (
          <EmptyState label="Original normalized image is missing." />
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="relative mx-auto max-h-[78vh] max-w-full overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
              <img className="block max-h-[78vh] w-auto max-w-full select-none" src={mediaUrl(imagePath, side.updated_at)} alt={`${side.side} boundary`} onLoad={(event) => initialize(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)} draggable={false} />
              {corners.length === 4 && natural.width > 0 && natural.height > 0 && (
                <svg className="absolute inset-0 h-full w-full touch-none" viewBox={`0 0 ${natural.width} ${natural.height}`} preserveAspectRatio="none" onPointerMove={updateCorner} onPointerUp={() => setDragIndex(null)} onPointerLeave={() => setDragIndex(null)}>
                  <polygon points={corners.map((point) => point.join(",")).join(" ")} fill="rgba(56,189,248,0.12)" stroke="#38bdf8" strokeWidth={4} />
                  {corners.map((point, index) => (
                    <g key={index}>
                      <circle cx={point[0]} cy={point[1]} r={18} fill="black" fillOpacity={0.75} />
                      <circle className="cursor-grab" cx={point[0]} cy={point[1]} r={13} fill="#fbbf24" stroke="white" strokeWidth={2} onPointerDown={(event) => { event.preventDefault(); setDragIndex(index); }} />
                    </g>
                  ))}
                </svg>
              )}
            </div>
            <div className="space-y-3">
              <div className="rounded-lg border border-slate-800 bg-slate-950/35 p-3 text-sm text-slate-300">
                <div>Source: {boundary.boundary_source ?? "-"}</div>
                <div>Confidence: {boundary.confidence ?? "-"}</div>
              </div>
              <button className="w-full rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={resetAuto} type="button"><RotateCcw size={16} className="mr-2 inline" />Reset to auto</button>
              <button className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy || corners.length !== 4} onClick={() => onSave(corners)} type="button"><Save size={16} className="mr-2 inline" />Save boundary</button>
              <button className="w-full rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={onCancel} type="button">Cancel</button>
              <pre className="max-h-56 overflow-auto rounded bg-slate-950/70 p-3 text-xs text-slate-400">{JSON.stringify(corners, null, 2)}</pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function CenteringEditor({
  sources,
  measurements,
  busy,
  onCancel,
  onSave,
}: {
  sources: { front: CenteringSource | null; back: CenteringSource | null };
  measurements: CenteringMeasurement[];
  busy: boolean;
  onCancel: () => void;
  onSave: (payload: Partial<CenteringMeasurement>) => void;
}) {
  const [side, setSide] = useState<"front" | "back">(sources.front ? "front" : "back");
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const [lines, setLines] = useState<CenteringLines | null>(null);
  const [lineTemplates, setLineTemplates] = useState<Partial<Record<"front" | "back", PercentLines>>>({});
  const [dragging, setDragging] = useState<LineKey | null>(null);
  const [hoverLine, setHoverLine] = useState<LineKey | null>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [spaceDown, setSpaceDown] = useState(false);
  const [panning, setPanning] = useState<{ x: number; y: number; pan: { x: number; y: number } } | null>(null);
  const source = sources[side] ?? sources.front ?? sources.back;
  const result = lines ? liveCentering(lines) : null;
  const savedMeasurement = measurements.find((measurement) => measurement.side === side) ?? null;
  const otherSide = side === "front" ? "back" : "front";

  useEffect(() => {
    setLines(null);
    setNatural({ width: 0, height: 0 });
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [side, source?.file_path]);

  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      if (event.code === "Space") {
        setSpaceDown(true);
      }
    };
    const keyUp = (event: KeyboardEvent) => {
      if (event.code === "Space") {
        setSpaceDown(false);
        setPanning(null);
      }
    };
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    return () => {
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
    };
  }, []);

  const initializeLines = (width: number, height: number) => {
    setNatural({ width, height });
    const template = lineTemplates[side];
    setLines(template ? linesFromPercent(template, width, height) : linesFromMeasurement(savedMeasurement, width, height));
  };

  const setCurrentLines = (nextLines: CenteringLines) => {
    setLines(nextLines);
    if (natural.width > 0 && natural.height > 0) {
      setLineTemplates((current) => ({ ...current, [side]: linesToPercent(nextLines, natural.width, natural.height) }));
    }
  };

  const updateLine = (event: PointerEvent<SVGSVGElement>) => {
    if (!dragging || !lines || natural.width <= 0 || natural.height <= 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * natural.width;
    const y = ((event.clientY - rect.top) / rect.height) * natural.height;
    const next = { ...lines };
    if (dragging.includes("left") || dragging.includes("right")) {
      next[dragging] = Math.max(0, Math.min(natural.width, x));
    } else {
      next[dragging] = Math.max(0, Math.min(natural.height, y));
    }
    setCurrentLines(next);
  };

  const startGuideDrag = (event: PointerEvent<SVGElement>, key: LineKey) => {
    event.preventDefault();
    event.stopPropagation();
    setDragging(key);
  };

  const handleWheel = (event: WheelEvent<HTMLDivElement>) => {
    event.preventDefault();
    const next = Math.max(0.5, Math.min(4, zoom + (event.deltaY < 0 ? 0.12 : -0.12)));
    setZoom(next);
  };

  const startPan = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 1 && !spaceDown) return;
    event.preventDefault();
    setPanning({ x: event.clientX, y: event.clientY, pan });
    event.currentTarget.setPointerCapture(event.pointerId);
  };

  const updatePan = (event: PointerEvent<HTMLDivElement>) => {
    if (!panning) return;
    setPan({
      x: panning.pan.x + event.clientX - panning.x,
      y: panning.pan.y + event.clientY - panning.y,
    });
  };

  const save = () => {
    if (!source || !lines || !natural.width || !natural.height) return;
    onSave({
      side,
      source: "manual",
      image_label: source.label,
      image_width: natural.width,
      image_height: natural.height,
      media_id: "owned_card_id" in source ? source.id : null,
      ...normalizeLinePayload(lines, natural.width, natural.height),
    });
  };

  const resetLines = () => {
    if (!natural.width || !natural.height) return;
    setCurrentLines(defaultLines(natural.width, natural.height));
  };

  const copyLinesToOtherSide = () => {
    if (!lines || !natural.width || !natural.height) return;
    setLineTemplates((current) => ({ ...current, [otherSide]: linesToPercent(lines, natural.width, natural.height) }));
  };

  const guideColor = (key: LineKey) => key.startsWith("outer") ? "#f43f5e" : "#38bdf8";
  const guideFill = (key: LineKey) => key.startsWith("outer") ? "#fb7185" : "#7dd3fc";
  const isVertical = (key: LineKey) => key.includes("left") || key.includes("right");
  const guideCursor = (key: LineKey) => isVertical(key) ? "cursor-ew-resize" : "cursor-ns-resize";
  const scaleX = (value: number) => `${(value / Math.max(1, natural.width)) * 100}%`;
  const scaleY = (value: number) => `${(value / Math.max(1, natural.height)) * 100}%`;
  const drawGuide = (key: LineKey) => {
    if (!lines) return null;
    const active = dragging === key || hoverLine === key;
    const vertical = isVertical(key);
    const value = lines[key];
    const lineProps = vertical
      ? { x1: value, x2: value, y1: 0, y2: natural.height }
      : { x1: 0, x2: natural.width, y1: value, y2: value };
    const cx = vertical ? value : natural.width / 2;
    const cy = vertical ? natural.height / 2 : value;
    return (
      <g key={key}>
        <line {...lineProps} stroke="black" strokeOpacity={0.75} strokeWidth={active ? 8 : 6} />
        <line {...lineProps} stroke={guideColor(key)} strokeWidth={active ? 4 : 3} />
        <line
          {...lineProps}
          className={guideCursor(key)}
          data-guide-handle
          onPointerDown={(event) => startGuideDrag(event, key)}
          onPointerEnter={() => setHoverLine(key)}
          onPointerLeave={() => setHoverLine(null)}
          stroke="transparent"
          strokeWidth={28}
        />
        <circle cx={cx} cy={cy} r={active ? 14 : 11} fill="black" fillOpacity={0.75} />
        <circle
          className={`${guideCursor(key)} transition`}
          cx={cx}
          cy={cy}
          data-guide-handle
          fill={guideFill(key)}
          onPointerDown={(event) => startGuideDrag(event, key)}
          onPointerEnter={() => setHoverLine(key)}
          onPointerLeave={() => setHoverLine(null)}
          r={active ? 11 : 8}
          stroke="white"
          strokeOpacity={0.8}
          strokeWidth={2}
          style={{ filter: `drop-shadow(0 0 8px ${guideColor(key)})` }}
        />
        <circle
          className={guideCursor(key)}
          cx={cx}
          cy={cy}
          data-guide-handle
          fill="transparent"
          onPointerDown={(event) => startGuideDrag(event, key)}
          onPointerEnter={() => setHoverLine(key)}
          onPointerLeave={() => setHoverLine(null)}
          r={24}
        />
      </g>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="max-h-[94vh] w-full max-w-7xl overflow-auto rounded-xl border border-slate-700 bg-charcoal-900/95 p-4 shadow-2xl shadow-black/50">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Centering beállítása</h2>
            <p className="mt-1 text-sm text-slate-400">Piros: külső kártyaszél. Kék: belső artwork/border határ. Görgővel zoom, Space + drag vagy középső egérgomb: pan.</p>
          </div>
          <div className="flex gap-2">
            <button className={`rounded-lg px-3 py-2 text-sm ${side === "front" ? "bg-blue-600 text-white" : "border border-slate-700 text-slate-300"}`} disabled={!sources.front} onClick={() => setSide("front")} type="button">Front</button>
            <button className={`rounded-lg px-3 py-2 text-sm ${side === "back" ? "bg-blue-600 text-white" : "border border-slate-700 text-slate-300"}`} disabled={!sources.back} onClick={() => setSide("back")} type="button">Back</button>
          </div>
        </div>

        {!source ? (
          <EmptyState label="Nincs használható front/back kép a centering szerkesztőhöz." />
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div
              className={`relative flex h-[72vh] items-center justify-center overflow-hidden rounded-lg border border-slate-800 bg-slate-950 ${spaceDown || panning ? "cursor-grab" : ""}`}
              onPointerDown={startPan}
              onPointerMove={updatePan}
              onPointerUp={() => { setPanning(null); setDragging(null); }}
              onWheel={handleWheel}
            >
              <div
                className="relative inline-block max-h-full max-w-full transition-transform duration-100"
                style={{ transform: `translate(${pan.x}px, ${pan.y}px) scale(${zoom})`, transformOrigin: "center" }}
              >
                <img
                  className="block max-h-[72vh] w-auto max-w-full select-none"
                  src={mediaUrl(source.file_path, cacheKeyFor(source))}
                  alt={source.label ?? side}
                  onLoad={(event) => initializeLines(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)}
                  draggable={false}
                />
                {lines && natural.width > 0 && natural.height > 0 && (
                  <svg
                    className="absolute inset-0 h-full w-full touch-none"
                    onPointerMove={updateLine}
                    onPointerUp={() => { setDragging(null); setHoverLine(null); }}
                    onPointerLeave={() => { setDragging(null); setHoverLine(null); }}
                    viewBox={`0 0 ${natural.width} ${natural.height}`}
                    preserveAspectRatio="none"
                  >
                    {(["outer_left_px", "outer_right_px", "outer_top_px", "outer_bottom_px", "inner_left_px", "inner_right_px", "inner_top_px", "inner_bottom_px"] as LineKey[]).map(drawGuide)}
                  </svg>
                )}
              </div>
              <div className="absolute bottom-3 left-3 rounded-lg border border-slate-700 bg-slate-950/80 px-3 py-2 text-xs text-slate-300">
                Zoom {formatNumber(zoom, 2)}x
              </div>
            </div>

            <div className="space-y-3">
              {result && <CenteringResultCard side={side} result={result} />}
              <div className="grid grid-cols-2 gap-2">
                <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={resetLines} type="button">Reset lines</button>
                <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }} type="button">Reset zoom</button>
                <button className="rounded-lg border border-cyan-500/40 px-3 py-2 text-sm text-cyan-100 hover:bg-cyan-500/10 disabled:opacity-50" disabled={!sources[otherSide] || !lines} onClick={copyLinesToOtherSide} type="button">Copy to {otherSide}</button>
                <button className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy || !lines} onClick={save} type="button">Save measurement</button>
              </div>
              <button className="w-full rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={onCancel} type="button">Cancel</button>
              <div className="rounded-lg border border-slate-800 bg-slate-950/35 p-4 text-xs leading-6 text-slate-300">
                <div className="mb-2 font-semibold text-slate-100">Centering reference</div>
                <div>Gem Mint 10: 55/45 or better</div>
                <div>Mint 9: 60/40 or better</div>
                <div>NM-MT 8.5: 65/35 or better</div>
                <div>NM-MT 8: 70/30 or better</div>
                <div>EX-MT 7.5: 75/25 or better</div>
                <div>Below 7: worse than 75/25</div>
              </div>
              {lines && (
                <div className="text-[11px] text-slate-500">
                  X: outer {scaleX(lines.outer_left_px)} / {scaleX(lines.outer_right_px)} · inner {scaleX(lines.inner_left_px)} / {scaleX(lines.inner_right_px)}<br />
                  Y: outer {scaleY(lines.outer_top_px)} / {scaleY(lines.outer_bottom_px)} · inner {scaleY(lines.inner_top_px)} / {scaleY(lines.inner_bottom_px)}
                </div>
              )}
              <details className="rounded-lg border border-slate-800 bg-slate-950/25 p-3">
                <summary className="cursor-pointer text-sm font-medium text-slate-300">Másodlagos eszközök</summary>
                <div className="mt-3 text-xs leading-6 text-slate-400">
                  Reset lines csak a modalban állítja vissza az automatikus alaphelyzetet. A mentett mérés addig nem változik, amíg nem nyomsz Save measurement gombot.
                </div>
              </details>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
