import { Camera } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { CollectionSnapshot, CollectionSummary } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";
import { formatDate, formatHuf } from "../utils/format";

export function DashboardPage() {
  const [summary, setSummary] = useState<CollectionSummary | null>(null);
  const [snapshots, setSnapshots] = useState<CollectionSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [summaryData, snapshotData] = await Promise.all([
        api.getCollectionSummary(),
        api.getCollectionSnapshots(),
      ]);
      setSummary(summaryData);
      setSnapshots(snapshotData.slice().reverse());
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

  const createSnapshot = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await api.createCollectionSnapshot();
      await load();
      setMessage("Snapshot mentve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Snapshot mentési hiba");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="Dashboard adatok betöltése..." />;
  if (error && !summary) return <EmptyState label={`Nem sikerült betölteni a dashboardot: ${error}`} />;
  if (!summary) return <EmptyState label="Nincs elérhető összesítés." />;

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-xl font-semibold text-slate-100">Dashboard</h2>
          <p className="mt-1 text-sm text-slate-400">Élő, lokális összesítés a SQLite adatbázisból.</p>
        </div>
        <button
          className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-medium text-white hover:bg-blue-400 disabled:opacity-60"
          disabled={busy}
          onClick={createSnapshot}
          type="button"
        >
          <Camera size={16} />
          Snapshot készítése
        </button>
      </div>

      {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard label="Összesített érték" value={formatHuf(summary.collection_value_huf)} tone="good" />
        <StatCard label="Bekerülési költség" value={formatHuf(summary.cost_basis_huf)} />
        <StatCard
          label="Becsült profit"
          value={formatHuf(summary.unrealized_profit_huf)}
          tone={summary.unrealized_profit_huf >= 0 ? "good" : "bad"}
        />
        <StatCard label="Kártyák száma" value={summary.total_cards} />
        <StatCard label="Egyedi kártyák" value={summary.unique_cards} />
        <StatCard
          label="Hiányzó árak száma"
          value={summary.cards_missing_price_total}
          tone={summary.cards_missing_price_total > 0 ? "warn" : "good"}
        />
      </div>

      <Panel title="Gyűjtemény érték trend" subtitle="A grafikon snapshotok alapján frissül.">
        {snapshots.length === 0 ? (
          <EmptyState label="Még nincs gyűjtemény snapshot." />
        ) : (
          <div className="h-80">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={snapshots}>
                <defs>
                  <linearGradient id="valueFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="5%" stopColor="#60a5fa" stopOpacity={0.45} />
                    <stop offset="95%" stopColor="#60a5fa" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
                <XAxis dataKey="snapshot_date" tickFormatter={formatDate} stroke="#94a3b8" />
                <YAxis stroke="#94a3b8" tickFormatter={(value) => `${Math.round(Number(value) / 1000)}k`} />
                <Tooltip
                  contentStyle={{ background: "#111722", border: "1px solid #334155", borderRadius: 8 }}
                  formatter={(value) => formatHuf(Number(value))}
                  labelFormatter={(value) => formatDate(String(value))}
                />
                <Area
                  dataKey="collection_value_huf"
                  fill="url(#valueFill)"
                  name="Gyűjtemény érték"
                  stroke="#60a5fa"
                  strokeWidth={2}
                  type="monotone"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </Panel>
    </div>
  );
}
