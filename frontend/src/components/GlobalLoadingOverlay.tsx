import { Loader2, ScanLine } from "lucide-react";

type GlobalLoadingOverlayProps = {
  title: string;
  subtitle?: string;
  steps?: string[];
};

export function GlobalLoadingOverlay({ title, subtitle, steps = [] }: GlobalLoadingOverlayProps) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-[#0d1117]/74 p-4 backdrop-blur-xl">
      <div className="glass-surface w-full max-w-md p-5">
        <div className="flex items-start gap-4">
          <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border border-cyan-300/30 bg-cyan-300/10 text-cyan-100 shadow-[0_0_32px_rgba(103,232,249,0.16)]">
            <ScanLine className="absolute animate-pulse" size={26} />
            <Loader2 className="animate-spin text-cyan-200/80" size={34} />
          </div>
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-wide text-blue-200">Lokális feldolgozás</div>
            <h2 className="mt-1 text-base font-semibold text-slate-50">{title}</h2>
            {subtitle && <p className="mt-2 text-sm leading-6 text-slate-300">{subtitle}</p>}
          </div>
        </div>

        {steps.length > 0 && (
          <div className="control-surface mt-5 space-y-2 rounded-2xl p-3">
            {steps.map((step, index) => (
              <div key={`${step}-${index}`} className="flex items-center gap-2 text-xs text-slate-300">
                <span className="h-1.5 w-1.5 rounded-full bg-cyan-300 shadow-[0_0_12px_rgba(103,232,249,0.8)]" />
                <span>{step}</span>
              </div>
            ))}
          </div>
        )}

        <div className="mt-4 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
          Nincs külső API-hívás. Csak lokális feldolgozás fut.
        </div>
      </div>
    </div>
  );
}
