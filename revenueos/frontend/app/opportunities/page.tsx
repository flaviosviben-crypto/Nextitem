"use client";

import Link from "next/link";
import { useState } from "react";
import { ChevronDown } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { Funnel } from "@/components/charts";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Meter,
  SectionTitle,
  Skeleton,
  Td,
  Th,
  Value,
  inputClass,
} from "@/components/ui";
import { Opportunity, api, useApi } from "@/lib/api";
import { compactMoney, matchColor, money, num, pct } from "@/lib/format";

type OppList = { total: number; total_impact: number; opportunities: Opportunity[]; types: string[] };
type PipelineRow = {
  id: string;
  customer_id: string;
  customer_name: string;
  reason: string | null;
  product: string | null;
  match_pct: number | null;
  value: number | null;
  contactable: boolean;
  priority: number;
  status: string;
  note?: string;
};
type Pipeline = {
  rows: PipelineRow[];
  counts: Record<string, number>;
  statuses: string[];
  won_value: number;
  open_value: number;
};

export default function OpportunitiesPage() {
  const [type, setType] = useState("");
  const opps = useApi<OppList>(`/opportunities${type ? `?type=${type}` : ""}`);
  const pipeline = useApi<Pipeline>("/pipeline");
  const [tab, setTab] = useState<"feed" | "pipeline">("feed");

  return (
    <Page>
      <PageHeader
        eyebrow="Opportunities"
        title="Where the revenue is"
        subtitle="Detected from your data, ranked by expected value, urgency and confidence. Every figure states the assumption behind it."
        actions={
          <div className="flex rounded-lg border border-[var(--line)] p-0.5">
            {(["feed", "pipeline"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1.5 text-[12.5px] capitalize transition-colors ${
                  tab === t ? "bg-[var(--raised)] font-medium" : "text-[var(--ink-2)]"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        }
      />

      {tab === "feed" ? (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <select value={type} onChange={(e) => setType(e.target.value)} className={`${inputClass} w-auto`}>
              <option value="">All types</option>
              {opps.data?.types.map((t) => (
                <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
              ))}
            </select>
            {opps.data && (
              <span className="text-[12.5px] text-[var(--ink-3)]">
                {num(opps.data.total)} opportunities ·{" "}
                {compactMoney(opps.data.opportunities.reduce((s, o) => s + (o.expected_value || 0), 0))} expected
              </span>
            )}
          </div>

          {opps.loading ? (
            <div className="space-y-3">
              {[0, 1, 2].map((i) => <Skeleton key={i} className="h-[130px] w-full" />)}
            </div>
          ) : opps.error ? (
            <ErrorState message={opps.error} onRetry={opps.refresh} />
          ) : !opps.data?.opportunities.length ? (
            <Card>
              <EmptyState
                title="No opportunities detected"
                body="Nothing in the current dataset crosses the threshold. Import more transaction history to sharpen detection."
                action={<Link href="/data"><Button>Open data</Button></Link>}
              />
            </Card>
          ) : (
            <div className="space-y-3">
              {opps.data.opportunities.map((o) => <OpportunityCard key={o.id} opp={o} />)}
            </div>
          )}
        </>
      ) : (
        <PipelineView pipeline={pipeline} />
      )}
    </Page>
  );
}

function OpportunityCard({ opp }: { opp: Opportunity }) {
  const [open, setOpen] = useState(false);
  const customers = opp.entities.filter((e) => e.type === "customer");
  const products = opp.entities.filter((e) => e.type === "product");

  return (
    <Card id={opp.id} className="scroll-mt-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-2">
            <Badge color="var(--accent)">{opp.type.replace(/_/g, " ")}</Badge>
            <span className="text-[11px] text-[var(--ink-3)]">Priority {opp.score}/100</span>
          </div>
          <h3 className="text-[15px] font-semibold tracking-[-0.01em]">{opp.title}</h3>
          <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-[var(--ink-2)]">
            {opp.explanation}
          </p>
        </div>
        <div className="text-right">
          <div className="num text-[20px] font-semibold">{compactMoney(opp.expected_value)}</div>
          <div className="text-[10.5px] text-[var(--ink-3)]">expected value</div>
          {opp.impact != null && (
            <div className="num mt-1 text-[11px] text-[var(--ink-3)]">
              {compactMoney(opp.impact)} best case
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-3">
        <Driver label="Likelihood" value={opp.probability} display={pct(opp.probability)} />
        <Driver label="Urgency" value={opp.urgency} display={pct(opp.urgency)} />
        <Driver label="Confidence" value={opp.confidence} display={pct(opp.confidence)} />
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--raised)] px-3.5 py-2.5">
        <p className="text-[13px]">
          <span className="font-medium">Do this: </span>
          {opp.action}
        </p>
        {(customers.length > 0 || products.length > 0) && (
          <button
            onClick={() => setOpen((o) => !o)}
            className="inline-flex shrink-0 items-center gap-1 text-[12.5px] text-[var(--accent)]"
          >
            {open ? "Hide" : "Show"} {customers.length || products.length}{" "}
            {customers.length ? "customers" : "products"}
            <ChevronDown size={13} className={open ? "rotate-180" : ""} />
          </button>
        )}
      </div>

      <p className="mt-2 text-[11px] text-[var(--ink-3)]">{opp.impact_basis}.</p>

      {open && (
        <div className="fade-in mt-3 overflow-hidden rounded-xl border border-[var(--line)]">
          <table className="w-full">
            <thead>
              <tr>
                <Th>{customers.length ? "Customer" : "Product"}</Th>
                <Th>Why</Th>
                <Th align="right">Value</Th>
                <Th align="right">Match</Th>
              </tr>
            </thead>
            <tbody>
              {(customers.length ? customers : products).map((e) => (
                <tr key={e.id} className="row-link">
                  <Td>
                    <Link
                      href={
                        e.type === "customer"
                          ? `/customers/${encodeURIComponent(e.id)}`
                          : `/inventory/${encodeURIComponent(e.id)}`
                      }
                      className="font-medium hover:text-[var(--accent)]"
                    >
                      {e.name}
                    </Link>
                    {e.contactable === false && (
                      <span className="ml-2 text-[10.5px] text-[var(--warning)]">no consent</span>
                    )}
                  </Td>
                  <Td>
                    <span className="block max-w-[420px] truncate text-[12.5px] text-[var(--ink-2)]">
                      {e.detail || e.suggested_product || "—"}
                    </span>
                  </Td>
                  <Td align="right"><Value>{e.value != null ? money(e.value) : null}</Value></Td>
                  <Td align="right">
                    {e.match_pct != null ? (
                      <span style={{ color: matchColor(e.match_pct) }}>{e.match_pct}%</span>
                    ) : (
                      <Value>{null}</Value>
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function Driver({ label, value, display }: { label: string; value: number; display: string }) {
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between text-[11.5px]">
        <span className="text-[var(--ink-3)]">{label}</span>
        <span className="num">{display}</span>
      </div>
      <Meter value={value} height={4} />
    </div>
  );
}

function PipelineView({ pipeline }: { pipeline: ReturnType<typeof useApi<Pipeline>> }) {
  const [saving, setSaving] = useState<string | null>(null);

  const update = async (row: PipelineRow, status: string) => {
    setSaving(row.id);
    try {
      await api.patch(`/pipeline/${encodeURIComponent(row.id)}`, { status });
      pipeline.refresh();
    } finally {
      setSaving(null);
    }
  };

  if (pipeline.loading) return <Skeleton className="h-[400px] w-full" />;
  if (pipeline.error) return <ErrorState message={pipeline.error} onRetry={pipeline.refresh} />;
  if (!pipeline.data?.rows.length) {
    return (
      <Card>
        <EmptyState
          title="Pipeline is empty"
          body="Opportunities become pipeline items automatically once they are detected."
        />
      </Card>
    );
  }

  const counts = pipeline.data.counts;
  return (
    <div className="grid gap-5 lg:grid-cols-[1fr_2.2fr]">
      <Card>
        <SectionTitle title="Pipeline" hint="Advisor decisions across detected opportunities." />
        <Funnel
          stages={pipeline.data.statuses
            .filter((s) => s !== "Lost")
            .map((s) => ({ label: s, value: counts[s] || 0 }))}
        />
        <div className="mt-5 space-y-2 border-t border-[var(--line)] pt-4 text-[13px]">
          <div className="flex justify-between">
            <span className="text-[var(--ink-3)]">Open value</span>
            <span className="num">{money(pipeline.data.open_value)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-[var(--ink-3)]">Won value</span>
            <span className="num" style={{ color: "var(--good)" }}>{money(pipeline.data.won_value)}</span>
          </div>
        </div>
      </Card>

      <Card padded={false}>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px]">
            <thead>
              <tr>
                <Th>Customer</Th>
                <Th>Reason</Th>
                <Th align="right">Value</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {pipeline.data.rows.slice(0, 120).map((row) => (
                <tr key={row.id}>
                  <Td>
                    <Link
                      href={`/customers/${encodeURIComponent(row.customer_id)}`}
                      className="font-medium hover:text-[var(--accent)]"
                    >
                      {row.customer_name}
                    </Link>
                    {!row.contactable && (
                      <span className="ml-2 text-[10.5px] text-[var(--warning)]">no consent</span>
                    )}
                  </Td>
                  <Td>
                    <span className="block max-w-[320px] truncate text-[12.5px] text-[var(--ink-2)]">
                      {row.product || row.reason || "—"}
                    </span>
                  </Td>
                  <Td align="right"><Value>{row.value != null ? money(row.value) : null}</Value></Td>
                  <Td>
                    <select
                      value={row.status}
                      disabled={saving === row.id}
                      onChange={(e) => update(row, e.target.value)}
                      className="rounded-md border border-[var(--line)] bg-[var(--raised)] px-2 py-1 text-[12px] outline-none"
                    >
                      {pipeline.data!.statuses.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
