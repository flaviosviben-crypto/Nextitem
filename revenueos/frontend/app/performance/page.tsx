"use client";

/**
 * Performance — the page that decides whether the pilot gets renewed.
 *
 * It reports three revenue figures deliberately, in decreasing order of size
 * and increasing order of assumption, each labelled with what it actually
 * proves. Overstating this once costs the relationship permanently.
 */

import { useState } from "react";
import { Page, PageHeader } from "@/components/Shell";
import { Card, ErrorState, SectionTitle, Skeleton, Stat, Td, Th, Value } from "@/components/ui";
import { Funnel } from "@/components/charts";
import { useApi, type Performance } from "@/lib/api";
import { money, num, pct, triggerLabel } from "@/lib/format";

const WINDOWS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
];

export default function PerformancePage() {
  const [window, setWindow] = useState(30);
  const { data, loading, error, refresh } = useApi<Performance>(
    `/performance?window_days=${window}`,
    [window],
  );

  return (
    <Page>
      <PageHeader
        eyebrow="Results"
        title="Performance"
        subtitle="What RevenueOS produced, and what the boutique did with it."
        actions={
          <div className="flex gap-1.5">
            {WINDOWS.map((w) => (
              <button
                key={w.days}
                onClick={() => setWindow(w.days)}
                className={
                  window === w.days
                    ? "rounded-lg border border-[var(--accent)] px-3 py-1.5 text-[12px] font-medium"
                    : "rounded-lg border border-[var(--line)] px-3 py-1.5 text-[12px] text-[var(--ink-2)] hover:border-[var(--line-strong)]"
                }
              >
                {w.label}
              </button>
            ))}
          </div>
        }
      />

      {loading && <Skeleton className="h-64 w-full rounded-xl" />}
      {error && <ErrorState message={error} onRetry={refresh} />}

      {data && !loading && (
        <div className="space-y-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Opportunities generated"
              value={num(data.opportunities_generated)}
              hint="Customers RevenueOS surfaced in this window"
            />
            <Stat
              label="Customers contacted"
              value={num(data.customers_contacted)}
              hint="Recorded as contacted by an advisor"
            />
            <Stat
              label="Converted"
              value={num(data.conversions)}
              tone={data.conversions > 0 ? "good" : "default"}
              hint="Advisor marked the conversation as resulting in a sale"
            />
            <Stat
              label="Conversion rate"
              value={data.conversion_rate === null ? "—" : pct(data.conversion_rate)}
              hint="Converted ÷ contacted. Measured, not modelled."
            />
          </div>

          <Card>
            <SectionTitle
              title="Revenue"
              hint="Observed first, estimated last — and each one says what it is."
            />
            <div className="space-y-4">
              <RevenueRow
                label="Revenue from contacted customers"
                value={data.contacted_revenue}
                basis={data.contacted_revenue_basis}
                tone="var(--ink)"
              />
              <RevenueRow
                label="Revenue after contact"
                value={data.influenced_revenue}
                basis={data.influenced_revenue_basis}
                tone="var(--s1)"
              />
              {data.recorded_sales_count > 0 && (
                <RevenueRow
                  label="Sales recorded by advisors"
                  value={data.recorded_sales}
                  basis={data.recorded_sales_basis}
                  tone="var(--s4)"
                />
              )}
              <RevenueRow
                label="Estimated incremental revenue"
                value={data.estimated_incremental_revenue}
                basis={data.incremental_revenue_basis}
                tone="var(--good)"
              />
            </div>
            <p className="mt-5 rounded-lg bg-[var(--raised)] p-3.5 text-[12px] leading-relaxed text-[var(--ink-2)]">
              {data.measurement_caveat}
            </p>
          </Card>

          {data.opportunities_generated > 0 && (
            <Card>
              <SectionTitle
                title="From opportunity to sale"
                hint="Where the funnel leaks is where the pilot needs attention."
              />
              <Funnel
                stages={[
                  { label: "Generated", value: data.opportunities_generated },
                  { label: "Contacted", value: data.customers_contacted },
                  { label: "Converted", value: data.conversions },
                ]}
              />
              <p className="mt-4 text-[12px] text-[var(--ink-3)]">
                {num(data.untouched)} not yet reviewed · {num(data.open)} in progress ·{" "}
                {num(data.ignored)} set aside.
              </p>
            </Card>
          )}

          {data.by_trigger.length > 0 && (
            <Card padded={false}>
              <div className="p-5 pb-0">
                <SectionTitle
                  title="Which reasons actually work"
                  hint="Conversion by why the customer was surfaced — the fastest way to tune the engine."
                />
              </div>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-[13px]">
                  <thead>
                    <tr>
                      <Th>Reason</Th>
                      <Th align="right">Generated</Th>
                      <Th align="right">Contacted</Th>
                      <Th align="right">Converted</Th>
                      <Th align="right">Rate</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_trigger.map((row) => (
                      <tr key={row.trigger} className="border-t border-[var(--line)]">
                        <Td>{triggerLabel(row.trigger)}</Td>
                        <Td align="right">{num(row.generated)}</Td>
                        <Td align="right">{num(row.contacted)}</Td>
                        <Td align="right">{num(row.converted)}</Td>
                        <Td align="right">
                          <Value hint="Nobody contacted from this reason yet">
                            {row.conversion_rate === null ? null : pct(row.conversion_rate)}
                          </Value>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>
      )}
    </Page>
  );
}

function RevenueRow({
  label,
  value,
  basis,
  tone,
}: {
  label: string;
  value: number;
  basis: string;
  tone: string;
}) {
  return (
    <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-[var(--line)] pb-4 last:border-0 last:pb-0">
      <div className="min-w-[240px] flex-1">
        <div className="text-[13px] font-medium">{label}</div>
        <p className="mt-1 text-[12px] leading-snug text-[var(--ink-3)]">{basis}</p>
      </div>
      <div className="num text-[22px] font-semibold" style={{ color: tone }}>
        {money(value)}
      </div>
    </div>
  );
}
