export function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-white/10 bg-slate-950/38 p-6 text-sm leading-6 text-slate-300">
      {label}
    </div>
  );
}
