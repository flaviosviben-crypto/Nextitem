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
import {
  EXPECTED_VALUE,
  EXPECTED_VALUE_HELP,
  money,
  num,
  pct,
  triggerLabel,
} from "@/lib/format";

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

      {loading && (
        <div className="space-y-3">
          {[0, 1].map((i) => (
            <Skeleton key={i} className="h-32 w-full rounded-xl" />
          ))}
        </div>
      )}

      {data && !loading && (
        <div className="space-y-6">
          {/* Commercial outcome first. Leading with how much the engine detected
              answers a question about the engine; this page has to answer whether
              any of it turned into activity a boutique can bank. */}
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat
              label="Revenue after contact"
              value={money(data.influenced_revenue)}
              tone={data.influenced_revenue > 0 ? "good" : "default"}
              hint="Observed. Spend within 30 days of a recorded contact — time-linked, not proof of cause."
            />
            <Stat
              label="Recommended customers contacted"
              value={`${num(data.customers_contacted)} / ${num(data.prioritized_today)}`}
              hint="Observed. Share of recommended customers advisors actually contacted."
            />
            <Stat
              label="Measured conversion rate"
              value={data.conversion_rate === null ? "—" : pct(data.conversion_rate)}
              hint="Converted ÷ contacted. Measured from advisor outcomes, not modelled."
            />
          </div>

          {/* Nothing measured yet is the normal state of a new workspace. Say what
              is waiting and what will fill this page, rather than showing a wall
              of zeroes that reads as a product which did not work. */}
          {data.customers_contacted === 0 && data.opportunities_detected > 0 && (
            <Card>
              {/* The link between the two halves of the product, stated once:
                  here is what the engine put on the table, and here is why the
                  page below it is still empty. Both figures come from the API —
                  a hard-coded number here would be a lie the moment the data
                  changed. Expected is never presented as earned. */}
              <p className="text-[14px] leading-relaxed text-[var(--ink)]">
                {data.prioritized_expected_value > 0 ? (
                  <>
                    RevenueOS identified{" "}
                    <span className="num font-semibold" title={EXPECTED_VALUE_HELP}>
                      {money(data.prioritized_expected_value)}
                    </span>{" "}
                    in {EXPECTED_VALUE.toLowerCase()} across{" "}
                    {num(data.prioritized_today)}{" "}
                    {data.prioritized_today === 1 ? "recommendation" : "recommendations"} during
                    the selected {window}-day period, drawn from{" "}
                    {num(data.opportunities_detected)} detected{" "}
                    {data.opportunities_detected === 1 ? "opportunity" : "opportunities"}.
                  </>
                ) : (
                  <>
                    RevenueOS has {num(data.opportunities_detected)} detected{" "}
                    {data.opportunities_detected === 1 ? "opportunity" : "opportunities"} in the
                    selected {window}-day period, of which {num(data.prioritized_today)}{" "}
                    {data.prioritized_today === 1 ? "is" : "are"} recommended.
                  </>
                )}
              </p>
              <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--ink-2)]">
                That is modelled, not earned. Measured commercial results appear here once
                advisors contact those customers and record what happened.
              </p>
            </Card>
          )}

          {/* Two halves of the same question — how much, and where it stopped —
              so on a wide screen they are read together rather than a scroll
              apart. They stack again below xl, where side-by-side would squeeze
              the revenue rows past readability. */}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] xl:items-start">
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

          {data.opportunities_detected > 0 && (
            <Card>
              <SectionTitle
                title="From opportunity to sale"
                hint="Where the funnel leaks is where the pilot needs attention."
              />
              <Funnel
                stages={[
                  { label: "Detected", value: data.opportunities_detected },
                  { label: "Recommended", value: data.prioritized_today },
                  // Recommended splits into decided and still-waiting; showing
                  // the decided half is what connects the inbox to this page.
                  {
                    label: "Decisions made",
                    value: Math.max(0, data.prioritized_today - data.awaiting_decision),
                  },
                  { label: "Contacted", value: data.customers_contacted },
                  { label: "Converted", value: data.conversions },
                ]}
              />
              <p className="mt-4 text-[12px] text-[var(--ink-3)]">
                {num(data.awaiting_decision)} awaiting a decision · {num(data.open)} in
                progress · {num(data.ignored)} set aside ·{" "}
                {num(data.detected_not_recommended)} detected but not recommended.
              </p>
              <p className="mt-1.5 text-[12px] text-[var(--muted)]">
                Every stage is counted from when each opportunity was first
                recommended, so this funnel reflects the selected window, not
                today's current list.
              </p>
            </Card>
          )}
          </div>

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
                      <Th align="right">Recommended</Th>
                      <Th align="right">Contacted</Th>
                      <Th align="right">Converted</Th>
                      <Th align="right">Rate</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_trigger.map((row) => (
                      <tr key={row.trigger} className="border-t border-[var(--line)]">
                        <Td>{triggerLabel(row.trigger)}</Td>
                        <Td align="right">{num(row.recommended)}</Td>
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
