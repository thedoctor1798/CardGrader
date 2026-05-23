import { Plus, RefreshCw, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { Card, OwnedCardWithCard } from "../api/types";
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
  const [existingCardId, setExistingCardId] = useState<number | null>(null);
  const [cardForm, setCardForm] = useState<CardForm>(emptyCardForm);
  const [copyForm, setCopyForm] = useState<CopyForm>(emptyCopyForm);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ownedCards, cardList] = await Promise.all([api.getOwnedCards(), api.getCards()]);
      setCards(cardList);
      const withCards = await Promise.all(
        ownedCards.map(async (ownedCard) => {
          const card = cardList.find((item) => item.id === ownedCard.card_id) ?? null;
          try {
            const price = await api.getLatestOwnedCardPrice(ownedCard.id);
            return { ...ownedCard, card, latest_raw_price_huf: price.raw_price_huf };
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
            className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:opacity-60"
            disabled={busy}
            onClick={() => setShowCreate(true)}
            type="button"
          >
            <Plus size={16} />
            Új kártya hozzáadása
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800/50 disabled:opacity-60"
            disabled={busy}
            onClick={seedRowlet}
            type="button"
          >
            <RefreshCw size={16} />
            Rowlet demo seed
          </button>
        </div>
      }
    >
      {message && <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {error && <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
      <div className="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-sm text-blue-100">
        A demo seed mostantól nem hoz létre duplikátumot. Az elsődleges út az új kártya hozzáadása.
      </div>

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
                  <td className="px-4 py-4 text-slate-300">{formatHuf(item.latest_raw_price_huf)}</td>
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
