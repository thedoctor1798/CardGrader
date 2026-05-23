import { Play, RefreshCw, Upload } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api, mediaUrl } from "../api/client";
import type { AnalysisReport, AnalysisRun, Card, CardMedia, OwnedCard, PriceObservation } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";
import { formatHuf, formatNumber } from "../utils/format";

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

export function CardDetailPage({ ownedCardId }: CardDetailPageProps) {
  const [ownedCard, setOwnedCard] = useState<OwnedCard | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [media, setMedia] = useState<CardMedia[]>([]);
  const [latestPrice, setLatestPrice] = useState<PriceObservation | null>(null);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [uploadLabel, setUploadLabel] = useState("front");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [priceForm, setPriceForm] = useState<PriceForm>(emptyPriceForm);

  const latestAnalysis = analysisRuns[0] ?? null;

  const loadReport = useCallback(async (analysisRunId: number | null) => {
    if (!analysisRunId) {
      setReport(null);
      return;
    }
    try {
      setReport(await api.getAnalysisReport(analysisRunId));
    } catch {
      setReport(null);
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
    };
  }, [report]);

  const handleUpload = async (event: FormEvent) => {
    event.preventDefault();
    if (!uploadFile) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.uploadMedia(ownedCardId, uploadLabel, uploadFile);
      setUploadFile(null);
      await load();
      setMessage("Kép feltöltve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Feltöltési hiba");
    } finally {
      setBusy(false);
    }
  };

  const handlePriceSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ownedCard) return;
    setBusy(true);
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
      if (latestAnalysis) {
        await loadReport(latestAnalysis.id);
      }
      setMessage("Ár mentve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ár mentési hiba");
    } finally {
      setBusy(false);
    }
  };

  const runAnalysis = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const newRun = await api.runOpenCvAnalysis(ownedCardId);
      await api.scoreAnalysisRun(newRun.id);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      await loadReport(newRun.id);
      setMessage("OpenCV elemzés és score elkészült.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Elemzési hiba");
    } finally {
      setBusy(false);
    }
  };

  const refreshScore = async () => {
    if (!latestAnalysis) return;
    setBusy(true);
    setMessage(null);
    try {
      await api.scoreAnalysisRun(latestAnalysis.id);
      await loadReport(latestAnalysis.id);
      const runsData = await api.getAnalysisRuns(ownedCardId);
      setAnalysisRuns(runsData);
      setMessage("Score/report frissítve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Score/report hiba");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="Kártya részletek betöltése..." />;
  if (error && !ownedCard) return <EmptyState label={`Nem sikerült betölteni a kártyát: ${error}`} />;
  if (!ownedCard) return <EmptyState label="Owned card nem található." />;

  return (
    <div className="space-y-4">
      {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
      <div className="grid gap-4 xl:grid-cols-[360px_minmax(0,1fr)_420px]">
        <div className="space-y-4">
          <Panel title={card?.name ?? `Card #${ownedCard.card_id}`} subtitle={ownedCard.copy_label ?? "Nincs copy label"}>
            <div className="space-y-3 text-sm text-slate-300">
              <div className="flex justify-between gap-4"><span>Status</span><span>{ownedCard.status ?? "-"}</span></div>
              <div className="flex justify-between gap-4"><span>Bekerülés</span><span>{formatHuf(ownedCard.acquired_price_huf)}</span></div>
              <div className="flex justify-between gap-4"><span>Forrás</span><span>{ownedCard.acquired_source ?? "-"}</span></div>
              <div className="flex justify-between gap-4"><span>Set</span><span>{[card?.set_name, card?.card_number].filter(Boolean).join(" · ") || "-"}</span></div>
            </div>
          </Panel>

          <Panel title="Media preview">
            {frontImage ? (
              <img
                alt={frontImage.label}
                className="aspect-[3/4] w-full rounded-lg border border-slate-800 object-cover"
                src={mediaUrl(frontImage.file_path)}
              />
            ) : (
              <EmptyState label="Még nincs feltöltött kép." />
            )}
            <form className="mt-4 space-y-3" onSubmit={handleUpload}>
              <select
                className="w-full rounded-lg border border-slate-800 bg-charcoal-950 px-3 py-2 text-sm"
                onChange={(event) => setUploadLabel(event.target.value)}
                value={uploadLabel}
              >
                {mediaLabels.map((label) => <option key={label}>{label}</option>)}
              </select>
              <input
                className="w-full rounded-lg border border-slate-800 bg-charcoal-950 px-3 py-2 text-sm text-slate-300"
                onChange={(event) => setUploadFile(event.target.files?.[0] ?? null)}
                type="file"
              />
              <button
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-60"
                disabled={busy || !uploadFile}
                type="submit"
              >
                <Upload size={16} />
                Kép feltöltése
              </button>
            </form>
          </Panel>

          <Panel title="Ár precheck">
            {latestPrice ? (
              <div className="grid grid-cols-2 gap-2 text-sm">
                <StatCard label="Raw" value={formatHuf(latestPrice.raw_price_huf)} />
                <StatCard label="PSA 8" value={formatHuf(latestPrice.psa_8_price_huf)} />
                <StatCard label="PSA 9" value={formatHuf(latestPrice.psa_9_price_huf)} />
                <StatCard label="PSA 10" value={formatHuf(latestPrice.psa_10_price_huf)} />
                <StatCard label="Confidence" value={formatNumber(latestPrice.price_confidence, 2)} />
              </div>
            ) : (
              <EmptyState label="Még nincs ár rögzítve." />
            )}
            <form className="mt-4 grid grid-cols-2 gap-3" onSubmit={handlePriceSubmit}>
              {([
                ["raw_price_huf", "Raw HUF"],
                ["psa_8_price_huf", "PSA 8 HUF"],
                ["psa_9_price_huf", "PSA 9 HUF"],
                ["psa_10_price_huf", "PSA 10 HUF"],
                ["price_confidence", "Confidence 0-1"],
              ] as const).map(([field, placeholder]) => (
                <input
                  key={field}
                  className="rounded-lg border border-slate-800 bg-charcoal-950 px-3 py-2 text-sm"
                  inputMode="decimal"
                  onChange={(event) => setPriceForm((current) => ({ ...current, [field]: event.target.value }))}
                  placeholder={placeholder}
                  step="0.01"
                  type="number"
                  value={priceForm[field]}
                />
              ))}
              <textarea
                className="col-span-2 min-h-20 rounded-lg border border-slate-800 bg-charcoal-950 px-3 py-2 text-sm"
                onChange={(event) => setPriceForm((current) => ({ ...current, notes: event.target.value }))}
                placeholder="Megjegyzés"
                value={priceForm.notes}
              />
              <button className="col-span-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-60" disabled={busy} type="submit">
                Manuális ár mentése
              </button>
            </form>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel
            title="Képi elemzés"
            subtitle="Lokális OpenCV preprocessing, resized képek és cropok."
            action={
              <button
                className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-60"
                disabled={busy}
                onClick={runAnalysis}
                type="button"
              >
                <Play size={16} />
                OpenCV elemzés indítása
              </button>
            }
          >
            {latestAnalysis ? (
              <div className="grid gap-3 sm:grid-cols-4">
                <StatCard label="Status" value={latestAnalysis.status ?? "-"} />
                <StatCard label="Centering" value={formatNumber(latestAnalysis.centering_score)} />
                <StatCard label="Confidence" value={latestAnalysis.confidence_level ?? "-"} />
                <StatCard label="OpenCV" value={latestAnalysis.opencv_version ?? "-"} />
              </div>
            ) : (
              <EmptyState label="Még nincs elemzés. Tölts fel legalább egy front vagy back képet, majd indíts OpenCV elemzést." />
            )}
          </Panel>

          <Panel title="Assets gallery">
            {!report || report.assets.length === 0 ? (
              <EmptyState label="Még nincs megjeleníthető analysis asset." />
            ) : (
              <div className="space-y-5">
                {([
                  ["Resized", groupedAssets.resized],
                  ["Corners", groupedAssets.corners],
                  ["Edges", groupedAssets.edges],
                ] as const).map(([title, assets]) => (
                  <div key={title}>
                    <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">{title}</h3>
                    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                      {assets.map((asset) => (
                        <figure key={asset.id} className="rounded-lg border border-slate-800 bg-charcoal-900 p-2">
                          <img className="aspect-square w-full rounded object-cover" src={mediaUrl(asset.file_path)} alt={asset.label ?? "asset"} />
                          <figcaption className="mt-2 truncate text-xs text-slate-400">{asset.label}</figcaption>
                        </figure>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel
            title="Report / score"
            action={
              <button
                className="inline-flex items-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/10 disabled:opacity-60"
                disabled={busy || !latestAnalysis}
                onClick={refreshScore}
                type="button"
              >
                <RefreshCw size={16} />
                Score/report frissítése
              </button>
            }
          >
            {!latestAnalysis ? (
              <EmptyState label="Még nincs elemzés. Tölts fel legalább egy front vagy back képet, majd indíts OpenCV elemzést." />
            ) : !report ? (
              <EmptyState label="A report még nincs elkészítve. Indíts score/report frissítést." />
            ) : (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-2">
                  <StatCard label="AI score" value={formatNumber(report.scores.overall_score)} tone="good" />
                  <StatCard
                    label="Grade range"
                    value={`${report.estimated_grade_range.estimated_grade_low ?? "-"} – ${report.estimated_grade_range.estimated_grade_high ?? "-"}`}
                    tone="warn"
                  />
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
                <div className="rounded-lg border border-slate-800 bg-charcoal-900 p-4 text-sm leading-6 text-slate-300">
                  {report.human_summary}
                </div>
                <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-100">
                  <div className="font-semibold">{report.recommendation ?? "-"}</div>
                  <p className="mt-2 leading-6">{report.recommendation_reason}</p>
                </div>
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
    </div>
  );
}
