import type { ReactNode } from "react";

type PanelProps = {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function Panel({ title, subtitle, action, children, className = "" }: PanelProps) {
  return (
    <section className={`glass-surface overflow-hidden rounded-2xl ${className}`}>
      {(title || subtitle || action) && (
        <div className="flex flex-col gap-4 border-b border-white/10 px-4 py-4 sm:flex-row sm:items-start sm:justify-between sm:px-5">
          <div className="min-w-0">
            {title && <h2 className="text-base font-semibold text-slate-50">{title}</h2>}
            {subtitle && <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className="p-4 sm:p-5">{children}</div>
    </section>
  );
}
