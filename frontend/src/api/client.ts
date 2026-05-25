import type {
  AnalysisReport,
  AnalysisRunDetail,
  AnalysisRun,
  AnalysisFinding,
  AnnotationResponse,
  AppInfo,
  Card,
  CardMedia,
  CenteringMeasurement,
  DerivedMediaCreate,
  CleanupGeneratedMediaResponse,
  CollectionSnapshot,
  CollectionSummary,
  CollectionValuation,
  DemoSeedResponse,
  LocalAIStatus,
  LocalAIAnalysisResponse,
  LocalAIConfig,
  LocalAIDebugSingleImageResponse,
  LocalAIDryRun,
  LocalAITestConnection,
  RemoteAIGradeResponse,
  RecognitionAcceptResponse,
  RecognitionResponse,
  OwnedCard,
  ManualPriceCreate,
  PriceFetchRequest,
  PriceFetchResponse,
  PriceHistoryEntry,
  PriceHistoryResponse,
  PriceLatestResponse,
  PriceObservation,
  PriceRefreshResponse,
  ResetLocalDataResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? "http://127.0.0.1:8710" : "");

type RequestOptions = {
  notFoundAsNull?: boolean;
};

async function request<T>(path: string, init?: RequestInit, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    if (response.status === 404 && options.notFoundAsNull) {
      return null as T;
    }
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") {
        message = data.detail;
      } else if (data.detail?.message) {
        message = data.detail.message;
      } else if (data.detail?.error) {
        message = data.detail.error;
      } else {
        message = data.message ?? message;
      }
    } catch {
      // Keep the HTTP status text when the backend does not return JSON.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export function mediaUrl(filePath?: string | null, cacheKey?: string | number | null): string {
  if (!filePath) return "";
  const normalized = filePath.replace(/\\/g, "/").replace(/^media\//, "");
  const version = cacheKey === null || cacheKey === undefined || cacheKey === "" ? "" : `?v=${encodeURIComponent(String(cacheKey))}`;
  return `${API_BASE_URL}/media/${normalized}${version}`;
}

export const api = {
  getAppInfo: () => request<AppInfo>("/api/app/info"),
  getLocalAIStatus: () => request<LocalAIStatus>("/api/local-ai/status"),
  getLocalAIConfig: () => request<LocalAIConfig>("/api/local-ai/config"),
  testLocalAIConnection: () => request<LocalAITestConnection>("/api/local-ai/test-connection", { method: "POST" }),
  getCollectionSummary: () => request<CollectionSummary>("/api/collection/summary"),
  getCollectionValuation: () => request<CollectionValuation>("/api/collection/valuation"),
  getCollectionSnapshots: () => request<CollectionSnapshot[]>("/api/collection/snapshots"),
  createCollectionSnapshot: () => request<CollectionSnapshot>("/api/collection/snapshot", { method: "POST" }),
  getOwnedCards: () => request<OwnedCard[]>("/api/owned-cards"),
  getOwnedCard: (id: number) => request<OwnedCard>(`/api/owned-cards/${id}`),
  createOwnedCard: (body: Partial<OwnedCard>) =>
    request<OwnedCard>("/api/owned-cards", { method: "POST", body: JSON.stringify(body) }),
  updateOwnedCard: (id: number, body: Partial<OwnedCard>) =>
    request<OwnedCard>(`/api/owned-cards/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  getCards: () => request<Card[]>("/api/cards"),
  getCard: (id: number) => request<Card>(`/api/cards/${id}`),
  createCard: (body: Partial<Card>) => request<Card>("/api/cards", { method: "POST", body: JSON.stringify(body) }),
  updateCard: (id: number, body: Partial<Card>) =>
    request<Card>(`/api/cards/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  seedRowlet: () => request<DemoSeedResponse>("/api/demo/seed-rowlet", { method: "POST" }),
  resetLocalData: () => request<ResetLocalDataResponse>("/api/demo/reset-local-data", { method: "POST" }),
  cleanupGeneratedMedia: () => request<CleanupGeneratedMediaResponse>("/api/demo/cleanup-generated-media", { method: "POST" }),
  getOwnedCardMedia: (id: number) => request<CardMedia[]>(`/api/owned-cards/${id}/media`),
  uploadMedia: (ownedCardId: number, label: string, file: File) => {
    const body = new FormData();
    body.append("label", label);
    body.append("file", file);
    return request<CardMedia>(`/api/owned-cards/${ownedCardId}/media`, { method: "POST", body });
  },
  createDerivedMedia: (mediaId: number, body: DerivedMediaCreate) =>
    request<CardMedia>(`/api/media/${mediaId}/derive`, { method: "POST", body: JSON.stringify(body) }),
  recognizeCardFromMedia: (mediaId: number) =>
    request<RecognitionResponse>(`/api/media/${mediaId}/recognize-card`, { method: "POST" }),
  acceptRecognitionCandidate: (attemptId: number, catalogCardId: number, ownedCardId?: number | null, createOwnedCard = false) =>
    request<RecognitionAcceptResponse>(`/api/recognition-attempts/${attemptId}/accept`, {
      method: "POST",
      body: JSON.stringify({
        catalog_card_id: catalogCardId,
        owned_card_id: ownedCardId ?? null,
        create_owned_card: createOwnedCard,
      }),
    }),
  getLatestOwnedCardPrice: (id: number) =>
    request<PriceObservation | null>(`/api/owned-cards/${id}/latest-price`, undefined, { notFoundAsNull: true }),
  getLatestOwnedCardPriceHistory: (id: number) =>
    request<PriceLatestResponse>(`/api/owned-cards/${id}/prices/latest`),
  getLatestCardPriceHistory: (cardId: number) =>
    request<PriceLatestResponse>(`/api/prices/latest/${cardId}`),
  getPriceHistory: (cardId: number) =>
    request<PriceHistoryResponse>(`/api/prices/history/${cardId}`),
  fetchCardPrices: (cardId: number, body: PriceFetchRequest = {}) =>
    request<PriceFetchResponse>(`/api/prices/fetch/${cardId}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  createManualPrice: (body: ManualPriceCreate) =>
    request<PriceHistoryEntry>("/api/prices/manual", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  refreshOwnedPrices: () => request<PriceRefreshResponse>("/api/prices/refresh-owned", { method: "POST" }),
  refreshAllPrices: () => request<PriceRefreshResponse>("/api/prices/refresh-all", { method: "POST" }),
  createPrice: (cardId: number, body: Partial<PriceObservation>) =>
    request<PriceObservation>(`/api/cards/${cardId}/prices`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getAnalysisRuns: (ownedCardId: number) => request<AnalysisRun[]>(`/api/owned-cards/${ownedCardId}/analysis-runs`),
  getAnalysisRunDetail: (analysisRunId: number) => request<AnalysisRunDetail>(`/api/analysis-runs/${analysisRunId}`),
  runOpenCvAnalysis: (ownedCardId: number) =>
    request<AnalysisRun>(`/api/owned-cards/${ownedCardId}/analyze/opencv`, { method: "POST" }),
  runLocalAIFastAnalysis: (ownedCardId: number) =>
    request<LocalAIAnalysisResponse>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-fast`, { method: "POST" }),
  runLocalAIFrontAnalysis: (ownedCardId: number) =>
    request<LocalAIAnalysisResponse>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-front`, { method: "POST" }),
  runLocalAIBackAnalysis: (ownedCardId: number) =>
    request<LocalAIAnalysisResponse>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-back`, { method: "POST" }),
  runLocalAIAggregate: (ownedCardId: number) =>
    request<{ analysis_run: AnalysisRun; finding_count: number; report: AnalysisReport }>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-aggregate`, { method: "POST" }),
  runLocalAIFullReview: (ownedCardId: number) =>
    request<{ aggregate: { analysis_run: AnalysisRun; finding_count: number; report: AnalysisReport } }>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-full-review`, { method: "POST" }),
  runRemoteAIGrade: (ownedCardId: number) =>
    request<RemoteAIGradeResponse>(`/api/owned-cards/${ownedCardId}/analyze/remote-ai-grade`, { method: "POST" }),
  runLocalAIDryRun: (ownedCardId: number) =>
    request<LocalAIDryRun>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-dry-run`, { method: "POST" }),
  runLocalAIDryRunForPass: (ownedCardId: number, passType: "front" | "back" | "fast" | "full") =>
    request<LocalAIDryRun>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-dry-run?pass_type=${passType}`, { method: "POST" }),
  runLocalAIDebugSingleImage: (ownedCardId: number) =>
    request<LocalAIDebugSingleImageResponse>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-debug-single-image`, { method: "POST" }),
  scoreAnalysisRun: (analysisRunId: number) =>
    request<AnalysisRun>(`/api/analysis-runs/${analysisRunId}/score`, { method: "POST" }),
  annotateAnalysisRun: (analysisRunId: number) =>
    request<AnnotationResponse>(`/api/analysis-runs/${analysisRunId}/annotate`, { method: "POST" }),
  getAnalysisReport: (analysisRunId: number) => request<AnalysisReport>(`/api/analysis-runs/${analysisRunId}/report`),
  getAnalysisFindings: (analysisRunId: number) => request<AnalysisFinding[]>(`/api/analysis-runs/${analysisRunId}/findings`),
  getCenteringMeasurements: (ownedCardId: number) =>
    request<CenteringMeasurement[]>(`/api/owned-cards/${ownedCardId}/centering-measurements`),
  getLatestCentering: (ownedCardId: number) => request<CenteringMeasurement>(`/api/owned-cards/${ownedCardId}/latest-centering`),
  createCenteringMeasurement: (ownedCardId: number, body: Partial<CenteringMeasurement>) =>
    request<CenteringMeasurement>(`/api/owned-cards/${ownedCardId}/centering-measurements`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};
