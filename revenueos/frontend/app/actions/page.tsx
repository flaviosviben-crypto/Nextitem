"use client";

/**
 * Action Center — what the advisor committed to, and what came of it.
 *
 * Opportunities are a proposal; this is the record. Every state change is
 * written to an audit trail server-side, which is what makes the outreach
 * defensible to a luxury house's legal team.
 */

import { Fragment, useState } from "react";
import Link from "next/link";
import { Page, PageHeader } from "@/components/Shell";
import { OutreachPanel } from "@/components/OutreachPanel";
import { DeclineMenu, type Decline } from "@/components/DeclineReason";
import {
  Badge,
  Card,
  EmptyState,
  ErrorState,
  FilterChip,
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

/**
 * The stored states, said the way an advisor would.
 *
 * "New" means nobody has decided yet — not that it is new, nor that it is due.
 * "Approved" means decided but not yet acted on, which is a queue, not an
 * outcome. Both labels are presentation only: the pipeline, the audit trail and
 * every performance figure keep the stored values, so nothing downstream has to
 * learn a second vocabulary.
 */
const STATUS_LABEL: Record<string, string> = {
  New: "Awaiting decision",
  Approved: "Ready to contact",
  // "Ignored" reads as neglect. The advisor made a decision and gave a reason
  // for it; the stored value stays "Ignored" so nothing downstream changes.
  Ignored: "Set aside",
};

export default function ActionsPage() {
  const [status, setStatus] = useState("");
  // Today's recommended workload, or the whole detected universe. Defaulting to
  // today keeps this screen a queue rather than a backlog to feel guilty about.
  const [scope, setScope] = useState<"today" | "all">("today");
  // Which row has its outreach draft open. One at a time: this is a table, and
  // two expanded drafts stop it being one.
  const [drafting, setDrafting] = useState<string | null>(null);
  // A row whose status control was moved to "Set aside". The change is not sent
  // until a reason is chosen — the API requires one, and asking here keeps the
  // two ways of setting something aside consistent.
  const [declining, setDeclining] = useState<string | null>(null);
  // Store is a real relationship on the row (the customer's own CRM or
  // transaction-derived store) — filtering by it narrows the whole screen,
  // the same way the status tiles already narrow by scope.
  const [store, setStore] = useState("");
  const { data, loading, error, refresh, setData } = useApi<ActionCenter>(
    `/actions?status=${encodeURIComponent(status)}&scope=${scope}&store=${encodeURIComponent(store)}`,
    [status, scope, store],
  );

  const update = async (row: ActionRow, next: string, decline?: Decline) => {
    // Setting aside needs a reason first. Nothing is sent, and nothing on
    // screen changes, until the advisor gives one.
    if (next === "Ignored" && !decline) {
      setDeclining(row.id);
      return;
    }
    // Optimistic: the advisor moved on before the request returned.
    setData((prev) =>
      prev
        ? { ...prev, rows: prev.rows.map((r) => (r.id === row.id ? { ...r, status: next } : r)) }
        : prev,
    );
    try {
      await api.patch(`/actions/${encodeURIComponent(row.id)}`, {
        status: next,
        ...(decline ? { reason: decline.reason, reason_note: decline.note } : {}),
      });
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

      {data && (
        <div className="mb-5 flex flex-wrap items-center gap-1.5">
          <FilterChip active={scope === "today"} onClick={() => setScope("today")}>
            Recommended today · {data.todays_list}
          </FilterChip>
          <FilterChip active={scope === "all"} onClick={() => setScope("all")}>
            All detected · {data.detected}
          </FilterChip>
          {data.stores.length > 0 && (
            <select
              value={store}
              onChange={(e) => setStore(e.target.value)}
              className={`${inputClass} w-auto py-1 text-[12px]`}
            >
              <option value="">All stores</option>
              {data.stores.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          )}
          <span className="ml-1 text-[12px] text-[var(--muted)]">
            {data.awaiting_decision} of today&apos;s recommendations still awaiting a decision ·{" "}
            {data.detected_not_prioritized} detected but not prioritized for today
          </span>
        </div>
      )}

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
                <div className="eyebrow">{STATUS_LABEL[s] ?? s}</div>
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
                <table className="w-full min-w-[880px] table-fixed text-[13px]">
                  {/* Declared widths, so a long reason wraps inside its own
                      column instead of resizing the table around it. They are
                      percentages, so the whole table grows with the container
                      and the extra desktop width lands where it is worth most:
                      the reason, which was clamping mid-sentence. */}
                  <colgroup>
                    <col className="w-[16%]" />
                    <col className="w-[30%]" />
                    <col className="w-[17%]" />
                    <col className="w-[9%]" />
                    <col className="w-[11%]" />
                    <col className="w-[17%]" />
                  </colgroup>
                  <thead>
                    <tr>
                      <Th>Customer</Th>
                      <Th>Why now</Th>
                      <Th>Product</Th>
                      <Th>Channel</Th>
                      <Th align="right" wrap>Expected value</Th>
                      <Th>Status</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row) => (
                      <Fragment key={row.id}>
                      <tr className="border-t border-[var(--line)]">
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
                          {row.store && (
                            <div className="mt-1 text-[11px] text-[var(--ink-3)]">{row.store}</div>
                          )}
                        </Td>
                        <Td wrap>
                          <span className="text-[var(--ink-3)]">{triggerLabel(row.trigger)}</span>
                          <div
                            className="mt-0.5 line-clamp-2 text-[12.5px] leading-snug text-[var(--ink-2)]"
                            title={row.reason ?? undefined}
                          >
                            {row.reason}
                          </div>
                        </Td>
                        <Td>
                          <div className="truncate" title={row.product ?? undefined}>
                            <Value>{row.product}</Value>
                          </div>
                          {row.match_pct !== null && (
                            <span className="text-[11px] text-[var(--ink-3)]">
                              {row.match_pct}% match
                            </span>
                          )}
                        </Td>
                        <Td>
                          <Value hint="No permitted channel on file">{row.channel}</Value>
                        </Td>
                        <Td align="right">
                          <Value>{money(row.influenced_value)}</Value>
                        </Td>
                        <Td className="relative">
                          <select
                            value={row.status}
                            onChange={(e) => update(row, e.target.value)}
                            className={`${inputClass} w-full max-w-full py-1 text-[12px]`}
                            style={{ color: STATE_COLOR[row.status] }}
                          >
                            {data.statuses.map((s) => (
                              <option key={s} value={s}>
                                {STATUS_LABEL[s] ?? s}
                              </option>
                            ))}
                          </select>
                          {declining === row.id && (
                            <DeclineMenu
                              align="left"
                              onDecline={(d) => update(row, "Ignored", d)}
                              onClose={() => setDeclining(null)}
                            />
                          )}
                          {/* Was its own column; folded in here so the reason
                              column has the room it needs. Only a decision has
                              a date worth reading — falling back to created_at
                              stamped today's date identically on every row,
                              which is a column of noise, not information. */}
                          {row.updated_at && (
                            <div className="mt-1 text-[11px] text-[var(--muted)]">
                              Decided {shortDate(row.updated_at)}
                            </div>
                          )}
                          {/* A row that is decided but not yet acted on still
                              needs the thing the advisor came for. Reopening
                              the draft here is what makes "Later" on the
                              Opportunities panel a safe thing to press. */}
                          {/* Why it was set aside, where the decision itself is
                              — secondary text rather than a column, because it
                              is only ever present on Ignored rows. */}
                          {row.decline_reason_label && (
                            <div
                              className="mt-1 text-[11px] text-[var(--ink-3)]"
                              title={row.decline_note ?? undefined}
                            >
                              {row.decline_reason_label}
                              {row.decline_note ? ` — ${row.decline_note}` : ""}
                            </div>
                          )}
                          {row.status === "Approved" && (
                            <button
                              onClick={() => setDrafting(drafting === row.id ? null : row.id)}
                              className="mt-1 text-[11.5px] text-[var(--accent)] underline-offset-2 hover:underline"
                            >
                              {drafting === row.id ? "Hide draft" : "Draft outreach"}
                            </button>
                          )}
                        </Td>
                      </tr>
                      {drafting === row.id && (
                        <tr>
                          <td colSpan={6} className="px-4 pb-4">
                            <OutreachPanel
                              opportunityId={row.id}
                              customerName={row.customer_name}
                              onDone={() => {
                                setDrafting(null);
                                refresh();
                              }}
                              onDismiss={() => setDrafting(null)}
                            />
                          </td>
                        </tr>
                      )}
                      </Fragment>
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
