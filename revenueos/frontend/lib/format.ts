/**
 * Formatting helpers.
 *
 * The rule everywhere: a null/undefined value renders as "—", never as 0.
 * A boutique must be able to tell "no sales" from "we don't know".
 */

const EUR = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

const EUR_PRECISE = new Intl.NumberFormat("en-IE", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 2,
});

export const EMPTY = "—";

export function money(value: number | null | undefined, precise = false): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return precise ? EUR_PRECISE.format(value) : EUR.format(value);
}

export function compactMoney(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `€${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 10_000) return `€${Math.round(value / 1000)}K`;
  if (abs >= 1_000) return `€${(value / 1000).toFixed(1)}K`;
  return EUR.format(value);
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return EMPTY;
  return `${(value * 100).toFixed(digits)}%`;
}

export function days(value: number | null | undefined): string {
  if (value === null || value === undefined) return EMPTY;
  if (value === 0) return "today";
  if (value === 1) return "1 day";
  return `${num(value)} days`;
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return EMPTY;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return EMPTY;
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function monthLabel(value: string): string {
  const [y, m] = value.split("-").map(Number);
  if (!y || !m) return value;
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-GB", {
    month: "short",
    year: "2-digit",
  });
}

/** Segment tone → semantic colour role. */
export function toneColor(tone: string | null | undefined): string {
  switch (tone) {
    case "positive":
      return "var(--good)";
    case "warning":
      return "var(--warning)";
    case "negative":
      return "var(--critical)";
    default:
      return "var(--ink-3)";
  }
}

export function riskColor(riskClass: string | null | undefined): string {
  switch (riskClass) {
    case "Dead Stock":
      return "var(--critical)";
    case "At Risk":
      return "var(--serious)";
    case "Slow Moving":
      return "var(--warning)";
    case "Hot":
      return "var(--s1)";
    case "Healthy":
      return "var(--good)";
    default:
      return "var(--ink-3)";
  }
}

export function matchColor(pctValue: number | null | undefined): string {
  if (pctValue === null || pctValue === undefined) return "var(--ink-3)";
  if (pctValue >= 80) return "var(--good)";
  if (pctValue >= 60) return "var(--s1)";
  if (pctValue >= 40) return "var(--warning)";
  return "var(--ink-3)";
}

export const SERIES = [
  "var(--s1)",
  "var(--s2)",
  "var(--s3)",
  "var(--s4)",
  "var(--s5)",
  "var(--s6)",
  "var(--s7)",
  "var(--s8)",
];

/** Fixed-slot assignment: a series keeps its colour when others are filtered out. */
export function seriesColor(index: number): string {
  return SERIES[index] ?? "var(--ink-3)";
}

export function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}
