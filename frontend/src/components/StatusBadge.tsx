import type { ReactNode } from "react";

type StatusBadgeProps = {
  children: ReactNode;
  tone?: "neutral" | "info" | "success" | "warning" | "danger";
  className?: string;
};

const toneClass = {
  neutral: "border-white/10 bg-slate-900/55 text-slate-100",
  info: "border-cyan-300/30 bg-cyan-300/10 text-cyan-100",
  success: "border-emerald-300/30 bg-emerald-300/10 text-emerald-100",
  warning: "border-amber-300/35 bg-amber-300/10 text-amber-100",
  danger: "border-rose-300/35 bg-rose-300/10 text-rose-100",
};

export function StatusBadge({ children, tone = "neutral", className = "" }: StatusBadgeProps) {
  return (
    <span className={`inline-flex min-h-7 items-center rounded-full border px-2.5 py-1 text-xs font-medium shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] ${toneClass[tone]} ${className}`}>
      {children}
    </span>
  );
}
