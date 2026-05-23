export function formatHuf(value?: number | null): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("hu-HU", {
    style: "currency",
    currency: "HUF",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatNumber(value?: number | null, digits = 1): string {
  if (value === null || value === undefined) return "-";
  return new Intl.NumberFormat("hu-HU", {
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatDate(value?: string | null): string {
  if (!value) return "-";
  return new Intl.DateTimeFormat("hu-HU", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}
