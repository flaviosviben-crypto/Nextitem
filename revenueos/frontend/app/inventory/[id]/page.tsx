"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft, Users } from "lucide-react";
import { useApi } from "@/lib/api";
import { count, cx, date as fmtDate, isKnown, money, percent } from "@/lib/format";
import { SEGMENT_TONE, STOCK_TONE, riskTone } from "@/lib/theme";
import {
  Badge,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Note,
  SectionHeader,
  Skeleton,
  Value,
} from "@/components/ui";
import {
  HorizontalBars,
  MatchScore,
  SignalBreakdown,
  Stat,
  type MatchSignal,
} from "@/components/data";
import { ScoreRing } from "@/components/ui";

type Detail = {
  product: {
    productId: string;
    name: string;
    sku: string | null;
    brand: string | null;
    category: string | null;
    subcategory: string | null;
    color: string | null;
    size: string | null;
    season: string | null;
    gender: string | null;
    price: number | null;
    originalPrice: number | null;
    cost: number | null;
    stock: number | null;
    retailValue: number | null;
    marginPct: number | null;
    marginValue: number | null;
    daysInStock: number | null;
    daysInStockEstimated: boolean;
    unitsSold: number | null;
    unitsSold90d: number | null;
    sellThrough: number | null;
    weeklyVelocity: number | null;
    weeksOfCover: number | null;
    riskScore: number | null;
    status: string | null;
    arrivalDate: string | null;
    lastSoldDate: string | null;
    revenue: number | null;
    avgSellingPrice: number | null;
  };
  riskDrivers: { name: string; points: number; detail: string; weight: number }[];
  recommendedAction: { action: string; label: string; detail: string };
  statusMeta: { tone?: string; meaning?: string };
  bestCustomers: {
    customerId: string;
    customerName: string;
    segment: string | null;
    totalSpend: number | null;
    scorePct: number;
    dataConfidence: string;
    signals: MatchSignal[];
    missingSignals: string[];
    headline: string;
  }[];
  salesHistory: { month: string; units: number | null; revenue: number | null }[];
};

export default function ProductDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;
  const { data, error, isLoading, mutate } = useApi<Detail>(id ? `/inventory/${id}` : null);

  if (isLoading) return <ProductSkeleton />;
  if (error) return <ErrorState error={error} retry={() => mutate()} />;
  if (!data) return null;

  const p = data.product;

  return (
    <div className="space-y-5">
      <button
        onClick={() => router.push("/inventory")}
        className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink)]"
      >
        <ArrowLeft className="size-3.5" /> All inventory
      </button>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[21px] font-semibold tracking-[-0.02em]">{p.name}</h1>
              {p.status ? (
                <Badge tone={STOCK_TONE[p.status] ?? "neutral"}>{p.status}</Badge>
              ) : null}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-[var(--color-ink-4)]">
              {p.sku ? <span className="font-mono">{p.sku}</span> : null}
              {[p.brand, p.category, p.subcategory, p.color, p.size ? `Size ${p.size}` : null, p.season]
                .filter(Boolean)
                .map((value) => (
                  <span key={String(value)}>· {value}</span>
                ))}
            </div>
            {data.statusMeta?.meaning ? (
              <p className="mt-2.5 text-[12.5px] text-[var(--color-ink-3)]">
                {data.statusMeta.meaning}
              </p>
            ) : null}
          </div>
          <div className="flex items-center gap-7">
            <div className="grid grid-cols-2 gap-x-8 gap-y-4">
              <Stat label="Price">
                <Value known={isKnown(p.price)}>{money(p.price)}</Value>
              </Stat>
              <Stat label="Stock">
                <Value known={isKnown(p.stock)}>{count(p.stock)}</Value>
              </Stat>
              <Stat label="Stock value">
                <Value known={isKnown(p.retailValue)}>{money(p.retailValue)}</Value>
              </Stat>
              <Stat label="Margin">
                <Value known={isKnown(p.marginPct)}>
                  {isKnown(p.marginPct) ? `${p.marginPct.toFixed(0)}%` : null}
                </Value>
              </Stat>
            </div>
            <div className="text-center">
              <ScoreRing value={p.riskScore} size={62} tone={riskTone(p.riskScore)} />
              <div className="mt-1.5 text-[10.5px] text-[var(--color-ink-4)]">Risk score</div>
            </div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[1fr_1.15fr]">
        <Card>
          <SectionHeader
            eyebrow="Why this score"
            title="Risk drivers"
            subtitle="Each driver contributes only when its input exists in your data."
          />
          {data.riskDrivers.length ? (
            <div className="space-y-2.5">
              {data.riskDrivers.map((driver) => (
                <div key={driver.name} className="grid grid-cols-[120px_1fr] items-center gap-3">
                  <div className="text-[11.5px] font-medium text-[var(--color-ink-2)]">
                    {driver.name}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                        <div
                          className="h-full rounded-full"
                          style={{
                            width: `${Math.min(100, (driver.points / 35) * 100)}%`,
                            background:
                              driver.points > 15
                                ? "var(--color-danger)"
                                : driver.points > 7
                                  ? "var(--color-warning)"
                                  : "var(--color-ink-4)",
                          }}
                        />
                      </div>
                      <span className="num w-8 shrink-0 text-right text-[11px] text-[var(--color-ink-4)]">
                        +{driver.points.toFixed(0)}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[11.5px] text-[var(--color-ink-3)]">
                      {driver.detail}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState compact title="No risk drivers" description="This product is not at risk." />
          )}

          {data.recommendedAction?.label ? (
            <div className="mt-5">
              <Note
                tone={data.recommendedAction.action === "monitor" ? "info" : "warning"}
                icon={<AlertTriangle className="size-3.5" />}
              >
                <span className="font-medium">{data.recommendedAction.label}. </span>
                {data.recommendedAction.detail}
              </Note>
            </div>
          ) : null}
        </Card>

        <Card>
          <SectionHeader
            eyebrow="Performance"
            title="How it has sold"
            subtitle={
              p.arrivalDate
                ? `Arrived ${fmtDate(p.arrivalDate)}${p.daysInStockEstimated ? " (estimated)" : ""}`
                : undefined
            }
          />
          <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
            <Stat label="Units sold">
              <Value known={isKnown(p.unitsSold)}>{count(p.unitsSold)}</Value>
            </Stat>
            <Stat label="Sell-through">
              <Value known={isKnown(p.sellThrough)}>{percent(p.sellThrough)}</Value>
            </Stat>
            <Stat label="Days in stock">
              <Value known={isKnown(p.daysInStock)}>
                {isKnown(p.daysInStock) ? Math.round(p.daysInStock) : null}
              </Value>
            </Stat>
            <Stat label="Weeks of cover" hint="at current pace">
              <Value known={isKnown(p.weeksOfCover)}>
                {isKnown(p.weeksOfCover) ? p.weeksOfCover.toFixed(1) : null}
              </Value>
            </Stat>
          </div>
          {data.salesHistory.length > 1 ? (
            <div className="mt-5 border-t border-[var(--color-line)] pt-4">
              <div className="eyebrow mb-2">Monthly units sold</div>
              <HorizontalBars
                data={data.salesHistory.slice(-8).map((row) => ({
                  label: row.month,
                  value: row.units ?? 0,
                }))}
                format="number"
                height={Math.max(120, data.salesHistory.slice(-8).length * 24)}
                color="var(--color-accent)"
              />
            </div>
          ) : (
            <p className="mt-5 border-t border-[var(--color-line)] pt-4 text-[12px] italic text-[var(--color-ink-4)]">
              Not enough sales history to chart.
            </p>
          )}
        </Card>
      </div>

      <Card>
        <SectionHeader
          eyebrow="Matching engine"
          title="Best customers for this piece"
          subtitle="Who to call about it, ranked on the signals your data supports."
          action={
            <Link
              href={`/recommendations?product=${p.productId}`}
              className="text-[12.5px] text-[var(--color-ink-3)] hover:text-[var(--color-ink)]"
            >
              Open in recommendations
            </Link>
          }
        />
        {data.bestCustomers.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {data.bestCustomers.slice(0, 8).map((match) => (
              <div
                key={match.customerId}
                className="rounded-[11px] border border-[var(--color-line)] p-3.5 transition-colors hover:border-[var(--color-line-strong)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <Link href={`/customers/${match.customerId}`} className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium hover:text-[var(--color-accent)]">
                      {match.customerName}
                    </div>
                    <div className="mt-0.5 flex items-center gap-2">
                      {match.segment ? (
                        <Badge tone={SEGMENT_TONE[match.segment] ?? "neutral"} size="sm">
                          {match.segment}
                        </Badge>
                      ) : null}
                      <span className="num text-[11.5px] text-[var(--color-ink-4)]">
                        {money(match.totalSpend, { compact: true })} lifetime
                      </span>
                    </div>
                  </Link>
                  <MatchScore pct={match.scorePct} confidence={match.dataConfidence} />
                </div>
                <div className="mt-3 border-t border-[var(--color-line)] pt-3">
                  <SignalBreakdown signals={match.signals} missing={match.missingSignals} limit={3} />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            compact
            icon={<Users className="size-4" />}
            title="No strong customer matches"
            description="No customer in your base shows meaningful affinity for this piece. That is itself the signal: this is a candidate for a markdown or a bundle rather than one-to-one outreach."
          />
        )}
      </Card>
    </div>
  );
}

function ProductSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-4 w-28" />
      <Skeleton className="h-28 w-full" />
      <div className="grid gap-4 lg:grid-cols-2">
        <CardSkeleton rows={4} />
        <CardSkeleton rows={4} />
      </div>
    </div>
  );
}
