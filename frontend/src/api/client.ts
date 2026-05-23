import type {
  AnalysisReport,
  AnalysisRun,
  Card,
  CardMedia,
  CollectionSnapshot,
  CollectionSummary,
  OwnedCard,
  PriceObservation,
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
  getCollectionSummary: () => request<CollectionSummary>("/api/collection/summary"),
  getCollectionSnapshots: () => request<CollectionSnapshot[]>("/api/collection/snapshots"),
  createCollectionSnapshot: () => request<CollectionSnapshot>("/api/collection/snapshot", { method: "POST" }),
  getOwnedCards: () => request<OwnedCard[]>("/api/owned-cards"),
  getOwnedCard: (id: number) => request<OwnedCard>(`/api/owned-cards/${id}`),
  getCard: (id: number) => request<Card>(`/api/cards/${id}`),
  seedRowlet: () => request<{ card: Card; owned_card: OwnedCard; created: boolean }>("/api/demo/seed-rowlet", { method: "POST" }),
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
  scoreAnalysisRun: (analysisRunId: number) =>
    request<AnalysisRun>(`/api/analysis-runs/${analysisRunId}/score`, { method: "POST" }),
  getAnalysisReport: (analysisRunId: number) => request<AnalysisReport>(`/api/analysis-runs/${analysisRunId}/report`),
};
