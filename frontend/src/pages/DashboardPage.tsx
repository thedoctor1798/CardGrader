import { Camera, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import type { CollectionSnapshot, CollectionSummary, CollectionValuation } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { GlobalLoadingOverlay } from "../components/GlobalLoadingOverlay";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";
import { formatDate, formatHuf } from "../utils/format";

export function DashboardPage() {
  const [summary, setSummary] = useState<CollectionSummary | null>(null);
  const [valuation, setValuation] = useState<CollectionValuation | null>(null);
  const [snapshots, setSnapshots] = useState<CollectionSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const latestSnapshot = useMemo(() => snapshots[snapshots.length - 1] ?? null, [snapshots]);

  const load = useCallback(async (showPageLoading = true) => {
    if (showPageLoading) setLoading(true);
    try {
      const [summaryData, snapshotData, valuationData] = await Promise.all([
        api.getCollectionSummary(),
        api.getCollectionSnapshots(),
        api.getCollectionValuation(),
      ]);
      setSummary(summaryData);
      setValuation(valuationData);
      setSnapshots(snapshotData.slice().reverse());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ismeretlen hiba");
    } finally {
      if (showPageLoading) setLoading(false);
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
      await load(false);
      setMessage("Snapshot mentve.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Snapshot mentési hiba");
    } finally {
      setBusy(false);
    }
  };

  const refreshOwnedPrices = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.refreshOwnedPrices();
      await load(false);
      setMessage(`Árfrissítés kész: ${result.success_count} sikeres, ${result.failure_count} sikertelen.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Árfrissítési hiba");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="Dashboard adatok betöltése..." />;
  if (error && !summary) return <EmptyState label={`Nem sikerült betölteni a dashboardot: ${error}`} />;
  if (!summary) return <EmptyState label="Nincs elérhető összesítés." />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-blue-300">Live summary</p>
          <h2 className="mt-1 text-2xl font-semibold text-slate-50">Dashboard</h2>
          <p className="mt-1 text-sm text-slate-400">
            A felső kártyák élő adatot mutatnak, a grafikon pedig csak mentett snapshotokból épül.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
            disabled={busy}
            onClick={() => load()}
            type="button"
          >
            <RefreshCw size={16} />
            Frissítés
          </button>
          <button
            className="inline-flex items-center gap-2 rounded-lg border border-emerald-500/40 px-3 py-2 text-sm text-emerald-100 hover:bg-emerald-500/10 disabled:opacity-60"
            disabled={busy}
            onClick={refreshOwnedPrices}
            type="button"
          >
            <RefreshCw size={16} />
            Árak frissítése
          </button>
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
      </div>

      {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
      {busy && (
        <GlobalLoadingOverlay
          title="Snapshot készítése..."
          subtitle="A lokális gyűjtemény-összesítő mentése folyamatban."
          steps={["Értékek számítása", "Snapshot mentése", "Grafikon frissítése"]}
        />
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
        <StatCard label="Összesített érték" value={formatHuf(valuation?.total_value_huf ?? summary.collection_value_huf)} tone="good" />
        <StatCard label="Bekerülési költség" value={formatHuf(summary.cost_basis_huf)} />
        <StatCard
          label="Becsült profit"
          value={formatHuf((valuation?.total_value_huf ?? summary.collection_value_huf) - summary.cost_basis_huf)}
          tone={(valuation?.total_value_huf ?? summary.collection_value_huf) - summary.cost_basis_huf >= 0 ? "good" : "bad"}
        />
        <StatCard label="Kártyák száma" value={summary.total_cards} />
        <StatCard label="Egyedi kártyák" value={summary.unique_cards} />
        <StatCard
          label="Hiányzó árak"
          value={valuation?.missing_price_cards ?? summary.cards_missing_price_total}
          tone={(valuation?.missing_price_cards ?? summary.cards_missing_price_total) > 0 ? "warn" : "good"}
        />
        <StatCard
          label="Hiányzó FX"
          value={valuation?.missing_fx_cards ?? 0}
          tone={(valuation?.missing_fx_cards ?? 0) > 0 ? "warn" : "good"}
        />
        <StatCard label="Raw érték" value={formatHuf(valuation?.raw_value_huf)} />
        <StatCard label="Graded érték" value={formatHuf(valuation?.graded_value_huf)} />
        <StatCard label="24h változás" value={formatHuf(valuation?.price_change_24h_huf)} tone={(valuation?.price_change_24h_huf ?? 0) >= 0 ? "good" : "bad"} />
        <StatCard label="7d változás" value={formatHuf(valuation?.price_change_7d_huf)} tone={(valuation?.price_change_7d_huf ?? 0) >= 0 ? "good" : "bad"} />
        <StatCard label="Utolsó árfrissítés" value={formatDate(valuation?.latest_refresh_at)} />
        <StatCard label="Utolsó FX" value={formatDate(valuation?.latest_fx_refresh_at)} />
      </div>

      {valuation?.fx_warnings?.length ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-100">
          {valuation.fx_warnings.join(" ")}
        </div>
      ) : null}

      <Panel
        title="Snapshot alapú értéktrend"
        subtitle="A grafikon csak mentett snapshotok alapján változik."
        action={
          latestSnapshot ? (
            <div className="rounded-full border border-slate-700 bg-slate-950/40 px-3 py-1 text-xs text-slate-300">
              Utolsó snapshot: {formatDate(latestSnapshot.created_at)}
            </div>
          ) : null
        }
      >
        {snapshots.length === 0 ? (
          <EmptyState label="Még nincs gyűjtemény snapshot." />
        ) : (
          <div className="space-y-3">
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
            <p className="text-xs text-slate-500">A grafikon csak mentett snapshotok alapján változik.</p>
          </div>
        )}
      </Panel>
    </div>
  );
}
