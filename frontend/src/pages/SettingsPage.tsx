import { RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AppInfo, LocalAIStatus } from "../api/types";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";

export function SettingsPage() {
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [localAI, setLocalAI] = useState<LocalAIStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [info, aiStatus] = await Promise.all([api.getAppInfo(), api.getLocalAIStatus()]);
      setAppInfo(info);
      setLocalAI(aiStatus);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nem sikerült betölteni az app infót.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetLocalData = async () => {
    if (!window.confirm("Biztosan törlöd a lokális teszt adatokat?")) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.resetLocalData();
      setMessage(`${result.message} Törölt sorok: ${Object.values(result.deleted).reduce((sum, value) => sum + value, 0)}.`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset hiba.");
    } finally {
      setBusy(false);
    }
  };

  const cleanupGeneratedMedia = async () => {
    if (!window.confirm("Biztosan törlöd a generált media fájlokat? Az originals mappa megmarad.")) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.cleanupGeneratedMedia();
      setMessage(`${result.message} Törölt fájlok: ${result.deleted_files}.`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Media cleanup hiba.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="App info betöltése..." />;

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-blue-300">Local runtime</p>
        <h2 className="mt-1 text-2xl font-semibold text-slate-50">Beállítások</h2>
        <p className="mt-1 text-sm text-slate-400">Lokális MVP állapot, Local AI státusz és fejlesztői segédeszközök.</p>
      </div>

      {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
      {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

      {appInfo ? (
        <Panel title={appInfo.name} subtitle="A frontend ezt a lokális backend app info endpointból olvassa.">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Mód" value="Local-only mód" tone="good" />
            <StatCard label="Külső API" value={appInfo.external_apis_enabled ? "bekapcsolva" : "kikapcsolva"} tone={appInfo.external_apis_enabled ? "warn" : "good"} />
            <StatCard label="Local AI" value={appInfo.local_ai_enabled ? "bekapcsolva" : "még nincs bekapcsolva"} tone={appInfo.local_ai_enabled ? "good" : "warn"} />
            <StatCard label="Adatbázis" value={`${appInfo.database.toUpperCase()} adatbázis`} />
          </div>
        </Panel>
      ) : (
        <EmptyState label="App info nem érhető el." />
      )}

      {localAI && (
        <Panel title="Local AI státusz" subtitle="Csak localhost model szerver engedélyezett. Nincs API kulcs és nincs külső AI hívás.">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Enabled" value={localAI.enabled ? "igen" : "nem"} tone={localAI.enabled ? "good" : "warn"} />
            <StatCard label="Provider" value={localAI.provider} />
            <StatCard label="Base URL" value={localAI.base_url} />
            <StatCard label="Model" value={localAI.model_name || "-"} />
            <StatCard label="Localhost" value={localAI.is_localhost ? "igen" : "nem"} tone={localAI.is_localhost ? "good" : "bad"} />
            <StatCard label="Reachable" value={localAI.reachable ? "igen" : "nem"} tone={localAI.reachable ? "good" : "warn"} />
            <StatCard label="Vision" value={localAI.vision_capable} />
          </div>
          <p className="mt-4 rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-sm text-slate-300">{localAI.message}</p>
        </Panel>
      )}

      <Panel title="Fejlesztői demo műveletek" subtitle="Csak lokális, single-user MVP használatra. Az originals media mappát egyik művelet sem törli.">
        <div className="grid gap-3 md:grid-cols-2">
          <button
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm font-medium text-rose-100 hover:bg-rose-500/20 disabled:opacity-60"
            disabled={busy}
            onClick={resetLocalData}
            type="button"
          >
            <Trash2 size={16} />
            Reset demo data
          </button>
          <button
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-100 hover:bg-amber-500/20 disabled:opacity-60"
            disabled={busy}
            onClick={cleanupGeneratedMedia}
            type="button"
          >
            <RefreshCw size={16} />
            Cleanup generated media
          </button>
        </div>
      </Panel>
    </div>
  );
}
