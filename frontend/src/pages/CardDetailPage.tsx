import { Play, RefreshCw, Upload, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, mediaUrl } from "../api/client";
import type {
  AnalysisAsset,
  AnalysisFinding,
  AnalysisReport,
  AnalysisRun,
  Card,
  CardMedia,
  LocalAIStatus,
  OwnedCard,
  PriceObservation,
} from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";
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

type CardDetailPageProps = {
  ownedCardId: number;
};

type PriceForm = {
  raw_price_huf: string;
  psa_8_price_huf: string;
  psa_9_price_huf: string;
  psa_10_price_huf: string;
  price_confidence: string;
  notes: string;
};

const emptyPriceForm: PriceForm = {
  raw_price_huf: "",
  psa_8_price_huf: "",
  psa_9_price_huf: "",
  psa_10_price_huf: "",
  price_confidence: "0.5",
  notes: "",
};

function formFromPrice(price: PriceObservation | null): PriceForm {
  if (!price) return emptyPriceForm;
  return {
    raw_price_huf: price.raw_price_huf?.toString() ?? "",
    psa_8_price_huf: price.psa_8_price_huf?.toString() ?? "",
    psa_9_price_huf: price.psa_9_price_huf?.toString() ?? "",
    psa_10_price_huf: price.psa_10_price_huf?.toString() ?? "",
    price_confidence: price.price_confidence?.toString() ?? "0.5",
    notes: "",
  };
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

export function CardDetailPage({ ownedCardId }: CardDetailPageProps) {
  const [ownedCard, setOwnedCard] = useState<OwnedCard | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [media, setMedia] = useState<CardMedia[]>([]);
  const [latestPrice, setLatestPrice] = useState<PriceObservation | null>(null);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [findings, setFindings] = useState<AnalysisFinding[]>([]);
  const [localAI, setLocalAI] = useState<LocalAIStatus | null>(null);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyLabel, setBusyLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [uploadLabel, setUploadLabel] = useState("front");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [priceForm, setPriceForm] = useState<PriceForm>(emptyPriceForm);
  const [previewAsset, setPreviewAsset] = useState<AnalysisAsset | CardMedia | null>(null);

  const busy = busyLabel !== null;
  const latestAnalysis = analysisRuns[0] ?? null;
  const visibleFindings = report?.findings?.length ? report.findings : findings;
  const hasAnalysisImage = media.some((item) => item.media_type === "image" && (item.label === "front" || item.label === "back"));

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

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const owned = await api.getOwnedCard(ownedCardId);
      setOwnedCard(owned);
      const [cardData, mediaData, runsData] = await Promise.all([
        api.getCard(owned.card_id),
        api.getOwnedCardMedia(ownedCardId),
        api.getAnalysisRuns(ownedCardId),
      ]);
      setCard(cardData);
      setMedia(mediaData);
      setAnalysisRuns(runsData);

      try {
        const price = await api.getLatestOwnedCardPrice(ownedCardId);
        setLatestPrice(price);
        setPriceForm(formFromPrice(price));
      } catch {
        setLatestPrice(null);
        setPriceForm(emptyPriceForm);
      }

      await loadReport(runsData[0]?.id ?? null);
      try {
        setLocalAI(await api.getLocalAIStatus());
      } catch {
        setLocalAI(null);
      }
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    } finally {
      setLoading(false);
    }
  }, [loadReport, ownedCardId]);

  useEffect(() => {
    load();
  }, [load]);

  const frontImage = useMemo(
    () => media.find((item) => item.label === "front" && item.media_type === "image") ?? media.find((item) => item.media_type === "image"),
    [media],
  );

  const groupedAssets = useMemo(() => {
    const assets = report?.assets ?? [];
    return {
      resized: assets.filter((asset) => asset.asset_type === "resized_image"),
      corners: assets.filter((asset) => asset.label?.includes("corner")),
      edges: assets.filter((asset) => asset.label?.includes("edge")),
      annotated: assets.filter((asset) => asset.asset_type === "annotated_image"),
    };
  }, [report]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!uploadFile) return;
    setBusyLabel("Kép feltöltése...");
    setMessage(null);
    try {
      await api.uploadMedia(ownedCardId, uploadLabel, uploadFile);
      setUploadFile(null);
      await load();
      setMessage("Kép feltöltve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feltöltési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const handlePriceSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ownedCard) return;
    setBusyLabel("Ár mentése...");
    setMessage(null);
    try {
      const saved = await api.createPrice(ownedCard.card_id, {
        source_name: "manual",
        currency: "HUF",
        raw_price_huf: optionalNumber(priceForm.raw_price_huf),
        psa_8_price_huf: optionalNumber(priceForm.psa_8_price_huf),
        psa_9_price_huf: optionalNumber(priceForm.psa_9_price_huf),
        psa_10_price_huf: optionalNumber(priceForm.psa_10_price_huf),
        price_confidence: optionalNumber(priceForm.price_confidence) ?? 0.5,
        notes: priceForm.notes.trim() || null,
      });
      setLatestPrice(saved);
      setPriceForm(formFromPrice(saved));
      if (latestAnalysis) await loadReport(latestAnalysis.id);
      setMessage("Ár mentve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ár mentési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const runAnalysis = async () => {
    if (!hasAnalysisImage) {
      setError("Tölts fel legalább egy front vagy back képet az OpenCV elemzéshez.");
      return;
    }
    setBusyLabel("Elemzés fut...");
    setMessage(null);
    try {
      const newRun = await api.runOpenCvAnalysis(ownedCardId);
      setBusyLabel("Report frissítése...");
      await api.scoreAnalysisRun(newRun.id);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(newRun.id);
      setMessage("OpenCV elemzés és score elkészült.");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Elemzési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const refreshScore = async () => {
    if (!latestAnalysis) return;
    setBusyLabel("Report frissítése...");
    setMessage(null);
    try {
      await api.scoreAnalysisRun(latestAnalysis.id);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(latestAnalysis.id);
      setMessage("Score/report frissítve.");
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Score/report hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const runLocalAI = async () => {
    if (!localAI?.enabled || !localAI.reachable) {
      setError("Local AI nincs bekapcsolva. Állítsd be az LM Studio/Ollama lokális szervert.");
      return;
    }
    setBusyLabel("Local AI elemzés fut...");
    setMessage(null);
    try {
      const aiResult = await api.runLocalAIFastAnalysis(ownedCardId);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(aiResult.analysis_run.id);
      setMessage(`Local AI elemzés elkészült. Findingok: ${aiResult.finding_count}.`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Local AI elemzési hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  const generateAnnotations = async () => {
    if (!latestAnalysis) return;
    setBusyLabel("Annotációk generálása...");
    setMessage(null);
    try {
      const result = await api.annotateAnalysisRun(latestAnalysis.id);
      await loadReport(latestAnalysis.id);
      setMessage(result.message);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Annotációs hiba");
    } finally {
      setBusyLabel(null);
    }
  };

  if (loading) return <LoadingState label="Kártya részletek betöltése..." />;
  if (error && !ownedCard) return <EmptyState label={`Nem sikerült betölteni a kártyát: ${error}`} />;
  if (!ownedCard) return <EmptyState label="Owned card nem található." />;

  return (
    <div className="space-y-4">
      {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {busyLabel && <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-sm text-blue-100">{busyLabel}</div>}
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

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

          <Panel title="Kép preview és feltöltés">
            {frontImage ? (
              <button className="block w-full text-left" onClick={() => setPreviewAsset(frontImage)} type="button">
                <img alt={frontImage.label} className="aspect-[3/4] w-full rounded-xl border border-slate-800 object-cover" src={mediaUrl(frontImage.file_path)} />
              </button>
            ) : (
              <EmptyState label="Még nincs feltöltött kép." />
            )}
            {!hasAnalysisImage && (
              <div className="mt-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                Tölts fel legalább egy front vagy back képet az OpenCV elemzéshez.
              </div>
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
            </form>
          </Panel>

          <Panel title="Ár precheck">
            {latestPrice ? (
              <div className="grid grid-cols-2 gap-2">
                <StatCard label="Raw ár" value={formatHuf(latestPrice.raw_price_huf)} />
                <StatCard label="PSA 8" value={formatHuf(latestPrice.psa_8_price_huf)} />
                <StatCard label="PSA 9" value={formatHuf(latestPrice.psa_9_price_huf)} />
                <StatCard label="PSA 10" value={formatHuf(latestPrice.psa_10_price_huf)} />
                <StatCard label="Confidence" value={formatNumber(latestPrice.price_confidence, 2)} />
              </div>
            ) : (
              <EmptyState label="Még nincs ár rögzítve." />
            )}
          </Panel>

          <Panel title="Manuális ár rögzítése">
            <form className="space-y-3" onSubmit={handlePriceSubmit}>
              <div className="grid grid-cols-2 gap-3">
                <FieldLabel label="Raw ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 8000" value={priceForm.raw_price_huf} onChange={(event) => setPriceForm({ ...priceForm, raw_price_huf: event.target.value })} /></FieldLabel>
                <FieldLabel label="PSA 8 ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 18000" value={priceForm.psa_8_price_huf} onChange={(event) => setPriceForm({ ...priceForm, psa_8_price_huf: event.target.value })} /></FieldLabel>
                <FieldLabel label="PSA 9 ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 28000" value={priceForm.psa_9_price_huf} onChange={(event) => setPriceForm({ ...priceForm, psa_9_price_huf: event.target.value })} /></FieldLabel>
                <FieldLabel label="PSA 10 ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 65000" value={priceForm.psa_10_price_huf} onChange={(event) => setPriceForm({ ...priceForm, psa_10_price_huf: event.target.value })} /></FieldLabel>
              </div>
              <FieldLabel label="Confidence">
                <input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="decimal" placeholder="pl. 0,7" value={priceForm.price_confidence} onChange={(event) => setPriceForm({ ...priceForm, price_confidence: event.target.value })} />
              </FieldLabel>
              <FieldLabel label="Megjegyzés">
                <textarea className="min-h-20 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" placeholder="pl. lokális manuális becslés" value={priceForm.notes} onChange={(event) => setPriceForm({ ...priceForm, notes: event.target.value })} />
              </FieldLabel>
              <button className="w-full rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy} type="submit">Ár mentése</button>
            </form>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Képi elemzés" subtitle="OpenCV előfeldolgozás és localhost-only Local AI opcionális elemzés.">
            <div className="grid gap-3 md:grid-cols-2">
              <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60" disabled={busy} onClick={runAnalysis} type="button">
                <Play size={16} /> {busyLabel === "Elemzés fut..." ? "Elemzés fut..." : "OpenCV elemzés indítása"}
              </button>
              <button className="inline-flex items-center justify-center gap-2 rounded-lg border border-emerald-500/40 px-3 py-2 text-sm font-medium text-emerald-200 hover:bg-emerald-500/10 disabled:opacity-50" disabled={busy || !localAI?.enabled || !localAI.reachable} onClick={runLocalAI} type="button">
                <Play size={16} /> Local AI elemzés indítása
              </button>
            </div>
            {!localAI?.enabled && <p className="mt-3 text-sm text-amber-200">Local AI nincs bekapcsolva. Állítsd be az LM Studio/Ollama lokális szervert.</p>}
            {localAI?.enabled && !localAI.reachable && <p className="mt-3 text-sm text-amber-200">{localAI.message}</p>}
            {latestAnalysis && (
              <div className="mt-4 grid grid-cols-2 gap-2">
                <StatCard label="Status" value={latestAnalysis.status ?? "-"} />
                <StatCard label="Centering" value={formatNumber(latestAnalysis.centering_score)} />
                <StatCard label="Confidence" value={latestAnalysis.confidence_level ?? "-"} />
                <StatCard label="Version" value={latestAnalysis.analysis_version ?? "-"} />
              </div>
            )}
          </Panel>

          <Panel title="Analysis run lista">
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
          </Panel>

          <Panel title="Asset gallery" subtitle="Kattints egy thumbnailre a nagyobb előnézethez.">
            {!report || report.assets.length === 0 ? (
              <EmptyState label="Még nincs megjeleníthető analysis asset." />
            ) : (
              <div className="space-y-5">
                {([
                  ["Annotated", groupedAssets.annotated],
                  ["Resized", groupedAssets.resized],
                  ["Corners", groupedAssets.corners],
                  ["Edges", groupedAssets.edges],
                ] as const).map(([title, assets]) => (
                  <div key={title}>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
                    {assets.length === 0 ? (
                      <div className="text-xs text-slate-500">Nincs asset ebben a csoportban.</div>
                    ) : (
                      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                        {assets.map((asset) => (
                          <button key={asset.id} className="rounded-lg border border-slate-800 bg-charcoal-900 p-2 text-left transition hover:border-blue-500/50 hover:bg-slate-800/40" onClick={() => setPreviewAsset(asset)} type="button">
                            <img className="aspect-square w-full rounded object-cover" src={mediaUrl(asset.file_path)} alt={asset.label ?? "asset"} />
                            <div className="mt-2 truncate text-xs text-slate-400">{asset.label}</div>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel
            title="Score és report"
            action={
              <div className="flex flex-wrap gap-2">
                <button className="inline-flex items-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/10 disabled:opacity-60" disabled={busy || !latestAnalysis} onClick={refreshScore} type="button">
                  <RefreshCw size={16} /> {busyLabel === "Report frissítése..." ? "Report frissítése..." : "Score/report frissítése"}
                </button>
                <button className="inline-flex items-center gap-2 rounded-lg border border-amber-500/40 px-3 py-2 text-sm text-amber-200 hover:bg-amber-500/10 disabled:opacity-60" disabled={busy || !latestAnalysis || visibleFindings.length === 0} onClick={generateAnnotations} type="button">
                  Annotációk generálása
                </button>
              </div>
            }
          >
            {!latestAnalysis ? (
              <EmptyState label="Még nincs elemzés. Tölts fel legalább egy front vagy back képet, majd indíts OpenCV elemzést." />
            ) : !report ? (
              <EmptyState label="A report még nincs elkészítve. Indíts score/report frissítést." />
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  <StatCard label="Overall score" value={formatNumber(report.scores.overall_score)} tone="good" />
                  <StatCard label="Grade range" value={`${report.estimated_grade_range.estimated_grade_low ?? "-"} - ${report.estimated_grade_range.estimated_grade_high ?? "-"}`} tone="warn" />
                  <StatCard label="Centering" value={formatNumber(report.scores.centering_score)} />
                  <StatCard label="Corners" value={formatNumber(report.scores.corners_score)} />
                  <StatCard label="Edges" value={formatNumber(report.scores.edges_score)} />
                  <StatCard label="Surface" value={formatNumber(report.scores.surface_score)} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <StatCard label="PSA 10 %" value={formatNumber(report.probabilities.psa_10_probability, 0)} />
                  <StatCard label="PSA 9 %" value={formatNumber(report.probabilities.psa_9_probability, 0)} />
                  <StatCard label="PSA 8 %" value={formatNumber(report.probabilities.psa_8_probability, 0)} />
                  <StatCard label="PSA 7- %" value={formatNumber(report.probabilities.psa_7_or_lower_probability, 0)} />
                </div>
                <div className="rounded-lg border border-slate-800 bg-charcoal-900 p-4 text-sm leading-6 text-slate-300">{report.human_summary}</div>
                <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
                  <div className="font-semibold">{report.recommendation ?? "-"}</div>
                  <p className="mt-2 leading-6">{report.recommendation_reason}</p>
                </div>

                {visibleFindings.length > 0 && (
                  <div className="rounded-lg border border-slate-800 bg-charcoal-900 p-4">
                    <h3 className="text-sm font-semibold text-slate-100">Talált hibák</h3>
                    <div className="mt-3 space-y-3">
                      {visibleFindings.map((finding) => (
                        <div key={finding.id} className="rounded-lg border border-slate-800 bg-slate-950/25 p-3 text-sm">
                          <div className="font-medium text-slate-100">{finding.title ?? "Finding"}</div>
                          <div className="mt-2 flex flex-wrap gap-2">
                            <FindingBadge>{finding.finding_type ?? "unknown"}</FindingBadge>
                            <FindingBadge tone={severityTone(finding.severity)}>{finding.severity ?? "-"}</FindingBadge>
                            <FindingBadge>confidence {formatNumber(finding.confidence, 2)}</FindingBadge>
                            <FindingBadge tone={finding.grade_impact === "high" ? "danger" : "default"}>impact {finding.grade_impact ?? "-"}</FindingBadge>
                          </div>
                          <p className="mt-2 leading-5 text-slate-300">{finding.description}</p>
                          <div className="mt-2 text-xs text-slate-500">{finding.location_label ?? "-"}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

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

      {previewAsset && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4" onClick={() => setPreviewAsset(null)}>
          <div className="max-h-[92vh] w-full max-w-5xl overflow-hidden rounded-xl border border-slate-700 bg-charcoal-900" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
              <div className="text-sm font-medium text-slate-100">{previewAsset.label ?? "Preview"}</div>
              <button className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100" onClick={() => setPreviewAsset(null)} type="button">
                <X size={18} />
              </button>
            </div>
            <div className="p-4">
              <img className="mx-auto max-h-[78vh] rounded-lg object-contain" src={mediaUrl(previewAsset.file_path)} alt={previewAsset.label ?? "preview"} />
            </div>
          </div>
        </div>
      )}
    </div>
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
