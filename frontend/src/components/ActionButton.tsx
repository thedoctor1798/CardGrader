import type { ButtonHTMLAttributes, ReactNode } from "react";

type ActionButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  tone?: "primary" | "secondary" | "success" | "warning" | "danger";
  children: ReactNode;
};

const toneClass = {
  primary: "gradient-primary font-bold",
  secondary: "glass-button text-slate-100",
  success: "border-emerald-300/35 bg-emerald-400/18 text-emerald-50 shadow-emerald-950/30 hover:bg-emerald-400/25",
  warning: "border-amber-300/35 bg-amber-400/14 text-amber-100 hover:bg-amber-400/20",
  danger: "border-rose-300/35 bg-rose-400/14 text-rose-100 hover:bg-rose-400/20",
};

export function ActionButton({ tone = "secondary", className = "", children, ...props }: ActionButtonProps) {
  return (
    <button
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-[14px] border px-4 py-2.5 text-sm font-semibold transition disabled:opacity-45 disabled:saturate-50 ${toneClass[tone]} ${className}`}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}
