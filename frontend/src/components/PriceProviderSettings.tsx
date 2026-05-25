import { RefreshCw, Save, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../api/client";
import type { PriceProviderSettingsUpdate, PriceProviderStatus, PriceProviderTestResponse } from "../api/types";
import { EmptyState } from "./EmptyState";
import { LoadingState } from "./LoadingState";
import { Panel } from "./Panel";

type ProviderForm = PriceProviderSettingsUpdate & {
  api_key: string;
};

type FormState = Record<"poketrace" | "tcgdex" | "pokemontcg", ProviderForm>;

const providerTitles: Record<string, string> = {
  manual: "Manual",
  local_json: "Local JSON",
  poketrace: "PokeTrace",
  tcgdex: "TCGdex",
  pokemontcg: "Pokemon TCG API",
};

const inputClass = "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 placeholder:text-slate-600";
const primaryButtonClass = "inline-flex items-center justify-center gap-2 rounded-lg border border-blue-500/40 bg-blue-500/10 px-3 py-2 text-sm font-medium text-blue-100 hover:bg-blue-500/20 disabled:opacity-60";
const secondaryButtonClass = "inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 disabled:opacity-60";

const defaultForms: FormState = {
  poketrace: {
    enabled: false,
    api_key: "",
    plan: "free",
    market: "US",
    daily_limit: 250,
    burst_limit: 1,
    burst_window_seconds: 2,
    timeout_seconds: 30,
    cache_ttl_hours: 24,
    min_match_score: 70,
    fetch_history: false,
    history_period: "30d",
    respect_retry_after: true,
  },
  tcgdex: {
    enabled: false,
    api_key: "",
    base_url: "https://api.tcgdex.net/v2",
    timeout_seconds: 30,
    rate_limit_seconds: 2,
    min_match_score: 70,
  },
  pokemontcg: {
    enabled: false,
    api_key: "",
    base_url: "https://api.pokemontcg.io/v2",
    timeout_seconds: 30,
    rate_limit_seconds: 2,
    min_match_score: 70,
  },
};

export function PriceProviderSettings() {
  const [providers, setProviders] = useState<PriceProviderStatus[]>([]);
  const [forms, setForms] = useState<FormState>(defaultForms);
  const [loading, setLoading] = useState(true);
  const [busyProvider, setBusyProvider] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<PriceProviderTestResponse | null>(null);

  const providersByName = useMemo(
    () => Object.fromEntries(providers.map((provider) => [provider.provider, provider])),
    [providers],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await api.getPriceProviderSettings();
      setProviders(response.providers);
      setForms({
        poketrace: formFromProvider(defaultForms.poketrace, response.providers.find((provider) => provider.provider === "poketrace")),
        tcgdex: formFromProvider(defaultForms.tcgdex, response.providers.find((provider) => provider.provider === "tcgdex")),
        pokemontcg: formFromProvider(defaultForms.pokemontcg, response.providers.find((provider) => provider.provider === "pokemontcg")),
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nem sikerült betölteni az árforrásokat.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const updateForm = (provider: keyof FormState, patch: Partial<ProviderForm>) => {
    setForms((current) => ({ ...current, [provider]: { ...current[provider], ...patch } }));
  };

  const saveProvider = async (provider: keyof FormState) => {
    setBusyProvider(provider);
    setMessage(null);
    setError(null);
    const form = forms[provider];
    const payload: PriceProviderSettingsUpdate = { ...form };
    if (!form.api_key?.trim()) {
      delete payload.api_key;
    }
    try {
      const response = await api.updatePriceProviderSetting(provider, payload);
      setProviders((current) => upsertProvider(current, response.provider));
      setForms((current) => ({ ...current, [provider]: { ...current[provider], api_key: "", clear_secret: false } }));
      setMessage(`${providerTitles[provider]} beállítások mentve.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Nem sikerült menteni az árforrást.");
    } finally {
      setBusyProvider(null);
    }
  };

  const testProvider = async (provider: keyof FormState) => {
    setBusyProvider(`${provider}:test`);
    setMessage(null);
    setError(null);
    try {
      const response = await api.testPriceProviderSetting(provider);
      setTestResult(response);
      if (response.ok) {
        setMessage(response.message || `${providerTitles[provider]} kapcsolat rendben.`);
      } else {
        setError(providerErrorMessage(response));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Kapcsolat teszt hiba.");
    } finally {
      setBusyProvider(null);
    }
  };

  if (loading) {
    return <LoadingState label="Árforrások betöltése..." />;
  }

  return (
    <Panel title="Árforrások" subtitle="Online és helyi árszolgáltatók. Az API kulcsok csak mentéskor mennek a backendnek.">
      <div className="space-y-4">
        {message && <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">{message}</div>}
        {error && <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-200">{error}</div>}

        <div className="grid gap-3 lg:grid-cols-2">
          <ProviderStatusCard provider={providersByName.manual} />
          <ProviderStatusCard provider={providersByName.local_json} />
        </div>

        <div className="grid gap-4 xl:grid-cols-3">
          <PokeTraceForm
            busy={busyProvider}
            form={forms.poketrace}
            provider={providersByName.poketrace}
            onChange={(patch) => updateForm("poketrace", patch)}
            onSave={() => saveProvider("poketrace")}
            onTest={() => testProvider("poketrace")}
          />
          <RawProviderForm
            busy={busyProvider}
            form={forms.tcgdex}
            provider={providersByName.tcgdex}
            providerKey="tcgdex"
            title="TCGdex"
            note="Raw price fallback. PSA graded ár nem várható."
            onChange={(patch) => updateForm("tcgdex", patch)}
            onSave={() => saveProvider("tcgdex")}
            onTest={() => testProvider("tcgdex")}
          />
          <RawProviderForm
            busy={busyProvider}
            form={forms.pokemontcg}
            provider={providersByName.pokemontcg}
            providerKey="pokemontcg"
            title="Pokemon TCG API"
            note="TCGPlayer/Cardmarket raw mezők. PSA graded ár nem várható."
            showApiKey
            onChange={(patch) => updateForm("pokemontcg", patch)}
            onSave={() => saveProvider("pokemontcg")}
            onTest={() => testProvider("pokemontcg")}
          />
        </div>

        {testResult && (
          <div className="rounded-lg border border-slate-800 bg-slate-950/40 p-3 text-sm text-slate-300">
            <div className="font-medium text-slate-100">Teszt: {providerTitles[testResult.provider] || testResult.provider}</div>
            <div className="mt-1">{testResult.message || (testResult.ok ? "OK" : testResult.error)}</div>
            {testResult.rate_limit_remaining !== null && testResult.rate_limit_remaining !== undefined && (
              <div className="mt-1">Rate limit maradek: {testResult.rate_limit_remaining}</div>
            )}
          </div>
        )}

        <div className="flex gap-3 rounded-lg border border-slate-800 bg-slate-950/30 p-3 text-sm text-slate-300">
          <ShieldCheck className="mt-0.5 shrink-0 text-emerald-300" size={18} />
          <p>
            Az API kulcsok nem kerülnek localStorage-ba és a backend nem küldi vissza őket teljes formában.
            Éles, publikus használat előtt ehhez admin autentikáció kell.
          </p>
        </div>
      </div>
    </Panel>
  );
}

function ProviderStatusCard({ provider }: { provider?: PriceProviderStatus }) {
  if (!provider) {
    return <EmptyState label="Árforrás státusz nem érhető el." />;
  }
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/30 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-slate-100">{providerTitles[provider.provider] || provider.provider}</div>
          <div className="mt-1 text-xs text-slate-500">Forras: {provider.source}</div>
        </div>
        <ProviderBadge provider={provider} />
      </div>
      {provider.path_info && <div className="mt-3 text-sm text-slate-400">{provider.path_info}</div>}
    </div>
  );
}

function PokeTraceForm(props: {
  provider?: PriceProviderStatus;
  form: ProviderForm;
  busy: string | null;
  onChange: (patch: Partial<ProviderForm>) => void;
  onSave: () => void;
  onTest: () => void;
}) {
  const { provider, form, busy, onChange, onSave, onTest } = props;
  return (
    <ProviderShell
      provider={provider}
      title="PokeTrace"
      note="Primary online provider. Free: 250/day, 1 request / 2 sec, eBay + TCGPlayer."
    >
      <Toggle checked={form.enabled} label="Enabled" onChange={(enabled) => onChange({ enabled })} />
      <Field label="API key">
        <input
          className={inputClass}
          placeholder={provider?.masked_api_key || "pt_..."}
          type="password"
          value={form.api_key}
          onChange={(event) => onChange({ api_key: event.target.value })}
        />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Plan">
          <select className={inputClass} value={form.plan || "free"} onChange={(event) => onChange(planPatch(event.target.value))}>
            <option value="free">free</option>
            <option value="pro">pro</option>
            <option value="scale">scale</option>
          </select>
        </Field>
        <Field label="Market">
          <select className={inputClass} value={form.market || "US"} onChange={(event) => onChange({ market: event.target.value })}>
            <option value="US">US</option>
            <option value="EU">EU</option>
          </select>
        </Field>
        <NumberField label="Daily limit" value={form.daily_limit} onChange={(daily_limit) => onChange({ daily_limit })} />
        <NumberField label="Burst limit" value={form.burst_limit} onChange={(burst_limit) => onChange({ burst_limit })} />
        <NumberField label="Burst window sec" value={form.burst_window_seconds} onChange={(burst_window_seconds) => onChange({ burst_window_seconds })} />
        <NumberField label="Cache TTL hours" value={form.cache_ttl_hours} onChange={(cache_ttl_hours) => onChange({ cache_ttl_hours })} />
        <NumberField label="Min match score" value={form.min_match_score} onChange={(min_match_score) => onChange({ min_match_score })} />
        <NumberField label="Timeout sec" value={form.timeout_seconds} onChange={(timeout_seconds) => onChange({ timeout_seconds })} />
      </div>
      <Toggle checked={Boolean(form.clear_secret)} label="Clear saved API key" onChange={(clear_secret) => onChange({ clear_secret })} />
      <ProviderActions busy={busy} provider="poketrace" onSave={onSave} onTest={onTest} />
    </ProviderShell>
  );
}

function RawProviderForm(props: {
  provider?: PriceProviderStatus;
  providerKey: "tcgdex" | "pokemontcg";
  title: string;
  note: string;
  showApiKey?: boolean;
  form: ProviderForm;
  busy: string | null;
  onChange: (patch: Partial<ProviderForm>) => void;
  onSave: () => void;
  onTest: () => void;
}) {
  const { provider, providerKey, title, note, showApiKey, form, busy, onChange, onSave, onTest } = props;
  return (
    <ProviderShell provider={provider} title={title} note={note}>
      <Toggle checked={form.enabled} label="Enabled" onChange={(enabled) => onChange({ enabled })} />
      {showApiKey && (
        <Field label="API key">
          <input
            className={inputClass}
            placeholder={provider?.masked_api_key || "optional"}
            type="password"
            value={form.api_key}
            onChange={(event) => onChange({ api_key: event.target.value })}
          />
        </Field>
      )}
      <Field label="Base URL">
        <input className={inputClass} value={form.base_url || ""} onChange={(event) => onChange({ base_url: event.target.value })} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <NumberField label="Rate limit sec" value={form.rate_limit_seconds} onChange={(rate_limit_seconds) => onChange({ rate_limit_seconds })} />
        <NumberField label="Min match score" value={form.min_match_score} onChange={(min_match_score) => onChange({ min_match_score })} />
        <NumberField label="Timeout sec" value={form.timeout_seconds} onChange={(timeout_seconds) => onChange({ timeout_seconds })} />
      </div>
      {showApiKey && <Toggle checked={Boolean(form.clear_secret)} label="Clear saved API key" onChange={(clear_secret) => onChange({ clear_secret })} />}
      <ProviderActions busy={busy} provider={providerKey} onSave={onSave} onTest={onTest} />
    </ProviderShell>
  );
}

function ProviderShell(props: { provider?: PriceProviderStatus; title: string; note: string; children: ReactNode }) {
  const { provider, title, note, children } = props;
  return (
    <div className="space-y-3 rounded-lg border border-slate-800 bg-slate-950/30 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-100">{title}</h3>
          <p className="mt-1 text-xs text-slate-500">{note}</p>
        </div>
        {provider && <ProviderBadge provider={provider} />}
      </div>
      {provider?.missing?.length ? <div className="text-xs text-amber-200">Hiányzó: {provider.missing.join(", ")}</div> : null}
      {children}
    </div>
  );
}

function ProviderBadge({ provider }: { provider: PriceProviderStatus }) {
  const text = provider.enabled ? (provider.configured ? "configured" : "missing") : "disabled";
  const color = provider.enabled && provider.configured ? "border-emerald-500/40 text-emerald-200" : provider.enabled ? "border-amber-500/40 text-amber-200" : "border-slate-700 text-slate-400";
  return <span className={`shrink-0 rounded-full border px-2 py-1 text-xs ${color}`}>{text}</span>;
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm text-slate-300">
      <span className="mb-1 block text-xs font-medium uppercase text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function NumberField({ label, value, onChange }: { label: string; value?: number | null; onChange: (value: number) => void }) {
  return (
    <Field label={label}>
      <input className={inputClass} inputMode="decimal" value={value ?? ""} onChange={(event) => onChange(Number(event.target.value || 0))} />
    </Field>
  );
}

function Toggle({ checked, label, onChange }: { checked: boolean; label: string; onChange: (checked: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-slate-300">
      <input checked={checked} className="h-4 w-4 accent-blue-500" type="checkbox" onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}

function ProviderActions(props: { busy: string | null; provider: keyof FormState; onSave: () => void; onTest: () => void }) {
  const { busy, provider, onSave, onTest } = props;
  return (
    <div className="flex flex-wrap gap-2 pt-1">
      <button className={primaryButtonClass} disabled={busy === provider} onClick={onSave} type="button">
        <Save size={15} />
        Mentés
      </button>
      <button className={secondaryButtonClass} disabled={busy === `${provider}:test`} onClick={onTest} type="button">
        <RefreshCw size={15} />
        Teszt
      </button>
    </div>
  );
}

function formFromProvider(defaults: ProviderForm, provider?: PriceProviderStatus): ProviderForm {
  if (!provider) {
    return { ...defaults };
  }
  return {
    ...defaults,
    enabled: provider.enabled,
    plan: provider.plan ?? defaults.plan,
    market: provider.market ?? defaults.market,
    base_url: provider.base_url ?? defaults.base_url,
    daily_limit: provider.daily_limit ?? defaults.daily_limit,
    burst_limit: provider.burst_limit ?? defaults.burst_limit,
    burst_window_seconds: provider.burst_window_seconds ?? defaults.burst_window_seconds,
    timeout_seconds: provider.timeout_seconds ?? defaults.timeout_seconds,
    cache_ttl_hours: provider.cache_ttl_hours ?? defaults.cache_ttl_hours,
    rate_limit_seconds: provider.rate_limit_seconds ?? defaults.rate_limit_seconds,
    min_match_score: provider.min_match_score ?? defaults.min_match_score,
    fetch_history: provider.fetch_history ?? defaults.fetch_history,
    history_period: provider.history_period ?? defaults.history_period,
    respect_retry_after: provider.respect_retry_after ?? defaults.respect_retry_after,
    api_key: "",
    clear_secret: false,
  };
}

function upsertProvider(providers: PriceProviderStatus[], provider: PriceProviderStatus): PriceProviderStatus[] {
  const rest = providers.filter((item) => item.provider !== provider.provider);
  return [...rest, provider].sort((left, right) => left.provider.localeCompare(right.provider));
}

function planPatch(plan: string): Partial<ProviderForm> {
  if (plan === "pro") {
    return { plan, daily_limit: 10000, burst_limit: 30, burst_window_seconds: 10 };
  }
  if (plan === "scale") {
    return { plan, daily_limit: 100000, burst_limit: 60, burst_window_seconds: 10 };
  }
  return { plan: "free", daily_limit: 250, burst_limit: 1, burst_window_seconds: 2 };
}

function providerErrorMessage(result: PriceProviderTestResponse): string {
  if (result.error === "provider_auth_failed") return "Az API kulcs elutasítva.";
  if (result.error === "provider_rate_limited") return "Rate limit elérve. Próbáld később.";
  if (result.error === "price_source_not_configured") return "Az árforrás nincs teljesen beállítva.";
  return result.message || result.error || "Árforrás teszt hiba.";
}
