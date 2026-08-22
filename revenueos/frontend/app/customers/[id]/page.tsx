"use client";

/**
 * Customer Detail — one question, answered above the fold.
 *
 * "Why is RevenueOS telling me to contact this customer?" The answer sits at
 * the top with the evidence beside it, so an advisor can verify it in seconds
 * rather than trusting a score. Everything below is the history that backs it.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ArrowLeft, ChevronDown, ChevronUp, ShieldOff } from "lucide-react";
import { Page } from "@/components/Shell";
import { BarList, SignalBreakdown } from "@/components/charts";
import {
  Badge,
  Card,
  ConfidenceTag,
  ErrorState,
  SectionTitle,
  Skeleton,
  Td,
  Th,
  Value,
} from "@/components/ui";
import { type CustomerDetail, type Match, useApi } from "@/lib/api";
import {
  days,
  lifecycleColor,
  matchColor,
  money,
  noProductMessage,
  num,
  pct,
  seriesColor,
  shortDate,
  valueColor,
} from "@/lib/format";

export default function CustomerDetailPage() {
  const params = useParams<{ id: string }>();
  const id = decodeURIComponent(params.id);
  const detail = useApi<CustomerDetail>(`/customers/${encodeURIComponent(id)}`);

  if (detail.loading) {
    return (
      <Page>
        <Skeleton className="mb-6 h-8 w-64" />
        <Skeleton className="mb-5 h-40 w-full rounded-xl" />
        <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <Skeleton className="h-[420px]" />
          <Skeleton className="h-[420px]" />
        </div>
      </Page>
    );
  }
  if (detail.error) {
    return (
      <Page>
        <ErrorState message={detail.error} onRetry={detail.refresh} />
      </Page>
    );
  }
  if (!detail.data) return null;

  const { profile: p, why_contact: why, value, lifecycle, eligibility } = detail.data;

  return (
    <Page>
      <Link
        href="/customers"
        className="mb-4 inline-flex items-center gap-1.5 text-[12.5px] text-[var(--ink-2)] hover:text-[var(--ink)]"
      >
        <ArrowLeft size={13} /> All customers
      </Link>

      <header className="mb-5">
        <h1 className="text-[24px] font-semibold tracking-[-0.02em]">{p.name}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {value.tier && <Badge color={valueColor(value.tier)}>{value.tier}</Badge>}
          {lifecycle.stage && (
            <Badge color={lifecycleColor(lifecycle.stage)}>{lifecycle.stage}</Badge>
          )}
          {p.store && <span className="text-[12px] text-[var(--ink-3)]">{p.store}</span>}
          <ConfidenceTag level={p.data_confidence} />
        </div>
      </header>

      {/* ---- The answer, first ---- */}
      <Card className="mb-5">
        <div className="eyebrow">Why contact them</div>
        <h2 className="mt-2 text-[17px] font-semibold tracking-[-0.01em]">{why.headline}</h2>
        {why.why_now && (
          <p className="mt-2 text-[14px] leading-relaxed text-[var(--ink-2)]">{why.why_now}</p>
        )}
        {why.customer_evidence.length > 0 && (
          <ul className="mt-2.5 space-y-1">
            {why.customer_evidence.map((line) => (
              <li key={line} className="text-[12.5px] leading-snug text-[var(--ink-3)]">
                · {line}
              </li>
            ))}
          </ul>
        )}

        {!why.product && why.contactable && (
          <p className="mt-3 text-[12.5px] text-[var(--ink-3)]">
            {noProductMessage(detail.data.product_matching_available)}
          </p>
        )}

        {why.product && (
          <div className="mt-4 rounded-lg border border-[var(--line)] bg-[var(--raised)] p-4">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-[14px] font-medium">{why.product.name}</span>
              <div className="flex items-center gap-2.5">
                <span className="num text-[14px]">{money(why.product.price)}</span>
                <Badge color={matchColor(why.product.match_pct)}>
                  {why.product.match_pct}% match
                </Badge>
              </div>
            </div>
            <ul className="mt-2.5 space-y-1">
              {why.product.why.map((r) => (
                <li key={r} className="text-[12px] leading-snug text-[var(--ink-2)]">
                  · {r}
                </li>
              ))}
            </ul>
            <p className="mt-2.5 text-[11px] text-[var(--ink-3)]">{why.product.availability}</p>
          </div>
        )}

        <p className="mt-4 border-t border-[var(--line)] pt-4 text-[13px] font-medium">
          {why.action}
        </p>
      </Card>

      {/* ---- The evidence behind each badge ---- */}
      <div className="mb-5 grid gap-4 lg:grid-cols-3">
        <Card>
          <div className="eyebrow">Value</div>
          <div className="mt-1.5 text-[15px] font-semibold" style={{ color: valueColor(value.tier) }}>
            {value.tier || "—"}
          </div>
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-2)]">{value.basis}</p>
          {value.signals.length > 0 && (
            <ul className="mt-2.5 space-y-1">
              {value.signals.map((sig) => (
                <li key={sig} className="text-[12px] leading-snug text-[var(--ink-3)]">
                  · {sig}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <div className="eyebrow">Buying cycle</div>
          <div
            className="mt-1.5 text-[15px] font-semibold"
            style={{ color: lifecycleColor(lifecycle.stage) }}
          >
            {lifecycle.stage || "—"}
          </div>
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-2)]">{lifecycle.basis}</p>
          {/* The cycle's provenance is stated, so "every 42 days" is never mistaken
              for this customer's own habit when it came from a cohort. */}
          <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-3)]">
            {lifecycle.cycle_basis}
          </p>
        </Card>

        <Card>
          <div className="eyebrow">How you may reach them</div>
          {eligibility?.status === "Actionable" ? (
            <>
              <div className="mt-1.5 text-[15px] font-semibold" style={{ color: "var(--good)" }}>
                Actionable
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-2)]">
                {eligibility.channels.map((c) => c.label).join(", ")}.
              </p>
            </>
          ) : (
            <>
              <div className="mt-1.5 flex items-center gap-1.5 text-[15px] font-semibold text-[var(--ink-3)]">
                <ShieldOff size={15} /> Suppressed
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-[var(--ink-2)]">
                {eligibility?.reason || "No permitted contact channel on file."}
              </p>
            </>
          )}
        </Card>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-5">
          <Card>
            <SectionTitle
              title="Purchase history"
              hint={`${num(p.order_count)} orders · ${money(p.total_spend)} lifetime · last purchase ${
                p.recency_days != null ? days(p.recency_days) + " ago" : "unknown"
              }`}
            />
            {detail.data.timeline.length === 0 ? (
              <p className="text-[13px] text-[var(--ink-3)]">
                No transactions imported for this customer.
              </p>
            ) : (
              <div className="max-h-[420px] overflow-auto">
                <table className="w-full min-w-[520px]">
                  <thead>
                    <tr>
                      <Th>Date</Th>
                      <Th>Item</Th>
                      <Th>Category</Th>
                      <Th align="right">Amount</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.data.timeline.map((t, i) => (
                      <tr key={`${t.transaction_id}-${i}`}>
                        <Td>
                          <Value>{shortDate(t.date)}</Value>
                        </Td>
                        <Td>
                          <Value>{t.product}</Value>
                          {t.brand && (
                            <span className="ml-2 text-[11px] text-[var(--ink-3)]">{t.brand}</span>
                          )}
                        </Td>
                        <Td>
                          <Value>{t.category}</Value>
                        </Td>
                        <Td align="right">
                          <Value>{money(t.amount)}</Value>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          {detail.data.recommendations.length > 0 && (
            <Card>
              <SectionTitle
                title="Other pieces that fit"
                hint="Ranked by how well they match this customer's own buying signals."
              />
              <div className="space-y-4">
                {detail.data.recommendations.slice(0, 4).map((m) => (
                  <Recommendation key={m.sku} match={m} />
                ))}
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-5">
          <Card>
            <SectionTitle title="What they buy" />
            <Affinity title="Categories" shares={p.category_affinity} />
            <Affinity title="Brands" shares={p.brand_affinity} />
            <Affinity title="Colours" shares={p.color_affinity} />
            {p.price_low && p.price_high && (
              <p className="mt-4 text-[12px] text-[var(--ink-2)]">
                Typically spends {money(p.price_low)}–{money(p.price_high)} per piece.
              </p>
            )}
          </Card>

          <Card>
            <SectionTitle title="At a glance" />
            <dl className="space-y-2.5 text-[13px]">
              <Row label="Lifetime spend" value={money(p.total_spend)} />
              <Row label="Orders" value={num(p.order_count)} />
              <Row label="Average basket" value={money(p.avg_order_value)} />
              <Row
                label="Buying cycle"
                value={lifecycle.cycle_days ? `${Math.round(lifecycle.cycle_days)} days` : null}
                hint={lifecycle.cycle_confidence || undefined}
              />
              <Row
                label="Through their cycle"
                value={lifecycle.cycle_position ? pct(lifecycle.cycle_position) : null}
              />
              <Row label="Last purchase" value={shortDate(p.last_purchase)} />
              <Row
                label="Discounted purchases"
                value={p.discount_share != null ? pct(p.discount_share) : null}
              />
            </dl>
          </Card>
        </div>
      </div>
    </Page>
  );
}

/**
 * A recommendation shows its reasons; the eight-signal breakdown that produced
 * them is one click away. The engine is not less sophisticated for being quiet.
 */
function Recommendation({ match }: { match: Match }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border-b border-[var(--line)] pb-4 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <span className="text-[13.5px] font-medium">{match.product_name}</span>
          {match.brand && (
            <span className="ml-2 text-[12px] text-[var(--ink-3)]">{match.brand}</span>
          )}
        </div>
        <div className="flex items-center gap-2.5">
          <span className="num text-[13px]">{money(match.price)}</span>
          <Badge color={matchColor(match.match_pct)}>{match.match_pct}% match</Badge>
        </div>
      </div>

      <ul className="mt-2 space-y-1">
        {match.why.slice(0, 3).map((r) => (
          <li key={r} className="text-[12px] leading-snug text-[var(--ink-2)]">
            · {r}
          </li>
        ))}
        {match.caveats.map((c) => (
          <li key={c} className="text-[12px] leading-snug text-[var(--warning)]">
            · {c}
          </li>
        ))}
      </ul>

      <button
        onClick={() => setOpen((v) => !v)}
        className="mt-2 flex items-center gap-1 text-[11px] text-[var(--ink-3)] transition-colors hover:text-[var(--ink-2)]"
      >
        {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        {open ? "Hide the full breakdown" : "How this match was scored"}
      </button>
      {open && (
        <div className="mt-3">
          <SignalBreakdown signals={match.signals} />
        </div>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number | null | undefined;
  hint?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4">
      <dt className="text-[var(--ink-2)]">{label}</dt>
      <dd className="num text-right">
        <Value>{value}</Value>
        {hint && value && (
          <span className="ml-2 text-[11px] font-normal text-[var(--ink-3)]">{hint}</span>
        )}
      </dd>
    </div>
  );
}

function Affinity({ title, shares }: { title: string; shares?: Record<string, number> }) {
  const rows = Object.entries(shares || {}).slice(0, 4);
  if (rows.length === 0) return null;
  return (
    <div className="mb-4 last:mb-0">
      <div className="eyebrow mb-2">{title}</div>
      <BarList
        rows={rows.map(([label, share], i) => ({
          label,
          value: share,
          color: seriesColor(i),
        }))}
        format={(v) => pct(v)}
      />
    </div>
  );
}
