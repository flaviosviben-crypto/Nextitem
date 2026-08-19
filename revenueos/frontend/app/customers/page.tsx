"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { StackedBar } from "@/components/charts";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  SectionTitle,
  TableSkeleton,
  Td,
  Th,
  Value,
  inputClass,
} from "@/components/ui";
import { CustomerRow, Summary, useApi } from "@/lib/api";
import { compactMoney, days, matchColor, money, num, seriesColor, shortDate } from "@/lib/format";

type Listing = {
  total: number;
  customers: CustomerRow[];
  facets: { segments: string[]; stores: string[] };
};

const SORTS = [
  { key: "customer_score", label: "Score" },
  { key: "total_spend", label: "Value" },
  { key: "overdue_ratio", label: "Overdue" },
  { key: "recency_days", label: "Recency" },
  { key: "potential_annual_value", label: "Potential" },
] as const;

export default function CustomersPage() {
  const [q, setQ] = useState("");
  const [segment, setSegment] = useState("");
  const [store, setStore] = useState("");
  const [sort, setSort] = useState<string>("customer_score");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [contactableOnly, setContactableOnly] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams({
      sort,
      direction,
      limit: "100",
    });
    if (q) params.set("q", q);
    if (segment) params.set("segment", segment);
    if (store) params.set("store", store);
    if (overdueOnly) params.set("overdue_only", "true");
    if (contactableOnly) params.set("contactable_only", "true");
    return `/customers?${params.toString()}`;
  }, [q, segment, store, sort, direction, overdueOnly, contactableOnly]);

  const listing = useApi<Listing>(query);
  const summary = useApi<Summary>("/summary");

  const toggleSort = (key: string) => {
    if (sort === key) setDirection((d) => (d === "desc" ? "asc" : "desc"));
    else {
      setSort(key);
      setDirection("desc");
    }
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Customers"
        title="Customer base"
        subtitle="Every customer scored against your own population — a €2,000 client is a VIP in one boutique and average in another."
      />

      {summary.data?.segments && summary.data.segments.length > 0 && (
        <Card className="mb-5">
          <SectionTitle title="Segments" hint="Share of your customer base, by behaviour." />
          <StackedBar
            data={summary.data.segments.map((s, i) => ({
              label: s.segment,
              value: s.customers,
              color: seriesColor(i),
              hint: s.play,
            }))}
          />
        </Card>
      )}

      <Card padded={false}>
        <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] p-3">
          <div className="relative min-w-[200px] flex-1">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--ink-3)]"
            />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search by name or ID"
              className={`${inputClass} w-full pl-8`}
            />
          </div>

          <select value={segment} onChange={(e) => setSegment(e.target.value)} className={`${inputClass} w-auto`}>
            <option value="">All segments</option>
            {listing.data?.facets.segments.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          {listing.data?.facets.stores.length ? (
            <select value={store} onChange={(e) => setStore(e.target.value)} className={`${inputClass} w-auto`}>
              <option value="">All stores</option>
              {listing.data.facets.stores.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          ) : null}

          <label className="flex items-center gap-2 rounded-lg border border-[var(--line)] px-2.5 py-2 text-[12.5px] text-[var(--ink-2)]">
            <input type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
            Overdue
          </label>
          <label className="flex items-center gap-2 rounded-lg border border-[var(--line)] px-2.5 py-2 text-[12.5px] text-[var(--ink-2)]">
            <input
              type="checkbox"
              checked={contactableOnly}
              onChange={(e) => setContactableOnly(e.target.checked)}
            />
            Contactable
          </label>

          <span className="ml-auto whitespace-nowrap text-[12px] text-[var(--ink-3)]">
            {listing.data ? `${num(listing.data.total)} customers` : ""}
          </span>
        </div>

        {listing.loading ? (
          <TableSkeleton rows={8} cols={7} />
        ) : listing.error ? (
          <ErrorState message={listing.error} onRetry={listing.refresh} />
        ) : !listing.data?.customers.length ? (
          <EmptyState
            title="No customers match"
            body="Clear the filters or widen the search."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[940px]">
              <thead>
                <tr>
                  <Th>Customer</Th>
                  <Th>Segment</Th>
                  <SortableTh label="Value" active={sort === "total_spend"} direction={direction} onClick={() => toggleSort("total_spend")} />
                  <Th align="right">Orders</Th>
                  <Th>Last purchase</Th>
                  <SortableTh label="Cycle" active={sort === "overdue_ratio"} direction={direction} onClick={() => toggleSort("overdue_ratio")} />
                  <Th>Recommended next</Th>
                  <SortableTh label="Score" active={sort === "customer_score"} direction={direction} onClick={() => toggleSort("customer_score")} />
                </tr>
              </thead>
              <tbody>
                {listing.data.customers.map((c) => (
                  <tr key={c.customer_id} className="row-link cursor-pointer">
                    <Td>
                      <Link href={`/customers/${encodeURIComponent(c.customer_id)}`} className="block">
                        <span className="font-medium">{c.name}</span>
                        <span className="mt-0.5 block text-[11px] text-[var(--ink-3)]">
                          {c.crm_record === false
                            ? "From transactions only"
                            : c.store || c.customer_id}
                          {!c.contactable && " · no consent"}
                        </span>
                      </Link>
                    </Td>
                    <Td>
                      <Badge color={toneOf(c.segment_tone)}>{c.segment || "—"}</Badge>
                    </Td>
                    <Td align="right">
                      <Value>{c.total_spend != null ? money(c.total_spend) : null}</Value>
                    </Td>
                    <Td align="right"><Value>{c.order_count}</Value></Td>
                    <Td>
                      <Value>{c.last_purchase ? shortDate(c.last_purchase) : null}</Value>
                      {c.recency_days != null && (
                        <span className="ml-2 text-[11px] text-[var(--ink-3)]">{days(c.recency_days)}</span>
                      )}
                    </Td>
                    <Td align="right">
                      {c.overdue_ratio != null ? (
                        <span
                          style={{ color: c.overdue_ratio > 1.3 ? "var(--serious)" : "var(--ink)" }}
                          title="Time since last purchase, relative to this customer's own buying cycle"
                        >
                          {c.overdue_ratio < 0.1 ? "just bought" : `${c.overdue_ratio.toFixed(1)}×`}
                        </span>
                      ) : (
                        <Value hint="No repurchase cadence established yet">{null}</Value>
                      )}
                    </Td>
                    <Td>
                      {c.recommended_product ? (
                        <span className="flex items-center gap-2">
                          <span
                            className="num text-[12px] font-semibold"
                            style={{ color: matchColor(c.recommended_product.match_pct) }}
                          >
                            {c.recommended_product.match_pct}%
                          </span>
                          <span className="truncate text-[12.5px] text-[var(--ink-2)]">
                            {c.recommended_product.name}
                          </span>
                        </span>
                      ) : (
                        <Value hint="No product clears the confidence threshold">{null}</Value>
                      )}
                    </Td>
                    <Td align="right">
                      <Value>{c.customer_score}</Value>
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

function SortableTh({
  label,
  active,
  direction,
  onClick,
}: {
  label: string;
  active: boolean;
  direction: "asc" | "desc";
  onClick: () => void;
}) {
  return (
    <Th align="right">
      <button
        onClick={onClick}
        className="inline-flex items-center gap-1 uppercase tracking-[0.05em] hover:text-[var(--ink)]"
      >
        {label}
        {active &&
          (direction === "desc" ? <ArrowDown size={11} /> : <ArrowUp size={11} />)}
      </button>
    </Th>
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
