import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { OwnedCardWithCard } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { formatHuf } from "../utils/format";

type CollectionPageProps = {
  onOpenOwnedCard: (id: number) => void;
};

export function CollectionPage({ onOpenOwnedCard }: CollectionPageProps) {
  const [items, setItems] = useState<OwnedCardWithCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const ownedCards = await api.getOwnedCards();
      const withCards = await Promise.all(
        ownedCards.map(async (ownedCard) => {
          try {
            const card = await api.getCard(ownedCard.card_id);
            return { ...ownedCard, card };
          } catch {
            return { ...ownedCard, card: null };
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

  if (loading) return <LoadingState label="Gyűjtemény betöltése..." />;

  return (
    <Panel
      title="Gyűjtemény"
      subtitle="Owned card rekordok a helyi SQLite adatbázisból. A demo seed mostantól nem hoz létre duplikátumot."
      action={
        <button
          className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-60"
          disabled={busy}
          onClick={seedRowlet}
          type="button"
        >
          <RefreshCw size={16} />
          Rowlet demo seed
        </button>
      }
    >
      {message && <div className="mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {error && <div className="mb-4 rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
      <div className="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-sm text-blue-100">
        A demo seed mostantól nem hoz létre duplikátumot. Régi tesztadatot nem törlünk automatikusan.
      </div>

      {items.length === 0 ? (
        <EmptyState label="Még nincs owned card rekord. A Rowlet demo seed gombbal létrehozhatsz egyet." />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="min-w-full divide-y divide-slate-800 text-sm">
            <thead className="bg-slate-950/35 text-left text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">ID</th>
                <th className="px-4 py-3">Kártya</th>
                <th className="px-4 py-3">Copy label</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Forrás</th>
                <th className="px-4 py-3">Bekerülés</th>
                <th className="px-4 py-3 text-right">Művelet</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 bg-charcoal-850">
              {items.map((item) => (
                <tr key={item.id} className="transition hover:bg-slate-800/40">
                  <td className="px-4 py-4 text-slate-400">{item.id}</td>
                  <td className="px-4 py-4">
                    <div className="font-medium text-slate-100">{item.card?.name ?? `Card #${item.card_id}`}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {[item.card?.set_name, item.card?.card_number, item.card?.language].filter(Boolean).join(" · ") || "-"}
                    </div>
                  </td>
                  <td className="px-4 py-4 text-slate-300">{item.copy_label ?? "-"}</td>
                  <td className="px-4 py-4">
                    <span className="rounded-full border border-slate-700 bg-slate-950/40 px-2 py-1 text-xs text-slate-300">
                      {item.status ?? "-"}
                    </span>
                  </td>
                  <td className="px-4 py-4 text-slate-300">{item.acquired_source ?? "-"}</td>
                  <td className="px-4 py-4 text-slate-300">{formatHuf(item.acquired_price_huf)}</td>
                  <td className="px-4 py-4 text-right">
                    <button
                      className="rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white shadow-sm shadow-blue-950/40 hover:bg-blue-400"
                      onClick={() => onOpenOwnedCard(item.id)}
                      type="button"
                    >
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
