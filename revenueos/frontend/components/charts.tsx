"use client";

/**
 * Hand-rolled SVG charts.
 *
 * Deliberately no charting library: it keeps the bundle small, the marks exactly
 * to spec (2px lines, 4px rounded data-ends, 2px surface gaps, recessive grid),
 * and the hover layer under our control. Every chart with a plot ships a
 * tooltip; identity is never carried by colour alone.
 */

import { ReactNode, useMemo, useRef, useState } from "react";
import { EMPTY, compactMoney, monthLabel, num } from "@/lib/format";

const SURFACE = "var(--surface)";
const GRID = "var(--grid)";
const INK3 = "var(--ink-3)";

/** Ordinal blue ramp — light to dark, safe on both surfaces. */
export const ORDINAL = ["#86b6ef", "#6da7ec", "#3987e5", "#256abf", "#184f95"];

function Tooltip({
  x,
  y,
  children,
  width = 190,
}: {
  x: number;
  y: number;
  children: ReactNode;
  width?: number;
}) {
  return (
    <div
      className="pointer-events-none absolute z-20 rounded-lg border border-[var(--line-strong)] bg-[var(--raised)] px-3 py-2 text-[12px] shadow-lg"
      style={{
        left: Math.max(4, x - width / 2),
        top: Math.max(4, y - 8),
        width,
        transform: "translateY(-100%)",
      }}
    >
      {children}
    </div>
  );
}

// ------------------------------------------------------------ trend chart ---

export type TrendPoint = {
  month: string;
  revenue: number;
  orders: number;
  customers: number;
  avg_order_value: number | null;
};

/**
 * Single-series revenue line with a crosshair. One series, so no legend box —
 * the section title names it.
 */
export function TrendChart({ data, height = 200 }: { data: TrendPoint[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const W = 720;
  const H = height;
  const pad = { top: 16, right: 16, bottom: 26, left: 52 };

  const geometry = useMemo(() => {
    if (data.length < 2) return null;
    const max = Math.max(...data.map((d) => d.revenue), 1);
    const innerW = W - pad.left - pad.right;
    const innerH = H - pad.top - pad.bottom;
    const x = (i: number) => pad.left + (i / (data.length - 1)) * innerW;
    const y = (v: number) => pad.top + innerH - (v / max) * innerH;
    const line = data.map((d, i) => `${i === 0 ? "M" : "L"} ${x(i)} ${y(d.revenue)}`).join(" ");
    const area = `${line} L ${x(data.length - 1)} ${pad.top + innerH} L ${x(0)} ${pad.top + innerH} Z`;
    const ticks = [0, 0.5, 1].map((f) => ({ value: max * f, y: y(max * f) }));
    return { max, x, y, line, area, ticks, innerH };
  }, [data, H]);

  if (!geometry) {
    return (
      <div className="flex h-[200px] items-center justify-center text-[13px] text-[var(--ink-3)]">
        Not enough dated history to plot a trend.
      </div>
    );
  }

  const onMove = (event: React.MouseEvent<HTMLDivElement>) => {
    const rect = wrapRef.current?.getBoundingClientRect();
    if (!rect) return;
    const ratio = (event.clientX - rect.left) / rect.width;
    const svgX = ratio * W;
    const innerW = W - pad.left - pad.right;
    const idx = Math.round(((svgX - pad.left) / innerW) * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, idx)));
  };

  const active = hover !== null ? data[hover] : null;
  const tipX = hover !== null ? (geometry.x(hover) / W) * (wrapRef.current?.clientWidth || W) : 0;

  return (
    <div
      ref={wrapRef}
      className="relative"
      onMouseMove={onMove}
      onMouseLeave={() => setHover(null)}
    >
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height }} role="img"
        aria-label="Monthly revenue trend">
        <defs>
          <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--s1)" stopOpacity="0.22" />
            <stop offset="100%" stopColor="var(--s1)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {geometry.ticks.map((t, i) => (
          <g key={i}>
            <line x1={pad.left} x2={W - pad.right} y1={t.y} y2={t.y} stroke={GRID} strokeWidth="1" />
            <text x={pad.left - 8} y={t.y + 4} textAnchor="end" fontSize="10" fill={INK3}>
              {compactMoney(t.value)}
            </text>
          </g>
        ))}

        <path d={geometry.area} fill="url(#trendFill)" />
        <path
          d={geometry.line}
          fill="none"
          stroke="var(--s1)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {data.map((d, i) =>
          i % Math.ceil(data.length / 6) === 0 || i === data.length - 1 ? (
            <text key={d.month} x={geometry.x(i)} y={H - 8} textAnchor="middle" fontSize="10" fill={INK3}>
              {monthLabel(d.month)}
            </text>
          ) : null,
        )}

        {hover !== null && (
          <g>
            <line
              x1={geometry.x(hover)}
              x2={geometry.x(hover)}
              y1={pad.top}
              y2={pad.top + geometry.innerH}
              stroke="var(--line-strong)"
              strokeWidth="1"
            />
            {/* 2px surface ring keeps the marker readable over the line */}
            <circle
              cx={geometry.x(hover)}
              cy={geometry.y(data[hover].revenue)}
              r="5"
              fill="var(--s1)"
              stroke={SURFACE}
              strokeWidth="2"
            />
          </g>
        )}
      </svg>

      {active && (
        <Tooltip x={tipX} y={height - 10}>
          <div className="font-semibold">{monthLabel(active.month)}</div>
          <div className="mt-1 flex justify-between gap-4 text-[var(--ink-2)]">
            <span>Revenue</span>
            <span className="num text-[var(--ink)]">{compactMoney(active.revenue)}</span>
          </div>
          <div className="flex justify-between gap-4 text-[var(--ink-2)]">
            <span>Orders</span>
            <span className="num text-[var(--ink)]">{num(active.orders)}</span>
          </div>
          <div className="flex justify-between gap-4 text-[var(--ink-2)]">
            <span>Customers</span>
            <span className="num text-[var(--ink)]">{num(active.customers)}</span>
          </div>
        </Tooltip>
      )}
    </div>
  );
}

// --------------------------------------------------------------- bar list ---

export type BarRow = {
  label: string;
  value: number;
  secondary?: string;
  color?: string;
  href?: string;
};

/**
 * Ranked horizontal bars. Direct-labelled, so no legend and no axis needed —
 * the label and the value are on the row itself.
 */
export function BarList({
  rows,
  format = compactMoney,
  emptyMessage = "No data yet.",
  max: providedMax,
}: {
  rows: BarRow[];
  format?: (v: number) => string;
  emptyMessage?: string;
  max?: number;
}) {
  const max = providedMax ?? Math.max(...rows.map((r) => r.value), 1);
  if (!rows.length) {
    return <p className="py-6 text-center text-[13px] text-[var(--ink-3)]">{emptyMessage}</p>;
  }
  return (
    <div className="space-y-2.5">
      {rows.map((row, i) => (
        <div key={row.label} className="group">
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[13px]">
            <span className="truncate" title={row.label}>
              {row.label}
            </span>
            <span className="num shrink-0 text-[var(--ink-2)]">
              {format(row.value)}
              {row.secondary && <span className="ml-2 text-[var(--ink-3)]">{row.secondary}</span>}
            </span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: GRID }}>
            <div
              className="h-full rounded-full transition-[width] duration-500"
              style={{
                width: `${Math.max(2, (row.value / max) * 100)}%`,
                background: row.color || `var(--s${(i % 8) + 1})`,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------- distribution bar ---

export type SegmentDatum = { label: string; value: number; color: string; hint?: string };

/**
 * A single stacked bar for composition, with a 2px surface gap between segments
 * and a legend beneath (identity never by colour alone).
 */
export function StackedBar({
  data,
  format = num,
}: {
  data: SegmentDatum[];
  format?: (v: number) => string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const total = data.reduce((sum, d) => sum + d.value, 0);
  if (!total) {
    return <p className="py-4 text-[13px] text-[var(--ink-3)]">Nothing to show yet.</p>;
  }
  return (
    <div>
      <div className="flex h-3 w-full gap-[2px] overflow-hidden rounded-full">
        {data.map((d, i) => (
          <div
            key={d.label}
            className="h-full transition-opacity first:rounded-l-full last:rounded-r-full"
            style={{
              width: `${(d.value / total) * 100}%`,
              background: d.color,
              opacity: hover === null || hover === i ? 1 : 0.35,
            }}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            title={`${d.label}: ${format(d.value)}`}
          />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-1 gap-x-5 gap-y-1.5 sm:grid-cols-2">
        {data.map((d, i) => (
          <div
            key={d.label}
            className="flex items-center justify-between gap-2 text-[12px]"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: d.color }} />
              <span className="truncate text-[var(--ink-2)]" title={d.hint || d.label}>
                {d.label}
              </span>
            </span>
            <span className="num shrink-0">{format(d.value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ----------------------------------------------------------------- funnel ---

export function Funnel({
  stages,
}: {
  stages: { label: string; value: number; hint?: string }[];
}) {
  const max = Math.max(...stages.map((s) => s.value), 1);
  return (
    <div className="space-y-3.5">
      {stages.map((stage, i) => {
        const prior = i > 0 ? stages[i - 1].value : null;
        const rate = prior && prior > 0 ? stage.value / prior : null;
        return (
          <div key={stage.label}>
            <div className="mb-1.5 flex items-baseline justify-between gap-3">
              <span className="text-[13px]">{stage.label}</span>
              <span className="num text-[13px] font-medium">
                {num(stage.value)}
                {rate !== null && (
                  <span className="ml-2 text-[11px] font-normal text-[var(--ink-3)]">
                    {(rate * 100).toFixed(0)}% of {stages[i - 1].label.toLowerCase()}
                  </span>
                )}
              </span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: GRID }}>
              <div
                className="h-full rounded-full transition-[width] duration-500"
                style={{ width: `${Math.max(1.5, (stage.value / max) * 100)}%`, background: ORDINAL[i % ORDINAL.length] }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// -------------------------------------------------------------- sparkline ---

export function Sparkline({
  values,
  width = 96,
  height = 26,
  color = "var(--s1)",
}: {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (values.length < 2) return <span className="text-[var(--ink-3)]">{EMPTY}</span>;
  const max = Math.max(...values);
  const min = Math.min(...values);
  const span = max - min || 1;
  const path = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / span) * (height - 4) - 2;
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} className="overflow-visible" aria-hidden="true">
      <path d={path} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// -------------------------------------------------------- signal breakdown --

/**
 * The match explanation: each signal's contribution to the score. Signals that
 * could not be measured are listed separately rather than shown as zero — that
 * distinction is the whole point of the engine.
 */
export function SignalBreakdown({
  signals,
}: {
  signals: { label: string; score: number; weight: number; impact: number; reason: string; applicable: boolean }[];
}) {
  const live = signals.filter((s) => s.applicable).sort((a, b) => b.impact - a.impact);
  const missing = signals.filter((s) => !s.applicable);

  return (
    <div className="space-y-3">
      {live.map((s) => (
        <div key={s.label}>
          <div className="flex items-baseline justify-between gap-3 text-[12px]">
            <span className="font-medium">{s.label}</span>
            <span className="num text-[var(--ink-3)]">
              {(s.score * 100).toFixed(0)}% · weight {(s.weight * 100).toFixed(0)}%
            </span>
          </div>
          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full" style={{ background: GRID }}>
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.max(1, s.score * 100)}%`,
                background: s.score >= 0.6 ? "var(--good)" : s.score >= 0.35 ? "var(--warning)" : "var(--critical)",
              }}
            />
          </div>
          <p className="mt-1 text-[12px] leading-snug text-[var(--ink-2)]">{s.reason}</p>
        </div>
      ))}

      {missing.length > 0 && (
        <div className="rounded-lg border border-dashed border-[var(--line)] p-3">
          <div className="eyebrow mb-1.5">Not measured</div>
          <ul className="space-y-1">
            {missing.map((s) => (
              <li key={s.label} className="text-[12px] text-[var(--ink-3)]">
                <span className="text-[var(--ink-2)]">{s.label}</span> — {s.reason}
              </li>
            ))}
          </ul>
          <p className="mt-2 text-[11px] leading-snug text-[var(--ink-3)]">
            These signals are excluded from the score rather than counted as zero, so missing
            data lowers confidence, not the match.
          </p>
        </div>
      )}
    </div>
  );
}
