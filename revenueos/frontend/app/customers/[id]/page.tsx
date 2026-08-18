"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  CalendarClock,
  Mail,
  Phone,
  ShoppingBag,
  Sparkles,
  Tag,
} from "lucide-react";
import { useApi } from "@/lib/api";
import {
  count,
  cx,
  date as fmtDate,
  days,
  initials,
  isKnown,
  money,
  percent,
  relativeDays,
} from "@/lib/format";
import { SEGMENT_TONE, matchTone } from "@/lib/theme";
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  SectionHeader,
  Skeleton,
  Value,
} from "@/components/ui";
import { MatchScore, SignalBreakdown, Stat, type MatchSignal } from "@/components/data";

type Affinity = { value: string; share: number };

type Detail = {
  customer: Record<string, unknown> & {
    customerId: string;
    name: string;
    segment: string | null;
    segmentReason: string | null;
    totalSpend: number | null;
    orderCount: number | null;
    avgOrderValue: number | null;
    recencyDays: number | null;
    lastPurchase: string | null;
    firstPurchase: string | null;
    expectedCycleDays: number | null;
    daysOverdue: number | null;
    churnRisk: number | null;
    customerScore: number | null;
    engagementScore: number | null;
    predicted12mValue: number | null;
    purchaseVelocity: number | null;
    discountRate: number | null;
    dataConfidence: string | null;
    email: string | null;
    phone: string | null;
    city: string | null;
    store: string | null;
    transactionLines: number | null;
  };
  affinities: {
    categories: Affinity[];
    brands: Affinity[];
    colors: Affinity[];
    sizes: Affinity[];
    seasonality: { month: number; share: number }[];
    priceBand: { low: number | null; high: number | null; mid: number | null };
  };
  timeline: {
    id: string;
    date: string | null;
    total: number | null;
    store: string | null;
    items: { name: string; category: string; brand: string; amount: number | null; discount: number | null }[];
  }[];
  recommendations: {
    productId: string;
    productName: string;
    brand: string;
    category: string;
    price: number | null;
    size: string;
    color: string;
    stock: number | null;
    scorePct: number;
    dataConfidence: string;
    signals: MatchSignal[];
    missingSignals: string[];
    headline: string;
  }[];
  nextBestActions: { priority: string; label: string; detail: string; kind: string }[];
  segmentMeta: { description?: string; play?: string };
};

const MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params?.id;

  const { data, error, isLoading, mutate } = useApi<Detail>(id ? `/customers/${id}` : null);
  const { data: summary } = useApi<{ summary: string; mode: string }>(
    id ? `/customers/${id}/summary` : null,
  );

  if (isLoading) return <DetailSkeleton />;
  if (error) return <ErrorState error={error} retry={() => mutate()} />;
  if (!data) return null;

  const c = data.customer;
  const band = data.affinities.priceBand;

  return (
    <div className="space-y-5">
      <button
        onClick={() => router.push("/customers")}
        className="flex items-center gap-1.5 text-[12.5px] text-[var(--color-ink-3)] transition-colors hover:text-[var(--color-ink)]"
      >
        <ArrowLeft className="size-3.5" /> All customers
      </button>

      {/* -------- header -------- */}
      <Card>
        <div className="flex flex-wrap items-start gap-5">
          <div className="grid size-14 shrink-0 place-items-center rounded-[14px] border border-[var(--color-line)] bg-[var(--color-surface-2)] text-[17px] font-semibold text-[var(--color-ink-2)]">
            {initials(c.name)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[22px] font-semibold tracking-[-0.02em]">{c.name}</h1>
              {c.segment ? (
                <Badge tone={SEGMENT_TONE[c.segment] ?? "neutral"}>{c.segment}</Badge>
              ) : null}
              {c.dataConfidence ? (
                <Badge size="sm" tone="neutral">
                  {c.dataConfidence} data confidence
                </Badge>
              ) : null}
            </div>
            {c.segmentReason ? (
              <p className="mt-1.5 text-[12.5px] text-[var(--color-ink-3)]">{c.segmentReason}</p>
            ) : null}
            <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-[var(--color-ink-4)]">
              {c.city ? <span>{c.city}</span> : null}
              {c.store ? <span>{c.store}</span> : null}
              {c.email ? (
                <a
                  href={`mailto:${c.email}`}
                  className="flex items-center gap-1 transition-colors hover:text-[var(--color-ink-2)]"
                >
                  <Mail className="size-3" /> {c.email}
                </a>
              ) : null}
              {c.phone ? (
                <span className="flex items-center gap-1">
                  <Phone className="size-3" /> {c.phone}
                </span>
              ) : null}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4">
            <Stat label="Lifetime value">
              <Value known={isKnown(c.totalSpend)}>{money(c.totalSpend)}</Value>
            </Stat>
            <Stat label="Customer score">
              <Value known={isKnown(c.customerScore)}>
                {isKnown(c.customerScore) ? Math.round(c.customerScore) : null}
              </Value>
            </Stat>
            <Stat label="Avg basket">
              <Value known={isKnown(c.avgOrderValue)}>{money(c.avgOrderValue)}</Value>
            </Stat>
            <Stat label="Last purchase" hint={fmtDate(c.lastPurchase, "")}>
              <span className="text-[14px]">{relativeDays(c.recencyDays)}</span>
            </Stat>
          </div>
        </div>
      </Card>

      {/* -------- AI summary + next best actions -------- */}
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <SectionHeader
            eyebrow="Profile intelligence"
            title="What we know about this customer"
          />
          {summary ? (
            <>
              <p className="text-[13.5px] leading-relaxed text-[var(--color-ink-2)]">
                {summary.summary}
              </p>
              <p className="mt-3 text-[11px] text-[var(--color-ink-4)]">
                {summary.mode === "ai"
                  ? "Written by Claude from computed metrics only."
                  : "Composed from computed metrics."}{" "}
                Based on {count(c.transactionLines)} purchase line
                {c.transactionLines === 1 ? "" : "s"}.
              </p>
            </>
          ) : (
            <Skeleton className="h-16 w-full" />
          )}

          <div className="mt-5 grid grid-cols-2 gap-4 border-t border-[var(--color-line)] pt-4 sm:grid-cols-4">
            <Stat label="Shops every" hint="their own rhythm">
              <Value known={isKnown(c.expectedCycleDays)}>{days(c.expectedCycleDays)}</Value>
            </Stat>
            <Stat label="Churn risk">
              <Value known={isKnown(c.churnRisk)}>
                <span
                  style={{
                    color: isKnown(c.churnRisk)
                      ? c.churnRisk >= 0.6
                        ? "var(--color-danger)"
                        : c.churnRisk >= 0.35
                          ? "var(--color-warning)"
                          : "var(--color-positive)"
                      : undefined,
                  }}
                >
                  {percent(c.churnRisk)}
                </span>
              </Value>
            </Stat>
            <Stat label="12m potential">
              <Value known={isKnown(c.predicted12mValue)}>{money(c.predicted12mValue)}</Value>
            </Stat>
            <Stat label="Bought on sale">
              <Value known={isKnown(c.discountRate)}>{percent(c.discountRate)}</Value>
            </Stat>
          </div>
        </Card>

        <Card>
          <SectionHeader eyebrow="Clienteling" title="Next best actions" />
          <div className="space-y-2">
            {data.nextBestActions.map((action, index) => (
              <div
                key={`${action.kind}-${index}`}
                className="flex gap-3 rounded-[10px] border border-[var(--color-line)] px-3 py-2.5"
              >
                <span
                  className="mt-1.5 size-1.5 shrink-0 rounded-full"
                  style={{
                    background:
                      action.priority === "high"
                        ? "var(--color-accent)"
                        : action.priority === "medium"
                          ? "var(--color-info)"
                          : "var(--color-ink-4)",
                  }}
                />
                <div className="min-w-0">
                  <div className="text-[12.5px] font-medium">{action.label}</div>
                  <div className="mt-0.5 text-[11.5px] leading-relaxed text-[var(--color-ink-3)]">
                    {action.detail}
                  </div>
                </div>
              </div>
            ))}
            {!data.nextBestActions.length ? (
              <EmptyState compact title="No action needed" description="This customer is on track." />
            ) : null}
          </div>
          {data.segmentMeta?.play ? (
            <div className="mt-4 rounded-[10px] bg-[var(--color-surface-2)] px-3 py-2.5 text-[11.5px] leading-relaxed text-[var(--color-ink-3)]">
              <span className="font-medium text-[var(--color-ink-2)]">Segment play: </span>
              {data.segmentMeta.play}
            </div>
          ) : null}
        </Card>
      </div>

      {/* -------- affinities -------- */}
      <Card>
        <SectionHeader
          eyebrow="Taste profile"
          title="What they actually buy"
          subtitle="Shares of spend, derived from their transaction history."
        />
        <div className="grid gap-6 md:grid-cols-2 xl:grid-cols-4">
          <AffinityBlock title="Categories" rows={data.affinities.categories} />
          <AffinityBlock title="Brands" rows={data.affinities.brands} />
          <AffinityBlock title="Colours" rows={data.affinities.colors} />
          <div>
            <div className="eyebrow mb-3">Price & size</div>
            <div className="space-y-3">
              <div>
                <div className="text-[11.5px] text-[var(--color-ink-4)]">Typical price band</div>
                <div className="num mt-0.5 text-[13.5px] font-medium">
                  <Value known={isKnown(band.low) && isKnown(band.high)}>
                    {money(band.low)} – {money(band.high)}
                  </Value>
                </div>
              </div>
              <div>
                <div className="text-[11.5px] text-[var(--color-ink-4)]">Sizes bought</div>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {data.affinities.sizes.length ? (
                    data.affinities.sizes.map((size) => (
                      <Badge key={size.value} size="sm">
                        {size.value}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-[12px] italic text-[var(--color-ink-4)]">
                      No size data
                    </span>
                  )}
                </div>
              </div>
              {data.affinities.seasonality.length ? (
                <div>
                  <div className="text-[11.5px] text-[var(--color-ink-4)]">Peak months</div>
                  <div className="mt-1 flex flex-wrap gap-1.5">
                    {data.affinities.seasonality.map((month) => (
                      <Badge key={month.month} size="sm" tone="info">
                        {MONTHS[month.month]} {percent(month.share)}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </Card>

      {/* -------- recommendations -------- */}
      <Card>
        <SectionHeader
          eyebrow="Matching engine"
          title="What to recommend"
          subtitle="Ranked on the signals available for this customer. Every score shows its reasoning."
          action={
            <Link
              href={`/recommendations?customer=${c.customerId}`}
              className="text-[12.5px] text-[var(--color-ink-3)] hover:text-[var(--color-ink)]"
            >
              Open in recommendations
            </Link>
          }
        />
        {data.recommendations.length ? (
          <div className="grid gap-3 lg:grid-cols-2">
            {data.recommendations.slice(0, 6).map((rec) => (
              <div
                key={rec.productId}
                className="rounded-[11px] border border-[var(--color-line)] p-3.5 transition-colors hover:border-[var(--color-line-strong)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <Link href={`/inventory/${rec.productId}`} className="min-w-0 flex-1">
                    <div className="truncate text-[13px] font-medium hover:text-[var(--color-accent)]">
                      {rec.productName}
                    </div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11.5px] text-[var(--color-ink-4)]">
                      <span>{rec.category}</span>
                      <span>·</span>
                      <span className="num">{money(rec.price)}</span>
                      {rec.size ? (
                        <>
                          <span>·</span>
                          <span>Size {rec.size}</span>
                        </>
                      ) : null}
                      {isKnown(rec.stock) ? (
                        <>
                          <span>·</span>
                          <span>{rec.stock} in stock</span>
                        </>
                      ) : null}
                    </div>
                  </Link>
                  <MatchScore pct={rec.scorePct} confidence={rec.dataConfidence} />
                </div>
                <div className="mt-3 border-t border-[var(--color-line)] pt-3">
                  <SignalBreakdown
                    signals={rec.signals}
                    missing={rec.missingSignals}
                    limit={4}
                  />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            compact
            icon={<Tag className="size-4" />}
            title="No recommendations available"
            description="Upload an inventory file to match this customer against real stock."
            action={<Button onClick={() => router.push("/data")}>Upload inventory</Button>}
          />
        )}
      </Card>

      {/* -------- timeline -------- */}
      <Card>
        <SectionHeader
          eyebrow="History"
          title="Purchase timeline"
          subtitle={
            isKnown(c.orderCount)
              ? `${count(c.orderCount)} orders since ${fmtDate(c.firstPurchase)}`
              : undefined
          }
        />
        {data.timeline.length ? (
          <div className="relative space-y-3 pl-5">
            <div className="absolute bottom-2 left-[5px] top-2 w-px bg-[var(--color-line)]" />
            {data.timeline.slice(0, 14).map((order) => (
              <div key={order.id} className="relative">
                <div className="absolute -left-5 top-2 size-[9px] rounded-full border-2 border-[var(--color-canvas)] bg-[var(--color-accent)]" />
                <div className="rounded-[10px] border border-[var(--color-line)] px-3.5 py-2.5">
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-[12.5px] font-medium">{fmtDate(order.date)}</div>
                    <div className="num text-[13px] font-semibold">
                      <Value known={isKnown(order.total)}>{money(order.total)}</Value>
                    </div>
                  </div>
                  <div className="mt-1.5 space-y-1">
                    {order.items.map((item, index) => (
                      <div
                        key={index}
                        className="flex items-center justify-between gap-3 text-[11.5px] text-[var(--color-ink-3)]"
                      >
                        <span className="truncate">{item.name}</span>
                        <span className="flex shrink-0 items-center gap-2">
                          {isKnown(item.discount) && item.discount > 0 ? (
                            <Badge size="sm" tone="warning">
                              -{Math.round(item.discount)}%
                            </Badge>
                          ) : null}
                          <span className="num">{money(item.amount)}</span>
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyState
            compact
            icon={<ShoppingBag className="size-4" />}
            title="No purchase history"
            description="This customer exists in your CRM but has no transactions in the data you uploaded."
          />
        )}
      </Card>
    </div>
  );
}

function AffinityBlock({ title, rows }: { title: string; rows: Affinity[] }) {
  return (
    <div>
      <div className="eyebrow mb-3">{title}</div>
      {rows.length ? (
        <div className="space-y-2">
          {rows.slice(0, 5).map((row) => (
            <div key={row.value}>
              <div className="mb-1 flex items-center justify-between gap-2 text-[12px]">
                <span className="truncate capitalize">{row.value}</span>
                <span className="num shrink-0 text-[var(--color-ink-4)]">
                  {percent(row.share)}
                </span>
              </div>
              <div className="h-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                <div
                  className="h-full rounded-full bg-[var(--color-accent)]"
                  style={{ width: `${Math.min(100, row.share * 100)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-[12px] italic text-[var(--color-ink-4)]">
          Not enough information
        </p>
      )}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-4 w-28" />
      <Skeleton className="h-32 w-full" />
      <div className="grid gap-4 lg:grid-cols-[1.3fr_1fr]">
        <CardSkeleton rows={4} />
        <CardSkeleton rows={4} />
      </div>
      <CardSkeleton rows={3} />
    </div>
  );
}
