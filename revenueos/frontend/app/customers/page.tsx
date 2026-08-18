"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Search, Users } from "lucide-react";
import { query, useApi } from "@/lib/api";
import { cx, count, initials, isKnown, money, percent, relativeDays } from "@/lib/format";
import { SEGMENT_TONE } from "@/lib/theme";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Value,
} from "@/components/ui";
import { Card } from "@/components/ui";
import { DataTable } from "@/components/data";

type CustomerRow = {
  customerId: string;
  name: string;
  segment: string | null;
  segmentReason: string | null;
  totalSpend: number | null;
  orderCount: number | null;
  avgOrderValue: number | null;
  recencyDays: number | null;
  daysOverdue: number | null;
  churnRisk: number | null;
  customerScore: number | null;
  predicted12mValue: number | null;
  dataConfidence: string | null;
  city: string | null;
};

type CustomerList = {
  hasData: boolean;
  rows: CustomerRow[];
  total: number;
  facets: { segments: string[]; cities: string[] };
};

const PAGE_SIZE = 40;

function CustomersInner() {
  const router = useRouter();
  const params = useSearchParams();

  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [segment, setSegment] = useState(params.get("segment") ?? "");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [city, setCity] = useState("");
  const [sortBy, setSortBy] = useState("customer_score");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebounced(search);
      setOffset(0);
    }, 220);
    return () => clearTimeout(timer);
  }, [search]);

  const url = useMemo(
    () =>
      `/customers${query({
        search: debounced,
        segment,
        status,
        city,
        sortBy,
        order,
        limit: PAGE_SIZE,
        offset,
      })}`,
    [debounced, segment, status, city, sortBy, order, offset],
  );

  const { data, error, isLoading, mutate } = useApi<CustomerList>(url, {
    keepPreviousData: true,
  });

  const toggleSort = (key: string) => {
    const map: Record<string, string> = {
      name: "display_name",
      segment: "segment",
      value: "total_spend",
      last: "recency_days",
      frequency: "order_count",
      status: "days_overdue",
      opportunity: "predicted_12m_value",
      score: "customer_score",
    };
    const column = map[key] ?? key;
    if (column === sortBy) {
      setOrder(order === "desc" ? "asc" : "desc");
    } else {
      setSortBy(column);
      setOrder("desc");
    }
    setOffset(0);
  };

  if (error) return <ErrorState error={error} retry={() => mutate()} />;

  const activeFilters = [segment, status, city].filter(Boolean).length;

  return (
    <div>
      <PageHeader
        eyebrow="Customer intelligence"
        title="Customers"
        subtitle="Every profile below is computed from purchase history, not from a CRM field someone typed in."
        action={
          data ? (
            <div className="text-right">
              <div className="num text-[20px] font-semibold">{count(data.total)}</div>
              <div className="text-[11.5px] text-[var(--color-ink-4)]">
                {activeFilters ? "matching" : "total"} customers
              </div>
            </div>
          ) : undefined
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2.5">
        <div className="min-w-[220px] flex-1">
          <Input
            icon={<Search className="size-3.5" />}
            placeholder="Search name, city or ID…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <Select
          value={segment}
          onChange={(event) => {
            setSegment(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">All segments</option>
          {data?.facets.segments.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </Select>
        <Select
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">Any status</option>
          <option value="overdue">Overdue</option>
          <option value="active">In window</option>
          <option value="never">No purchase date</option>
        </Select>
        <Select
          value={city}
          onChange={(event) => {
            setCity(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">All cities</option>
          {data?.facets.cities.map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </Select>
        {activeFilters ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setSegment("");
              setStatus("");
              setCity("");
              setOffset(0);
            }}
          >
            Clear
          </Button>
        ) : null}
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
            rowKey={(row) => row.customerId}
            onRowClick={(row) => router.push(`/customers/${row.customerId}`)}
            sortKey={
              {
                display_name: "name",
                segment: "segment",
                total_spend: "value",
                recency_days: "last",
                order_count: "frequency",
                days_overdue: "status",
                predicted_12m_value: "opportunity",
                customer_score: "score",
              }[sortBy] ?? sortBy
            }
            sortOrder={order}
            onSort={toggleSort}
            empty={
              <EmptyState
                icon={<Users className="size-5" />}
                title="No customers match those filters"
                description="Try clearing a filter or widening your search."
              />
            }
            columns={[
              {
                key: "name",
                header: "Customer",
                sortable: true,
                render: (row) => (
                  <div className="flex items-center gap-2.5">
                    <div className="grid size-7 shrink-0 place-items-center rounded-full border border-[var(--color-line)] bg-[var(--color-surface-2)] text-[10.5px] font-semibold text-[var(--color-ink-3)]">
                      {initials(row.name)}
                    </div>
                    <div className="min-w-0">
                      <div className="truncate font-medium">{row.name}</div>
                      {row.city ? (
                        <div className="truncate text-[11px] text-[var(--color-ink-4)]">
                          {row.city}
                        </div>
                      ) : null}
                    </div>
                  </div>
                ),
              },
              {
                key: "segment",
                header: "Segment",
                sortable: true,
                render: (row) =>
                  row.segment ? (
                    <Badge tone={SEGMENT_TONE[row.segment] ?? "neutral"} size="sm">
                      {row.segment}
                    </Badge>
                  ) : (
                    <span className="text-[var(--color-ink-4)]">—</span>
                  ),
              },
              {
                key: "value",
                header: "Value",
                align: "right",
                sortable: true,
                render: (row) => (
                  <Value known={isKnown(row.totalSpend)} className="num font-medium">
                    {money(row.totalSpend)}
                  </Value>
                ),
              },
              {
                key: "last",
                header: "Last purchase",
                align: "right",
                sortable: true,
                render: (row) => (
                  <span className="text-[var(--color-ink-2)]">
                    {relativeDays(row.recencyDays)}
                  </span>
                ),
              },
              {
                key: "frequency",
                header: "Orders",
                align: "right",
                sortable: true,
                render: (row) => (
                  <Value known={isKnown(row.orderCount)} className="num">
                    {count(row.orderCount)}
                  </Value>
                ),
              },
              {
                key: "status",
                header: "Status",
                sortable: true,
                render: (row) => <StatusCell row={row} />,
              },
              {
                key: "opportunity",
                header: "12m potential",
                align: "right",
                sortable: true,
                render: (row) => (
                  <Value known={isKnown(row.predicted12mValue)} className="num">
                    {money(row.predicted12mValue, { compact: true })}
                  </Value>
                ),
              },
            ]}
          />
        )}
      </Card>

      {data && data.total > PAGE_SIZE ? (
        <div className="mt-4 flex items-center justify-between">
          <div className="text-[12.5px] text-[var(--color-ink-4)]">
            Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, data.total)} of{" "}
            {count(data.total)}
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Previous
            </Button>
            <Button
              size="sm"
              disabled={offset + PAGE_SIZE >= data.total}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function StatusCell({ row }: { row: CustomerRow }) {
  if (!isKnown(row.daysOverdue)) {
    return <span className="text-[12px] italic text-[var(--color-ink-4)]">No history</span>;
  }
  if (row.daysOverdue > 0) {
    const severe = isKnown(row.churnRisk) && row.churnRisk >= 0.6;
    return (
      <Badge tone={severe ? "danger" : "warning"} size="sm">
        {Math.round(row.daysOverdue)}d overdue
      </Badge>
    );
  }
  return (
    <span className="text-[12px] text-[var(--color-ink-3)]">
      Due in {Math.abs(Math.round(row.daysOverdue))}d
    </span>
  );
}

export default function CustomersPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <CustomersInner />
    </Suspense>
  );
}
