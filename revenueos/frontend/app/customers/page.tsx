"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  TableSkeleton,
  Td,
  Th,
  Value,
  inputClass,
} from "@/components/ui";
import { CustomerRow, useApi } from "@/lib/api";
import { days, lifecycleColor, matchColor, money, num, pct, shortDate, valueColor } from "@/lib/format";

type Listing = {
  total: number;
  customers: CustomerRow[];
  facets: { value_tiers: string[]; lifecycles: string[]; stores: string[] };
};

export default function CustomersPage() {
  const [q, setQ] = useState("");
  // Value and lifecycle filter separately, because they answer different
  // questions: "who are my best customers" and "who is drifting away".
  const [valueTier, setValueTier] = useState("");
  const [lifecycle, setLifecycle] = useState("");
  const [store, setStore] = useState("");
  const [sort, setSort] = useState<string>("customer_score");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [contactableOnly, setContactableOnly] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams({
      sort,
      direction,
      limit: "100",
    });
    if (q) params.set("q", q);
    if (valueTier) params.set("value_tier", valueTier);
    if (lifecycle) params.set("lifecycle", lifecycle);
    if (store) params.set("store", store);
    if (contactableOnly) params.set("contactable_only", "true");
    return `/customers?${params.toString()}`;
  }, [q, valueTier, lifecycle, store, sort, direction, contactableOnly]);

  const listing = useApi<Listing>(query);

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
        subtitle="Value and buying cycle are shown separately. A customer is a VIP because of what they spend, not because of when they last came in."
      />

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

          <select
            value={valueTier}
            onChange={(e) => setValueTier(e.target.value)}
            className={`${inputClass} w-auto`}
          >
            <option value="">All value tiers</option>
            {listing.data?.facets.value_tiers.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>

          <select
            value={lifecycle}
            onChange={(e) => setLifecycle(e.target.value)}
            className={`${inputClass} w-auto`}
          >
            <option value="">All stages</option>
            {listing.data?.facets.lifecycles.map((s) => (
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
          <TableSkeleton rows={8} cols={8} />
        ) : listing.error ? (
          <ErrorState message={listing.error} onRetry={listing.refresh} />
        ) : !listing.data?.customers.length ? (
          <EmptyState
            title="No customers match"
            body="Clear the filters or widen the search."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1020px]">
              <thead>
                <tr>
                  <Th>Customer</Th>
                  <Th>Value</Th>
                  <Th>Cycle stage</Th>
                  <SortableTh label="Value" active={sort === "total_spend"} direction={direction} onClick={() => toggleSort("total_spend")} />
                  <Th align="right">Orders</Th>
                  <Th>Last purchase</Th>
                  <SortableTh label="Through cycle" active={sort === "cycle_position"} direction={direction} onClick={() => toggleSort("cycle_position")} />
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
                          {!c.contactable && " · cannot contact"}
                        </span>
                      </Link>
                    </Td>
                    <Td>
                      {c.value_tier ? (
                        <Badge color={valueColor(c.value_tier)}>{c.value_tier}</Badge>
                      ) : (
                        <Value>{null}</Value>
                      )}
                    </Td>
                    <Td>
                      {c.lifecycle ? (
                        <Badge color={lifecycleColor(c.lifecycle)}>{c.lifecycle}</Badge>
                      ) : (
                        <Value>{null}</Value>
                      )}
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
                      {c.cycle_position != null ? (
                        <span
                          style={{ color: lifecycleColor(c.lifecycle) }}
                          title={
                            c.cycle_days
                              ? `${c.recency_days} days since last purchase, against a ${Math.round(c.cycle_days)}-day cycle (${c.cycle_confidence} confidence)`
                              : undefined
                          }
                        >
                          {pct(Math.min(c.cycle_position, 3))}
                        </span>
                      ) : (
                        <Value hint="Not enough purchase history to estimate a cycle">{null}</Value>
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

