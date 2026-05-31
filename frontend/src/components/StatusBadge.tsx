import type { ReactNode } from "react";

type StatusBadgeProps = {
  children: ReactNode;
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
  className?: string;
};

const toneClass = {
  neutral: "border-slate-500/25 bg-slate-500/10 text-slate-200",
  info: "border-blue-400/30 bg-blue-400/10 text-blue-100",
  success: "border-emerald-400/30 bg-emerald-400/10 text-emerald-100",
  warning: "border-amber-400/35 bg-amber-400/10 text-amber-100",
  danger: "border-rose-400/35 bg-rose-400/10 text-rose-100",
};

export function StatusBadge({ children, tone = "neutral", className = "" }: StatusBadgeProps) {
  return (
    <span className={`inline-flex min-h-7 items-center rounded-full border px-2.5 py-1 text-xs font-medium ${toneClass[tone]} ${className}`}>
      {children}
    </span>
  );
}
