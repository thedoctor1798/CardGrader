import type { ReactNode } from "react";

type StatCardProps = {
  label: string;
  value: ReactNode;
  tone?: "default" | "good" | "warn" | "bad";
};

const toneClass = {
  default: "text-slate-100",
  good: "text-emerald-300",
  warn: "text-amber-300",
  bad: "text-rose-300",
};

export function StatCard({ label, value, tone = "default" }: StatCardProps) {
  return (
    <div className="rounded-lg border border-slate-800 bg-charcoal-850 px-4 py-3">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={`mt-2 text-xl font-semibold ${toneClass[tone]}`}>{value}</div>
    </div>
  );
}
