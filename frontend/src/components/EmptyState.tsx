export function EmptyState({ label }: { label: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-700 bg-charcoal-900 p-6 text-sm text-slate-400">
      {label}
    </div>
  );
}
