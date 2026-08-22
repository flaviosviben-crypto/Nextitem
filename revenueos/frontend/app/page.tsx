"use client";

/**
 * Overview — a signpost, not a dashboard.
 *
 * The advisor's job is on the next screen. This page tells them how much work
 * is waiting, whether last month's work paid off, and nothing else. Every
 * executive metric that used to live here was removed on purpose: an advisor
 * reading charts is an advisor not calling customers.
 */

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { Badge, Button, Card, EmptyState, ErrorState, SectionTitle, Skeleton, Stat } from "@/components/ui";
import { api, useApi, type Overview } from "@/lib/api";
import {
  EXPECTED_VALUE,
  EXPECTED_VALUE_HELP,
  FUNNEL,
  greeting,
  lifecycleColor,
  matchColor,
  money,
  num,
  pct,
  valueColor,
} from "@/lib/format";

export default function OverviewPage() {
  const { data, loading, error, refresh } = useApi<Overview>("/overview");

  const loadDemo = async () => {
    await api.post("/data/demo");
    refresh();
  };

  if (loading) {
    return (
      <Page>
        <Skeleton className="mb-6 h-16 w-full rounded-xl" />
        <Skeleton className="h-64 w-full rounded-xl" />
      </Page>
    );
  }

  if (error) {
    return (
      <Page>
        <ErrorState message={error} onRetry={refresh} />
      </Page>
    );
  }

  if (!data?.loaded) {
    return (
      <Page>
        <EmptyState
          title="No boutique data yet"
          body="Send us your customer, transaction and product exports and we'll set RevenueOS up for you — or explore a demo boutique to see how it works."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Button variant="primary" onClick={loadDemo}>
                Explore demo boutique
              </Button>
              <Link href="/data">
                <Button>Import data</Button>
              </Link>
            </div>
          }
        />
      </Page>
    );
  }

  const today = data.today!;
  const month = data.this_month!;

  return (
    <Page>
      <PageHeader eyebrow={greeting()} title="Overview" subtitle={today.note} />

      {/* ---- The one thing that matters today ---- */}
      {/* The hero is the dominant element, and on a wide screen it earns that
          by putting the headline figure beside the list it refers to rather
          than above it — the same information, roughly half the height. */}
      <Card className="mb-6">
        <div className="grid gap-6 xl:grid-cols-[minmax(280px,340px)_1fr] xl:gap-8">
        <div className="flex flex-wrap items-end justify-between gap-4 xl:flex-col xl:items-start xl:justify-start xl:gap-6">
          <div className="min-w-0">
            <div className="eyebrow">Waiting for you today</div>
            <div className="num mt-1.5 text-[40px] font-semibold leading-none">
              {num(today.opportunities)}
            </div>
            <p className="mt-2 text-[14px] text-[var(--ink-2)]">
              {today.opportunities === 1 ? "customer" : "customers"} worth a conversation
            </p>
            {/* The relationship, in one quiet line: the value is not the size of
                the pile RevenueOS found, it is how little of it needs working. */}
            <p className="mt-1.5 text-[12.5px] text-[var(--muted)]">
              {FUNNEL.recommended} from {num(today.detected)}{" "}
              {today.detected === 1 ? "opportunity" : "opportunities"} detected
              {today.influenced_value > 0 && (
                <span title={`${EXPECTED_VALUE_HELP} ${today.value_basis}`}>
                  {" · "}
                  {money(today.influenced_value)} {EXPECTED_VALUE.toLowerCase()}
                </span>
              )}
            </p>
          </div>
          <Link href="/opportunities">
            <Button variant="primary">
              Work the list <ArrowRight size={14} />
            </Button>
          </Link>
        </div>

        {today.top.length > 0 && (
          <div className="space-y-2 border-t border-[var(--line)] pt-4 xl:mt-0 xl:border-l xl:border-t-0 xl:pl-8 xl:pt-0">
            {today.top.map((row) => (
              <Link
                key={row.id}
                href={`/customers/${encodeURIComponent(row.customer_id)}`}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg px-2 py-2 transition-colors hover:bg-[var(--raised)]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[13px] font-medium">{row.customer_name}</span>
                    {row.value_tier && (
                      <Badge color={valueColor(row.value_tier)}>{row.value_tier}</Badge>
                    )}
                    {row.lifecycle && (
                      <Badge color={lifecycleColor(row.lifecycle)}>{row.lifecycle}</Badge>
                    )}
                  </div>
                  <p className="mt-0.5 text-[12px] leading-snug text-[var(--ink-2)]">
                    {row.why_now}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2.5">
                  {row.product && (
                    <span className="text-[12px] text-[var(--ink-3)]">{row.product}</span>
                  )}
                  {row.match_pct !== null && (
                    <Badge color={matchColor(row.match_pct)}>{row.match_pct}% match</Badge>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}

        </div>
      </Card>

      {/* ---- Did last month's work pay off? ---- */}
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat
          label="Contacted (30 days)"
          value={num(month.customers_contacted)}
          hint="Customers an advisor recorded reaching out to"
          href="/performance"
        />
        <Stat
          label="Converted"
          value={num(month.conversions)}
          tone={(month.conversions || 0) > 0 ? "good" : "default"}
          hint="Conversations that led to a sale"
          href="/performance"
        />
        <Stat
          label="Conversion rate"
          value={month.conversion_rate === null ? "—" : pct(month.conversion_rate)}
          hint="Measured from advisor outcomes, not modelled"
          href="/performance"
        />
        <Stat
          label="Revenue after contact"
          value={money(month.influenced_revenue)}
          hint="Observed spend within 30 days of a contact"
          href="/performance"
        />
      </div>

      {/* ---- Who the boutique is selling to ---- */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <SectionTitle
            title="Customer value"
            hint="How much each group is worth. Independent of where they are in their cycle."
          />
          <BreakdownList
            rows={(data.base?.value || []).map((r) => ({
              label: r.tier,
              customers: r.customers,
              color: valueColor(r.tier),
              meaning: r.meaning,
            }))}
            total={data.base?.customers || 0}
          />
        </Card>

        <Card>
          <SectionTitle
            title="Where they are in their cycle"
            hint="Timing only. A VIP who has gone quiet is still a VIP."
          />
          <BreakdownList
            rows={(data.base?.lifecycle || []).map((r) => ({
              label: r.stage,
              customers: r.customers,
              color: lifecycleColor(r.stage),
              meaning: r.meaning,
            }))}
            total={data.base?.customers || 0}
          />
        </Card>
      </div>

      {data.compliance && data.compliance.suppressed > 0 && (
        <p className="mt-5 text-[12px] leading-relaxed text-[var(--ink-3)]">
          {num(data.compliance.actionable)} of {num(data.counts?.customers)} customers can be
          contacted today. The remaining {num(data.compliance.suppressed)} are held back by
          consent, missing contact details, or the {data.compliance.frequency_cap_days}-day
          frequency cap.
        </p>
      )}
    </Page>
  );
}

function BreakdownList({
  rows,
  total,
}: {
  rows: { label: string; customers: number; color: string; meaning: string }[];
  total: number;
}) {
  if (rows.length === 0) {
    return <p className="text-[13px] text-[var(--ink-3)]">Not enough data yet.</p>;
  }
  return (
    <div className="space-y-3.5">
      {rows.map((row) => (
        <div key={row.label}>
          <div className="mb-1.5 flex items-baseline justify-between gap-3">
            <span className="flex items-center gap-2 text-[13px]">
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: row.color }} />
              {row.label}
            </span>
            <span className="num text-[13px] font-medium">
              {num(row.customers)}
              <span className="ml-2 text-[11px] font-normal text-[var(--ink-3)]">
                {total ? pct(row.customers / total) : "—"}
              </span>
            </span>
          </div>
          <p className="text-[12px] leading-snug text-[var(--ink-3)]">{row.meaning}</p>
        </div>
      ))}
    </div>
  );
}
