import { BarChart3, Boxes, Settings } from "lucide-react";
import type { Page } from "../App";
import { BrandLogo } from "./BrandLogo";

type SidebarProps = {
  page: Page;
  onNavigate: (page: Page) => void;
};

const items = [
  { page: "dashboard" as const, label: "Dashboard", icon: BarChart3 },
  { page: "collection" as const, label: "Gyűjtemény", icon: Boxes },
  { page: "settings" as const, label: "Beállítások", icon: Settings },
];

export function Sidebar({ page, onNavigate }: SidebarProps) {
  return (
    <aside className="hidden w-64 shrink-0 border-r border-slate-800 bg-charcoal-900/95 px-4 py-5 lg:block">
      <div className="mb-7 rounded-xl border border-slate-800 bg-slate-950/25 px-4 py-4">
        <div className="flex items-center gap-3">
          <BrandLogo className="h-11 w-11 shrink-0" />
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase tracking-wide text-blue-300">CardGrader</div>
            <div className="mt-1 text-sm text-slate-400">AI Local Edition</div>
          </div>
        </div>
      </div>
      <nav className="space-y-1">
        {items.map((item) => {
          const Icon = item.icon;
          const active = page === item.page;
          return (
            <button
              key={item.page}
              className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition ${
                active
                  ? "border border-blue-500/30 bg-blue-500/15 text-blue-100"
                  : "border border-transparent text-slate-400 hover:border-slate-800 hover:bg-slate-800/60 hover:text-slate-100"
              }`}
              onClick={() => onNavigate(item.page)}
              type="button"
            >
              <Icon size={18} />
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
