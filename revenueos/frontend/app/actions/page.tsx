"use client";

/**
 * Action Center — what the advisor committed to, and what came of it.
 *
 * Opportunities are a proposal; this is the record. Every state change is
 * written to an audit trail server-side, which is what makes the outreach
 * defensible to a luxury house's legal team.
 */

import { useState } from "react";
import Link from "next/link";
import { Page, PageHeader } from "@/components/Shell";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
  Td,
  Th,
  Value,
  inputClass,
} from "@/components/ui";
import { api, useApi, type ActionCenter, type ActionRow } from "@/lib/api";
import { lifecycleColor, money, shortDate, triggerLabel, valueColor } from "@/lib/format";

// Colour carries the same meaning as the word, never instead of it.
const STATE_COLOR: Record<string, string> = {
  New: "var(--ink-3)",
  Approved: "var(--s1)",
  Scheduled: "var(--s4)",
  Contacted: "var(--warning)",
  Converted: "var(--good)",
  Ignored: "var(--ink-3)",
};

export default function ActionsPage() {
  const [status, setStatus] = useState("");
  const { data, loading, error, refresh, setData } = useApi<ActionCenter>(
    `/actions?status=${encodeURIComponent(status)}`,
    [status],
  );

  const update = async (row: ActionRow, next: string) => {
    // Optimistic: the advisor moved on before the request returned.
    setData((prev) =>
      prev
        ? { ...prev, rows: prev.rows.map((r) => (r.id === row.id ? { ...r, status: next } : r)) }
        : prev,
    );
    try {
      await api.patch(`/actions/${encodeURIComponent(row.id)}`, { status: next });
    } finally {
      refresh();
    }
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Workflow"
        title="Action Center"
        subtitle="Every opportunity an advisor decided on, and where it stands."
      />

      {loading && <Skeleton className="h-64 w-full rounded-xl" />}
      {error && <ErrorState message={error} onRetry={refresh} />}

      {data && (
        <>
          <div className="mb-5 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {data.statuses.map((s) => (
              <button
                key={s}
                onClick={() => setStatus(status === s ? "" : s)}
                className={
                  status === s
                    ? "card border-[var(--accent)] p-3 text-left"
                    : "card p-3 text-left transition-colors hover:border-[var(--line-strong)]"
                }
              >
                <div className="eyebrow">{s}</div>
                <div className="num mt-1.5 text-[20px] font-semibold">{data.counts[s] ?? 0}</div>
              </button>
            ))}
          </div>

          {data.counts.Converted > 0 && (
            <Card className="mb-5">
              <div className="eyebrow">Recorded from converted opportunities</div>
              <div className="num mt-1.5 text-[24px] font-semibold">
                {money(data.converted_value)}
              </div>
              <p className="mt-2 text-[12px] leading-snug text-[var(--ink-3)]">
                {data.converted_value_basis}
              </p>
            </Card>
          )}

          {data.rows.length === 0 ? (
            <EmptyState
              title="Nothing here yet"
              body={
                status
                  ? `No opportunities are currently ${status.toLowerCase()}.`
                  : "Approve an opportunity from Today's Opportunities and it will appear here."
              }
            />
          ) : (
            <Card padded={false}>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] text-[13px]">
                  <thead>
                    <tr>
                      <Th>Customer</Th>
                      <Th>Why</Th>
                      <Th>Product</Th>
                      <Th>Channel</Th>
                      <Th align="right">If it converts</Th>
                      <Th>Updated</Th>
                      <Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row) => (
                      <tr key={row.id} className="border-t border-[var(--line)]">
                        <Td>
                          <Link
                            href={`/customers/${encodeURIComponent(row.customer_id)}`}
                            className="font-medium hover:underline"
                          >
                            {row.customer_name}
                          </Link>
                          <div className="mt-1 flex gap-1.5">
                            {row.value_tier && (
                              <Badge color={valueColor(row.value_tier)}>{row.value_tier}</Badge>
                            )}
                            {row.lifecycle && (
                              <Badge color={lifecycleColor(row.lifecycle)}>{row.lifecycle}</Badge>
                            )}
                          </div>
                        </Td>
                        <Td>
                          <span className="text-[var(--ink-3)]">{triggerLabel(row.trigger)}</span>
                          <div className="mt-0.5 max-w-[280px] text-[12px] leading-snug text-[var(--ink-2)]">
                            {row.reason}
                          </div>
                        </Td>
                        <Td>
                          <Value>{row.product}</Value>
                          {row.match_pct !== null && (
                            <span className="ml-1.5 text-[11px] text-[var(--ink-3)]">
                              {row.match_pct}%
                            </span>
                          )}
                        </Td>
                        <Td>
                          <Value hint="No permitted channel on file">{row.channel}</Value>
                        </Td>
                        <Td align="right">
                          <Value>{money(row.influenced_value)}</Value>
                        </Td>
                        <Td>
                          <Value>{shortDate(row.updated_at || row.created_at)}</Value>
                        </Td>
                        <Td>
                          <select
                            value={row.status}
                            onChange={(e) => update(row, e.target.value)}
                            className={`${inputClass} py-1 text-[12px]`}
                            style={{ color: STATE_COLOR[row.status] }}
                          >
                            {data.statuses.map((s) => (
                              <option key={s} value={s}>
                                {s}
                              </option>
                            ))}
                          </select>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}
    </Page>
  );
}
