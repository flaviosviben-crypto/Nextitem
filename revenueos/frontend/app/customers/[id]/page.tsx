"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ChevronDown, Sparkles } from "lucide-react";
import { Page } from "@/components/Shell";
import { BarList, SignalBreakdown } from "@/components/charts";
import {
  Badge,
  Card,
  ConfidenceTag,
  EmptyState,
  ErrorState,
  Meter,
  SectionTitle,
  Skeleton,
  Td,
  Th,
  Value,
} from "@/components/ui";
import { Match, useApi } from "@/lib/api";
import { compactMoney, days, matchColor, money, num, pct, seriesColor, shortDate } from "@/lib/format";

type Detail = {
  profile: Record<string, any>;
  recommendations: Match[];
  timeline: {
    date: string | null;
    product: string | null;
    category: string | null;
    brand: string | null;
    amount: number | null;
    quantity: number | null;
    store: string | null;
  }[];
  opportunities: { id: string; title: string; action: string }[];
};

type Narrative = { summary: string; actions: string[]; engine: string };

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const detail = useApi<Detail>(`/customers/${encodeURIComponent(id)}`);
  const narrative = useApi<Narrative>(`/customers/${encodeURIComponent(id)}/narrative`);

  if (detail.loading) {
    return (
      <Page>
        <Skeleton className="mb-6 h-8 w-64" />
        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <Skeleton className="h-[420px]" />
          <Skeleton className="h-[420px]" />
        </div>
      </Page>
    );
  }
  if (detail.error) return <Page><ErrorState message={detail.error} onRetry={detail.refresh} /></Page>;
  if (!detail.data) return null;

  const p = detail.data.profile;
  const overdue = p.overdue_ratio as number | null;

  return (
    <Page>
      <Link
        href="/customers"
        className="mb-4 inline-flex items-center gap-1.5 text-[12.5px] text-[var(--ink-2)] hover:text-[var(--ink)]"
      >
        <ArrowLeft size={14} /> All customers
      </Link>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[24px] font-semibold tracking-[-0.02em]">{p.name}</h1>
            <Badge color={toneOf(p.segment_tone)}>{p.segment}</Badge>
            {p.marketing_consent !== true && (
              <Badge color="var(--warning)">Consent not on file</Badge>
            )}
          </div>
          <p className="mt-1.5 text-[13px] text-[var(--ink-2)]">
            {[p.store, p.city, p.customer_id].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex items-center gap-5">
          <MiniStat label="Customer score" value={p.customer_score != null ? String(p.customer_score) : "—"} />
          <MiniStat label="Lifetime value" value={money(p.total_spend)} />
          <MiniStat label="Annual potential" value={money(p.potential_annual_value)} />
        </div>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <FactCard label="Orders" value={num(p.order_count)} hint={p.spend_source ? `From ${p.spend_source}` : undefined} />
        <FactCard label="Average basket" value={money(p.avg_order_value)} />
        <FactCard
          label="Last purchase"
          value={p.last_purchase ? shortDate(p.last_purchase) : "—"}
          hint={p.recency_days != null ? `${days(p.recency_days)} ago` : "No purchase on record"}
        />
        <FactCard
          label="Buying cycle"
          value={p.cadence_days ? `${Math.round(p.cadence_days)} days` : "—"}
          hint={
            overdue == null
              ? "Not enough purchases to establish"
              : overdue > 1.2
                ? `${overdue.toFixed(1)}× past due`
                : overdue < 0.15
                  ? "Just purchased — not due yet"
                  : `${Math.round(overdue * 100)}% through the cycle`
          }
          tone={overdue != null && overdue > 1.3 ? "warning" : undefined}
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <Card>
            <SectionTitle
              title="What we know"
              hint={
                narrative.data?.engine === "claude"
                  ? "Written by the analyst from computed metrics."
                  : "Computed directly from this customer's history."
              }
              action={
                narrative.data?.engine === "claude" ? (
                  <span className="inline-flex items-center gap-1 text-[11px] text-[var(--ink-3)]">
                    <Sparkles size={11} /> AI summary
                  </span>
                ) : null
              }
            />
            {narrative.loading ? (
              <div className="space-y-2">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-[85%]" />
              </div>
            ) : (
              <p className="text-[13.5px] leading-relaxed text-[var(--ink-2)]">
                {narrative.data?.summary}
              </p>
            )}

            {narrative.data?.actions?.length ? (
              <div className="mt-5 border-t border-[var(--line)] pt-4">
                <div className="eyebrow mb-2.5">Next best actions</div>
                <ol className="space-y-2">
                  {narrative.data.actions.map((action, i) => (
                    <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed">
                      <span className="num mt-0.5 text-[11px] font-semibold text-[var(--ink-3)]">
                        {i + 1}
                      </span>
                      <span>{action}</span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
          </Card>

          <Card>
            <SectionTitle
              title="Recommended products"
              hint="Ranked by fit, with the reasoning behind every score."
            />
            {detail.data.recommendations.length ? (
              <div className="space-y-2.5">
                {detail.data.recommendations.map((m) => (
                  <RecommendationRow key={m.sku} match={m} />
                ))}
              </div>
            ) : (
              <EmptyState
                title="No confident recommendation"
                body="No catalogue product clears the evidence threshold for this customer. Importing transaction history or product categories would change that."
              />
            )}
          </Card>

          <Card padded={false}>
            <div className="p-5 pb-3">
              <SectionTitle title="Purchase history" hint={`${detail.data.timeline.length} recorded lines.`} />
            </div>
            {detail.data.timeline.length ? (
              <div className="max-h-[380px] overflow-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <Th>Date</Th>
                      <Th>Product</Th>
                      <Th>Category</Th>
                      <Th align="right">Amount</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.data.timeline.map((t, i) => (
                      <tr key={i}>
                        <Td><Value>{t.date ? shortDate(t.date) : null}</Value></Td>
                        <Td>
                          <span className="text-[13px]">{t.product || "—"}</span>
                          {t.brand && (
                            <span className="ml-2 text-[11px] text-[var(--ink-3)]">{t.brand}</span>
                          )}
                        </Td>
                        <Td><span className="text-[var(--ink-2)]">{t.category || "—"}</span></Td>
                        <Td align="right">{money(t.amount)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <EmptyState
                title="No transaction history"
                body="This customer's metrics come from CRM summary fields. Import transactions for cadence, affinity and product-level matching."
              />
            )}
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <SectionTitle title="Buying profile" />
            <AffinityBlock title="Categories" data={p.category_affinity} />
            <AffinityBlock title="Brands" data={p.brand_affinity} />
            <AffinityBlock title="Colours" data={p.color_affinity} />
            {p.size_affinity_by_family && Object.keys(p.size_affinity_by_family).length > 0 && (
              <div className="mt-4">
                <div className="eyebrow mb-2">Sizes</div>
                <div className="space-y-1.5">
                  {Object.entries(p.size_affinity_by_family as Record<string, Record<string, number>>).map(
                    ([family, sizes]) => (
                      <div key={family} className="flex items-baseline justify-between gap-3 text-[12.5px]">
                        <span className="text-[var(--ink-2)]">{family}</span>
                        <span className="num">{Object.keys(sizes).slice(0, 2).join(", ")}</span>
                      </div>
                    ),
                  )}
                </div>
              </div>
            )}

            <div className="mt-4 space-y-2 border-t border-[var(--line)] pt-4 text-[12.5px]">
              <Row label="Price band">
                {p.price_low && p.price_high ? `${money(p.price_low)} – ${money(p.price_high)}` : "—"}
              </Row>
              <Row label="Buys on discount">
                {p.discount_share != null ? pct(p.discount_share) : "—"}
              </Row>
              <Row label="Spend trend">
                {p.spend_growth != null ? (
                  <span style={{ color: p.spend_growth >= 0 ? "var(--good)" : "var(--critical)" }}>
                    {p.spend_growth >= 0 ? "+" : ""}
                    {pct(p.spend_growth)}
                  </span>
                ) : (
                  "—"
                )}
              </Row>
              <Row label="Data confidence">
                <ConfidenceTag level={p.data_confidence} />
              </Row>
            </div>
          </Card>

          {p.segment_play && (
            <Card>
              <div className="eyebrow mb-2">Segment play</div>
              <p className="text-[13px] leading-relaxed text-[var(--ink-2)]">{p.segment_play}</p>
            </Card>
          )}

          {detail.data.opportunities.length > 0 && (
            <Card>
              <SectionTitle title="In these opportunities" />
              <ul className="space-y-2">
                {detail.data.opportunities.map((o) => (
                  <li key={o.id}>
                    <Link
                      href={`/opportunities#${o.id}`}
                      className="row-link block rounded-lg border border-[var(--line)] p-3"
                    >
                      <span className="block text-[13px] font-medium">{o.title}</span>
                      <span className="mt-1 block text-[12px] text-[var(--ink-2)]">{o.action}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </Page>
  );
}

function RecommendationRow({ match }: { match: Match }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-xl border border-[var(--line)]">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3.5 p-3.5 text-left"
      >
        <span className="w-11 shrink-0 text-center">
          <span className="num block text-[17px] font-semibold" style={{ color: matchColor(match.match_pct) }}>
            {match.match_pct}%
          </span>
          <span className="block text-[9.5px] uppercase tracking-wide text-[var(--ink-3)]">match</span>
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-medium">{match.product_name}</span>
          <span className="mt-0.5 block truncate text-[12px] text-[var(--ink-3)]">
            {[match.brand, match.category, money(match.price)].filter(Boolean).join(" · ")}
            {match.stock != null && ` · ${match.stock} in stock`}
          </span>
        </span>
        <span className="hidden shrink-0 text-right sm:block">
          <ConfidenceTag level={match.data_confidence} />
          {match.expected_value != null && (
            <span className="num mt-1 block text-[11px] text-[var(--ink-3)]">
              {money(match.expected_value)} expected
            </span>
          )}
        </span>
        <ChevronDown
          size={15}
          className={`shrink-0 text-[var(--ink-3)] transition-transform ${open ? "rotate-180" : ""}`}
        />
      </button>

      {!open && match.why.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3.5 pb-3.5">
          {match.why.slice(0, 3).map((why, i) => (
            <span key={i} className="rounded-md bg-[var(--raised)] px-2 py-1 text-[11px] text-[var(--ink-2)]">
              {why}
            </span>
          ))}
        </div>
      )}

      {open && (
        <div className="fade-in border-t border-[var(--line)] p-4">
          <SignalBreakdown signals={match.signals} />
          {match.caveats.length > 0 && (
            <div className="mt-4 rounded-lg border border-[var(--line)] p-3">
              <div className="eyebrow mb-1.5">Worth knowing</div>
              <ul className="space-y-1">
                {match.caveats.map((c, i) => (
                  <li key={i} className="text-[12px] text-[var(--ink-2)]">{c}</li>
                ))}
              </ul>
            </div>
          )}
          <Link
            href={`/inventory/${encodeURIComponent(match.sku)}`}
            className="mt-3 inline-block text-[12px] text-[var(--accent)] hover:underline"
          >
            View product →
          </Link>
        </div>
      )}
    </div>
  );
}

function AffinityBlock({ title, data }: { title: string; data: Record<string, number> | undefined }) {
  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="mt-4">
        <div className="eyebrow mb-2">{title}</div>
        <p className="text-[12px] text-[var(--ink-3)]">Not enough information</p>
      </div>
    );
  }
  return (
    <div className="mt-4">
      <div className="eyebrow mb-2">{title}</div>
      <BarList
        rows={Object.entries(data)
          .slice(0, 4)
          .map(([label, value], i) => ({ label, value, color: seriesColor(i) }))}
        format={(v) => pct(v)}
        max={1}
      />
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="num mt-1 text-[17px] font-semibold">{value}</div>
    </div>
  );
}

function FactCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "warning";
}) {
  return (
    <div className="card p-4">
      <div className="eyebrow">{label}</div>
      <div
        className="num mt-1.5 text-[18px] font-semibold"
        style={{ color: tone === "warning" ? "var(--serious)" : undefined }}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-[11.5px] text-[var(--ink-3)]">{hint}</div>}
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[var(--ink-3)]">{label}</span>
      <span className="num text-right">{children}</span>
    </div>
  );
}

function toneOf(tone: string | undefined): string {
  switch (tone) {
    case "positive":
      return "var(--good)";
    case "warning":
      return "var(--warning)";
    case "negative":
      return "var(--critical)";
    default:
      return "var(--ink-3)";
  }
}
