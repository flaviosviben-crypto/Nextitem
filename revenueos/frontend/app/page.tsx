"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { ArrowRight, Sparkles, Upload } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { BarList, TrendChart, TrendPoint } from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  ConfidenceTag,
  EmptyState,
  ErrorState,
  SectionTitle,
  Skeleton,
  Stat,
  StatusPill,
} from "@/components/ui";
import { Briefing, Summary, api, useApi } from "@/lib/api";
import { compactMoney, greeting, matchColor, money, num, seriesColor } from "@/lib/format";

export default function OverviewPage() {
  const summary = useApi<Summary>("/summary");
  const briefing = useApi<Briefing>("/briefing");
  const trend = useApi<{ monthly: TrendPoint[] }>("/trend?months=12");

  if (summary.loading) return <LoadingOverview />;
  if (summary.error) return <Page><ErrorState message={summary.error} onRetry={summary.refresh} /></Page>;
  if (!summary.data?.loaded) return <Onboarding onLoaded={() => { summary.refresh(); briefing.refresh(); trend.refresh(); }} />;

  const head = briefing.data?.headline;
  const counts = summary.data.counts;

  return (
    <Page>
      <PageHeader
        eyebrow="Overview"
        title={`${greeting()}.`}
        subtitle={
          head?.revenue_opportunity
            ? `Your boutique has ${money(head.revenue_opportunity)} of identified revenue opportunity, weighted by how likely each play is to land.`
            : "Your workspace is ready."
        }
        actions={
          <>
            <Link href="/analyst">
              <Button variant="secondary">
                <Sparkles size={14} /> Ask the analyst
              </Button>
            </Link>
            <Link href="/opportunities">
              <Button variant="primary">
                See today&apos;s actions <ArrowRight size={14} />
              </Button>
            </Link>
          </>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Revenue opportunity"
          value={compactMoney(head?.revenue_opportunity)}
          hint="Expected value across all open plays"
          href="/opportunities"
        />
        <Stat
          label="Customers to contact"
          value={num(head?.customers_to_contact)}
          hint="With consent on file, ranked by value"
          href="/customers?overdue=1"
        />
        <Stat
          label="Inventory at risk"
          value={compactMoney(head?.at_risk_value)}
          hint={`${num(head?.products_at_risk)} products ageing or dead`}
          tone={head?.at_risk_value ? "warning" : "default"}
          href="/inventory?risk=At%20Risk"
        />
        <Stat
          label="Data health"
          value={head?.data_health != null ? `${head.data_health}/100` : "—"}
          hint="How much of the engine your data supports"
          tone={(head?.data_health ?? 0) >= 70 ? "good" : "warning"}
          href="/data"
        />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <Card>
          <SectionTitle
            title="Today's priorities"
            hint="Ranked by expected value, urgency and how confident the data makes us."
            action={
              <Link href="/opportunities" className="text-[12px] text-[var(--accent)] hover:underline">
                All opportunities
              </Link>
            }
          />
          {briefing.loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-[76px] w-full" />)}
            </div>
          ) : briefing.data?.priorities?.length ? (
            <ol className="space-y-2.5">
              {briefing.data.priorities.map((p, i) => (
                <li key={p.id}>
                  <Link
                    href={`/opportunities#${p.id}`}
                    className="row-link flex gap-3.5 rounded-xl border border-[var(--line)] p-3.5"
                  >
                    <span className="num mt-0.5 text-[12px] font-semibold text-[var(--ink-3)]">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-[13.5px] font-medium">{p.title}</span>
                      <span className="mt-1 block line-clamp-2 text-[12.5px] leading-relaxed text-[var(--ink-2)]">
                        {p.detail}
                      </span>
                      <span className="mt-2 flex flex-wrap items-center gap-2.5">
                        <Badge color="var(--accent)">{p.action.split(".")[0]}</Badge>
                        {p.customer_count > 0 && (
                          <span className="text-[11px] text-[var(--ink-3)]">
                            {p.customer_count} customers
                          </span>
                        )}
                      </span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="num block text-[15px] font-semibold">
                        {compactMoney(p.expected_value)}
                      </span>
                      <span className="block text-[10px] text-[var(--ink-3)]">expected</span>
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          ) : (
            <EmptyState
              title="No priorities right now"
              body="Nothing in the current dataset crosses the threshold for action. Import more history to sharpen the signal."
              action={<Link href="/data"><Button>Open data</Button></Link>}
            />
          )}
        </Card>

        <Card>
          <SectionTitle title="Contact today" hint="Highest-value customers past their own cycle." />
          {briefing.loading ? (
            <div className="space-y-2">
              {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-11 w-full" />)}
            </div>
          ) : briefing.data?.contact_today?.length ? (
            <ul className="-mx-2">
              {briefing.data.contact_today.map((c) => (
                <li key={c.customer_id}>
                  <Link
                    href={`/customers/${encodeURIComponent(c.customer_id)}`}
                    className="row-link flex items-center gap-3 rounded-lg px-2 py-2"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <span className="truncate text-[13px] font-medium">{c.name}</span>
                        {!c.contactable && (
                          <span title="No marketing consent on file">
                            <Badge color="var(--warning)">consent</Badge>
                          </span>
                        )}
                      </span>
                      <span className="mt-0.5 block truncate text-[11.5px] text-[var(--ink-3)]">
                        {c.reason}
                      </span>
                    </span>
                    {c.product && (
                      <span
                        className="num shrink-0 text-[12px] font-medium"
                        style={{ color: matchColor(c.product.match_pct) }}
                        title={`Best match: ${c.product.name}`}
                      >
                        {c.product.match_pct}%
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="py-6 text-center text-[13px] text-[var(--ink-3)]">
              Nobody is overdue right now.
            </p>
          )}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <Card>
          <SectionTitle
            title="Revenue"
            hint="Monthly revenue from imported transactions."
          />
          {trend.loading ? (
            <Skeleton className="h-[200px] w-full" />
          ) : (
            <TrendChart data={trend.data?.monthly || []} />
          )}
        </Card>

        <Card>
          <SectionTitle title="Customer base" hint="Value concentration across segments." />
          {summary.data.segments?.length ? (
            <BarList
              rows={summary.data.segments
                .slice()
                .sort((a, b) => (b.total_value || 0) - (a.total_value || 0))
                .slice(0, 6)
                .map((s, i) => ({
                  label: s.segment,
                  value: s.total_value || 0,
                  secondary: `${s.customers}`,
                  color: seriesColor(i),
                }))}
            />
          ) : (
            <p className="py-6 text-center text-[13px] text-[var(--ink-3)]">No segments yet.</p>
          )}
          <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 border-t border-[var(--line)] pt-3.5">
            <StatusPill label={`${num(counts?.customers)} customers`} color="var(--s1)" />
            <StatusPill label={`${num(counts?.transactions)} transactions`} color="var(--s3)" />
            <StatusPill label={`${num(counts?.products)} products`} color="var(--s4)" />
          </div>
        </Card>
      </div>
    </Page>
  );
}

function LoadingOverview() {
  return (
    <Page>
      <Skeleton className="mb-2 h-4 w-24" />
      <Skeleton className="mb-7 h-8 w-72" />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[104px] w-full" />)}
      </div>
      <div className="mt-6 grid gap-5 lg:grid-cols-[1.35fr_1fr]">
        <Skeleton className="h-[340px] w-full" />
        <Skeleton className="h-[340px] w-full" />
      </div>
    </Page>
  );
}

function Onboarding({ onLoaded }: { onLoaded: () => void }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDemo = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post("/data/demo", { seed: 7 });
      onLoaded();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the demo boutique.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <div className="mx-auto max-w-2xl pt-[8vh] text-center">
        <div
          className="mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-xl text-[18px] font-bold text-white"
          style={{ background: "linear-gradient(135deg, var(--s1), var(--s7))" }}
        >
          R
        </div>
        <h1 className="text-[30px] font-semibold tracking-[-0.02em]">Welcome to RevenueOS</h1>
        <p className="mx-auto mt-3 max-w-lg text-[14px] leading-relaxed text-[var(--ink-2)]">
          Turn your customer and inventory data into daily revenue opportunities — who to
          contact, what to recommend, and why it matters today.
        </p>

        <div className="mt-8 grid gap-3 sm:grid-cols-2">
          <button
            onClick={() => router.push("/data")}
            className="card p-5 text-left transition-colors hover:border-[var(--line-strong)]"
          >
            <Upload size={18} className="mb-3 text-[var(--accent)]" />
            <span className="block text-[14px] font-semibold">Upload my data</span>
            <span className="mt-1.5 block text-[12.5px] leading-relaxed text-[var(--ink-2)]">
              Any CSV export from your POS or e-commerce. Columns are detected automatically,
              in English or Italian.
            </span>
          </button>

          <button
            onClick={loadDemo}
            disabled={busy}
            className="card p-5 text-left transition-colors hover:border-[var(--line-strong)] disabled:opacity-60"
          >
            <Sparkles size={18} className="mb-3 text-[var(--s7)]" />
            <span className="block text-[14px] font-semibold">
              {busy ? "Building the boutique…" : "Explore demo boutique"}
            </span>
            <span className="mt-1.5 block text-[12.5px] leading-relaxed text-[var(--ink-2)]">
              160 customers, 300 products and 2,200 transactions with realistic buying
              behaviour — every number computed, nothing faked.
            </span>
          </button>
        </div>

        {error && <p className="mt-4 text-[13px] text-[var(--critical)]">{error}</p>}

        <p className="mt-8 text-[11.5px] leading-relaxed text-[var(--ink-3)]">
          Your data stays in your workspace. Nothing is sent to a model unless you ask the
          analyst a question, and contact details are never included when it is.
        </p>
      </div>
    </Page>
  );
}
