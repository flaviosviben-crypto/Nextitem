"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { Info, Search, Wand2 } from "lucide-react";
import { api, query, useApi } from "@/lib/api";
import { count, isKnown, money, percent } from "@/lib/format";
import { SEGMENT_TONE, STOCK_TONE } from "@/lib/theme";
import {
  Badge,
  Button,
  Card,
  CardSkeleton,
  EmptyState,
  ErrorState,
  Input,
  Note,
  PageHeader,
  SectionHeader,
  Skeleton,
  Tabs,
  Value,
} from "@/components/ui";
import { MatchScore, SignalBreakdown, type MatchSignal } from "@/components/data";

type Match = {
  productId: string;
  productName: string;
  brand: string | null;
  category: string | null;
  price: number | null;
  size: string | null;
  stock: number | null;
  status: string | null;
  scorePct: number;
  dataConfidence: string;
  signals: MatchSignal[];
  missingSignals: string[];
  headline: string;
};

type CustomerMatch = Match & {
  customerId: string;
  customerName: string;
  segment: string | null;
  totalSpend: number | null;
};

type ModeResponse = {
  mode: string;
  label: string;
  rows: {
    customer?: {
      customerId: string;
      name: string;
      segment: string | null;
      totalSpend: number | null;
      daysOverdue: number | null;
      dataConfidence: string;
    };
    products?: Match[];
    product?: {
      productId: string;
      name: string;
      brand: string | null;
      category: string | null;
      price: number | null;
      retailValue: number | null;
      daysInStock: number | null;
      riskScore: number | null;
      status: string | null;
    };
    customers?: CustomerMatch[];
  }[];
};

type Methodology = {
  weights: { key: string; label: string; weight: number }[];
  principle: string;
  unavailableSignals: string[];
  confidenceLevels: Record<string, string>;
};

const MODES = [
  { key: "vip", label: "VIP priority" },
  { key: "reactivation", label: "Reactivation" },
  { key: "cross_sell", label: "Cross-sell" },
  { key: "dead_stock", label: "Dead stock rescue" },
];

function RecommendationsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const [tab, setTab] = useState(params.get("customer") ? "customer" : params.get("product") ? "product" : "vip");
  const [customerId, setCustomerId] = useState(params.get("customer") ?? "");
  const [productId, setProductId] = useState(params.get("product") ?? "");
  const [showMethod, setShowMethod] = useState(false);

  const { data: method } = useApi<Methodology>("/recommendations/methodology");

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Matching engine"
        title="Recommendations"
        subtitle="Which piece for which client, and the reasoning behind every score."
        action={
          <Button
            size="sm"
            variant="ghost"
            icon={<Info className="size-3.5" />}
            onClick={() => setShowMethod((open) => !open)}
          >
            How scoring works
          </Button>
        }
      />

      {showMethod && method ? (
        <Card>
          <SectionHeader title="Scoring methodology" subtitle={method.principle} />
          <div className="grid gap-5 md:grid-cols-[1.2fr_1fr]">
            <div className="space-y-2">
              {method.weights.map((weight) => (
                <div key={weight.key} className="flex items-center gap-3">
                  <span className="w-[132px] shrink-0 text-[12px]">{weight.label}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                    <div
                      className="h-full rounded-full bg-[var(--color-accent)]"
                      style={{ width: `${(weight.weight / 0.22) * 100}%` }}
                    />
                  </div>
                  <span className="num w-9 shrink-0 text-right text-[11.5px] text-[var(--color-ink-4)]">
                    {(weight.weight * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
            <div className="space-y-2.5">
              <div className="eyebrow">Data confidence</div>
              {Object.entries(method.confidenceLevels).map(([level, meaning]) => (
                <div key={level} className="text-[11.5px] leading-relaxed">
                  <Badge size="sm" tone="neutral">{level}</Badge>{" "}
                  <span className="text-[var(--color-ink-3)]">{meaning}</span>
                </div>
              ))}
              {method.unavailableSignals.length ? (
                <Note tone="warning">
                  {method.unavailableSignals.join(" ")}
                </Note>
              ) : null}
            </div>
          </div>
        </Card>
      ) : null}

      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "customer", label: "For a customer" },
          { key: "product", label: "For a product" },
          ...MODES,
        ]}
      />

      {tab === "customer" ? (
        <ForCustomer customerId={customerId} setCustomerId={setCustomerId} />
      ) : tab === "product" ? (
        <ForProduct productId={productId} setProductId={setProductId} />
      ) : (
        <ModeView mode={tab} />
      )}
    </div>
  );
}

/* ---------------- picker ---------------- */
function EntityPicker({
  kind,
  onPick,
  placeholder,
}: {
  kind: "customers" | "products";
  onPick: (id: string, label: string) => void;
  placeholder: string;
}) {
  const [term, setTerm] = useState("");
  const [results, setResults] = useState<{ id: string; label: string; meta: string }[]>([]);

  useEffect(() => {
    if (term.trim().length < 2) {
      setResults([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      try {
        const data = await api<{
          customers: { customerId: string; name: string; segment: string; totalSpend: number | null }[];
          products: { productId: string; name: string; brand: string; price: number | null }[];
        }>(`/search${query({ q: term, limit: 6 })}`);
        if (cancelled) return;
        setResults(
          kind === "customers"
            ? data.customers.map((c) => ({
                id: c.customerId,
                label: c.name,
                meta: [c.segment, money(c.totalSpend, { compact: true })].filter(Boolean).join(" · "),
              }))
            : data.products.map((p) => ({
                id: p.productId,
                label: p.name,
                meta: [p.brand, money(p.price)].filter(Boolean).join(" · "),
              })),
        );
      } catch {
        if (!cancelled) setResults([]);
      }
    }, 180);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [term, kind]);

  return (
    <div className="relative">
      <Input
        icon={<Search className="size-3.5" />}
        placeholder={placeholder}
        value={term}
        onChange={(event) => setTerm(event.target.value)}
      />
      {results.length ? (
        <div className="absolute z-20 mt-1.5 w-full overflow-hidden rounded-[11px] border border-[var(--color-line-strong)] bg-[var(--color-elevated)] shadow-[var(--shadow-pop)]">
          {results.map((result) => (
            <button
              key={result.id}
              onClick={() => {
                onPick(result.id, result.label);
                setTerm("");
                setResults([]);
              }}
              className="flex w-full items-center justify-between gap-3 px-3.5 py-2.5 text-left text-[13px] transition-colors hover:bg-[var(--color-surface-2)]"
            >
              <span className="truncate">{result.label}</span>
              <span className="shrink-0 text-[11.5px] text-[var(--color-ink-4)]">{result.meta}</span>
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

/* ---------------- for a customer ---------------- */
function ForCustomer({
  customerId,
  setCustomerId,
}: {
  customerId: string;
  setCustomerId: (id: string) => void;
}) {
  const { data, error, isLoading } = useApi<{
    customer: { customerId: string; name: string; segment: string; totalSpend: number | null; dataConfidence: string };
    results: Match[];
  }>(customerId ? `/recommendations/for-customer/${customerId}?limit=12` : null);

  return (
    <div className="space-y-4">
      <Card>
        <SectionHeader
          title="Pick a customer"
          subtitle="Search by name or city, then see every piece in stock ranked for them."
        />
        <div className="max-w-md">
          <EntityPicker
            kind="customers"
            placeholder="Search a customer…"
            onPick={(id) => setCustomerId(id)}
          />
        </div>
      </Card>

      {!customerId ? (
        <EmptyState
          icon={<Wand2 className="size-5" />}
          title="Select a customer to begin"
          description="RevenueOS will rank your whole catalogue for them and show why each piece fits."
        />
      ) : isLoading ? (
        <CardSkeleton rows={5} />
      ) : error ? (
        <ErrorState error={error} />
      ) : data ? (
        <Card>
          <SectionHeader
            title={`Ranked for ${data.customer.name}`}
            subtitle={`${data.results.length} products scored · ${data.customer.dataConfidence} data confidence`}
            action={
              <Link
                href={`/customers/${data.customer.customerId}`}
                className="text-[12.5px] text-[var(--color-ink-3)] hover:text-[var(--color-ink)]"
              >
                Open profile
              </Link>
            }
          />
          <div className="grid gap-3 lg:grid-cols-2">
            {data.results.map((match) => (
              <MatchCard key={match.productId} match={match} />
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}

/* ---------------- for a product ---------------- */
function ForProduct({
  productId,
  setProductId,
}: {
  productId: string;
  setProductId: (id: string) => void;
}) {
  const { data, error, isLoading } = useApi<{
    product: { productId: string; name: string; brand: string; price: number | null; stock: number | null; status: string };
    results: CustomerMatch[];
  }>(productId ? `/recommendations/for-product/${productId}?limit=20` : null);

  return (
    <div className="space-y-4">
      <Card>
        <SectionHeader
          title="Pick a product"
          subtitle="Especially useful for a new arrival: find out immediately who to call."
        />
        <div className="max-w-md">
          <EntityPicker
            kind="products"
            placeholder="Search a product or SKU…"
            onPick={(id) => setProductId(id)}
          />
        </div>
      </Card>

      {!productId ? (
        <EmptyState
          icon={<Wand2 className="size-5" />}
          title="Select a product to begin"
          description="RevenueOS will rank your whole customer base for it."
        />
      ) : isLoading ? (
        <CardSkeleton rows={5} />
      ) : error ? (
        <ErrorState error={error} />
      ) : data ? (
        <Card>
          <SectionHeader
            title={`Best customers for ${data.product.name}`}
            subtitle={`${money(data.product.price)} · ${count(data.product.stock)} in stock · ${data.results.length} customers above the threshold`}
            action={
              <Link
                href={`/inventory/${data.product.productId}`}
                className="text-[12.5px] text-[var(--color-ink-3)] hover:text-[var(--color-ink)]"
              >
                Open product
              </Link>
            }
          />
          {data.results.length ? (
            <div className="grid gap-3 lg:grid-cols-2">
              {data.results.map((match) => (
                <CustomerMatchCard key={match.customerId} match={match} />
              ))}
            </div>
          ) : (
            <EmptyState
              compact
              title="No strong matches"
              description="Nobody in your base shows real affinity for this piece — treat it as markdown or bundle stock."
            />
          )}
        </Card>
      ) : null}
    </div>
  );
}

/* ---------------- batch modes ---------------- */
function ModeView({ mode }: { mode: string }) {
  const { data, error, isLoading } = useApi<ModeResponse>(
    `/recommendations/mode/${mode}?limit=10&perCustomer=3`,
  );

  if (isLoading) return <CardSkeleton rows={6} />;
  if (error) return <ErrorState error={error} />;
  if (!data?.rows?.length) {
    return (
      <EmptyState
        icon={<Wand2 className="size-5" />}
        title="Nothing in this mode right now"
        description="No customers or products currently meet the criteria for this play."
      />
    );
  }

  if (mode === "dead_stock") {
    return (
      <div className="space-y-4">
        {data.rows.map((row) => (
          <Card key={row.product!.productId}>
            <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
              <div className="min-w-0">
                <Link
                  href={`/inventory/${row.product!.productId}`}
                  className="text-[15px] font-semibold hover:text-[var(--color-accent)]"
                >
                  {row.product!.name}
                </Link>
                <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-[var(--color-ink-4)]">
                  {row.product!.status ? (
                    <Badge tone={STOCK_TONE[row.product!.status] ?? "neutral"} size="sm">
                      {row.product!.status}
                    </Badge>
                  ) : null}
                  <span className="num">{money(row.product!.retailValue)} tied up</span>
                  {isKnown(row.product!.daysInStock) ? (
                    <span>· {Math.round(row.product!.daysInStock)} days in stock</span>
                  ) : null}
                </div>
              </div>
              <div className="text-right text-[12px] text-[var(--color-ink-3)]">
                {row.customers?.length
                  ? `${row.customers.length} customers worth contacting first`
                  : "No affinity found — markdown candidate"}
              </div>
            </div>
            {row.customers?.length ? (
              <div className="grid gap-2.5 lg:grid-cols-3">
                {row.customers.map((match) => (
                  <CompactCustomer key={match.customerId} match={match} />
                ))}
              </div>
            ) : null}
          </Card>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {data.rows.map((row) => (
        <Card key={row.customer!.customerId}>
          <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <Link
                href={`/customers/${row.customer!.customerId}`}
                className="text-[15px] font-semibold hover:text-[var(--color-accent)]"
              >
                {row.customer!.name}
              </Link>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[12px] text-[var(--color-ink-4)]">
                {row.customer!.segment ? (
                  <Badge tone={SEGMENT_TONE[row.customer!.segment] ?? "neutral"} size="sm">
                    {row.customer!.segment}
                  </Badge>
                ) : null}
                <span className="num">{money(row.customer!.totalSpend)} lifetime</span>
                {isKnown(row.customer!.daysOverdue) && row.customer!.daysOverdue > 0 ? (
                  <span className="text-[var(--color-warning)]">
                    · {Math.round(row.customer!.daysOverdue)} days overdue
                  </span>
                ) : null}
              </div>
            </div>
          </div>
          <div className="grid gap-3 lg:grid-cols-3">
            {row.products?.map((match) => (
              <MatchCard key={match.productId} match={match} compact />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}

/* ---------------- cards ---------------- */
function MatchCard({ match, compact = false }: { match: Match; compact?: boolean }) {
  return (
    <div className="rounded-[11px] border border-[var(--color-line)] p-3.5 transition-colors hover:border-[var(--color-line-strong)]">
      <div className="flex items-start justify-between gap-3">
        <Link href={`/inventory/${match.productId}`} className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium hover:text-[var(--color-accent)]">
            {match.productName}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11.5px] text-[var(--color-ink-4)]">
            <span>{match.category}</span>
            <span>·</span>
            <span className="num">{money(match.price)}</span>
            {match.size ? <span>· {match.size}</span> : null}
          </div>
        </Link>
        <MatchScore pct={match.scorePct} confidence={compact ? undefined : match.dataConfidence} size={compact ? "sm" : "md"} />
      </div>
      <div className="mt-3 border-t border-[var(--color-line)] pt-3">
        <SignalBreakdown signals={match.signals} missing={compact ? undefined : match.missingSignals} limit={compact ? 3 : 4} />
      </div>
    </div>
  );
}

function CustomerMatchCard({ match }: { match: CustomerMatch }) {
  return (
    <div className="rounded-[11px] border border-[var(--color-line)] p-3.5 transition-colors hover:border-[var(--color-line-strong)]">
      <div className="flex items-start justify-between gap-3">
        <Link href={`/customers/${match.customerId}`} className="min-w-0 flex-1">
          <div className="truncate text-[13px] font-medium hover:text-[var(--color-accent)]">
            {match.customerName}
          </div>
          <div className="mt-0.5 flex items-center gap-2">
            {match.segment ? (
              <Badge tone={SEGMENT_TONE[match.segment] ?? "neutral"} size="sm">
                {match.segment}
              </Badge>
            ) : null}
            <span className="num text-[11.5px] text-[var(--color-ink-4)]">
              {money(match.totalSpend, { compact: true })}
            </span>
          </div>
        </Link>
        <MatchScore pct={match.scorePct} confidence={match.dataConfidence} />
      </div>
      <div className="mt-3 border-t border-[var(--color-line)] pt-3">
        <SignalBreakdown signals={match.signals} missing={match.missingSignals} limit={3} />
      </div>
    </div>
  );
}

function CompactCustomer({ match }: { match: CustomerMatch }) {
  return (
    <Link
      href={`/customers/${match.customerId}`}
      className="block rounded-[10px] border border-[var(--color-line)] px-3 py-2.5 transition-colors hover:border-[var(--color-line-strong)]"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-[12.5px] font-medium">{match.customerName}</span>
        <MatchScore pct={match.scorePct} size="sm" />
      </div>
      <div className="mt-1 line-clamp-2 text-[11px] leading-snug text-[var(--color-ink-4)]">
        {match.signals[0]?.reason}
      </div>
    </Link>
  );
}

export default function RecommendationsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <RecommendationsInner />
    </Suspense>
  );
}
