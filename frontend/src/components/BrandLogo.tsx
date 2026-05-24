import { useState } from "react";

type BrandLogoProps = {
  className?: string;
};

export function BrandLogo({ className = "" }: BrandLogoProps) {
  const [failed, setFailed] = useState(false);

  if (failed) {
    return (
      <div
        aria-label="CardGrader"
        className={`flex items-center justify-center rounded-lg border border-blue-400/30 bg-blue-500/10 text-xs font-semibold text-blue-100 ${className}`}
      >
        CG
      </div>
    );
  }

  return (
    <div className={`flex items-center justify-center rounded-lg ${className}`}>
      <img
        alt="CardGrader logo"
        className="h-full w-full object-contain"
        onError={() => setFailed(true)}
        src="/logo.png"
      />
    </div>
  );
}
