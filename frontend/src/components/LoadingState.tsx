export function LoadingState({ label = "Loading..." }: { label?: string }) {
  return (
    <div className="glass-surface flex items-center gap-3 rounded-2xl p-6 text-sm text-slate-300">
      <span className="h-3 w-3 animate-pulse rounded-full bg-blue-300 shadow-[0_0_18px_rgba(147,197,253,0.8)]" />
      <span>{label}</span>
    </div>
  );
}
