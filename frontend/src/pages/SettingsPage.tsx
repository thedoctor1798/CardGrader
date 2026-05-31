import { Bug, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { AppInfo, LocalAIConfig, LocalAIStatus, LocalAITestConnection } from "../api/types";
import { ActionButton } from "../components/ActionButton";
import { EmptyState } from "../components/EmptyState";
import { FxSettings } from "../components/FxSettings";
import { LoadingState } from "../components/LoadingState";
import { Panel } from "../components/Panel";
import { PriceProviderSettings } from "../components/PriceProviderSettings";
import { StatCard } from "../components/StatCard";
import { StatusBadge } from "../components/StatusBadge";

type SettingsPageProps = {
  debugMode: boolean;
  onToggleDebugMode: () => void;
};

export function SettingsPage({ debugMode, onToggleDebugMode }: SettingsPageProps) {
  const [appInfo, setAppInfo] = useState<AppInfo | null>(null);
  const [localAI, setLocalAI] = useState<LocalAIStatus | null>(null);
  const [localAIConfig, setLocalAIConfig] = useState<LocalAIConfig | null>(null);
  const [connectionTest, setConnectionTest] = useState<LocalAITestConnection | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [info, aiStatus, aiConfig] = await Promise.all([
        api.getAppInfo(),
        api.getLocalAIStatus(),
        api.getLocalAIConfig(),
      ]);
      setAppInfo(info);
      setLocalAI(aiStatus);
      setLocalAIConfig(aiConfig);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Settings failed to load.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const testLocalAIConnection = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const result = await api.testLocalAIConnection();
      setConnectionTest(result);
      setMessage(result.message);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Local AI connection test failed.");
    } finally {
      setBusy(false);
    }
  };

  const resetLocalData = async () => {
    if (!window.confirm("Reset local demo data?")) return;
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

  if (loading) return <LoadingState label="Loading settings..." />;

  return (
    <div className="space-y-5">
      {message && <div className="rounded-2xl border border-emerald-400/30 bg-emerald-500/10 p-3 text-sm text-emerald-100">{message}</div>}
      {error && <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-100">{error}</div>}

      {appInfo ? (
        <Panel title={appInfo.name} subtitle="Read-only runtime overview. Values are loaded from the local backend.">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Mode" value="Local only" tone="good" />
            <StatCard label="External APIs" value={appInfo.external_apis_enabled ? "enabled" : "disabled"} tone={appInfo.external_apis_enabled ? "warn" : "good"} />
            <StatCard label="Local AI" value={appInfo.local_ai_enabled ? "enabled" : "disabled"} tone={appInfo.local_ai_enabled ? "good" : "warn"} />
            <StatCard label="Database" value={appInfo.database.toUpperCase()} />
          </div>
        </Panel>
      ) : (
        <EmptyState label="App info is unavailable." />
      )}

      {localAI && (
        <Panel
          title="Local AI"
          subtitle="LM Studio can run server-local or through the Windows worker. Editing is still done in .env files, then the backend should be restarted."
          action={
            <div className="flex flex-wrap gap-2">
              <ActionButton disabled={busy} onClick={testLocalAIConnection}>
                <RefreshCw size={16} />
                Test connection
              </ActionButton>
              <ActionButton tone="warning" onClick={onToggleDebugMode}>
                <Bug size={16} />
                {debugMode ? "Developer mode on" : "Developer mode off"}
              </ActionButton>
            </div>
          }
        >
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Mode" value={localAI.mode} tone={localAI.enabled ? "good" : "warn"} />
            <StatCard label="Enabled" value={localAI.enabled ? "yes" : "no"} tone={localAI.enabled ? "good" : "warn"} />
            <StatCard label="Provider" value={localAI.provider} />
            <StatCard label="Model" value={localAI.model_name || "-"} />
            <StatCard label="Base URL" value={localAI.base_url} />
            <StatCard label="Worker URL" value={localAI.worker_base_url || "-"} />
            <StatCard label="Timeout" value={`${localAIConfig?.timeout_seconds ?? "-"}s`} />
            <StatCard label="Max images" value={localAIConfig?.max_images ?? "-"} />
            <StatCard label="Max tokens" value={localAIConfig?.max_tokens ?? "-"} />
            <StatCard label="Disable thinking" value={localAIConfig?.disable_thinking ? "yes" : "no"} tone={localAIConfig?.disable_thinking ? "good" : "warn"} />
            <StatCard label="Reachable" value={localAI.reachable ? "yes" : "no"} tone={localAI.reachable ? "good" : "warn"} />
            <StatCard label="Worker" value={localAI.worker_reachable ? "reachable" : "not reachable"} tone={localAI.worker_reachable ? "good" : "warn"} />
          </div>
          <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.035] p-3 text-sm leading-6 text-slate-300">{localAI.message}</div>
          <div className="mt-4 flex flex-wrap gap-2">
            <StatusBadge tone="info">AI_MODEL_NAME / LOCAL_AI_MODEL_NAME</StatusBadge>
            <StatusBadge tone="info">AI_MAX_CONTEXT_TOKENS</StatusBadge>
            <StatusBadge tone="info">AI_PHASE_A_MAX_OUTPUT_TOKENS</StatusBadge>
            <StatusBadge tone="info">AI_PHASE_B_MAX_OUTPUT_TOKENS</StatusBadge>
            <StatusBadge tone="info">SEND_DIAGNOSTIC_IMAGES_TO_AI</StatusBadge>
            <StatusBadge tone="info">ENABLE_IMAGE_PREPROCESSING</StatusBadge>
            <StatusBadge tone="info">ENABLE_TWO_PHASE_AI_GRADING</StatusBadge>
          </div>

          {connectionTest && (
            <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/35 p-4 text-sm text-slate-300">
              <div className="font-semibold text-slate-100">Connection test: {connectionTest.ok ? "OK" : "not OK"}</div>
              <div className="mt-1">Selected model: {connectionTest.selected_model || "-"}</div>
              <div className="mt-1">Selected model loaded: {connectionTest.selected_model_found ? "yes" : "no"}</div>
              <div className="mt-1">{connectionTest.message}</div>
              {debugMode && connectionTest.models.length > 0 && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-xs font-semibold uppercase text-slate-500">Loaded model list</summary>
                  <ul className="mt-2 max-h-48 space-y-1 overflow-auto">
                    {connectionTest.models.map((model) => (
                      <li key={model} className="rounded-lg bg-slate-900 px-2 py-1 text-xs">{model}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </Panel>
      )}

      <PriceProviderSettings />
      <FxSettings />

      {debugMode && (
        <Panel title="Developer maintenance" subtitle="Local single-user MVP actions. Originals are kept by generated media cleanup.">
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
      )}
    </div>
  );
}
