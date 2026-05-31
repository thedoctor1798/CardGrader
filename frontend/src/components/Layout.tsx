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
    <div className="relative isolate flex min-h-screen text-slate-100">
      <div className="pointer-events-none fixed inset-x-0 top-0 -z-10 h-72 bg-[linear-gradient(180deg,rgba(26,32,43,0.92),rgba(26,32,43,0))]" />
      <Sidebar page={page} debugMode={debugMode} onNavigate={onNavigate} />
      <div className="min-w-0 flex-1">
        <Topbar page={page} debugMode={debugMode} onToggleDebugMode={onToggleDebugMode} />
        <main className="mx-auto w-full max-w-[1900px] px-3 pb-28 pt-5 sm:px-6 sm:py-7 lg:px-8 lg:pb-10">{children}</main>
      </div>
      <MobileNav page={page} debugMode={debugMode} onNavigate={onNavigate} />
    </div>
  );
}
