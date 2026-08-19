"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Page } from "@/components/Shell";
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
import { Match, Product, useApi } from "@/lib/api";
import { days, matchColor, money, num, pct, riskColor, shortDate } from "@/lib/format";

type Detail = {
  product: Product;
  best_customers: Match[];
  recent_sales: { date: string | null; customer_id: string; amount: number; quantity: number }[];
  sales_count: number;
};

export default function ProductDetailPage() {
  const params = useParams<{ sku: string }>();
  const sku = decodeURIComponent(params.sku);
  const detail = useApi<Detail>(`/products/${encodeURIComponent(sku)}`);

  if (detail.loading) {
    return (
      <Page>
        <Skeleton className="mb-6 h-8 w-64" />
        <Skeleton className="h-[400px]" />
      </Page>
    );
  }
  if (detail.error) return <Page><ErrorState message={detail.error} onRetry={detail.refresh} /></Page>;
  if (!detail.data) return null;

  const p = detail.data.product;

  return (
    <Page>
      <Link
        href="/inventory"
        className="mb-4 inline-flex items-center gap-1.5 text-[12.5px] text-[var(--ink-2)] hover:text-[var(--ink)]"
      >
        <ArrowLeft size={14} /> All inventory
      </Link>

      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="text-[24px] font-semibold tracking-[-0.02em]">{p.product_name}</h1>
            <Badge color={riskColor(p.risk_class)}>
              {p.risk_class}
              {p.risk_score != null && ` · ${p.risk_score}/100`}
            </Badge>
          </div>
          <p className="mt-1.5 text-[13px] text-[var(--ink-2)]">
            {[p.sku, p.brand, p.category, p.color, p.size, p.season].filter(Boolean).join(" · ")}
          </p>
        </div>
        <div className="flex items-center gap-5">
          <MiniStat label="Price" value={money(p.price)} />
          <MiniStat label="Stock" value={p.stock != null ? num(p.stock) : "—"} />
          <MiniStat label="Stock value" value={money(p.stock_value)} />
        </div>
      </header>

      <div className="grid gap-5 lg:grid-cols-[1fr_1.25fr]">
        <div className="space-y-5">
          <Card>
            <SectionTitle title="Performance" />
            <div className="space-y-2.5 text-[13px]">
              <Row label="Units sold"><Value>{p.units_sold}</Value></Row>
              <Row label="Revenue">{money(p.revenue)}</Row>
              <Row label="Distinct buyers"><Value>{p.buyers}</Value></Row>
              <Row label="Sell-through">
                <Value hint="Needs both stock and sales history">
                  {p.sell_through != null ? pct(p.sell_through) : null}
                </Value>
              </Row>
              <Row label="Velocity">
                <Value hint="Needs an arrival date and sales">
                  {p.velocity_per_month != null ? `${p.velocity_per_month.toFixed(1)}/mo` : null}
                </Value>
              </Row>
              <Row label="Weeks of cover">
                <Value>{p.weeks_of_cover != null ? p.weeks_of_cover.toFixed(0) : null}</Value>
              </Row>
              <Row label="Days in stock">
                <Value hint="No arrival date in the imported data">
                  {p.days_in_stock != null ? num(p.days_in_stock) : null}
                </Value>
              </Row>
              <Row label="Last sold">
                <Value>{p.last_sold ? shortDate(p.last_sold) : null}</Value>
              </Row>
              <Row label="Margin">
                <Value hint="Add a cost column to compute margin">
                  {p.margin_rate != null ? pct(p.margin_rate) : null}
                </Value>
              </Row>
            </div>
          </Card>

          {p.risk_drivers?.length > 0 && (
            <Card>
              <SectionTitle title="Why this risk score" hint={p.risk_reason} />
              <div className="space-y-2.5">
                {p.risk_drivers.map((d) => (
                  <div key={d.driver}>
                    <div className="flex items-baseline justify-between gap-3 text-[12.5px]">
                      <span className="font-medium">{d.driver}</span>
                      <span
                        className="num"
                        style={{ color: d.points > 0 ? "var(--serious)" : "var(--good)" }}
                      >
                        {d.points > 0 ? "+" : ""}
                        {d.points}
                      </span>
                    </div>
                    <p className="mt-0.5 text-[12px] text-[var(--ink-2)]">{d.detail}</p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          <Card>
            <div className="eyebrow mb-2">Recommended action</div>
            <p className="text-[13.5px] leading-relaxed">{p.recommended_action}</p>
          </Card>
        </div>

        <div className="space-y-5">
          <Card>
            <SectionTitle
              title="Best customers for this product"
              hint="Who to call first, and the reason behind each match."
            />
            {detail.data.best_customers.length ? (
              <ol className="space-y-2">
                {detail.data.best_customers.map((m, i) => (
                  <li key={m.customer_id}>
                    <Link
                      href={`/customers/${encodeURIComponent(m.customer_id || "")}`}
                      className="row-link flex items-start gap-3.5 rounded-xl border border-[var(--line)] p-3.5"
                    >
                      <span className="num mt-0.5 w-5 text-[12px] font-semibold text-[var(--ink-3)]">
                        {i + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13.5px] font-medium">{m.customer_name}</span>
                        <span className="mt-1 block text-[12px] leading-relaxed text-[var(--ink-2)]">
                          {m.why.slice(0, 2).join(" · ")}
                        </span>
                        <span className="mt-1.5 block">
                          <ConfidenceTag level={m.data_confidence} />
                        </span>
                      </span>
                      <span className="num shrink-0 text-[16px] font-semibold" style={{ color: matchColor(m.match_pct) }}>
                        {m.match_pct}%
                      </span>
                    </Link>
                  </li>
                ))}
              </ol>
            ) : (
              <EmptyState
                title="No strong customer match"
                body="No customer in the dataset shows enough affinity for this product. More transaction history would sharpen this."
              />
            )}
          </Card>

          {detail.data.recent_sales.length > 0 && (
            <Card padded={false}>
              <div className="p-5 pb-3">
                <SectionTitle title="Recent sales" hint={`${detail.data.sales_count} recorded.`} />
              </div>
              <table className="w-full">
                <thead>
                  <tr>
                    <Th>Date</Th>
                    <Th>Customer</Th>
                    <Th align="right">Qty</Th>
                    <Th align="right">Amount</Th>
                  </tr>
                </thead>
                <tbody>
                  {detail.data.recent_sales.map((s, i) => (
                    <tr key={i}>
                      <Td><Value>{s.date ? shortDate(s.date) : null}</Value></Td>
                      <Td>
                        <Link
                          href={`/customers/${encodeURIComponent(s.customer_id)}`}
                          className="text-[var(--accent)] hover:underline"
                        >
                          {s.customer_id}
                        </Link>
                      </Td>
                      <Td align="right">{num(s.quantity)}</Td>
                      <Td align="right">{money(s.amount)}</Td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}
        </div>
      </div>
    </Page>
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

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-[var(--ink-3)]">{label}</span>
      <span className="num text-right">{children}</span>
    </div>
  );
}
