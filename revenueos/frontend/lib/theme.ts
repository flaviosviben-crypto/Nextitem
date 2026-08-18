/** Semantic colour lookups shared by badges, charts and meters. */
export type Tone = "accent" | "positive" | "warning" | "danger" | "info" | "neutral";

export const SEGMENT_TONE: Record<string, Tone> = {
  Champions: "positive",
  VIP: "positive",
  Loyal: "positive",
  "High Potential": "accent",
  Promising: "accent",
  New: "info",
  "At Risk": "warning",
  Sleeping: "warning",
  Lost: "danger",
  "Discount Driven": "neutral",
};

export const STOCK_TONE: Record<string, Tone> = {
  Hot: "positive",
  Healthy: "neutral",
  "Slow Moving": "info",
  "At Risk": "warning",
  "Dead Stock": "danger",
};

export const CONFIDENCE_TONE: Record<string, Tone> = {
  high: "positive",
  medium: "info",
  low: "warning",
  "very low": "danger",
};

export const PIPELINE_STAGES = [
  { key: "new", label: "New", tone: "neutral" as Tone },
  { key: "contacted", label: "Contacted", tone: "info" as Tone },
  { key: "interested", label: "Interested", tone: "accent" as Tone },
  { key: "won", label: "Won", tone: "positive" as Tone },
  { key: "lost", label: "Lost", tone: "danger" as Tone },
];

/** Categorical series colours — distinguishable in both themes. */
export const CHART_COLORS = [
  "#6d6bf5",
  "#3ecf8e",
  "#56b8f0",
  "#f5b544",
  "#f76d7a",
  "#a78bfa",
  "#2dd4bf",
  "#fb923c",
];

export function matchTone(pct: number | null | undefined): Tone {
  if (typeof pct !== "number") return "neutral";
  if (pct >= 75) return "positive";
  if (pct >= 60) return "accent";
  if (pct >= 45) return "info";
  return "neutral";
}

export function riskTone(score: number | null | undefined): Tone {
  if (typeof score !== "number") return "neutral";
  if (score >= 75) return "danger";
  if (score >= 55) return "warning";
  if (score >= 40) return "info";
  return "positive";
}
