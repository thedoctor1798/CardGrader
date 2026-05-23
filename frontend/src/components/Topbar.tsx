import { ShieldCheck } from "lucide-react";

export function Topbar() {
  return (
    <header className="flex flex-col gap-3 border-b border-slate-800 bg-charcoal-900/80 px-5 py-4 md:flex-row md:items-center md:justify-between">
      <div>
        <h1 className="text-lg font-semibold text-slate-100">CardGrader AI Local Edition</h1>
        <p className="text-xs text-slate-500">Lokális gyűjtemény, ár és grading precheck</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <input
          className="h-9 w-full rounded-lg border border-slate-800 bg-charcoal-950 px-3 text-sm text-slate-200 outline-none placeholder:text-slate-600 focus:border-blue-500 md:w-72"
          placeholder="Keresés a gyűjteményben..."
          type="search"
        />
        <span className="inline-flex h-8 items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-3 text-xs text-emerald-200">
          <ShieldCheck size={14} />
          Local-only mód
        </span>
        <span className="inline-flex h-8 items-center rounded-full border border-slate-700 bg-slate-800/70 px-3 text-xs text-slate-300">
          Külső API: kikapcsolva
        </span>
      </div>
    </header>
  );
}
