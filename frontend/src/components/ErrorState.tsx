import type { ReactNode } from "react";

type ErrorStateProps = {
  title?: string;
  message: string;
  action?: ReactNode;
};

export function ErrorState({ title = "Something went wrong", message, action }: ErrorStateProps) {
  return (
    <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 p-5 text-sm text-rose-100">
      <div className="font-semibold text-rose-50">{title}</div>
      <p className="mt-1 leading-6">{message}</p>
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
