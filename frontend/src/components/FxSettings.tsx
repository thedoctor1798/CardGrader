import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { FxRatesResponse } from "../api/types";
import { LoadingState } from "./LoadingState";
import { Panel } from "./Panel";

export function FxSettings() {
  const [fx, setFx] = useState<FxRatesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setFx(await api.getFxRates());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nem sikerült betölteni az árfolyamokat.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const refresh = async () => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const response = await api.refreshFxRates({ currencies: ["USD", "EUR"], target_currency: "HUF", force: true });
      setFx(response);
      setMessage(response.ok ? "Árfolyamok frissítve." : "Az árfolyam frissítés részben sikertelen.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Árfolyam frissítési hiba.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="Árfolyamok betöltése..." />;

  return (
    <Panel title="Árfolyam / FX" subtitle="Automatikus HUF konverzió Frankfurter no-key árfolyamokkal, backend DB cache-ből.">
      <div className="space-y-4">
        {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
        {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input checked={Boolean(fx?.enabled)} className="h-4 w-4 accent-blue-500" disabled readOnly type="checkbox" />
          FX conversion enabled
        </label>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <FxInfo label="Enabled" value={fx?.enabled ? "igen" : "nem"} tone={fx?.enabled ? "good" : "warn"} />
          <FxInfo label="Provider" value={fx?.provider || "-"} />
          <FxInfo label="Target" value={fx?.target_currency || "HUF"} />
          <FxInfo label="Cache TTL" value={`${fx?.cache_ttl_hours ?? "-"}h`} />
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          {(fx?.rates ?? []).map((rate) => (
            <div key={`${rate.base_currency}-${rate.target_currency}`} className="rounded-lg border border-slate-800 bg-slate-950/30 p-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-100">{rate.base_currency} → {rate.target_currency}</div>
                  <div className="mt-1 text-2xl font-semibold text-slate-50">{rate.rate ? rate.rate.toFixed(4) : "-"}</div>
                </div>
                <span className="rounded-full border border-slate-700 px-2 py-1 text-xs text-slate-400">{rate.source || "-"}</span>
              </div>
              <div className="mt-3 text-xs text-slate-500">Dátum: {rate.rate_date || "-"} · Lejár: {rate.expires_at ? new Date(rate.expires_at).toLocaleString("hu-HU") : "-"}</div>
              {rate.warning || rate.error ? <div className="mt-2 text-sm text-amber-200">{rate.message || rate.warning || rate.error}</div> : null}
            </div>
          ))}
        </div>
        <button
          className="inline-flex items-center justify-center gap-2 rounded-lg border border-blue-500/40 bg-blue-500/10 px-4 py-2 text-sm font-medium text-blue-100 hover:bg-blue-500/20 disabled:opacity-60"
          disabled={busy}
          onClick={refresh}
          type="button"
        >
          <RefreshCw size={16} />
          USD/EUR árfolyam frissítése
        </button>
      </div>
    </Panel>
  );
}

function FxInfo({ label, value, tone }: { label: string; value: string; tone?: "good" | "warn" }) {
  const color = tone === "good" ? "text-emerald-200" : tone === "warn" ? "text-amber-200" : "text-slate-100";
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-4">
      <div className="text-xs uppercase text-slate-500">{label}</div>
      <div className={`mt-1 text-sm font-semibold ${color}`}>{value}</div>
    </div>
  );
}
