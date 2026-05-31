export function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-700/80 bg-white/[0.035] p-6 text-sm leading-6 text-slate-400">
      {label}
    </div>
  );
}
