"use client";

import Link from "next/link";
import { Lightbulb } from "lucide-react";
import { useApi } from "@/lib/api";
import { count, isKnown, money, percent, signedPercent } from "@/lib/format";
import { SEGMENT_TONE } from "@/lib/theme";
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  PageHeader,
  SectionHeader,
  Skeleton,
  Value,
} from "@/components/ui";
import { HorizontalBars, KpiCard, RevenueChart } from "@/components/data";

type Insights = {
  hasData: boolean;
  review: string;
  mode: string;
  facts: {
    revenue?: { last30Days?: number; previous30Days?: number; changePct?: number | null; available?: boolean };
    customers?: { total: number; overdue: number; highValueOverdue: number; newLast90Days: number | null };
    inventory?: { stockValue: number | null; atRiskValue: number | null; atRiskSkus: number; over120DaysValue: number | null };
    opportunities?: { count: number; expectedValue: number | null };
  };
  trend: { available: boolean; points: { date: string; revenue: number; orders: number }[] };
  categories: { value: string; revenue: number; share: number | null; growth: number | null }[];
  brands: { value: string; revenue: number; growth: number | null }[];
  segments: { segment: string; customers: number; totalSpend: number | null; shareOfRevenue: number | null }[];
  concentration: { available: boolean; top10Share?: number; top20Share?: number };
};

const SECTION_TONE: Record<string, string> = {
  Wins: "var(--color-positive)",
  Risks: "var(--color-danger)",
  Opportunities: "var(--color-accent)",
  "Recommended actions": "var(--color-info)",
};

export default function InsightsPage() {
  const { data, error, isLoading, mutate } = useApi<Insights>("/insights");

  if (isLoading) return <InsightsSkeleton />;
  if (error) return <ErrorState error={error} retry={() => mutate()} />;
  if (!data?.hasData) {
    return (
      <div>
        <PageHeader eyebrow="Executive summary" title="Insights" />
        <EmptyState
          icon={<Lightbulb className="size-5" />}
          title="No data loaded"
          description="The weekly review is written from your computed metrics."
          action={
            <Link href="/data">
              <Button variant="primary">Go to Data</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const sections = parseSections(data.review);
  const revenue = data.facts.revenue;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Executive summary"
        title="Business review"
        subtitle="Everything below is derived from computed metrics — no commentary is written without a figure behind it."
        action={
          <Badge tone={data.mode === "ai" ? "positive" : "neutral"} dot>
            {data.mode === "ai" ? "Written by Claude" : "Composed from metrics"}
          </Badge>
        }
      />

      <section className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Revenue (last 30 days)"
          value={revenue?.last30Days ?? null}
          format="currency"
          trend={revenue?.changePct ?? null}
          detail={
            isKnown(revenue?.previous30Days)
              ? `versus ${money(revenue!.previous30Days)} in the prior 30 days`
              : undefined
          }
          accent
        />
        <KpiCard
          label="High-value customers overdue"
          value={data.facts.customers?.highValueOverdue ?? null}
          format="number"
          detail={`of ${count(data.facts.customers?.overdue)} overdue in total`}
          href="/customers?status=overdue"
        />
        <KpiCard
          label="Stock at risk"
          value={data.facts.inventory?.atRiskValue ?? null}
          format="currency"
          detail={
            isKnown(data.facts.inventory?.over120DaysValue)
              ? `${money(data.facts.inventory!.over120DaysValue)} over 120 days old`
              : undefined
          }
          href="/inventory?status=At%20Risk"
        />
        <KpiCard
          label="Opportunity pipeline"
          value={data.facts.opportunities?.expectedValue ?? null}
          format="currency"
          detail={`${count(data.facts.opportunities?.count)} opportunities detected`}
          href="/opportunities"
        />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        {sections.map((section) => (
          <Card key={section.title}>
            <div className="mb-3.5 flex items-center gap-2.5">
              <span
                className="size-2 rounded-full"
                style={{ background: SECTION_TONE[section.title] ?? "var(--color-ink-4)" }}
              />
              <h2 className="text-[14px] font-semibold">{section.title}</h2>
            </div>
            <ul className="space-y-2.5">
              {section.items.map((item, index) => (
                <li
                  key={index}
                  className="flex gap-2.5 text-[13px] leading-relaxed text-[var(--color-ink-2)]"
                >
                  <span className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--color-ink-4)]" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </Card>
        ))}
      </div>

      {data.trend?.available ? (
        <Card>
          <SectionHeader title="Revenue trajectory" subtitle="Weekly revenue over the review window" />
          <RevenueChart points={data.trend.points} height={220} />
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <SectionHeader title="Category performance" subtitle="Revenue with 90-day growth" />
          {data.categories.length ? (
            <div className="space-y-2">
              {data.categories.slice(0, 8).map((row) => (
                <div key={row.value} className="flex items-center gap-3">
                  <span className="w-24 shrink-0 truncate text-[12.5px]">{row.value}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                    <div
                      className="h-full rounded-full bg-[var(--color-accent)]"
                      style={{
                        width: `${((row.revenue / data.categories[0].revenue) * 100).toFixed(1)}%`,
                      }}
                    />
                  </div>
                  <span className="num w-14 shrink-0 text-right text-[12px] text-[var(--color-ink-3)]">
                    {money(row.revenue, { compact: true })}
                  </span>
                  <span
                    className="num w-12 shrink-0 text-right text-[11.5px]"
                    style={{
                      color: !isKnown(row.growth)
                        ? "var(--color-ink-4)"
                        : row.growth >= 0
                          ? "var(--color-positive)"
                          : "var(--color-danger)",
                    }}
                  >
                    {signedPercent(row.growth, 0)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState compact title="No category data" />
          )}
        </Card>

        <Card>
          <SectionHeader
            title="Customer base"
            subtitle={
              data.concentration?.available && isKnown(data.concentration.top10Share)
                ? `Top 10% of customers drive ${percent(data.concentration.top10Share)} of revenue`
                : undefined
            }
          />
          <div className="space-y-2">
            {data.segments.slice(0, 8).map((segment) => (
              <Link
                key={segment.segment}
                href={`/customers?segment=${encodeURIComponent(segment.segment)}`}
                className="flex items-center gap-3 rounded-[8px] px-1.5 py-1 transition-colors hover:bg-[var(--color-surface-2)]"
              >
                <Badge size="sm" tone={SEGMENT_TONE[segment.segment] ?? "neutral"} dot>
                  {segment.segment}
                </Badge>
                <span className="num ml-auto text-[12px] text-[var(--color-ink-4)]">
                  {segment.customers}
                </span>
                <span className="num w-16 text-right text-[12px] font-medium">
                  {money(segment.totalSpend, { compact: true })}
                </span>
                <span className="num w-11 text-right text-[11.5px] text-[var(--color-ink-4)]">
                  {percent(segment.shareOfRevenue)}
                </span>
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}

function parseSections(review: string) {
  const sections: { title: string; items: string[] }[] = [];
  let current: { title: string; items: string[] } | null = null;
  for (const line of review.split("\n")) {
    const trimmed = line.trim();
    if (trimmed.startsWith("## ")) {
      current = { title: trimmed.slice(3).trim(), items: [] };
      sections.push(current);
    } else if (trimmed.startsWith("- ") && current) {
      current.items.push(trimmed.slice(2).replace(/\*\*/g, ""));
    } else if (trimmed && current && !trimmed.startsWith("#")) {
      current.items.push(trimmed.replace(/\*\*/g, ""));
    }
  }
  return sections.filter((section) => section.items.length);
}

function InsightsSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-16 w-96" />
      <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[124px]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <CardSkeleton rows={4} />
        <CardSkeleton rows={4} />
      </div>
    </div>
  );
}
