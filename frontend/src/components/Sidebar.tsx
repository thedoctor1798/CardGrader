import { BarChart3, Boxes, Bug, PlusCircle, Settings } from "lucide-react";
import type { Page } from "../App";
import { BrandLogo } from "./BrandLogo";

type SidebarProps = {
  page: Page;
  debugMode: boolean;
  onNavigate: (page: Page) => void;
};

const baseItems = [
  { page: "dashboard" as const, label: "Dashboard", icon: BarChart3 },
  { page: "collection" as const, label: "Collection", icon: Boxes },
  { page: "add" as const, label: "Upload / Add", icon: PlusCircle },
  { page: "settings" as const, label: "Settings", icon: Settings },
];

export function Sidebar({ page, debugMode, onNavigate }: SidebarProps) {
  const items = debugMode ? [...baseItems, { page: "debug" as const, label: "Debug tools", icon: Bug }] : baseItems;

  return (
    <aside className="sticky top-0 hidden h-screen w-72 shrink-0 border-r border-white/10 bg-slate-950/72 px-4 py-5 backdrop-blur-2xl lg:block">
      <div className="mb-7 rounded-2xl border border-white/10 bg-white/[0.045] px-4 py-4">
        <div className="flex items-center gap-3">
          <BrandLogo className="h-11 w-11 shrink-0" />
          <div className="min-w-0">
            <div className="text-xs font-semibold uppercase text-blue-300">CardGrader</div>
            <div className="mt-1 text-sm text-slate-400">Local AI grading desk</div>
          </div>
        </div>
      </div>
      <nav className="space-y-1.5">
        {items.map((item) => {
          const Icon = item.icon;
          const active = page === item.page || (page === "detail" && item.page === "collection");
          return (
            <button
              key={item.page}
              className={`flex min-h-11 w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium transition ${
                active ? "bg-white text-slate-950 shadow-sm" : "text-slate-400 hover:bg-white/10 hover:text-slate-100"
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
