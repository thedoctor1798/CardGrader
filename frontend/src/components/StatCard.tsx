import type { ReactNode } from "react";

type StatCardProps = {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "good" | "warn" | "bad";
};

const toneClass = {
  default: "text-slate-100",
  good: "text-emerald-300",
  warn: "text-amber-300",
  bad: "text-rose-300",
};

export function StatCard({ label, value, hint, tone = "default" }: StatCardProps) {
  return (
    <div className="glass-card px-4 py-3.5">
      <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`metric-value mt-2 break-words text-xl font-semibold leading-tight sm:text-2xl ${toneClass[tone]}`}>{value}</div>
      {hint && <div className="mt-1 text-xs leading-5 text-slate-500">{hint}</div>}
    </div>
  );
}
