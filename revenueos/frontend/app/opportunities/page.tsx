"use client";

/**
 * Today's Opportunities — the screen the whole product exists to produce.
 *
 * Each card reads top to bottom in the order an advisor thinks:
 * who, why now, what to show them, why that piece, and how to reach them.
 * Scores, probabilities and model internals stay in the backend where they
 * belong; the advisor gets evidence they can verify in seconds.
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, ChevronUp, Info, ShieldOff } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import { OutreachPanel } from "@/components/OutreachPanel";
import { NotNowButton, type Decline } from "@/components/DeclineReason";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  FilterChip,
  Skeleton,
} from "@/components/ui";
import {
  api,
  useApi,
  type Opportunity,
  type OpportunityFeed,
  type ProductCard,
} from "@/lib/api";
import {
  EXPECTED_VALUE,
  EXPECTED_VALUE_HELP,
  lifecycleColor,
  matchColor,
  money,
  triggerLabel,
  valueColor,
} from "@/lib/format";

// Triggers whose meaning is already carried by the lifecycle badge beside them.
const LIFECYCLE_TRIGGERS = new Set(["due", "at_risk", "win_back"]);

export default function OpportunitiesPage() {
  const [trigger, setTrigger] = useState("");
  const { data, loading, slow, error, refresh, setData } = useApi<OpportunityFeed>(
    `/opportunities?trigger=${encodeURIComponent(trigger)}`,
    [trigger],
  );
  // Ids with a request in flight. Buttons disable while a decision is being
  // recorded, so an impatient second click cannot send a second decision.
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [failed, setFailed] = useState<string | null>(null);
  // Recommendations the advisor approved in this session. They have already
  // left the decision inbox — this keeps the outreach draft standing where the
  // card was, so approving does not mean hunting for what to say next.
  const [drafting, setDrafting] = useState<Opportunity[]>([]);

  /**
   * Record a decision, then take the card out of the inbox.
   *
   * The removal happens only after the API confirms, and it edits the same
   * counts the response carries, so what is on screen always matches what the
   * server would return on a refresh. Removing first and reconciling later
   * looks faster and lies when the request fails.
   */
  const act = async (opp: Opportunity, status: string, decline?: Decline) => {
    if (pending.has(opp.id)) return;
    setPending((prev) => new Set(prev).add(opp.id));
    setFailed(null);
    try {
      await api.patch(`/actions/${encodeURIComponent(opp.id)}`, {
        status,
        ...(decline ? { reason: decline.reason, reason_note: decline.note } : {}),
      });
      // Approve is the start of the outreach, not the end of the decision. The
      // panel opens only once the decision is persisted — the same rule the
      // card removal follows, for the same reason.
      if (status === "Approved") {
        setDrafting((prev) => (prev.some((o) => o.id === opp.id) ? prev : [opp, ...prev]));
      }
      setData((prev) =>
        prev
          ? {
              ...prev,
              opportunities: prev.opportunities.filter((o) => o.id !== opp.id),
              shown: Math.max(0, prev.shown - 1),
              // The day still recommended it. Only the queue shrinks.
              awaiting_decision: Math.max(0, (prev.awaiting_decision ?? prev.shown) - 1),
              decisions_made: (prev.decisions_made ?? 0) + 1,
              influenced_value: Math.max(
                0,
                prev.influenced_value - (opp.influenced_value ?? 0),
              ),
            }
          : prev,
      );
    } catch (err) {
      // Nothing was recorded, so nothing leaves the inbox.
      setFailed(
        err instanceof Error
          ? `${opp.customer_name}: ${err.message}`
          : `Could not record that decision for ${opp.customer_name}.`,
      );
      // Re-raised so the card knows the save failed and can leave the reason
      // the advisor chose on screen rather than silently discarding it.
      throw err;
    } finally {
      setPending((prev) => {
        const next = new Set(prev);
        next.delete(opp.id);
        return next;
      });
    }
  };

  const triggers = data?.triggers || [];

  // The feed *is* the awaiting queue: /opportunities defaults to the undecided
  // set, so the number of rows it returns is the count of decisions still owed.
  // Reading it from the rows rather than from a summary field means the header
  // can never disagree with the cards under it, and it stays correct against an
  // API build that predates the awaiting_decision/decisions_made fields — which
  // is what rendered "undefined of 20".
  const awaiting = data ? data.opportunities.length : 0;
  const decided = data ? Math.max(0, data.prioritized_today - awaiting) : 0;

  return (
    <Page>
      <PageHeader
        eyebrow="Today"
        title="Today's Opportunities"
        subtitle={
          data
            ? awaiting === 0 && decided > 0
              ? `Every one of today's ${data.prioritized_today} recommendations has a decision.`
              : `${awaiting} of ${data.prioritized_today} ` +
                `${data.prioritized_today === 1 ? "recommendation" : "recommendations"} ` +
                `still need a decision` +
                (decided > 0 ? ` · ${decided} decided` : "") +
                `. Selected from ${data.detected} detected ` +
                `${data.detected === 1 ? "opportunity" : "opportunities"}.`
            : "Who to contact today, and what to say."
        }
        actions={
          data && data.influenced_value > 0 ? (
            <div className="text-right">
              <div className="num text-[20px] font-semibold">{money(data.influenced_value)}</div>
              <div className="text-[12px] text-[var(--ink-2)]" title={EXPECTED_VALUE_HELP}>
                {EXPECTED_VALUE} of today&apos;s list
              </div>
            </div>
          ) : undefined
        }
      />

      {triggers.length > 1 && (
        <div className="mb-5 flex flex-wrap gap-1.5">
          <FilterChip active={!trigger} onClick={() => setTrigger("")}>
            All reasons
          </FilterChip>
          {triggers.map((t) => (
            <FilterChip key={t} active={trigger === t} onClick={() => setTrigger(t)}>
              {triggerLabel(t)}
            </FilterChip>
          ))}
        </div>
      )}

      {loading && (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      )}

      {error && <ErrorState message={error} onRetry={refresh} />}

      {failed && (
        <div className="mb-4 rounded-lg border border-[var(--critical)] bg-[color-mix(in_srgb,var(--critical)_10%,transparent)] px-3.5 py-2.5 text-[13px] text-[var(--ink)]">
          {failed} — nothing was recorded, so the recommendation is still here.
        </div>
      )}

      {data && !loading && data.opportunities.length === 0 && (
        decided > 0 ? (
          /* Every recommendation has been ruled on. That is the day finished,
             not an empty screen, and it must not read as one. */
          <Card className="text-center">
            <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-full bg-[color-mix(in_srgb,var(--good)_16%,transparent)]">
              <Check size={19} className="text-[var(--good)]" />
            </div>
            <h2 className="mt-3 text-[17px] font-semibold">You&apos;re done for today</h2>
            <p className="mx-auto mt-1.5 max-w-[440px] text-[13.5px] leading-relaxed text-[var(--ink-2)]">
              All {data.prioritized_today} of today&apos;s recommendations have a decision.
              RevenueOS will select the next list on the following run.
            </p>
            <Link href="/actions" className="mt-4 inline-block">
              <Button variant="primary">View Action Center</Button>
            </Link>
          </Card>
        ) : (
          <EmptyState
            title="Nothing meets the bar today"
            body={
              data.detected > 0
                ? "RevenueOS found weaker signals but none strong enough to interrupt someone over. A short list is the honest answer — check back tomorrow."
                : "Import your customer and transaction exports to start seeing opportunities."
            }
          />
        )
      )}

      {data && !loading && data.opportunities.length > 0 && data.held_back > 0 && (
        <p className="mb-4 text-[12px] text-[var(--muted)]">
          {data.held_back} further {data.held_back === 1 ? "opportunity" : "opportunities"} cleared
          the bar but sit beyond a day&apos;s capacity. They stay detected and are
          reconsidered on the next run.
        </p>
      )}

      {drafting.length > 0 && (
        <div className="mb-5 space-y-3">
          <div className="eyebrow">Ready to contact</div>
          {drafting.map((opp) => (
            <OutreachPanel
              key={opp.id}
              opportunityId={opp.id}
              customerName={opp.customer_name}
              onDone={() => setDrafting((prev) => prev.filter((o) => o.id !== opp.id))}
              onDismiss={() => setDrafting((prev) => prev.filter((o) => o.id !== opp.id))}
            />
          ))}
        </div>
      )}

      <div className="space-y-3">
        {data?.opportunities.map((opp) => (
          <OpportunityCard
            key={opp.id}
            opp={opp}
            busy={pending.has(opp.id)}
            onAct={(status, decline) => act(opp, status, decline)}
          />
        ))}
      </div>

      {data && data.suppressed_count > 0 && (
        <p className="mt-6 flex items-center gap-2 text-[12px] text-[var(--ink-3)]">
          <ShieldOff size={13} />
          {data.suppressed_count} further{" "}
          {data.suppressed_count === 1 ? "customer was" : "customers were"} held back — no
          permitted contact channel, or contacted too recently.
        </p>
      )}
    </Page>
  );
}

function OpportunityCard({
  opp,
  busy,
  onAct,
}: {
  opp: Opportunity;
  busy?: boolean;
  onAct: (status: string, decline?: Decline) => Promise<void>;
}) {
  const [showWhy, setShowWhy] = useState(false);

  return (
    <Card className={busy ? "pointer-events-none opacity-60 transition-opacity" : undefined}>
      {/* On a wide screen the card reads left to right in the order a
          salesperson thinks — who and why now, then what to show them, then
          what it is worth and the decision. Below xl it falls back to the
          original stack; nothing is hidden at either width, it is the same
          content in a shape that fits the screen it is on. */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)_minmax(210px,0.8fr)] xl:items-start xl:gap-7">
      <div className="min-w-0">
      {/* ---- Who ---- */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/customers/${encodeURIComponent(opp.customer_id)}`}
            className="text-[17px] font-semibold tracking-[-0.01em] hover:underline"
          >
            {opp.customer_name}
          </Link>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {opp.value_tier && <Badge color={valueColor(opp.value_tier)}>{opp.value_tier}</Badge>}
            {opp.lifecycle && (
              <Badge color={lifecycleColor(opp.lifecycle)}>{opp.lifecycle}</Badge>
            )}
            {/* The reason only earns a line when it says something the badges
                do not — "Due · Due to buy" is noise, "Due · New arrival" is not. */}
            {!LIFECYCLE_TRIGGERS.has(opp.trigger) && (
              <span className="text-[11px] text-[var(--ink-3)]">{triggerLabel(opp.trigger)}</span>
            )}
          </div>
        </div>
      </div>

      {/* ---- Why now ---- */}
      <p className="mt-3 text-[14.5px] leading-relaxed text-[var(--ink)]">{opp.why_now}</p>

      {/* ---- The evidence, one click away and never in the way ---- */}
      {/* Sits under the reason it expands on, which is also the shortest
          column — otherwise the card ended in a band of empty space as tall as
          the product panel beside it. */}
      <button
        onClick={() => setShowWhy((v) => !v)}
        className="mt-3 flex items-center gap-1 text-[12px] text-[var(--ink-3)] transition-colors hover:text-[var(--ink-2)]"
      >
        {showWhy ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        {showWhy ? "Hide the detail" : "Why this customer"}
      </button>
      </div>

      {/* ---- What, and why that ---- */}
      <div className="min-w-0 xl:border-l xl:border-[var(--line)] xl:pl-7">
        {opp.product ? (
          <ProductSuggestion product={opp.product} />
        ) : (
          <p className="text-[12.5px] text-[var(--ink-3)]">
            No piece matched well enough to recommend.
          </p>
        )}
      </div>

      <div className="min-w-0 xl:border-l xl:border-[var(--line)] xl:pl-7">
      {/* ---- What it is worth ---- */}
      {opp.influenced_value !== null && (
        <div className="flex items-baseline gap-2" title={EXPECTED_VALUE_HELP}>
          <span className="text-[12px] text-[var(--ink-3)]">{EXPECTED_VALUE}</span>
          <span className="num text-[15px] font-semibold text-[var(--ink)]">
            {money(opp.influenced_value)}
          </span>
          {/* The caveat lives in the tooltip, not on the card. Repeating
              "modelled, not a forecast" beside every figure made the number
              read as a disclaimer rather than a number. */}
          <Info size={12} className="text-[var(--muted)]" aria-hidden />
          <span className="sr-only">{EXPECTED_VALUE_HELP}</span>
        </div>
      )}

      {/* ---- How to act ---- */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4 xl:mt-3 xl:flex-col xl:items-stretch xl:border-t-0 xl:pt-0">
        <p className="text-[13.5px] font-medium text-[var(--ink)]">{opp.action}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="primary" size="sm" disabled={busy} onClick={() => onAct("Approved")}>
            Approve
          </Button>
          <Button size="sm" disabled={busy} onClick={() => onAct("Scheduled")}>
            Schedule
          </Button>
          <NotNowButton disabled={busy} onDecline={(d) => onAct("Ignored", d)} />
        </div>
      </div>

      </div>
      </div>


      {showWhy && (
        <div className="mt-3 space-y-2.5 rounded-lg bg-[var(--raised)] p-4 text-[12px] leading-relaxed text-[var(--ink-2)]">
          {opp.evidence && <p>{opp.evidence}</p>}
          <p>
            <span className="text-[var(--ink-3)]">How the expected value is built: </span>
            {opp.value_basis.charAt(0).toLowerCase() + opp.value_basis.slice(1)}.
          </p>
          <p className="text-[var(--ink-3)]">{opp.probability_basis}.</p>
          {opp.eligibility.channels.length > 0 && (
            <p>
              <span className="text-[var(--ink-3)]">Permitted channels: </span>
              {opp.eligibility.channels.map((c) => c.label).join(", ")}.
            </p>
          )}
          {opp.product?.caveats?.map((c) => (
            <p key={c} className="text-[var(--warning)]">
              {c}
            </p>
          ))}
          {opp.alternatives.length > 0 && (
            <p>
              <span className="text-[var(--ink-3)]">Also worth showing: </span>
              {opp.alternatives.map((a) => a.name).join(", ")}.
            </p>
          )}
        </div>
      )}
    </Card>
  );
}

function ProductSuggestion({ product }: { product: ProductCard }) {
  const reasons = useMemo(() => product.why.slice(0, 3), [product.why]);
  return (
    <div className="mt-3 rounded-lg border border-[var(--line)] bg-[var(--raised)] p-4 xl:mt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="min-w-0">
          <span className="text-[14px] font-medium">{product.name}</span>
          {product.brand && (
            <span className="ml-2 text-[12px] text-[var(--ink-3)]">{product.brand}</span>
          )}
        </div>
        <div className="flex items-center gap-2.5">
          <span className="num text-[14px] font-medium">{money(product.price)}</span>
          <Badge color={matchColor(product.match_pct)}>{product.match_pct}% match</Badge>
        </div>
      </div>
      {reasons.length > 0 && (
        <ul className="mt-2.5 space-y-1">
          {reasons.map((r) => (
            <li key={r} className="text-[12px] leading-snug text-[var(--ink-2)]">
              · {r}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2.5 text-[11px] text-[var(--ink-3)]">{product.availability}</p>
    </div>
  );
}
