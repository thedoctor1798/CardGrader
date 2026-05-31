import type { ReactNode } from "react";
import type { Page } from "../App";
import { MobileNav } from "./MobileNav";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type LayoutProps = {
  page: Page;
  debugMode: boolean;
  onNavigate: (page: Page) => void;
  onToggleDebugMode: () => void;
  children: ReactNode;
};

export function Layout({ page, debugMode, onNavigate, onToggleDebugMode, children }: LayoutProps) {
  return (
    <div className="flex min-h-screen text-slate-100">
      <Sidebar page={page} debugMode={debugMode} onNavigate={onNavigate} />
      <div className="min-w-0 flex-1">
        <Topbar page={page} debugMode={debugMode} onToggleDebugMode={onToggleDebugMode} />
        <main className="mx-auto w-full max-w-[1900px] px-3 pb-28 pt-4 sm:px-6 sm:py-6 lg:px-8 lg:pb-8">{children}</main>
      </div>
      <MobileNav page={page} debugMode={debugMode} onNavigate={onNavigate} />
    </div>
  );
}
