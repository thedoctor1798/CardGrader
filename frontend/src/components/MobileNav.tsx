import { BarChart3, Boxes, Bug, PlusCircle, Settings } from "lucide-react";
import type { Page } from "../App";

type MobileNavProps = {
  page: Page;
  debugMode: boolean;
  onNavigate: (page: Page) => void;
};

const baseItems = [
  { page: "dashboard" as const, label: "Home", icon: BarChart3 },
  { page: "collection" as const, label: "Cards", icon: Boxes },
  { page: "add" as const, label: "Add", icon: PlusCircle },
  { page: "settings" as const, label: "Settings", icon: Settings },
];

export function MobileNav({ page, debugMode, onNavigate }: MobileNavProps) {
  const items = debugMode ? [...baseItems, { page: "debug" as const, label: "Debug", icon: Bug }] : baseItems;

  return (
    <nav className="fixed inset-x-3 bottom-3 z-40 rounded-2xl border border-white/10 bg-slate-950/88 p-1.5 shadow-2xl shadow-black/35 backdrop-blur-xl lg:hidden">
      <div className="grid" style={{ gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))` }}>
        {items.map((item) => {
          const Icon = item.icon;
          const active = page === item.page || (page === "detail" && item.page === "collection");
          return (
            <button
              key={item.page}
              className={`flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-xl text-[11px] font-medium transition ${
                active ? "bg-white text-slate-950" : "text-slate-400 hover:bg-white/10 hover:text-slate-100"
              }`}
              onClick={() => onNavigate(item.page)}
              type="button"
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
