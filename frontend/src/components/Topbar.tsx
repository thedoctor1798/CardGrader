import { Bug, ShieldCheck } from "lucide-react";
import type { Page } from "../App";
import { BrandLogo } from "./BrandLogo";
import { StatusBadge } from "./StatusBadge";

type TopbarProps = {
  page: Page;
  debugMode: boolean;
  onToggleDebugMode: () => void;
};

const pageTitle: Record<Page, { title: string; subtitle: string }> = {
  dashboard: {
    title: "Dashboard",
    subtitle: "Collection value, grading work, and local AI health at a glance.",
  },
  collection: {
    title: "Collection",
    subtitle: "Search, filter, add, and open owned cards.",
  },
  add: {
    title: "Upload / Add Card",
    subtitle: "Start with a front image or create a card record manually.",
  },
  detail: {
    title: "Card Workflow",
    subtitle: "Images, recognition, centering, AI grading, and prices in one place.",
  },
  settings: {
    title: "Settings",
    subtitle: "Local AI, preprocessing, pricing, and runtime configuration.",
  },
  debug: {
    title: "Debug Tools",
    subtitle: "Raw diagnostics and developer-only maintenance actions.",
  },
};

export function Topbar({ page, debugMode, onToggleDebugMode }: TopbarProps) {
  const copy = pageTitle[page];

  return (
    <header className="sticky top-0 z-30 border-b border-white/10 bg-[#111722]/72 px-3 py-3 shadow-lg shadow-black/10 backdrop-blur-2xl sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-[1900px] flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <BrandLogo className="h-10 w-10 shrink-0 lg:hidden" />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-semibold text-slate-50 sm:text-2xl">{copy.title}</h1>
            <p className="mt-0.5 line-clamp-2 text-xs leading-5 text-slate-400 sm:text-sm">{copy.subtitle}</p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone="success" className="gap-1.5">
            <ShieldCheck size={14} />
            Local only
          </StatusBadge>
          <button
            className={`inline-flex min-h-9 items-center gap-1.5 rounded-full border px-3 text-xs font-semibold transition ${
              debugMode
                ? "border-amber-300/40 bg-amber-300/14 text-amber-100 shadow-[0_0_24px_rgba(245,158,11,0.12)]"
                : "glass-button text-slate-300"
            }`}
            onClick={onToggleDebugMode}
            type="button"
          >
            <Bug size={14} />
            {debugMode ? "Debug on" : "Debug off"}
          </button>
        </div>
      </div>
    </header>
  );
}
