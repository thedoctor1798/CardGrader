export function LoadingState({ label = "Betöltés..." }: { label?: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-charcoal-850 p-6 text-sm text-slate-400">
      {label}
    </div>
  );
}
