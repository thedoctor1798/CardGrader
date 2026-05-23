import type {
  AnalysisReport,
  AnalysisRun,
  AnalysisFinding,
  AnnotationResponse,
  AppInfo,
  Card,
  CardMedia,
  CleanupGeneratedMediaResponse,
  CollectionSnapshot,
  CollectionSummary,
  DemoSeedResponse,
  LocalAIStatus,
  LocalAIAnalysisResponse,
  LocalAIConfig,
  LocalAIDebugSingleImageResponse,
  LocalAIDryRun,
  LocalAITestConnection,
  OwnedCard,
  PriceObservation,
  ResetLocalDataResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8710";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const data = await response.json();
      message = data.detail ?? message;
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

export function mediaUrl(filePath?: string | null): string {
  if (!filePath) return "";
  const normalized = filePath.replace(/\\/g, "/").replace(/^media\//, "");
  return `${API_BASE_URL}/media/${normalized}`;
}

export const api = {
  getAppInfo: () => request<AppInfo>("/api/app/info"),
  getLocalAIStatus: () => request<LocalAIStatus>("/api/local-ai/status"),
  getLocalAIConfig: () => request<LocalAIConfig>("/api/local-ai/config"),
  testLocalAIConnection: () => request<LocalAITestConnection>("/api/local-ai/test-connection", { method: "POST" }),
  getCollectionSummary: () => request<CollectionSummary>("/api/collection/summary"),
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
  getLatestOwnedCardPrice: (id: number) => request<PriceObservation>(`/api/owned-cards/${id}/latest-price`),
  createPrice: (cardId: number, body: Partial<PriceObservation>) =>
    request<PriceObservation>(`/api/cards/${cardId}/prices`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  getAnalysisRuns: (ownedCardId: number) => request<AnalysisRun[]>(`/api/owned-cards/${ownedCardId}/analysis-runs`),
  runOpenCvAnalysis: (ownedCardId: number) =>
    request<AnalysisRun>(`/api/owned-cards/${ownedCardId}/analyze/opencv`, { method: "POST" }),
  runLocalAIFastAnalysis: (ownedCardId: number) =>
    request<LocalAIAnalysisResponse>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-fast`, { method: "POST" }),
  runLocalAIDryRun: (ownedCardId: number) =>
    request<LocalAIDryRun>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-dry-run`, { method: "POST" }),
  runLocalAIDebugSingleImage: (ownedCardId: number) =>
    request<LocalAIDebugSingleImageResponse>(`/api/owned-cards/${ownedCardId}/analyze/local-ai-debug-single-image`, { method: "POST" }),
  scoreAnalysisRun: (analysisRunId: number) =>
    request<AnalysisRun>(`/api/analysis-runs/${analysisRunId}/score`, { method: "POST" }),
  annotateAnalysisRun: (analysisRunId: number) =>
    request<AnnotationResponse>(`/api/analysis-runs/${analysisRunId}/annotate`, { method: "POST" }),
  getAnalysisReport: (analysisRunId: number) => request<AnalysisReport>(`/api/analysis-runs/${analysisRunId}/report`),
  getAnalysisFindings: (analysisRunId: number) => request<AnalysisFinding[]>(`/api/analysis-runs/${analysisRunId}/findings`),
};
