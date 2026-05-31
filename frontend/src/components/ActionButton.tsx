import type { ButtonHTMLAttributes, ReactNode } from "react";

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: "primary" | "secondary" | "success" | "warning" | "danger";
  children: ReactNode;
};

const toneClass = {
  primary: "border-blue-400/35 bg-blue-500 text-white shadow-blue-950/30 hover:bg-blue-400",
  secondary: "border-white/10 bg-white/[0.055] text-slate-100 hover:bg-white/[0.09]",
  success: "border-emerald-400/35 bg-emerald-500 text-white shadow-emerald-950/30 hover:bg-emerald-400",
  warning: "border-amber-400/35 bg-amber-500/12 text-amber-100 hover:bg-amber-500/18",
  danger: "border-rose-400/35 bg-rose-500/12 text-rose-100 hover:bg-rose-500/18",
};

export function ActionButton({ tone = "secondary", className = "", children, ...props }: ActionButtonProps) {
  return (
    <button
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border px-4 py-2.5 text-sm font-semibold transition disabled:opacity-55 ${toneClass[tone]} ${className}`}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}
