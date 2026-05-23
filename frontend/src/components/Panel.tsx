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
    <section className={`overflow-hidden rounded-xl border border-slate-800/90 bg-charcoal-850/95 shadow-panel ${className}`}>
      {(title || subtitle || action) && (
        <div className="flex items-start justify-between gap-4 border-b border-slate-800 bg-slate-950/20 px-5 py-4">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-slate-50">{title}</h2>}
            {subtitle && <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-400">{subtitle}</p>}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}
