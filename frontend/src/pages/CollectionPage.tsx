import { ImagePlus, Play, Plus, RefreshCw, Upload, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api, mediaUrl } from "../api/client";
import type { Card, CardMedia, OwnedCardWithCard, RecognitionCandidate, RecognitionResponse } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { formatHuf } from "../utils/format";

const statuses = ["raw_owned", "graded_owned", "sent_to_grading", "listed_for_sale", "sold", "kept_long_term"];
const sources = ["pack", "blister", "single_purchase", "trade", "unknown"];

type CollectionPageProps = {
  onOpenOwnedCard: (id: number) => void;
};

type CardForm = {
  name: string;
  set_name: string;
  set_code: string;
  card_number: string;
  language: string;
  rarity: string;
  variant: string;
  notes: string;
};

type CopyForm = {
  copy_label: string;
  status: string;
  acquired_price_huf: string;
  acquired_source: string;
  acquired_at: string;
  storage_location: string;
  personal_notes: string;
};

const emptyCardForm: CardForm = {
  name: "",
  set_name: "",
  set_code: "",
  card_number: "",
  language: "",
  rarity: "",
  variant: "",
  notes: "",
};

const emptyCopyForm: CopyForm = {
  copy_label: "",
  status: "raw_owned",
  acquired_price_huf: "",
  acquired_source: "unknown",
  acquired_at: "",
  storage_location: "",
  personal_notes: "",
};

function clean(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function optionalInt(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const parsed = Number(trimmed.replace(",", "."));
  return Number.isFinite(parsed) ? Math.round(parsed) : null;
}

function entryValueHuf(entry?: { converted_market_price?: number | null; converted_raw_price?: number | null; market_price?: number | null; raw_price?: number | null; currency?: string | null } | null): number | null {
  if (!entry) return null;
  if (entry.converted_market_price !== null && entry.converted_market_price !== undefined) return entry.converted_market_price;
  if (entry.converted_raw_price !== null && entry.converted_raw_price !== undefined) return entry.converted_raw_price;
  if (entry.currency === "HUF") return entry.market_price ?? entry.raw_price ?? null;
  return null;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="space-y-1.5 text-xs font-medium text-slate-400">
      <span>{label}</span>
      {children}
    </label>
  );
}

export function CollectionPage({ onOpenOwnedCard }: CollectionPageProps) {
  const [items, setItems] = useState<OwnedCardWithCard[]>([]);
  const [cards, setCards] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showImageAdd, setShowImageAdd] = useState(false);
  const [existingCardId, setExistingCardId] = useState<number | null>(null);
  const [cardForm, setCardForm] = useState<CardForm>(emptyCardForm);
  const [copyForm, setCopyForm] = useState<CopyForm>(emptyCopyForm);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [recognitionFile, setRecognitionFile] = useState<File | null>(null);
  const [recognitionMedia, setRecognitionMedia] = useState<CardMedia | null>(null);
  const [recognitionResult, setRecognitionResult] = useState<RecognitionResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ownedCards, cardList] = await Promise.all([api.getOwnedCards(), api.getCards()]);
      setCards(cardList);
      const withCards = await Promise.all(
        ownedCards.map(async (ownedCard) => {
          const card = cardList.find((item) => item.id === ownedCard.card_id) ?? null;
          try {
            const price = await api.getLatestOwnedCardPriceHistory(ownedCard.id);
            if (price.latest) {
              return { ...ownedCard, card, latest_raw_price_huf: entryValueHuf(price.latest) };
            }
            const legacyPrice = await api.getLatestOwnedCardPrice(ownedCard.id);
            return { ...ownedCard, card, latest_raw_price_huf: legacyPrice?.raw_price_huf ?? null };
          } catch {
            return { ...ownedCard, card, latest_raw_price_huf: null };
          }
        }),
      );
      setItems(withCards);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const likelyDuplicate = useMemo(() => {
    const name = cardForm.name.trim().toLowerCase();
    const setCode = cardForm.set_code.trim().toLowerCase();
    const number = cardForm.card_number.trim().toLowerCase();
    if (!name || !setCode || !number) return null;
    return cards.find(
      (card) =>
        card.name.trim().toLowerCase() === name &&
        (card.set_code ?? "").trim().toLowerCase() === setCode &&
        (card.card_number ?? "").trim().toLowerCase() === number,
    ) ?? null;
  }, [cardForm.card_number, cardForm.name, cardForm.set_code, cards]);

  const resetForm = () => {
    setCardForm(emptyCardForm);
    setCopyForm(emptyCopyForm);
    setExistingCardId(null);
  };

  const recognitionAttemptId = recognitionResult?.recognition_attempt?.id ?? recognitionResult?.recognition_attempt_id ?? null;
  const extracted = recognitionResult?.recognition_attempt?.extracted;

  const recognitionErrorMessage = (err: unknown, fallback: string) => {
    const message = err instanceof Error ? err.message : fallback;
    const lower = message.toLowerCase();
    if (lower.includes("worker") || lower.includes("local_ai_worker") || lower.includes("connection")) {
      return "Az AI worker nem elérhető. Ellenőrizd a Windows gépet, Tailscale-t és LM Studio-t.";
    }
    if (lower.includes("json")) {
      return "Nem sikerült felismerni a kártyát. Ellenőrizd, hogy LM Studio-ban a thinking/reasoning ki van kapcsolva.";
    }
    if (lower.includes("unsupported") || lower.includes("file type")) {
      return "Nem támogatott fájltípus. Használj JPG, PNG vagy WEBP képet.";
    }
    return message || fallback;
  };

  const uploadRecognitionImage = async (event: FormEvent) => {
    event.preventDefault();
    if (!recognitionFile) {
      setError("Válassz ki egy teljes front kártyaképet.");
      return;
    }
    setBusy(true);
    setMessage(null);
    setRecognitionResult(null);
    try {
      const uploaded = await api.uploadRecognitionMedia(recognitionFile, "front");
      setRecognitionMedia(uploaded.media);
      setMessage("Kép feltöltve. Indíthatod a kártya felismerést.");
      setError(null);
    } catch (err) {
      setError(recognitionErrorMessage(err, "Nem sikerült feltölteni a képet."));
    } finally {
      setBusy(false);
    }
  };

  const recognizeUploadedImage = async () => {
    if (!recognitionMedia) {
      setError("Nincs media rekord a felismeréshez. Tölts fel előbb egy képet.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.recognizeCardFromMedia(recognitionMedia.id);
      setRecognitionResult(result);
      if (result.ok) {
        setMessage(result.candidates.length > 0 ? `Felismerés kész. Találatok: ${result.candidates.length}.` : "Nem találtunk biztos találatot a katalógusban.");
      } else {
        setError(result.message || "Nem sikerült felismerni a kártyát.");
      }
    } catch (err) {
      setError(recognitionErrorMessage(err, "Nem sikerült felismerni a kártyát."));
    } finally {
      setBusy(false);
    }
  };

  const acceptImageCandidate = async (candidate: RecognitionCandidate) => {
    if (!recognitionAttemptId) {
      setError("Hiányzó felismerési azonosító. Futtasd újra a felismerést.");
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const accepted = await api.acceptRecognitionCandidate(recognitionAttemptId, candidate.catalog_card_id, null, true);
      await load();
      setShowImageAdd(false);
      setRecognitionFile(null);
      setRecognitionMedia(null);
      setRecognitionResult(null);
      setMessage(`Kártya hozzáadva: ${accepted.owned_card.name}.`);
      onOpenOwnedCard(accepted.owned_card.id);
    } catch (err) {
      setError(recognitionErrorMessage(err, "Nem sikerült elfogadni a találatot."));
    } finally {
      setBusy(false);
    }
  };

  const prefillManualFromRecognition = () => {
    setCardForm({
      ...emptyCardForm,
      name: extracted?.name ?? "",
      set_name: extracted?.set_text ?? "",
      set_code: extracted?.set_code ?? "",
      card_number: extracted?.card_number ?? "",
      rarity: extracted?.rarity ?? "",
      language: extracted?.language ?? "",
    });
    setCopyForm(emptyCopyForm);
    setExistingCardId(null);
    setShowCreate(true);
    setShowImageAdd(false);
    setMessage("A kézi űrlapot előtöltöttem a felismerés alapján.");
  };

  const seedRowlet = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.seedRowlet();
      await load();
      setMessage(result.created ? "Rowlet demo létrehozva." : "Rowlet demo már létezik, megnyitva/frissítve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    } finally {
      setBusy(false);
    }
  };

  const submitCreate = async (event: FormEvent) => {
    event.preventDefault();
    if (!cardForm.name.trim()) {
      setError("A kártya neve kötelező.");
      return;
    }
    let useExisting = existingCardId;
    if (!useExisting && likelyDuplicate) {
      const confirmed = window.confirm("Ez a kártya már létezhet. Új példányt szeretnél hozzáadni meglévő kártyához?");
      if (confirmed) useExisting = likelyDuplicate.id;
    }

    setBusy(true);
    setMessage(null);
    try {
      const card = useExisting
        ? cards.find((item) => item.id === useExisting) ?? await api.getCard(useExisting)
        : await api.createCard({
          name: cardForm.name.trim(),
          set_name: clean(cardForm.set_name),
          set_code: clean(cardForm.set_code),
          card_number: clean(cardForm.card_number),
          language: clean(cardForm.language),
          rarity: clean(cardForm.rarity),
          variant: clean(cardForm.variant),
          notes: clean(cardForm.notes),
        });
      const owned = await api.createOwnedCard({
        card_id: card.id,
        copy_label: clean(copyForm.copy_label),
        status: copyForm.status,
        acquired_price_huf: optionalInt(copyForm.acquired_price_huf),
        acquired_source: copyForm.acquired_source,
        acquired_at: clean(copyForm.acquired_at),
        storage_location: clean(copyForm.storage_location),
        personal_notes: clean(copyForm.personal_notes),
      });
      await load();
      resetForm();
      setShowCreate(false);
      setMessage("Kártya hozzáadva.");
      onOpenOwnedCard(owned.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kártya létrehozási hiba");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="Gyűjtemény betöltése..." />;

  return (
    <Panel
      title="Gyűjtemény"
      subtitle="Saját kártyák és owned copy rekordok a helyi SQLite adatbázisból."
      action={
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60"
            disabled={busy}
            onClick={() => setShowImageAdd((current) => !current)}
            type="button"
          >
            <ImagePlus size={16} />
            Kép alapján hozzáadás
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
            disabled={busy}
            onClick={() => setShowCreate(true)}
            type="button"
          >
            <Plus size={16} />
            Új kártya hozzáadása
          </button>
        </div>
      }
    >
      {message && <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {error && <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
      <div className="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-sm text-blue-100">
        A demo seed mostantól nem hoz létre duplikátumot. Az elsődleges út az új kártya hozzáadása.
      </div>

      {showImageAdd && (
        <div className="mb-5 rounded-xl border border-emerald-500/25 bg-emerald-500/10 p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-emerald-50">Kártya felismerése képből</h3>
              <p className="mt-1 text-sm text-emerald-100/80">Tölts fel egy teljes, éles front képet, majd indítsd a felismerést.</p>
            </div>
            <button className="rounded-lg p-2 text-emerald-100/70 hover:bg-emerald-500/10 hover:text-emerald-50" onClick={() => setShowImageAdd(false)} type="button">
              <X size={18} />
            </button>
          </div>

          <form className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]" onSubmit={uploadRecognitionImage}>
            <input
              className="w-full rounded-lg border border-emerald-500/30 bg-slate-950 px-3 py-2 text-sm text-slate-200"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              onChange={(event) => {
                setRecognitionFile(event.target.files?.[0] ?? null);
                setRecognitionMedia(null);
                setRecognitionResult(null);
              }}
            />
            <button className="inline-flex items-center justify-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy || !recognitionFile} type="submit">
              <Upload size={16} />
              Kép feltöltése
            </button>
          </form>

          {recognitionMedia && (
            <div className="mt-4 grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
              <div className="overflow-hidden rounded-lg border border-slate-800 bg-slate-950">
                <img className="max-h-80 w-full object-contain" src={mediaUrl(recognitionMedia.file_path, recognitionMedia.id)} alt="Feltöltött kártya" />
              </div>
              <div className="space-y-3">
                <button
                  className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
                  disabled={busy}
                  onClick={recognizeUploadedImage}
                  type="button"
                >
                  <Play size={16} />
                  Kártya felismerése
                </button>

                {extracted && (
                  <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"><span className="text-slate-500">Név</span><div className="mt-1 text-slate-100">{extracted.name || "-"}</div></div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"><span className="text-slate-500">Szám</span><div className="mt-1 text-slate-100">{extracted.card_number || "-"}</div></div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"><span className="text-slate-500">Set</span><div className="mt-1 text-slate-100">{extracted.set_text || extracted.set_code || "-"}</div></div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"><span className="text-slate-500">Set kód</span><div className="mt-1 text-slate-100">{extracted.set_code || "-"}</div></div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"><span className="text-slate-500">Ritkaság</span><div className="mt-1 text-slate-100">{extracted.rarity || "-"}</div></div>
                    <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm"><span className="text-slate-500">Nyelv</span><div className="mt-1 text-slate-100">{extracted.language || "-"}</div></div>
                  </div>
                )}

                {recognitionResult?.ok && recognitionResult.candidates.length === 0 && (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
                    Nem találtunk biztos találatot a katalógusban. Próbálj teljesebb, élesebb front képet, vagy használd a kézi megadást.
                  </div>
                )}

                {recognitionResult?.candidates.length ? (
                  <div className="space-y-2">
                    {recognitionResult.candidates.map((candidate) => (
                      <div key={candidate.id} className="rounded-lg border border-slate-800 bg-slate-950/45 p-3">
                        <div className="flex gap-3">
                          {candidate.thumbnail_file_path && (
                            <img className="h-20 w-14 rounded border border-slate-800 object-cover" src={mediaUrl(candidate.thumbnail_file_path, candidate.id)} alt={candidate.name} />
                          )}
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-start justify-between gap-2">
                              <div>
                                <div className="font-medium text-slate-50">{candidate.rank}. {candidate.name}</div>
                                <div className="mt-1 text-xs text-slate-400">
                                  {[candidate.set_name, candidate.set_code, candidate.card_number, candidate.rarity, candidate.language].filter(Boolean).join(" · ") || "-"}
                                </div>
                              </div>
                              <span className="rounded-full border border-emerald-500/30 px-2 py-0.5 text-xs text-emerald-100">{Math.round(candidate.score)}%</span>
                            </div>
                            {candidate.match_reasons.length > 0 && (
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {candidate.match_reasons.map((reason) => (
                                  <span key={reason} className="rounded-full border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300">{reason}</span>
                                ))}
                              </div>
                            )}
                            <div className="mt-3 flex flex-wrap gap-2">
                              <button className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy} onClick={() => acceptImageCandidate(candidate)} type="button">
                                Ez az
                              </button>
                              <button className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-800/50" onClick={recognizeUploadedImage} type="button">
                                Másikat választok
                              </button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : null}

                <button className="rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-200 hover:bg-slate-800/50" onClick={prefillManualFromRecognition} type="button">
                  Kézi megadás
                </button>
              </div>
            </div>
          )}
        </div>
      )}
      <details className="mb-4 rounded-lg border border-slate-800 bg-slate-950/25 p-3">
        <summary className="cursor-pointer text-sm font-medium text-slate-300">Fejlesztői / Debug eszközök</summary>
        <button
          className="mt-3 inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800/50 disabled:opacity-60"
          disabled={busy}
          onClick={seedRowlet}
          type="button"
        >
          <RefreshCw size={16} />
          Rowlet demo seed
        </button>
      </details>

      {showCreate && (
        <div className="mb-5 rounded-xl border border-slate-800 bg-slate-950/35 p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold text-slate-100">Új kártya hozzáadása</h3>
              <p className="mt-1 text-sm text-slate-400">Először létrejön a card rekord, utána az owned copy.</p>
            </div>
            <button className="rounded-lg p-2 text-slate-400 hover:bg-slate-800 hover:text-slate-100" onClick={() => setShowCreate(false)} type="button">
              <X size={18} />
            </button>
          </div>

          {likelyDuplicate && !existingCardId && (
            <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
              Ez a kártya már létezhet: {likelyDuplicate.name} / {likelyDuplicate.set_code} / {likelyDuplicate.card_number}. Választhatod meglévő kártyaként is.
              <button className="ml-3 rounded border border-amber-400/40 px-2 py-1 text-xs" onClick={() => setExistingCardId(likelyDuplicate.id)} type="button">
                Meglévőhöz új példány
              </button>
            </div>
          )}

          <form className="space-y-5" onSubmit={submitCreate}>
            <div>
              <h4 className="mb-3 text-sm font-semibold text-slate-200">Card adatok</h4>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Field label="Név"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.name} onChange={(event) => setCardForm({ ...cardForm, name: event.target.value })} /></Field>
                <Field label="Set név"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.set_name} onChange={(event) => setCardForm({ ...cardForm, set_name: event.target.value })} /></Field>
                <Field label="Set kód"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.set_code} onChange={(event) => setCardForm({ ...cardForm, set_code: event.target.value })} /></Field>
                <Field label="Kártyaszám"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.card_number} onChange={(event) => setCardForm({ ...cardForm, card_number: event.target.value })} /></Field>
                <Field label="Nyelv"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.language} onChange={(event) => setCardForm({ ...cardForm, language: event.target.value })} /></Field>
                <Field label="Rarity"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.rarity} onChange={(event) => setCardForm({ ...cardForm, rarity: event.target.value })} /></Field>
                <Field label="Variant"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.variant} onChange={(event) => setCardForm({ ...cardForm, variant: event.target.value })} /></Field>
                <Field label="Megjegyzés"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={cardForm.notes} onChange={(event) => setCardForm({ ...cardForm, notes: event.target.value })} /></Field>
              </div>
            </div>

            <div>
              <h4 className="mb-3 text-sm font-semibold text-slate-200">Owned copy adatok</h4>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                <Field label="Copy label"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={copyForm.copy_label} onChange={(event) => setCopyForm({ ...copyForm, copy_label: event.target.value })} /></Field>
                <Field label="Status"><select className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={copyForm.status} onChange={(event) => setCopyForm({ ...copyForm, status: event.target.value })}>{statuses.map((status) => <option key={status}>{status}</option>)}</select></Field>
                <Field label="Bekerülési ár"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" inputMode="numeric" value={copyForm.acquired_price_huf} onChange={(event) => setCopyForm({ ...copyForm, acquired_price_huf: event.target.value })} /></Field>
                <Field label="Forrás"><select className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={copyForm.acquired_source} onChange={(event) => setCopyForm({ ...copyForm, acquired_source: event.target.value })}>{sources.map((source) => <option key={source}>{source}</option>)}</select></Field>
                <Field label="Szerzés dátuma"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" type="date" value={copyForm.acquired_at} onChange={(event) => setCopyForm({ ...copyForm, acquired_at: event.target.value })} /></Field>
                <Field label="Tárolási hely"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={copyForm.storage_location} onChange={(event) => setCopyForm({ ...copyForm, storage_location: event.target.value })} /></Field>
                <Field label="Személyes megjegyzés"><input className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100" value={copyForm.personal_notes} onChange={(event) => setCopyForm({ ...copyForm, personal_notes: event.target.value })} /></Field>
              </div>
            </div>

            <button className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-60" disabled={busy} type="submit">
              <Plus size={16} />
              Kártya hozzáadása
            </button>
          </form>
        </div>
      )}

      {items.length === 0 ? (
        <EmptyState label="Még nincs owned card rekord. Hozzáadhatsz saját kártyát vagy létrehozhatod a Rowlet demót." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="min-w-full divide-y divide-slate-800 text-sm">
            <thead className="bg-slate-950/35 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Kártya</th>
                <th className="px-4 py-3">Set</th>
                <th className="px-4 py-3">Szám</th>
                <th className="px-4 py-3">Copy label</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Bekerülés</th>
                <th className="px-4 py-3">Latest raw</th>
                <th className="px-4 py-3 text-right">Művelet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 bg-charcoal-850">
              {items.map((item) => (
                <tr key={item.id} className="transition hover:bg-slate-800/40">
                  <td className="px-4 py-4 font-medium text-slate-100">{item.card?.name ?? `Card #${item.card_id}`}</td>
                  <td className="px-4 py-4 text-slate-300">{item.card?.set_name ?? "-"}</td>
                  <td className="px-4 py-4 text-slate-300">{item.card?.card_number ?? "-"}</td>
                  <td className="px-4 py-4 text-slate-300">{item.copy_label ?? "-"}</td>
                  <td className="px-4 py-4"><span className="rounded-full border border-slate-700 bg-slate-950/40 px-2 py-1 text-xs text-slate-300">{item.status ?? "-"}</span></td>
                  <td className="px-4 py-4 text-slate-300">{formatHuf(item.acquired_price_huf)}</td>
                  <td className="px-4 py-4 text-slate-300">{item.latest_raw_price_huf === null || item.latest_raw_price_huf === undefined ? "Még nincs ár" : formatHuf(item.latest_raw_price_huf)}</td>
                  <td className="px-4 py-4 text-right">
                    <button className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white shadow-sm shadow-blue-950/40 hover:bg-blue-500" onClick={() => onOpenOwnedCard(item.id)} type="button">
                      Megnyitás
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}
