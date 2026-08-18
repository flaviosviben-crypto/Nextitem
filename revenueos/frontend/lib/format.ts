/**
 * Formatting rules, in one place.
 *
 * The central one: `null`/`undefined` means "we do not know", and every
 * formatter renders that as an explicit phrase — never as 0, never as "—"
 * with no explanation. A boutique owner acting on a fake zero is the exact
 * failure this product exists to avoid.
 */
export const UNKNOWN = "Not enough information";
export const UNKNOWN_SHORT = "—";

export function isKnown(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function money(value: unknown, opts?: { compact?: boolean; fallback?: string }): string {
  if (!isKnown(value)) return opts?.fallback ?? UNKNOWN_SHORT;
  const abs = Math.abs(value);
  if (opts?.compact && abs >= 1000) {
    const units: [number, string][] = [
      [1_000_000, "M"],
      [1_000, "K"],
    ];
    for (const [factor, suffix] of units) {
      if (abs >= factor) {
        const scaled = value / factor;
        const digits = Math.abs(scaled) >= 100 ? 0 : 1;
        return `€${scaled.toFixed(digits).replace(/\.0$/, "")}${suffix}`;
      }
    }
  }
  return `€${value.toLocaleString("en-GB", {
    minimumFractionDigits: abs < 100 && abs % 1 !== 0 ? 2 : 0,
    maximumFractionDigits: abs < 100 && abs % 1 !== 0 ? 2 : 0,
  })}`;
}

export function count(value: unknown, fallback = UNKNOWN_SHORT): string {
  if (!isKnown(value)) return fallback;
  return Math.round(value).toLocaleString("en-GB");
}

export function decimal(value: unknown, digits = 1, fallback = UNKNOWN_SHORT): string {
  if (!isKnown(value)) return fallback;
  return value.toFixed(digits);
}

/** A 0..1 ratio as a percentage. */
export function percent(value: unknown, digits = 0, fallback = UNKNOWN_SHORT): string {
  if (!isKnown(value)) return fallback;
  return `${(value * 100).toFixed(digits)}%`;
}

/** An already-0..100 score as a percentage. */
export function score(value: unknown, fallback = UNKNOWN_SHORT): string {
  if (!isKnown(value)) return fallback;
  return `${Math.round(value)}%`;
}

export function signedPercent(value: unknown, digits = 1, fallback = UNKNOWN_SHORT): string {
  if (!isKnown(value)) return fallback;
  return `${value >= 0 ? "+" : ""}${(value * 100).toFixed(digits)}%`;
}

export function days(value: unknown, fallback = UNKNOWN_SHORT): string {
  if (!isKnown(value)) return fallback;
  const rounded = Math.round(value);
  return `${rounded} ${Math.abs(rounded) === 1 ? "day" : "days"}`;
}

export function date(value: unknown, fallback = UNKNOWN_SHORT): string {
  if (typeof value !== "string" || !value) return fallback;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return fallback;
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function relativeDays(value: unknown): string {
  if (!isKnown(value)) return UNKNOWN_SHORT;
  const rounded = Math.round(value);
  if (rounded === 0) return "Today";
  if (rounded === 1) return "Yesterday";
  if (rounded < 30) return `${rounded} days ago`;
  if (rounded < 365) return `${Math.round(rounded / 30)} months ago`;
  const years = rounded / 365;
  return `${years.toFixed(years < 2 ? 1 : 0)} years ago`;
}

export function initials(name: unknown): string {
  if (typeof name !== "string" || !name.trim()) return "?";
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function greeting(now = new Date()): string {
  const hour = now.getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export function titleCase(value: unknown): string {
  if (typeof value !== "string" || !value) return "";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export const cx = (...classes: unknown[]) =>
  classes.filter((c): c is string => typeof c === "string" && c.length > 0).join(" ");
