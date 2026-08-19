"use client";

import { Sparkles } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { BarList, TrendChart, TrendPoint } from "@/components/charts";
import { Badge, Card, EmptyState, SectionTitle, Skeleton, Stat } from "@/components/ui";
import { Summary, useApi } from "@/lib/api";
import { compactMoney, money, num, pct, seriesColor } from "@/lib/format";

type Brief = { brief: string; engine: string; trend: TrendPoint[]; computed_brief?: string };
type Overview = {
  summary: Record<string, any>;
  categories: { category: string; revenue: number; units_sold: number; customers: number; stock_value: number }[];
  brands: { brand: string; revenue: number; units_sold: number; customers: number }[];
};

export default function InsightsPage() {
  const brief = useApi<Brief>("/ai/brief");
  const overview = useApi<Overview>("/inventory/overview");
  const summary = useApi<Summary>("/summary");

  const sections = brief.data?.brief ? splitBrief(brief.data.brief) : [];

  return (
    <Page>
      <PageHeader
        eyebrow="Insights"
        title="This week"
        subtitle="A read of the business from computed metrics — what moved, what is at risk, and what to do about it."
        actions={
          brief.data && (
            <Badge color={brief.data.engine === "claude" ? "var(--accent)" : "var(--ink-3)"}>
              {brief.data.engine === "claude" ? "AI briefing" : "Computed briefing"}
            </Badge>
          )
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Customers"
          value={num(summary.data?.counts?.customers)}
          hint={`${num(summary.data?.customers?.contactable)} contactable`}
        />
        <Stat
          label="Average basket"
          value={money(summary.data?.customers?.avg_order_value as number | null)}
          hint="Across all recorded orders"
        />
        <Stat
          label="Top 20% share"
          value={
            summary.data?.customers?.top_20_pct_share != null
              ? pct(summary.data.customers.top_20_pct_share as number)
              : "—"
          }
          hint="Of total customer spend"
        />
        <Stat
          label="Overdue customers"
          value={num(summary.data?.customers?.overdue_customers)}
          hint="Past their own repurchase cycle"
          tone="warning"
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Card>
          <SectionTitle title="Weekly briefing" />
          {brief.loading ? (
            <div className="space-y-2.5">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <Skeleton key={i} className={`h-4 ${i % 3 === 2 ? "w-[60%]" : "w-full"}`} />
              ))}
            </div>
          ) : sections.length > 0 ? (
            <div className="space-y-4">
              {sections.map((s) => (
                <div key={s.heading}>
                  <div className="eyebrow mb-1.5">{s.heading}</div>
                  <p className="text-[13.5px] leading-relaxed text-[var(--ink-2)]">{s.body}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[13.5px] leading-relaxed text-[var(--ink-2)]">
              {brief.data?.brief || "Not enough data yet to summarise the week."}
            </p>
          )}
        </Card>

        <Card>
          <SectionTitle title="Revenue trend" hint="Last six months of recorded sales." />
          {brief.loading ? (
            <Skeleton className="h-[200px] w-full" />
          ) : (
            <TrendChart data={brief.data?.trend || []} height={220} />
          )}
        </Card>
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <Card>
          <SectionTitle title="Category performance" hint="Revenue earned against stock held." />
          {overview.data?.categories?.length ? (
            <div className="space-y-4">
              <BarList
                rows={overview.data.categories.slice(0, 8).map((c, i) => ({
                  label: c.category,
                  value: c.revenue,
                  secondary: `${num(c.customers)} customers`,
                  color: seriesColor(i),
                }))}
              />
            </div>
          ) : (
            <EmptyState title="No category data" body="Import transactions with a category column." />
          )}
        </Card>

        <Card>
          <SectionTitle title="Brand performance" hint="Where your customers actually spend." />
          {overview.data?.brands?.length ? (
            <BarList
              rows={overview.data.brands.slice(0, 8).map((b, i) => ({
                label: b.brand,
                value: b.revenue,
                secondary: `${num(b.units_sold)} units`,
                color: seriesColor(i),
              }))}
            />
          ) : (
            <EmptyState title="No brand data" body="Import transactions with a brand column." />
          )}
        </Card>
      </div>
    </Page>
  );
}

/** The briefing prompt asks for four named sections; parse them for display. */
function splitBrief(text: string): { heading: string; body: string }[] {
  const headings = ["Wins", "Risks", "Opportunities", "Recommended actions"];
  const found: { heading: string; index: number }[] = [];
  for (const heading of headings) {
    const match = new RegExp(`(^|\\n|\\s)${heading}[.:]?\\s`, "i").exec(text);
    if (match) found.push({ heading, index: match.index });
  }
  if (found.length < 2) return [];
  found.sort((a, b) => a.index - b.index);
  return found.map((f, i) => {
    const start = f.index;
    const end = i + 1 < found.length ? found[i + 1].index : text.length;
    const body = text
      .slice(start, end)
      .replace(new RegExp(`^\\s*${f.heading}[.:]?\\s*`, "i"), "")
      .trim();
    return { heading: f.heading, body };
  });
}
