"use client";

import Link from "next/link";
import { Suspense, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronDown, Target } from "lucide-react";
import { post, useApi } from "@/lib/api";
import { count, cx, isKnown, money, percent } from "@/lib/format";
import { PIPELINE_STAGES, SEGMENT_TONE, matchTone } from "@/lib/theme";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Select,
  Skeleton,
  Tabs,
  Value,
} from "@/components/ui";
import { KpiCard, MatchScore } from "@/components/data";

type Opportunity = {
  id: string;
  kind: string;
  kindLabel: string;
  title: string;
  explanation: string;
  action: string;
  estimatedValue: number | null;
  probability: number;
  urgency: number;
  confidence: number;
  score: number;
  matchPct: number | null;
  status: string;
  customers: { customerId?: string; name?: string; customerName?: string; segment?: string | null; scorePct?: number; totalSpend?: number | null }[];
  customersTotal: number;
  products: { productId?: string; name?: string; productName?: string; price?: number | null; scorePct?: number }[];
  productsTotal: number;
  evidence: { label: string; value: string }[];
};

type Feed = {
  hasData: boolean;
  rows: Opportunity[];
  total: number;
  summary: { count: number; expectedValue: number | null; totalValue: number | null; customersInvolved: number };
  kinds: Record<string, { label: string }>;
  pipeline: Record<string, { count: number; value: number }>;
};

function OpportunitiesInner() {
  const params = useSearchParams();
  const [kind, setKind] = useState(params.get("kind") ?? "");
  const [stage, setStage] = useState("");
  const [expanded, setExpanded] = useState<string | null>(params.get("focus"));
  const [pending, setPending] = useState<string | null>(null);

  const url = useMemo(() => {
    const search = new URLSearchParams({ limit: "60" });
    if (kind) search.set("kind", kind);
    if (stage) search.set("status", stage);
    return `/opportunities?${search}`;
  }, [kind, stage]);

  const { data, error, isLoading, mutate } = useApi<Feed>(url, { keepPreviousData: true });

  const setStatus = async (id: string, status: string) => {
    setPending(id);
    try {
      await post(`/opportunities/${id}/status`, { status });
      await mutate();
    } finally {
      setPending(null);
    }
  };

  if (error) return <ErrorState error={error} retry={() => mutate()} />;
  if (isLoading && !data) return <Skeleton className="h-96 w-full" />;
  if (!data?.hasData) {
    return (
      <div>
        <PageHeader eyebrow="Sales pipeline" title="Opportunities" />
        <EmptyState
          icon={<Target className="size-5" />}
          title="No data loaded"
          description="Load your data and RevenueOS will surface the opportunities inside it."
          action={
            <Link href="/data">
              <Button variant="primary">Go to Data</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Sales pipeline"
        title="Opportunities"
        subtitle="Scored as probability × value × urgency × confidence, then normalised to 0-100. Move them through the pipeline as you work them."
      />

      <section className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Expected revenue"
          value={data.summary.expectedValue}
          format="currency"
          detail="Probability-weighted across all opportunities"
          accent
        />
        <KpiCard
          label="Total potential"
          value={data.summary.totalValue}
          format="currency"
          detail="If every opportunity converted"
        />
        <KpiCard
          label="Opportunities"
          value={data.summary.count}
          format="number"
          detail={`${data.summary.customersInvolved} customers involved`}
        />
        <KpiCard
          label="In progress"
          value={
            (data.pipeline.contacted?.count ?? 0) + (data.pipeline.interested?.count ?? 0)
          }
          format="number"
          detail={`${data.pipeline.won?.count ?? 0} won · ${data.pipeline.lost?.count ?? 0} lost`}
        />
      </section>

      {/* pipeline board */}
      <Card>
        <div className="grid gap-2 sm:grid-cols-5">
          {PIPELINE_STAGES.map((s) => {
            const entry = data.pipeline[s.key] ?? { count: 0, value: 0 };
            const active = stage === s.key;
            return (
              <button
                key={s.key}
                onClick={() => setStage(active ? "" : s.key)}
                className={cx(
                  "rounded-[10px] border px-3 py-2.5 text-left transition-colors",
                  active
                    ? "border-[var(--color-accent-line)] bg-[var(--color-accent-soft)]"
                    : "border-[var(--color-line)] hover:border-[var(--color-line-strong)]",
                )}
              >
                <div className="flex items-center gap-1.5">
                  <span
                    className="size-1.5 rounded-full"
                    style={{ background: `var(--color-${s.tone === "neutral" ? "ink-4" : s.tone})` }}
                  />
                  <span className="text-[11.5px] font-medium">{s.label}</span>
                </div>
                <div className="num mt-1.5 text-[17px] font-semibold">{entry.count}</div>
                <div className="num text-[11px] text-[var(--color-ink-4)]">
                  {money(entry.value, { compact: true })}
                </div>
              </button>
            );
          })}
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-2.5">
        <Select value={kind} onChange={(event) => setKind(event.target.value)}>
          <option value="">All opportunity types</option>
          {Object.entries(data.kinds).map(([key, meta]) => (
            <option key={key} value={key}>
              {meta.label}
            </option>
          ))}
        </Select>
        {kind || stage ? (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setKind("");
              setStage("");
            }}
          >
            Clear filters
          </Button>
        ) : null}
        <span className="ml-auto text-[12.5px] text-[var(--color-ink-4)]">
          {count(data.total)} shown
        </span>
      </div>

      <div className="space-y-2.5">
        {data.rows.map((opportunity) => (
          <OpportunityCard
            key={opportunity.id}
            opportunity={opportunity}
            expanded={expanded === opportunity.id}
            onToggle={() =>
              setExpanded(expanded === opportunity.id ? null : opportunity.id)
            }
            onStatus={(status) => setStatus(opportunity.id, status)}
            pending={pending === opportunity.id}
          />
        ))}
        {!data.rows.length ? (
          <EmptyState
            compact
            title="Nothing here"
            description="No opportunities match the current filters."
          />
        ) : null}
      </div>
    </div>
  );
}

function OpportunityCard({
  opportunity,
  expanded,
  onToggle,
  onStatus,
  pending,
}: {
  opportunity: Opportunity;
  expanded: boolean;
  onToggle: () => void;
  onStatus: (status: string) => void;
  pending: boolean;
}) {
  const stage = PIPELINE_STAGES.find((s) => s.key === opportunity.status) ?? PIPELINE_STAGES[0];

  return (
    <Card padded={false} className="overflow-hidden">
      <button onClick={onToggle} className="flex w-full items-start gap-4 px-4 py-3.5 text-left">
        <div className="mt-0.5 flex shrink-0 flex-col items-center gap-1">
          <div
            className="num grid size-9 place-items-center rounded-[10px] text-[13px] font-semibold"
            style={{
              background: "var(--color-accent-soft)",
              color: "var(--color-accent)",
            }}
          >
            {opportunity.score.toFixed(0)}
          </div>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[13.5px] font-medium">{opportunity.title}</span>
            <Badge size="sm" tone="neutral">
              {opportunity.kindLabel}
            </Badge>
            <Badge size="sm" tone={stage.tone} dot>
              {stage.label}
            </Badge>
          </div>
          <p className="mt-1 line-clamp-2 text-[12px] leading-relaxed text-[var(--color-ink-3)]">
            {opportunity.explanation}
          </p>
        </div>
        <div className="hidden shrink-0 text-right sm:block">
          <Value known={isKnown(opportunity.estimatedValue)} className="num text-[14px] font-semibold">
            {money(opportunity.estimatedValue)}
          </Value>
          <div className="num mt-0.5 text-[11px] text-[var(--color-ink-4)]">
            {percent(opportunity.probability)} likely
          </div>
        </div>
        <ChevronDown
          className={cx(
            "mt-1 size-4 shrink-0 text-[var(--color-ink-4)] transition-transform",
            expanded && "rotate-180",
          )}
        />
      </button>

      {expanded ? (
        <div className="animate-fade-up border-t border-[var(--color-line)] px-4 py-4">
          <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
            <div className="space-y-4">
              <div>
                <div className="eyebrow mb-2">Score components</div>
                <div className="space-y-1.5">
                  {[
                    ["Purchase probability", opportunity.probability],
                    ["Urgency", opportunity.urgency],
                    ["Data confidence", opportunity.confidence],
                  ].map(([label, value]) => (
                    <div key={String(label)} className="flex items-center gap-2.5">
                      <span className="w-[128px] shrink-0 text-[11.5px] text-[var(--color-ink-3)]">
                        {label}
                      </span>
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--color-surface-2)]">
                        <div
                          className="h-full rounded-full bg-[var(--color-accent)]"
                          style={{ width: `${Math.min(100, Number(value) * 100)}%` }}
                        />
                      </div>
                      <span className="num w-9 shrink-0 text-right text-[11px] text-[var(--color-ink-4)]">
                        {percent(Number(value))}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              {opportunity.evidence?.length ? (
                <div>
                  <div className="eyebrow mb-2">Evidence</div>
                  <div className="space-y-1">
                    {opportunity.evidence.map((item) => (
                      <div
                        key={item.label}
                        className="flex items-center justify-between gap-3 text-[12px]"
                      >
                        <span className="text-[var(--color-ink-3)]">{item.label}</span>
                        <span className="num font-medium">{item.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : null}

              <div>
                <div className="eyebrow mb-2">Recommended action</div>
                <p className="text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
                  {opportunity.action}
                </p>
              </div>

              <div>
                <div className="eyebrow mb-2">Move to</div>
                <div className="flex flex-wrap gap-1.5">
                  {PIPELINE_STAGES.map((s) => (
                    <Button
                      key={s.key}
                      size="sm"
                      variant={opportunity.status === s.key ? "primary" : "secondary"}
                      loading={pending}
                      onClick={() => onStatus(s.key)}
                    >
                      {s.label}
                    </Button>
                  ))}
                </div>
              </div>
            </div>

            <div className="space-y-4">
              {opportunity.customers?.length ? (
                <div>
                  <div className="eyebrow mb-2">
                    Customers ({opportunity.customersTotal})
                  </div>
                  <div className="space-y-1.5">
                    {opportunity.customers.map((customer, index) => {
                      const id = customer.customerId;
                      const name = customer.customerName ?? customer.name;
                      const body = (
                        <div className="flex items-center justify-between gap-3 rounded-[9px] border border-[var(--color-line)] px-3 py-2 text-[12.5px] transition-colors hover:border-[var(--color-line-strong)]">
                          <span className="min-w-0 flex-1 truncate">{name}</span>
                          {customer.segment ? (
                            <Badge size="sm" tone={SEGMENT_TONE[customer.segment] ?? "neutral"}>
                              {customer.segment}
                            </Badge>
                          ) : null}
                          {isKnown(customer.scorePct) ? (
                            <MatchScore pct={customer.scorePct} size="sm" />
                          ) : isKnown(customer.totalSpend) ? (
                            <span className="num text-[11.5px] text-[var(--color-ink-4)]">
                              {money(customer.totalSpend, { compact: true })}
                            </span>
                          ) : null}
                        </div>
                      );
                      return id ? (
                        <Link key={id} href={`/customers/${id}`}>
                          {body}
                        </Link>
                      ) : (
                        <div key={index}>{body}</div>
                      );
                    })}
                  </div>
                </div>
              ) : null}

              {opportunity.products?.length ? (
                <div>
                  <div className="eyebrow mb-2">Products ({opportunity.productsTotal})</div>
                  <div className="space-y-1.5">
                    {opportunity.products.map((product, index) => {
                      const id = product.productId;
                      const name = product.productName ?? product.name;
                      const body = (
                        <div className="flex items-center justify-between gap-3 rounded-[9px] border border-[var(--color-line)] px-3 py-2 text-[12.5px] transition-colors hover:border-[var(--color-line-strong)]">
                          <span className="min-w-0 flex-1 truncate">{name}</span>
                          {isKnown(product.scorePct) ? (
                            <MatchScore pct={product.scorePct} size="sm" />
                          ) : (
                            <span className="num text-[11.5px] text-[var(--color-ink-4)]">
                              {money(product.price)}
                            </span>
                          )}
                        </div>
                      );
                      return id ? (
                        <Link key={id} href={`/inventory/${id}`}>
                          {body}
                        </Link>
                      ) : (
                        <div key={index}>{body}</div>
                      );
                    })}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}
    </Card>
  );
}

export default function OpportunitiesPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96 w-full" />}>
      <OpportunitiesInner />
    </Suspense>
  );
}
