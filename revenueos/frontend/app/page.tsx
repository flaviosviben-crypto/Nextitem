"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Boxes,
  ChevronRight,
  Sparkles,
  Target,
  TrendingUp,
  Users,
} from "lucide-react";
import { useApi } from "@/lib/api";
import { cx, greeting, isKnown, money, percent } from "@/lib/format";
import { SEGMENT_TONE, matchTone } from "@/lib/theme";
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
import {
  DistributionChart,
  DonutChart,
  HorizontalBars,
  KpiCard,
  RevenueChart,
} from "@/components/data";
import { Onboarding } from "@/components/onboarding";

type Kpi = {
  key: string;
  label: string;
  value: number | null;
  format: "currency" | "number" | "percent0to100";
  detail: string;
  href: string;
};

type Priority = {
  kind: string;
  title: string;
  detail: string;
  estimatedValue: number | null;
  customerCount: number;
  productCount: number;
  topScore: number;
  href: string;
  cta: string;
};

type Opportunity = {
  id: string;
  kindLabel: string;
  title: string;
  explanation: string;
  action: string;
  estimatedValue: number | null;
  probability: number;
  score: number;
  matchPct: number | null;
};

type Overview = {
  hasData: boolean;
  workspace: { name: string; counts: Record<string, number> };
  kpis: Kpi[];
  priorities: Priority[];
  opportunities: Opportunity[];
  opportunitySummary: { count: number; expectedValue: number | null; totalValue: number | null };
  revenueTrend: {
    available: boolean;
    reason?: string;
    points: { date: string; revenue: number; orders: number }[];
    change: number | null;
    last30Days: number;
  };
  segments: { segment: string; customers: number; totalSpend: number | null; shareOfRevenue: number | null }[];
  valueDistribution: { label: string; customers: number }[];
  concentration: { available: boolean; top10Share?: number; top20Share?: number };
  categoryPerformance: { value: string; revenue: number; growth: number | null }[];
  inventory: {
    skus: number;
    retailValue: number | null;
    atRiskValue: number | null;
    atRiskSkus: number;
    avgSellThrough: number | null;
    statusCounts: Record<string, number>;
  } | null;
  dataHealth: { score: number | null; grade: string; summary: string };
};

export default function OverviewPage() {
  const router = useRouter();
  const { data, error, isLoading, mutate } = useApi<Overview>("/overview");
  const { data: brief } = useApi<{ briefing: string; mode: string; hasData: boolean }>(
    "/overview/briefing",
  );

  if (isLoading) return <OverviewSkeleton />;
  if (error) return <ErrorState error={error} retry={() => mutate()} />;
  if (!data?.hasData) return <Onboarding />;

  const opportunityValue = data.opportunitySummary?.expectedValue;

  return (
    <div className="space-y-7">
      {/* ---------------- hero ---------------- */}
      <section className="animate-fade-up">
        <div className="eyebrow mb-2.5">{data.workspace.name}</div>
        <h1 className="text-[28px] font-semibold leading-tight tracking-[-0.03em]">
          {greeting()}.
        </h1>
        <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-[var(--color-ink-2)]">
          {isKnown(opportunityValue) ? (
            <>
              Your store has{" "}
              <span className="num font-semibold text-[var(--color-ink)]">
                {money(opportunityValue)}
              </span>{" "}
              in identified revenue opportunities.
            </>
          ) : (
            "Here is what needs your attention today."
          )}
        </p>

        {brief?.briefing ? (
          <div className="mt-4 flex max-w-3xl items-start gap-3 rounded-[12px] border border-[var(--color-line)] bg-[var(--color-surface)] px-4 py-3.5">
            <Sparkles className="mt-0.5 size-4 shrink-0 text-[var(--color-accent)]" />
            <div className="min-w-0">
              <p className="text-[13px] leading-relaxed text-[var(--color-ink-2)]">
                {brief.briefing}
              </p>
              {brief.mode === "deterministic" ? (
                <p className="mt-2 text-[11px] text-[var(--color-ink-4)]">
                  Composed from computed metrics. Add an Anthropic API key in Settings for a
                  written briefing over the same figures.
                </p>
              ) : null}
            </div>
          </div>
        ) : null}

        <div className="mt-5 flex flex-wrap gap-2.5">
          <Button
            variant="primary"
            icon={<Target className="size-3.5" />}
            onClick={() => router.push("/opportunities")}
          >
            See today&apos;s actions
          </Button>
          <Button
            icon={<Sparkles className="size-3.5" />}
            onClick={() => router.push("/analyst")}
          >
            Ask the analyst
          </Button>
        </div>
      </section>

      {/* ---------------- KPIs ---------------- */}
      <section className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        {data.kpis.map((kpi, index) => (
          <KpiCard
            key={kpi.key}
            label={kpi.label}
            value={kpi.value}
            detail={kpi.detail}
            format={kpi.format}
            href={kpi.href}
            accent={index === 0}
            trend={kpi.key === "revenueOpportunity" ? data.revenueTrend?.change : undefined}
          />
        ))}
      </section>

      {/* ---------------- priorities ---------------- */}
      <section>
        <SectionHeader
          eyebrow="AI priorities"
          title="Today's priorities"
          subtitle="Ranked by expected revenue, probability and how urgent the window is."
          action={
            <Link
              href="/opportunities"
              className="flex items-center gap-1 text-[12.5px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink)]"
            >
              All opportunities <ChevronRight className="size-3.5" />
            </Link>
          }
        />
        {data.priorities.length ? (
          <div className="space-y-2.5">
            {data.priorities.map((priority, index) => (
              <Link key={priority.kind} href={priority.href} className="block">
                <Card
                  padded={false}
                  className="group flex items-center gap-4 px-4 py-3.5 transition-colors hover:border-[var(--color-line-strong)]"
                >
                  <div className="num grid size-7 shrink-0 place-items-center rounded-full border border-[var(--color-line)] bg-[var(--color-surface-2)] text-[12px] font-semibold text-[var(--color-ink-3)]">
                    {index + 1}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13.5px] font-medium">{priority.title}</div>
                    <div className="mt-0.5 truncate text-[12px] text-[var(--color-ink-3)]">
                      {priority.detail}
                    </div>
                  </div>
                  <div className="hidden shrink-0 text-right sm:block">
                    <Value known={isKnown(priority.estimatedValue)} className="num text-[14px] font-semibold">
                      {money(priority.estimatedValue)}
                    </Value>
                    <div className="mt-0.5 text-[11px] text-[var(--color-ink-4)]">
                      potential value
                    </div>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-[var(--color-ink-4)] transition-transform group-hover:translate-x-0.5" />
                </Card>
              </Link>
            ))}
          </div>
        ) : (
          <EmptyState
            compact
            title="No priorities right now"
            description="Every customer is inside their normal window and no stock is at risk."
          />
        )}
      </section>

      {/* ---------------- opportunity feed + revenue ---------------- */}
      <section className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <Card>
          <SectionHeader
            title="Revenue trend"
            subtitle={
              data.revenueTrend?.available
                ? `${money(data.revenueTrend.last30Days)} in the last 30 days`
                : undefined
            }
            action={
              data.revenueTrend?.available && isKnown(data.revenueTrend.change) ? (
                <Badge tone={data.revenueTrend.change >= 0 ? "positive" : "danger"}>
                  {data.revenueTrend.change >= 0 ? "+" : ""}
                  {(data.revenueTrend.change * 100).toFixed(1)}% vs prior 30d
                </Badge>
              ) : undefined
            }
          />
          {data.revenueTrend?.available ? (
            <RevenueChart points={data.revenueTrend.points} />
          ) : (
            <EmptyState
              compact
              icon={<TrendingUp className="size-4" />}
              title="No revenue trend yet"
              description={data.revenueTrend?.reason}
            />
          )}
        </Card>

        <Card>
          <SectionHeader
            title="Opportunity feed"
            subtitle={`${data.opportunitySummary.count} detected`}
          />
          <div className="-mx-1 max-h-[280px] space-y-1.5 overflow-y-auto px-1">
            {data.opportunities.slice(0, 7).map((opportunity) => (
              <Link
                key={opportunity.id}
                href={`/opportunities?focus=${opportunity.id}`}
                className="block rounded-[10px] border border-[var(--color-line)] px-3 py-2.5 transition-colors hover:border-[var(--color-line-strong)] hover:bg-[var(--color-surface-2)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="truncate text-[12.5px] font-medium">{opportunity.title}</div>
                    <div className="mt-0.5 text-[11px] text-[var(--color-ink-4)]">
                      {opportunity.kindLabel}
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <div className="num text-[12.5px] font-semibold">
                      {money(opportunity.estimatedValue, { compact: true })}
                    </div>
                    <div className="num text-[10.5px] text-[var(--color-ink-4)]">
                      {opportunity.score.toFixed(0)}/100
                    </div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </Card>
      </section>

      {/* ---------------- customer + inventory health ---------------- */}
      <section className="grid gap-4 lg:grid-cols-2">
        <Card>
          <SectionHeader
            title="Customer health"
            subtitle={
              data.concentration?.available && isKnown(data.concentration.top20Share)
                ? `Your top 20% of customers drive ${percent(data.concentration.top20Share)} of revenue`
                : "Segments derived from your own spend distribution"
            }
            action={
              <Link href="/customers" className="text-[12.5px] text-[var(--color-ink-3)] hover:text-[var(--color-ink)]">
                View all
              </Link>
            }
          />
          <div className="grid gap-5 sm:grid-cols-[1fr_190px]">
            <div className="space-y-2">
              {data.segments.slice(0, 6).map((segment) => (
                <Link
                  key={segment.segment}
                  href={`/customers?segment=${encodeURIComponent(segment.segment)}`}
                  className="flex items-center gap-3 rounded-[8px] px-1.5 py-1 transition-colors hover:bg-[var(--color-surface-2)]"
                >
                  <Badge tone={SEGMENT_TONE[segment.segment] ?? "neutral"} size="sm" dot>
                    {segment.segment}
                  </Badge>
                  <div className="num ml-auto text-[12px] text-[var(--color-ink-3)]">
                    {segment.customers}
                  </div>
                  <div className="num w-16 text-right text-[12px] font-medium">
                    {money(segment.totalSpend, { compact: true })}
                  </div>
                </Link>
              ))}
            </div>
            {data.valueDistribution?.length ? (
              <div>
                <div className="eyebrow mb-1">Value distribution</div>
                <DistributionChart data={data.valueDistribution} height={168} />
              </div>
            ) : null}
          </div>
        </Card>

        <Card>
          <SectionHeader
            title="Inventory intelligence"
            subtitle={
              data.inventory
                ? `${data.inventory.skus} SKUs · ${money(data.inventory.retailValue, { compact: true })} retail value`
                : undefined
            }
            action={
              <Link href="/inventory" className="text-[12.5px] text-[var(--color-ink-3)] hover:text-[var(--color-ink)]">
                View all
              </Link>
            }
          />
          {data.inventory ? (
            <div className="grid gap-5 sm:grid-cols-[190px_1fr]">
              <DonutChart
                height={190}
                data={Object.entries(data.inventory.statusCounts).map(([name, value]) => ({
                  name,
                  value,
                }))}
              />
              <div className="space-y-3">
                <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-2.5">
                  <div className="eyebrow">Capital at risk</div>
                  <div className="num mt-1 text-[18px] font-semibold text-[var(--color-warning)]">
                    {money(data.inventory.atRiskValue)}
                  </div>
                  <div className="mt-0.5 text-[11px] text-[var(--color-ink-4)]">
                    across {data.inventory.atRiskSkus} SKUs
                  </div>
                </div>
                <div className="rounded-[10px] border border-[var(--color-line)] px-3 py-2.5">
                  <div className="eyebrow">Average sell-through</div>
                  <div className="num mt-1 text-[18px] font-semibold">
                    <Value known={isKnown(data.inventory.avgSellThrough)}>
                      {percent(data.inventory.avgSellThrough)}
                    </Value>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <EmptyState
              compact
              icon={<Boxes className="size-4" />}
              title="No inventory loaded"
              description="Upload your stock export to unlock product recommendations and dead-stock detection."
              action={<Button onClick={() => router.push("/data")}>Upload inventory</Button>}
            />
          )}
        </Card>
      </section>

      {/* ---------------- category performance ---------------- */}
      {data.categoryPerformance?.length ? (
        <section>
          <Card>
            <SectionHeader
              title="Category performance"
              subtitle="Revenue by category, with 90-day growth"
            />
            <div className="grid gap-6 lg:grid-cols-[1fr_1fr]">
              <HorizontalBars
                data={data.categoryPerformance.map((row) => ({
                  label: row.value,
                  value: row.revenue,
                }))}
                height={Math.max(180, data.categoryPerformance.length * 26)}
              />
              <div className="space-y-1.5 self-center">
                {data.categoryPerformance.slice(0, 6).map((row) => (
                  <div
                    key={row.value}
                    className="flex items-center justify-between gap-3 rounded-[8px] px-2 py-1.5 text-[12.5px]"
                  >
                    <span className="truncate">{row.value}</span>
                    <span className="num shrink-0 text-[var(--color-ink-3)]">
                      {money(row.revenue, { compact: true })}
                    </span>
                    <span
                      className={cx(
                        "num w-14 shrink-0 text-right text-[11.5px]",
                        !isKnown(row.growth)
                          ? "text-[var(--color-ink-4)]"
                          : row.growth >= 0
                            ? "text-[var(--color-positive)]"
                            : "text-[var(--color-danger)]",
                      )}
                    >
                      {isKnown(row.growth)
                        ? `${row.growth >= 0 ? "+" : ""}${(row.growth * 100).toFixed(0)}%`
                        : "—"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </Card>
        </section>
      ) : null}
    </div>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-7">
      <div>
        <Skeleton className="mb-3 h-3 w-32" />
        <Skeleton className="h-8 w-64" />
        <Skeleton className="mt-3 h-5 w-96" />
      </div>
      <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[124px]" />
        ))}
      </div>
      <div className="space-y-2.5">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[62px]" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.35fr_1fr]">
        <CardSkeleton rows={4} />
        <CardSkeleton rows={4} />
      </div>
    </div>
  );
}
