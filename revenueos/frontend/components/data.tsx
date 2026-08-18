"use client";

import Link from "next/link";
import { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ArrowDownRight, ArrowUpRight, ChevronRight, Minus } from "lucide-react";
import { cx, isKnown, money, percent, score as fmtScore } from "@/lib/format";
import { CHART_COLORS, CONFIDENCE_TONE, matchTone, type Tone } from "@/lib/theme";
import { Badge, Card, Value } from "@/components/ui";

/* ------------------------------------------------------------------ *
 * KPI
 * ------------------------------------------------------------------ */
export function KpiCard({
  label,
  value,
  detail,
  format = "number",
  href,
  trend,
  accent = false,
}: {
  label: string;
  value: number | null | undefined;
  detail?: string;
  format?: "currency" | "number" | "percent0to100";
  href?: string;
  trend?: number | null;
  accent?: boolean;
}) {
  const known = isKnown(value);
  const rendered = !known
    ? null
    : format === "currency"
      ? money(value, { compact: Math.abs(value) >= 100000 })
      : format === "percent0to100"
        ? fmtScore(value)
        : Math.round(value).toLocaleString("en-GB");

  const body = (
    <Card
      className={cx(
        "group relative h-full overflow-hidden",
        href && "transition-colors hover:border-[var(--color-line-strong)]",
      )}
    >
      {accent ? (
        <div
          className="pointer-events-none absolute -right-16 -top-16 size-40 rounded-full opacity-[0.16] blur-2xl"
          style={{ background: "var(--color-accent)" }}
        />
      ) : null}
      <div className="relative">
        <div className="flex items-start justify-between gap-2">
          <div className="eyebrow">{label}</div>
          {href ? (
            <ChevronRight className="size-3.5 shrink-0 text-[var(--color-ink-4)] transition-transform group-hover:translate-x-0.5" />
          ) : null}
        </div>
        <div className="mt-3 flex items-baseline gap-2">
          <Value known={known} className="num text-[27px] font-semibold leading-none">
            {rendered}
          </Value>
          {isKnown(trend) ? <TrendPill value={trend} /> : null}
        </div>
        {detail ? (
          <div className="mt-2.5 text-[12px] leading-relaxed text-[var(--color-ink-3)]">
            {detail}
          </div>
        ) : null}
      </div>
    </Card>
  );

  return href ? (
    <Link href={href} className="block h-full">
      {body}
    </Link>
  ) : (
    body
  );
}

export function TrendPill({ value }: { value: number }) {
  const flat = Math.abs(value) < 0.005;
  const tone: Tone = flat ? "neutral" : value > 0 ? "positive" : "danger";
  const Icon = flat ? Minus : value > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <Badge tone={tone} size="sm">
      <Icon className="size-3" />
      {flat ? "flat" : `${value > 0 ? "+" : ""}${(value * 100).toFixed(1)}%`}
    </Badge>
  );
}

export function Stat({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <div>
      <div className="eyebrow mb-1.5">{label}</div>
      <div className="num text-[16px] font-semibold leading-none">{children}</div>
      {hint ? <div className="mt-1.5 text-[11.5px] text-[var(--color-ink-4)]">{hint}</div> : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Match explainability — the visual form of the signal payload
 * ------------------------------------------------------------------ */
export type MatchSignal = {
  name: string;
  key: string;
  value: number;
  impact: number;
  direction: "positive" | "neutral" | "negative";
  reason: string;
};

export function MatchScore({
  pct,
  confidence,
  size = "md",
}: {
  pct: number | null | undefined;
  confidence?: string;
  size?: "sm" | "md" | "lg";
}) {
  const tone = matchTone(pct);
  const sizes = {
    sm: "text-[13px]",
    md: "text-[17px]",
    lg: "text-[24px]",
  };
  return (
    <div className="flex items-center gap-2">
      <span
        className={cx("num font-semibold leading-none", sizes[size])}
        style={{ color: `var(--color-${tone === "neutral" ? "ink-2" : tone})` }}
      >
        {isKnown(pct) ? `${Math.round(pct)}%` : "—"}
      </span>
      {confidence ? (
        <Badge tone={CONFIDENCE_TONE[confidence] ?? "neutral"} size="sm">
          {confidence} confidence
        </Badge>
      ) : null}
    </div>
  );
}

export function SignalBreakdown({
  signals,
  missing,
  limit = 6,
}: {
  signals: MatchSignal[];
  missing?: string[];
  limit?: number;
}) {
  if (!signals?.length) return null;
  const max = Math.max(...signals.map((s) => s.impact), 0.0001);

  return (
    <div className="space-y-2.5">
      {signals.slice(0, limit).map((signal) => {
        const tone: Tone =
          signal.direction === "positive"
            ? "positive"
            : signal.direction === "negative"
              ? "danger"
              : "neutral";
        return (
          <div key={signal.key} className="grid grid-cols-[132px_1fr] items-start gap-3">
            <div className="pt-0.5 text-[11.5px] font-medium text-[var(--color-ink-2)]">
              {signal.name}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                  <div
                    className="h-full rounded-full transition-[width] duration-500"
                    style={{
                      width: `${Math.max(4, (signal.impact / max) * 100)}%`,
                      background: `var(--color-${tone === "neutral" ? "ink-4" : tone})`,
                    }}
                  />
                </div>
                <span className="num w-9 shrink-0 text-right text-[11px] text-[var(--color-ink-4)]">
                  {(signal.impact * 100).toFixed(0)}
                </span>
              </div>
              <div className="mt-1 text-[11.5px] leading-snug text-[var(--color-ink-3)]">
                {signal.reason}
              </div>
            </div>
          </div>
        );
      })}
      {missing?.length ? (
        <div className="border-t border-[var(--color-line)] pt-2.5 text-[11px] leading-relaxed text-[var(--color-ink-4)]">
          Not used (no data): {missing.join(", ")}. Their weight was redistributed across the
          signals above rather than counted against this match.
        </div>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Tables
 * ------------------------------------------------------------------ */
export function DataTable<T>({
  rows,
  columns,
  onRowClick,
  empty,
  sortKey,
  sortOrder,
  onSort,
  rowKey,
}: {
  rows: T[];
  columns: {
    key: string;
    header: string;
    width?: string;
    align?: "left" | "right";
    sortable?: boolean;
    render: (row: T) => ReactNode;
  }[];
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  sortKey?: string;
  sortOrder?: "asc" | "desc";
  onSort?: (key: string) => void;
  rowKey: (row: T) => string;
}) {
  if (!rows.length && empty) return <>{empty}</>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse">
        <thead>
          <tr className="border-b border-[var(--color-line)]">
            {columns.map((column) => (
              <th
                key={column.key}
                style={{ width: column.width }}
                className={cx(
                  "eyebrow whitespace-nowrap px-3 py-2.5 font-semibold",
                  column.align === "right" ? "text-right" : "text-left",
                  column.sortable && onSort && "cursor-pointer select-none hover:text-[var(--color-ink-2)]",
                )}
                onClick={column.sortable && onSort ? () => onSort(column.key) : undefined}
              >
                {column.header}
                {sortKey === column.key ? (
                  <span className="ml-1 text-[var(--color-accent)]">
                    {sortOrder === "asc" ? "↑" : "↓"}
                  </span>
                ) : null}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={rowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={cx(
                "border-b border-[var(--color-line)] transition-colors last:border-0",
                onRowClick && "cursor-pointer hover:bg-[var(--color-surface-2)]",
              )}
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cx(
                    "px-3 py-2.5 text-[13px]",
                    column.align === "right" && "text-right",
                  )}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Charts
 * ------------------------------------------------------------------ */
const tooltipStyle = {
  background: "var(--color-elevated)",
  border: "1px solid var(--color-line-strong)",
  borderRadius: 10,
  fontSize: 12,
  padding: "8px 10px",
  boxShadow: "var(--shadow-pop)",
  color: "var(--color-ink)",
};

export function RevenueChart({
  points,
  height = 240,
}: {
  points: { date: string; revenue: number; orders: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={points} margin={{ top: 6, right: 4, bottom: 0, left: -18 }}>
        <defs>
          <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--color-accent)" stopOpacity={0.28} />
            <stop offset="100%" stopColor="var(--color-accent)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <XAxis
          dataKey="date"
          tickLine={false}
          axisLine={false}
          tickFormatter={(value: string) =>
            new Date(value).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
          }
          minTickGap={30}
        />
        <YAxis
          tickLine={false}
          axisLine={false}
          tickFormatter={(value: number) => money(value, { compact: true })}
          width={54}
        />
        <RechartsTooltip
          contentStyle={tooltipStyle}
          labelFormatter={(value) =>
            new Date(String(value)).toLocaleDateString("en-GB", {
              day: "numeric",
              month: "long",
              year: "numeric",
            })
          }
          formatter={(value: number, name: string) =>
            name === "revenue" ? [money(value), "Revenue"] : [value, "Orders"]
          }
        />
        <Area
          type="monotone"
          dataKey="revenue"
          stroke="var(--color-accent)"
          strokeWidth={2}
          fill="url(#revenueFill)"
          dot={false}
          activeDot={{ r: 3.5, strokeWidth: 0 }}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function HorizontalBars({
  data,
  valueKey = "value",
  labelKey = "label",
  format = "currency",
  height = 220,
  color,
}: {
  data: Record<string, unknown>[];
  valueKey?: string;
  labelKey?: string;
  format?: "currency" | "number" | "percent";
  height?: number;
  color?: string;
}) {
  const formatValue = (value: number) =>
    format === "currency"
      ? money(value, { compact: true })
      : format === "percent"
        ? percent(value)
        : Math.round(value).toLocaleString("en-GB");

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 0, right: 12, bottom: 0, left: 4 }}>
        <XAxis type="number" hide />
        <YAxis
          type="category"
          dataKey={labelKey}
          tickLine={false}
          axisLine={false}
          width={104}
          tick={{ fontSize: 11.5 }}
        />
        <RechartsTooltip
          contentStyle={tooltipStyle}
          cursor={{ fill: "var(--color-surface-2)" }}
          formatter={(value: number) => formatValue(value)}
        />
        <Bar dataKey={valueKey} radius={[0, 5, 5, 0]} barSize={13}>
          {data.map((_, index) => (
            <Cell key={index} fill={color ?? CHART_COLORS[index % CHART_COLORS.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DistributionChart({
  data,
  height = 180,
}: {
  data: { label: string; customers: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
        {/* Bucket labels are long money ranges; the tooltip carries them
            legibly instead of crushing eight rotated labels onto the axis. */}
        <XAxis dataKey="label" tickLine={false} axisLine={false} tick={false} height={6} />
        <YAxis tickLine={false} axisLine={false} width={30} />
        <RechartsTooltip
          contentStyle={tooltipStyle}
          cursor={{ fill: "var(--color-surface-2)" }}
          labelFormatter={(label) => `Lifetime spend ${label}`}
          formatter={(value: number) => [`${value} customers`, ""]}
        />
        <Bar dataKey="customers" fill="var(--color-accent)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DonutChart({
  data,
  height = 210,
}: {
  data: { name: string; value: number }[];
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <PieChart>
        <Pie
          data={data}
          dataKey="value"
          nameKey="name"
          innerRadius="58%"
          outerRadius="86%"
          paddingAngle={2}
          stroke="none"
        >
          {data.map((_, index) => (
            <Cell key={index} fill={CHART_COLORS[index % CHART_COLORS.length]} />
          ))}
        </Pie>
        <RechartsTooltip contentStyle={tooltipStyle} />
        <Legend
          verticalAlign="bottom"
          height={30}
          iconType="circle"
          iconSize={7}
          formatter={(value: string) => (
            <span style={{ color: "var(--color-ink-3)", fontSize: 11.5 }}>{value}</span>
          )}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
