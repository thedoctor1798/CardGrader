import type { ReactNode } from "react";
import type { Page } from "../App";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

type LayoutProps = {
  page: Page;
  onNavigate: (page: Page) => void;
  children: ReactNode;
};

export function Layout({ page, onNavigate, children }: LayoutProps) {
  return (
    <div className="flex min-h-screen bg-charcoal-950 text-slate-100">
      <Sidebar page={page} onNavigate={onNavigate} />
      <div className="min-w-0 flex-1">
        <Topbar />
        <main className="mx-auto w-full max-w-[1900px] px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
