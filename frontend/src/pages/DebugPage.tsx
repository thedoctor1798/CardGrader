import { RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AppInfo, LocalAIConfig, LocalAIStatus, PriceProvidersStatusResponse } from "../api/types";
import { ActionButton } from "../components/ActionButton";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";

export function DebugPage() {
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [localAI, setLocalAI] = useState<LocalAIStatus | null>(null);
  const [localAIConfig, setLocalAIConfig] = useState<LocalAIConfig | null>(null);
  const [priceStatus, setPriceStatus] = useState<PriceProvidersStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [info, aiStatus, aiConfig, providers] = await Promise.all([
        api.getAppInfo(),
        api.getLocalAIStatus(),
        api.getLocalAIConfig(),
        api.getPriceProviderStatus(),
      ]);
      setAppInfo(info);
      setLocalAI(aiStatus);
      setLocalAIConfig(aiConfig);
      setPriceStatus(providers);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Debug data failed to load.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resetLocalData = async () => {
    if (!window.confirm("Reset local demo data? This cannot be undone.")) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.resetLocalData();
      setMessage(`${result.message} Deleted rows: ${Object.values(result.deleted).reduce((sum, value) => sum + value, 0)}.`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  };

  const cleanupGeneratedMedia = async () => {
    if (!window.confirm("Delete generated media files? Originals will be kept.")) return;
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.cleanupGeneratedMedia();
      setMessage(`${result.message} Deleted files: ${result.deleted_files}.`);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Media cleanup failed.");
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label="Loading debug tools..." />;

  return (
    <div className="space-y-5">
      {message && <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-100">{message}</div>}
      {error && <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-100">{error}</div>}

      <Panel
        title="Runtime diagnostics"
        subtitle="Developer-only status and raw configuration previews. Normal workflows hide this detail."
        action={
          <ActionButton disabled={busy} onClick={load}>
            <RefreshCw size={16} />
            Refresh
          </ActionButton>
        }
      >
        {!appInfo ? (
          <EmptyState label="App info is unavailable." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="App" value={appInfo.name} />
            <StatCard label="Database" value={appInfo.database.toUpperCase()} />
            <StatCard label="External APIs" value={appInfo.external_apis_enabled ? "enabled" : "disabled"} tone={appInfo.external_apis_enabled ? "warn" : "good"} />
            <StatCard label="Local AI" value={appInfo.local_ai_enabled ? "enabled" : "disabled"} tone={appInfo.local_ai_enabled ? "good" : "warn"} />
          </div>
        )}
      </Panel>

      <Panel title="Local AI raw status" subtitle="Use this when LM Studio, worker mode, or model selection needs troubleshooting.">
        {localAI ? (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <StatCard label="Mode" value={localAI.mode} tone={localAI.enabled ? "good" : "warn"} />
              <StatCard label="Provider" value={localAI.provider} />
              <StatCard label="Model" value={localAI.model_name || "-"} />
              <StatCard label="Reachable" value={localAI.reachable ? "yes" : "no"} tone={localAI.reachable ? "good" : "warn"} />
              <StatCard label="Worker" value={localAI.worker_reachable ? "reachable" : "not reachable"} tone={localAI.worker_reachable ? "good" : "warn"} />
              <StatCard label="Timeout" value={`${localAIConfig?.timeout_seconds ?? "-"}s`} />
              <StatCard label="Max images" value={localAIConfig?.max_images ?? "-"} />
              <StatCard label="Max tokens" value={localAIConfig?.max_tokens ?? "-"} />
            </div>
            <pre className="max-h-96 overflow-auto whitespace-pre-wrap rounded-2xl border border-white/10 bg-slate-950/60 p-4 text-xs text-slate-300">
              {JSON.stringify({ localAI, localAIConfig }, null, 2)}
            </pre>
          </div>
        ) : (
          <EmptyState label="Local AI status is unavailable." />
        )}
      </Panel>

      <Panel title="Price provider diagnostics" subtitle="Provider configuration status without exposing secrets.">
        {!priceStatus ? (
          <EmptyState label="No provider status loaded." />
        ) : (
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {priceStatus.providers.map((provider) => (
              <div key={provider.provider} className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold text-slate-50">{provider.provider}</div>
                    <div className="mt-1 text-xs text-slate-500">{provider.source}</div>
                  </div>
                  <StatusBadge tone={provider.enabled && provider.configured ? "success" : "warning"}>
                    {provider.enabled && provider.configured ? "ready" : "needs setup"}
                  </StatusBadge>
                </div>
                {provider.missing.length > 0 && <div className="mt-3 text-xs text-amber-100">Missing: {provider.missing.join(", ")}</div>}
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Maintenance actions" subtitle="These actions are intentionally kept out of the normal user workflow.">
        <div className="grid gap-3 md:grid-cols-2">
          <ActionButton tone="danger" disabled={busy} onClick={resetLocalData}>
            <Trash2 size={16} />
            Reset demo data
          </ActionButton>
          <ActionButton tone="warning" disabled={busy} onClick={cleanupGeneratedMedia}>
            <RefreshCw size={16} />
            Cleanup generated media
          </ActionButton>
        </div>
      </Panel>
    </div>
  );
}
