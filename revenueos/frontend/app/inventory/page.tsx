"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Boxes, Search } from "lucide-react";
import { query, useApi } from "@/lib/api";
import { count, cx, days, isKnown, money, percent } from "@/lib/format";
import { STOCK_TONE, riskTone } from "@/lib/theme";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  SectionHeader,
  Select,
  Skeleton,
  Tabs,
  Value,
} from "@/components/ui";
import { DataTable, DonutChart, HorizontalBars, KpiCard } from "@/components/data";

type ProductRow = {
  productId: string;
  name: string;
  sku: string | null;
  brand: string | null;
  category: string | null;
  price: number | null;
  stock: number | null;
  retailValue: number | null;
  daysInStock: number | null;
  daysInStockEstimated: boolean;
  sellThrough: number | null;
  unitsSold: number | null;
  riskScore: number | null;
  status: string | null;
  marginPct: number | null;
  recommendedAction: { label: string; detail: string } | null;
};

type ProductList = {
  hasData: boolean;
  rows: ProductRow[];
  total: number;
  facets: { statuses: string[]; categories: string[]; brands: string[] };
};

type Overview = {
  hasData: boolean;
  kpis: {
    skus: number;
    unitsInStock: number | null;
    retailValue: number | null;
    inventoryValue: number | null;
    estimatedMargin: number | null;
    avgMarginPct: number | null;
    avgSellThrough: number | null;
    avgDaysInStock: number | null;
    statusCounts: Record<string, number>;
    atRiskValue: number | null;
    atRiskSkus: number;
    ageBuckets: Record<string, number>;
  };
  categoryMix: { value: string; retailValue: number | null; avgRisk: number | null; skus: number }[];
  brandMix: { value: string; retailValue: number | null; skus: number }[];
  sizeMix: { value: string; units: number | null }[];
  colorMix: { value: string; units: number | null }[];
};

const AGE_ORDER = ["0-30 days", "31-60 days", "61-90 days", "91-180 days", "181-365 days", "365+ days"];
const PAGE_SIZE = 40;

function InventoryInner() {
  const router = useRouter();
  const params = useSearchParams();

  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [category, setCategory] = useState("");
  const [brand, setBrand] = useState("");
  const [inStockOnly, setInStockOnly] = useState(true);
  const [sortBy, setSortBy] = useState("risk_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);
  const [mixTab, setMixTab] = useState("category");

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(search);
      setOffset(0);
    }, 220);
    return () => clearTimeout(timer);
  }, [search]);

  const url = useMemo(
    () =>
      `/inventory${query({
        search: debounced,
        status,
        category,
        brand,
        inStockOnly,
        sortBy,
        order,
        limit: PAGE_SIZE,
        offset,
      })}`,
    [debounced, status, category, brand, inStockOnly, sortBy, order, offset],
  );

  const { data, error, isLoading, mutate } = useApi<ProductList>(url, { keepPreviousData: true });
  const { data: overview } = useApi<Overview>("/inventory/overview");

  const toggleSort = (key: string) => {
    const map: Record<string, string> = {
      product: "product_name",
      stock: "stock",
      value: "retail_value",
      age: "days_in_stock",
      sell: "sell_through",
      risk: "risk_score",
    };
    const column = map[key] ?? key;
    if (column === sortBy) setOrder(order === "desc" ? "asc" : "desc");
    else {
      setSortBy(column);
      setOrder("desc");
    }
    setOffset(0);
  };

  if (error) return <ErrorState error={error} retry={() => mutate()} />;

  const kpis = overview?.kpis;
  const mixData =
    mixTab === "category"
      ? overview?.categoryMix
      : mixTab === "brand"
        ? overview?.brandMix
        : mixTab === "size"
          ? overview?.sizeMix
          : overview?.colorMix;

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Stock intelligence"
        title="Inventory"
        subtitle="What is moving, what is ageing, and what to do about it before markdown season decides for you."
      />

      {kpis ? (
        <section className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
          <KpiCard
            label="Retail value"
            value={kpis.retailValue}
            format="currency"
            detail={`${count(kpis.skus)} SKUs · ${count(kpis.unitsInStock)} units on hand`}
            accent
          />
          <KpiCard
            label="Capital at risk"
            value={kpis.atRiskValue}
            format="currency"
            detail={`${kpis.atRiskSkus} SKUs ageing or not moving`}
          />
          <KpiCard
            label="Estimated margin"
            value={kpis.estimatedMargin}
            format="currency"
            detail={
              isKnown(kpis.avgMarginPct)
                ? `${kpis.avgMarginPct.toFixed(0)}% average margin`
                : "Add cost data to compute margin"
            }
          />
          <KpiCard
            label="Average sell-through"
            value={isKnown(kpis.avgSellThrough) ? kpis.avgSellThrough * 100 : null}
            format="percent0to100"
            detail={
              isKnown(kpis.avgDaysInStock)
                ? `${Math.round(kpis.avgDaysInStock)} days average stock age`
                : undefined
            }
          />
        </section>
      ) : (
        <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[124px]" />
          ))}
        </div>
      )}

      {overview?.hasData ? (
        <section className="grid gap-4 lg:grid-cols-[1fr_1fr_1fr]">
          <Card>
            <SectionHeader title="Stock health" subtitle="Products by status" />
            <DonutChart
              height={200}
              data={Object.entries(kpis?.statusCounts ?? {}).map(([name, value]) => ({
                name,
                value,
              }))}
            />
          </Card>
          <Card>
            <SectionHeader title="Stock ageing" subtitle="How long stock has been on hand" />
            <div className="space-y-2 pt-1">
              {AGE_ORDER.filter((bucket) => kpis?.ageBuckets?.[bucket]).map((bucket) => {
                const value = kpis!.ageBuckets[bucket];
                const max = Math.max(...Object.values(kpis!.ageBuckets));
                const old = bucket.startsWith("181") || bucket.startsWith("365");
                return (
                  <div key={bucket}>
                    <div className="mb-1 flex items-center justify-between text-[11.5px]">
                      <span className="text-[var(--color-ink-3)]">{bucket}</span>
                      <span className="num">{value}</span>
                    </div>
                    <div className="h-1.5 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                      <div
                        className="h-full rounded-full"
                        style={{
                          width: `${(value / max) * 100}%`,
                          background: old ? "var(--color-warning)" : "var(--color-accent)",
                        }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </Card>
          <Card>
            <SectionHeader
              title="Stock concentration"
              action={
                <Tabs
                  active={mixTab}
                  onChange={setMixTab}
                  tabs={[
                    { key: "category", label: "Cat" },
                    { key: "brand", label: "Brand" },
                    { key: "size", label: "Size" },
                    { key: "color", label: "Colour" },
                  ]}
                />
              }
            />
            {mixData?.length ? (
              <HorizontalBars
                data={mixData.slice(0, 7).map((row) => ({
                  label: row.value,
                  value:
                    "retailValue" in row && isKnown(row.retailValue)
                      ? row.retailValue
                      : ("units" in row ? row.units : null) ?? 0,
                }))}
                format={mixTab === "size" || mixTab === "color" ? "number" : "currency"}
                height={200}
              />
            ) : (
              <EmptyState compact title="No data for this dimension" />
            )}
          </Card>
        </section>
      ) : null}

      <div className="flex flex-wrap items-center gap-2.5">
        <div className="min-w-[220px] flex-1">
          <Input
            icon={<Search className="size-3.5" />}
            placeholder="Search product, SKU or brand…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
          <option value="">All statuses</option>
          {data?.facets.statuses.map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </Select>
        <Select value={category} onChange={(e) => { setCategory(e.target.value); setOffset(0); }}>
          <option value="">All categories</option>
          {data?.facets.categories.map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </Select>
        <Select value={brand} onChange={(e) => { setBrand(e.target.value); setOffset(0); }}>
          <option value="">All brands</option>
          {data?.facets.brands.map((value) => (
            <option key={value} value={value}>{value}</option>
          ))}
        </Select>
        <label className="flex cursor-pointer items-center gap-2 rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)] px-3 py-[7px] text-[12.5px] text-[var(--color-ink-2)]">
          <input
            type="checkbox"
            checked={inStockOnly}
            onChange={(e) => { setInStockOnly(e.target.checked); setOffset(0); }}
            className="size-3.5 accent-[var(--color-accent)]"
          />
          In stock only
        </label>
      </div>

      <Card padded={false} className="overflow-hidden">
        {isLoading && !data ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-11 w-full" />
            ))}
          </div>
        ) : (
          <DataTable
            rows={data?.rows ?? []}
            rowKey={(row) => row.productId}
            onRowClick={(row) => router.push(`/inventory/${row.productId}`)}
            sortOrder={order}
            onSort={toggleSort}
            empty={
              <EmptyState
                icon={<Boxes className="size-5" />}
                title="No products match those filters"
                description="Try clearing a filter, or turn off “in stock only”."
              />
            }
            columns={[
              {
                key: "product",
                header: "Product",
                sortable: true,
                render: (row) => (
                  <div className="min-w-0">
                    <div className="truncate font-medium">{row.name}</div>
                    <div className="truncate text-[11px] text-[var(--color-ink-4)]">
                      {[row.brand, row.category].filter(Boolean).join(" · ")}
                    </div>
                  </div>
                ),
              },
              {
                key: "stock",
                header: "Stock",
                align: "right",
                sortable: true,
                render: (row) => (
                  <Value known={isKnown(row.stock)} className="num">
                    {count(row.stock)}
                  </Value>
                ),
              },
              {
                key: "value",
                header: "Value",
                align: "right",
                sortable: true,
                render: (row) => (
                  <Value known={isKnown(row.retailValue)} className="num font-medium">
                    {money(row.retailValue, { compact: true })}
                  </Value>
                ),
              },
              {
                key: "age",
                header: "Days in stock",
                align: "right",
                sortable: true,
                render: (row) => (
                  <span className={cx("num", row.daysInStockEstimated && "text-[var(--color-ink-3)]")}>
                    <Value known={isKnown(row.daysInStock)}>
                      {isKnown(row.daysInStock) ? Math.round(row.daysInStock) : null}
                      {row.daysInStockEstimated ? "*" : ""}
                    </Value>
                  </span>
                ),
              },
              {
                key: "sell",
                header: "Sell-through",
                align: "right",
                sortable: true,
                render: (row) => (
                  <Value known={isKnown(row.sellThrough)} className="num">
                    {percent(row.sellThrough)}
                  </Value>
                ),
              },
              {
                key: "risk",
                header: "Risk",
                sortable: true,
                render: (row) =>
                  row.status ? (
                    <div className="flex items-center gap-2">
                      <Badge tone={STOCK_TONE[row.status] ?? "neutral"} size="sm">
                        {row.status}
                      </Badge>
                      {isKnown(row.riskScore) ? (
                        <span
                          className="num text-[11px]"
                          style={{ color: `var(--color-${riskTone(row.riskScore)})` }}
                        >
                          {Math.round(row.riskScore)}
                        </span>
                      ) : null}
                    </div>
                  ) : (
                    <span className="text-[var(--color-ink-4)]">—</span>
                  ),
              },
              {
                key: "action",
                header: "Recommended action",
                render: (row) => (
                  <span className="text-[12px] text-[var(--color-ink-3)]">
                    {row.recommendedAction?.label ?? "—"}
                  </span>
                ),
              },
            ]}
          />
        )}
      </Card>

      {data && data.total > PAGE_SIZE ? (
        <div className="flex items-center justify-between">
          <div className="text-[12.5px] text-[var(--color-ink-4)]">
            Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of {count(data.total)}
            {data.rows.some((r) => r.daysInStockEstimated) ? (
              <span className="ml-2 text-[var(--color-ink-4)]">
                * stock age estimated from first sale
              </span>
            ) : null}
          </div>
          <div className="flex gap-2">
            <Button size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <Button size="sm" disabled={offset + PAGE_SIZE >= data.total} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function InventoryPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <InventoryInner />
    </Suspense>
  );
}
