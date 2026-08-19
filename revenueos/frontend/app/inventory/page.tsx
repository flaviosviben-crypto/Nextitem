"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { BarList, ORDINAL, StackedBar } from "@/components/charts";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  SectionTitle,
  Stat,
  TableSkeleton,
  Td,
  Th,
  Value,
  inputClass,
} from "@/components/ui";
import { Product, useApi } from "@/lib/api";
import { compactMoney, days, money, num, pct, riskColor, seriesColor } from "@/lib/format";

type Listing = {
  total: number;
  products: Product[];
  facets: { categories: string[]; brands: string[]; risk_classes: string[] };
};

type Overview = {
  summary: Record<string, any>;
  ageing: { bucket: string; products: number; units: number; value: number }[];
  categories: { category: string; revenue: number; stock_value: number; units_sold: number }[];
  brands: { brand: string; revenue: number; units_sold: number }[];
};

export default function InventoryPage() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [risk, setRisk] = useState("");
  const [inStockOnly, setInStockOnly] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams({ limit: "120", sort: "risk_score" });
    if (q) params.set("q", q);
    if (category) params.set("category", category);
    if (risk) params.set("risk_class", risk);
    if (inStockOnly) params.set("in_stock_only", "true");
    return `/products?${params.toString()}`;
  }, [q, category, risk, inStockOnly]);

  const listing = useApi<Listing>(query);
  const overview = useApi<Overview>("/inventory/overview");
  const s = overview.data?.summary;

  return (
    <Page>
      <PageHeader
        eyebrow="Inventory"
        title="Inventory intelligence"
        subtitle="What is selling, what is ageing, and what to do about it — before anyone reaches for a discount."
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Stock value" value={compactMoney(s?.stock_value)} hint={`${num(s?.units)} units on hand`} />
        <Stat label="Potential margin" value={compactMoney(s?.margin_value)} hint="At current retail prices" />
        <Stat
          label="At risk"
          value={compactMoney(s?.at_risk_value)}
          hint={`${num(s?.at_risk_products)} products ageing or dead`}
          tone={s?.at_risk_value ? "warning" : "default"}
        />
        <Stat
          label="Median age"
          value={s?.median_days_in_stock != null ? `${num(s.median_days_in_stock)} days` : "—"}
          hint={s?.avg_sell_through != null ? `${pct(s.avg_sell_through)} average sell-through` : undefined}
        />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-3">
        <Card>
          <SectionTitle title="Stock ageing" hint="Value held by how long it has been on the floor." />
          {overview.data?.ageing?.length ? (
            <BarList
              rows={overview.data.ageing.map((a, i) => ({
                label: a.bucket,
                value: a.value,
                secondary: `${a.products} SKUs`,
                color: ORDINAL[i],
              }))}
            />
          ) : (
            <p className="py-6 text-center text-[13px] text-[var(--ink-3)]">
              Add arrival dates to see stock ageing.
            </p>
          )}
        </Card>

        <Card>
          <SectionTitle title="Health mix" hint="How the catalogue splits by risk." />
          {s?.by_class ? (
            <StackedBar
              data={Object.entries(s.by_class as Record<string, { products: number }>).map(([label, v]) => ({
                label,
                value: v.products,
                color: riskColor(label),
              }))}
            />
          ) : null}
        </Card>

        <Card>
          <SectionTitle title="Category revenue" hint="Sales against stock held." />
          {overview.data?.categories?.length ? (
            <BarList
              rows={overview.data.categories.slice(0, 6).map((c, i) => ({
                label: c.category,
                value: c.revenue,
                secondary: compactMoney(c.stock_value) + " held",
                color: seriesColor(i),
              }))}
            />
          ) : (
            <p className="py-6 text-center text-[13px] text-[var(--ink-3)]">No category sales yet.</p>
          )}
        </Card>
      </div>

      <Card className="mt-5" padded={false}>
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] p-3">
          <div className="relative min-w-[200px] flex-1">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search SKU, product, brand or category"
              className={`${inputClass} w-full pl-8`}
            />
          </div>
          <select value={category} onChange={(e) => setCategory(e.target.value)} className={`${inputClass} w-auto`}>
            <option value="">All categories</option>
            {listing.data?.facets.categories.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select value={risk} onChange={(e) => setRisk(e.target.value)} className={`${inputClass} w-auto`}>
            <option value="">All health</option>
            {listing.data?.facets.risk_classes.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <label className="flex items-center gap-2 rounded-lg border border-[var(--line)] px-2.5 py-2 text-[12.5px] text-[var(--ink-2)]">
            <input type="checkbox" checked={inStockOnly} onChange={(e) => setInStockOnly(e.target.checked)} />
            In stock
          </label>
          <span className="ml-auto whitespace-nowrap text-[12px] text-[var(--ink-3)]">
            {listing.data ? `${num(listing.data.total)} products` : ""}
          </span>
        </div>

        {listing.loading ? (
          <TableSkeleton rows={8} cols={7} />
        ) : listing.error ? (
          <ErrorState message={listing.error} onRetry={listing.refresh} />
        ) : !listing.data?.products.length ? (
          <EmptyState title="No products match" body="Clear the filters or import a product catalogue." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px]">
              <thead>
                <tr>
                  <Th>Product</Th>
                  <Th>Category</Th>
                  <Th align="right">Stock</Th>
                  <Th align="right">Value</Th>
                  <Th align="right">Age</Th>
                  <Th align="right">Sell-through</Th>
                  <Th>Health</Th>
                  <Th>Recommended action</Th>
                </tr>
              </thead>
              <tbody>
                {listing.data.products.map((p) => (
                  <tr key={p.sku} className="row-link cursor-pointer">
                    <Td>
                      <Link href={`/inventory/${encodeURIComponent(p.sku)}`} className="block">
                        <span className="font-medium">{p.product_name}</span>
                        <span className="mt-0.5 block text-[11px] text-[var(--ink-3)]">
                          {[p.sku, p.brand].filter(Boolean).join(" · ")}
                        </span>
                      </Link>
                    </Td>
                    <Td><span className="text-[var(--ink-2)]">{p.category || "—"}</span></Td>
                    <Td align="right"><Value>{p.stock}</Value></Td>
                    <Td align="right"><Value>{p.stock_value != null ? money(p.stock_value) : null}</Value></Td>
                    <Td align="right">
                      <Value hint="No arrival date in the imported data">
                        {p.days_in_stock != null ? `${num(p.days_in_stock)}d` : null}
                      </Value>
                    </Td>
                    <Td align="right">
                      <Value hint="Needs both stock and sales to compute">
                        {p.sell_through != null ? pct(p.sell_through) : null}
                      </Value>
                    </Td>
                    <Td>
                      <Badge color={riskColor(p.risk_class)}>
                        {p.risk_class}
                        {p.risk_score != null && ` ${p.risk_score}`}
                      </Badge>
                    </Td>
                    <Td>
                      <span
                        className="block max-w-[280px] truncate text-[12.5px] text-[var(--ink-2)]"
                        title={p.recommended_action}
                      >
                        {p.recommended_action}
                      </span>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </Page>
  );
}
