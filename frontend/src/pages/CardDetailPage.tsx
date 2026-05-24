import { Play, RefreshCw, Upload, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { PointerEvent, ReactNode } from "react";
import { api, mediaUrl } from "../api/client";
import type {
  AnalysisAsset,
  AnalysisFinding,
  AnalysisReport,
  AnalysisRun,
  Card,
  CardMedia,
  CenteringMeasurement,
  LocalAIDryRun,
  LocalAIDebugSingleImageResponse,
  LocalAIStatus,
  OwnedCard,
  PriceObservation,
} from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { GlobalLoadingOverlay } from "../components/GlobalLoadingOverlay";
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
const statuses = ["raw_owned", "graded_owned", "sent_to_grading", "listed_for_sale", "sold", "kept_long_term"];
const sources = ["pack", "blister", "single_purchase", "trade", "unknown"];

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
  raw_price_huf: "",
  psa_8_price_huf: "",
  psa_9_price_huf: "",
  psa_10_price_huf: "",
  price_confidence: "0.5",
  notes: "",
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
  return {
    title: label,
    subtitle: "Lokális művelet folyamatban.",
  };
}

export function CardDetailPage({ ownedCardId }: CardDetailPageProps) {
  const [ownedCard, setOwnedCard] = useState<OwnedCard | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [media, setMedia] = useState<CardMedia[]>([]);
  const [latestPrice, setLatestPrice] = useState<PriceObservation | null>(null);
  const [latestCentering, setLatestCentering] = useState<CenteringMeasurement | null>(null);
  const [centeringMeasurements, setCenteringMeasurements] = useState<CenteringMeasurement[]>([]);
  const [analysisRuns, setAnalysisRuns] = useState<AnalysisRun[]>([]);
  const [opencvAssets, setOpenCvAssets] = useState<AnalysisAsset[]>([]);
  const [findings, setFindings] = useState<AnalysisFinding[]>([]);
  const [localAI, setLocalAI] = useState<LocalAIStatus | null>(null);
  const [localAIDryRun, setLocalAIDryRun] = useState<LocalAIDryRun | null>(null);
  const [localAIDebug, setLocalAIDebug] = useState<LocalAIDebugSingleImageResponse | null>(null);
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
  const [showCenteringEditor, setShowCenteringEditor] = useState(false);

  const busy = busyLabel !== null;
  const workOverlay = workOverlayForLabel(busyLabel);
  const latestAnalysis = analysisRuns[0] ?? null;
  const visibleFindings = report?.findings?.length ? report.findings : findings;
  const hasAnalysisImage = media.some((item) => item.media_type === "image" && (item.label === "front" || item.label === "back"));
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
      : !localAI.model_name
        ? "LOCAL_AI_MODEL_NAME nincs beállítva."
        : !localAI.reachable
          ? "LM Studio nem érhető el."
          : null;

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
        const price = await api.getLatestOwnedCardPrice(ownedCardId);
        setLatestPrice(price);
        setPriceForm(formFromPrice(price));
      } catch {
        setLatestPrice(null);
        setPriceForm(emptyPriceForm);
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
  const latestFrontImage = useMemo(() => imageMedia.find((item) => item.label === "front") ?? null, [imageMedia]);
  const latestBackImage = useMemo(() => imageMedia.find((item) => item.label === "back") ?? null, [imageMedia]);
  const latestUploadedImage = imageMedia[0] ?? null;
  const previewImage = selectedPreviewSide === "front"
    ? latestFrontImage ?? latestBackImage ?? latestUploadedImage
    : latestBackImage ?? latestFrontImage ?? latestUploadedImage;

  useEffect(() => {
    if (selectedPreviewSide === "front" && !latestFrontImage && latestBackImage) {
      setSelectedPreviewSide("back");
    }
    if (selectedPreviewSide === "back" && !latestBackImage && latestFrontImage) {
      setSelectedPreviewSide("front");
    }
  }, [latestBackImage, latestFrontImage, selectedPreviewSide]);

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

  const handlePriceSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!ownedCard) return;
    setBusyLabel("Ár mentése...");
    setNotice(null);
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
      setScopedSuccess("price", "Ár mentve.");
    } catch (err) {
      setScopedError("price", err instanceof Error ? err.message : "Ár mentési hiba");
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
      const result = await api.runLocalAIDebugSingleImage(ownedCardId);
      setLocalAIDebug(result);
      setScopedSuccess("analysis", `Single-image debug: ${result.status}.`);
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
      imageMedia.find((item) => item.label === side);
    return {
      front: assetSource("front") ?? mediaSource("front") ?? null,
      back: assetSource("back") ?? mediaSource("back") ?? null,
    };
  }, [imageMedia, opencvAssets]);

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

  if (loading) return <LoadingState label="Kártya részletek betöltése..." />;
  if (error && !ownedCard) return <EmptyState label={`Nem sikerült betölteni a kártyát: ${error}`} />;
  if (!ownedCard) return <EmptyState label="Owned card nem található." />;

  return (
    <div className="space-y-4">
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
              <InlineNotice notice={notice} scope="media" />
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
              <InlineNotice notice={notice} scope="price" />
            </form>
          </Panel>
        </div>

        <div className="space-y-4">
          <Panel title="Képi elemzés" subtitle="OpenCV előfeldolgozás és localhost-only Local AI opcionális elemzés.">
            <div className="grid gap-3 md:grid-cols-3">
              <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60" disabled={busy} onClick={runAnalysis} type="button">
                <Play size={16} /> {busyLabel === "Elemzés fut..." ? "Elemzés fut..." : "OpenCV elemzés indítása"}
              </button>
              <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50" disabled={busy || Boolean(localAIBlockedReason)} onClick={runLocalAI} type="button">
                <Play size={16} /> Local AI elemzés
              </button>
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
            <details className="mt-4 rounded-lg border border-slate-800 bg-slate-950/25 p-3">
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
            </details>
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
                <details className="rounded-lg border border-slate-800 bg-slate-950/25 p-3">
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
                </details>
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
                <div className="grid grid-cols-2 gap-2">
                  <StatCard label="Overall score" value={formatNumber(report.scores.overall_score)} tone="good" />
                  <StatCard label="Grade range" value={`${report.estimated_grade_range.estimated_grade_low ?? "-"} - ${report.estimated_grade_range.estimated_grade_high ?? "-"}`} tone="warn" />
                  <StatCard label="Centering" value={formatNumber(report.scores.centering_score)} />
                  <StatCard label="Corners" value={formatNumber(report.scores.corners_score)} />
                  <StatCard label="Edges" value={formatNumber(report.scores.edges_score)} />
                  <StatCard label="Surface" value={formatNumber(report.scores.surface_score)} />
                </div>
                {(report.latest_centering || latestCentering) && (
                  <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 p-4 text-sm text-cyan-100">
                    <div className="font-semibold">Centering: L/R {(report.latest_centering ?? latestCentering)?.horizontal_ratio_label}, T/B {(report.latest_centering ?? latestCentering)?.vertical_ratio_label} (manual)</div>
                    <div className="mt-1">Score: {formatNumber((report.latest_centering ?? latestCentering)?.centering_score)} · {(report.latest_centering ?? latestCentering)?.estimated_grade_label}</div>
                    {centeringMeasurements.length > 1 && (
                      <div className="mt-3 space-y-1 text-xs text-cyan-200/80">
                        {centeringMeasurements.slice(0, 3).map((measurement) => (
                          <div key={measurement.id}>
                            {measurement.side}: L/R {measurement.horizontal_ratio_label}, T/B {measurement.vertical_ratio_label} · {formatDate(measurement.created_at)}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
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

                <InlineNotice notice={notice} scope="report" />

                <details className="rounded-lg border border-slate-800 bg-slate-950/25 p-3">
                  <summary className="cursor-pointer text-sm font-medium text-slate-300">Fejlesztői / Debug eszközök</summary>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="inline-flex items-center gap-2 rounded-lg border border-blue-500/40 px-3 py-2 text-sm text-blue-200 hover:bg-blue-500/10 disabled:opacity-60" disabled={busy || !latestAnalysis} onClick={refreshScore} type="button">
                      <RefreshCw size={16} /> Score/report frissítése
                    </button>
                    <button className="inline-flex items-center gap-2 rounded-lg border border-amber-500/40 px-3 py-2 text-sm text-amber-200 hover:bg-amber-500/10 disabled:opacity-60" disabled={busy || !latestAnalysis || visibleFindings.length === 0} onClick={generateAnnotations} type="button">
                      Annotációk generálása
                    </button>
                  </div>
                </details>

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
          latest={latestCentering}
          busy={busy}
          onCancel={() => setShowCenteringEditor(false)}
          onSave={saveCenteringMeasurement}
        />
      )}

      {workOverlay && <GlobalLoadingOverlay title={workOverlay.title} subtitle={workOverlay.subtitle} steps={workOverlay.steps} />}

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
              <img className="mx-auto max-h-[78vh] rounded-lg object-contain" src={mediaUrl(previewAsset.file_path, cacheKeyFor(previewAsset))} alt={previewAsset.label ?? "preview"} />
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

function linesFromMeasurement(measurement: CenteringMeasurement | null, width: number, height: number): CenteringLines {
  if (!measurement || measurement.image_width !== width || measurement.image_height !== height) return defaultLines(width, height);
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
  const shiftX = horizontal.first > horizontal.second ? "shifted right" : horizontal.second > horizontal.first ? "shifted left" : "balanced";
  const shiftY = vertical.first > vertical.second ? "shifted down" : vertical.second > vertical.first ? "shifted up" : "balanced";
  return { horizontal, vertical, grade, score: Math.round(score * 10) / 10, shiftX, shiftY };
}

function CenteringEditor({
  sources,
  latest,
  busy,
  onCancel,
  onSave,
}: {
  sources: { front: CenteringSource | null; back: CenteringSource | null };
  latest: CenteringMeasurement | null;
  busy: boolean;
  onCancel: () => void;
  onSave: (payload: Partial<CenteringMeasurement>) => void;
}) {
  const [side, setSide] = useState<"front" | "back">(sources.front ? "front" : "back");
  const [natural, setNatural] = useState({ width: 0, height: 0 });
  const [lines, setLines] = useState<CenteringLines | null>(null);
  const [dragging, setDragging] = useState<LineKey | null>(null);
  const source = sources[side] ?? sources.front ?? sources.back;
  const result = lines ? liveCentering(lines) : null;

  useEffect(() => {
    setLines(null);
    setNatural({ width: 0, height: 0 });
  }, [side, source?.file_path]);

  const initializeLines = (width: number, height: number) => {
    setNatural({ width, height });
    setLines(linesFromMeasurement(latest?.side === side ? latest : null, width, height));
  };

  const updateLine = (event: PointerEvent<SVGSVGElement>) => {
    if (!dragging || !lines || natural.width <= 0 || natural.height <= 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * natural.width;
    const y = ((event.clientY - rect.top) / rect.height) * natural.height;
    setLines((current) => {
      if (!current) return current;
      const next = { ...current };
      if (dragging.includes("left") || dragging.includes("right")) {
        next[dragging] = Math.max(0, Math.min(natural.width, x));
      } else {
        next[dragging] = Math.max(0, Math.min(natural.height, y));
      }
      return next;
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
      ...lines,
    });
  };

  const lineClass = (key: LineKey) => key.startsWith("outer") ? "stroke-rose-500" : "stroke-sky-400";
  const lineWidth = 3;
  const scaleX = (value: number) => `${(value / Math.max(1, natural.width)) * 100}%`;
  const scaleY = (value: number) => `${(value / Math.max(1, natural.height)) * 100}%`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="max-h-[94vh] w-full max-w-6xl overflow-auto rounded-xl border border-slate-700 bg-charcoal-900 p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">Centering beállítása</h2>
            <p className="mt-1 text-sm text-slate-400">Piros: külső kártyaszél. Kék: belső artwork/border határ.</p>
          </div>
          <div className="flex gap-2">
            <button className={`rounded-lg px-3 py-2 text-sm ${side === "front" ? "bg-blue-600 text-white" : "border border-slate-700 text-slate-300"}`} disabled={!sources.front} onClick={() => setSide("front")} type="button">Front</button>
            <button className={`rounded-lg px-3 py-2 text-sm ${side === "back" ? "bg-blue-600 text-white" : "border border-slate-700 text-slate-300"}`} disabled={!sources.back} onClick={() => setSide("back")} type="button">Back</button>
          </div>
        </div>

        {!source ? (
          <EmptyState label="Nincs használható front/back kép a centering szerkesztőhöz." />
        ) : (
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="flex justify-center overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
              <div className="relative inline-block max-h-[72vh] max-w-full">
                <img
                  className="block max-h-[72vh] w-auto max-w-full select-none"
                  src={mediaUrl(source.file_path, cacheKeyFor(source))}
                  alt={source.label ?? side}
                  onLoad={(event) => initializeLines(event.currentTarget.naturalWidth, event.currentTarget.naturalHeight)}
                  draggable={false}
                />
                {lines && natural.width > 0 && (
                  <svg
                    className="absolute inset-0 h-full w-full touch-none"
                    onPointerMove={updateLine}
                    onPointerUp={() => setDragging(null)}
                    onPointerLeave={() => setDragging(null)}
                    viewBox={`0 0 ${natural.width} ${natural.height}`}
                    preserveAspectRatio="none"
                  >
                    {(["outer_left_px", "outer_right_px", "inner_left_px", "inner_right_px"] as LineKey[]).map((key) => (
                      <line key={key} x1={lines[key]} x2={lines[key]} y1={0} y2={natural.height} className={`${lineClass(key)} cursor-ew-resize`} strokeWidth={lineWidth} onPointerDown={() => setDragging(key)} />
                    ))}
                    {(["outer_top_px", "outer_bottom_px", "inner_top_px", "inner_bottom_px"] as LineKey[]).map((key) => (
                      <line key={key} x1={0} x2={natural.width} y1={lines[key]} y2={lines[key]} className={`${lineClass(key)} cursor-ns-resize`} strokeWidth={lineWidth} onPointerDown={() => setDragging(key)} />
                    ))}
                  </svg>
                )}
              </div>
            </div>

            <div className="space-y-3">
              {result && (
                <div className="rounded-lg border border-cyan-500/25 bg-cyan-500/10 p-4 text-sm text-cyan-100">
                  <div className="text-base font-semibold">{result.grade}</div>
                  <div className="mt-2">L/R: {result.horizontal.label}</div>
                  <div>T/B: {result.vertical.label}</div>
                  <div>Score: {formatNumber(result.score)}</div>
                  <div className="mt-2 text-cyan-200">{result.shiftX} · {result.shiftY}</div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-2">
                <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={() => natural.width && setLines(defaultLines(natural.width, natural.height))} type="button">Reset lines</button>
                <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={() => natural.width && setLines(defaultLines(natural.width, natural.height))} type="button">Auto place lines</button>
                <button className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy || !lines} onClick={save} type="button">Save measurement</button>
                <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800" onClick={onCancel} type="button">Cancel</button>
              </div>
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
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
