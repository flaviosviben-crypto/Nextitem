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
import { ChevronDown, ChevronUp, ShieldOff } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  Skeleton,
  Value,
} from "@/components/ui";
import { api, useApi, type Opportunity, type OpportunityFeed, type ProductCard } from "@/lib/api";
import { lifecycleColor, matchColor, money, triggerLabel, valueColor } from "@/lib/format";

// Triggers whose meaning is already carried by the lifecycle badge beside them.
const LIFECYCLE_TRIGGERS = new Set(["due", "at_risk", "win_back"]);

export default function OpportunitiesPage() {
  const [trigger, setTrigger] = useState("");
  const { data, loading, error, refresh } = useApi<OpportunityFeed>(
    `/opportunities?trigger=${encodeURIComponent(trigger)}`,
    [trigger],
  );
  const [handled, setHandled] = useState<Record<string, string>>({});

  const act = async (opp: Opportunity, status: string) => {
    setHandled((prev) => ({ ...prev, [opp.id]: status }));
    try {
      await api.patch(`/actions/${encodeURIComponent(opp.id)}`, { status });
    } catch {
      setHandled((prev) => {
        const next = { ...prev };
        delete next[opp.id];
        return next;
      });
    }
  };

  const triggers = data?.triggers || [];

  return (
    <Page>
      <PageHeader
        eyebrow="Today"
        title="Today's Opportunities"
        subtitle={
          data
            ? `${data.shown} ${data.shown === 1 ? "customer" : "customers"} worth a conversation today.`
            : "Who to contact today, and what to say."
        }
        actions={
          data && data.influenced_value > 0 ? (
            <div className="text-right">
              <div className="eyebrow">If today's list converts</div>
              <div className="num text-[18px] font-semibold">{money(data.influenced_value)}</div>
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

      {data && !loading && data.opportunities.length === 0 && (
        <EmptyState
          title="Nothing meets the bar today"
          body={
            data.total_detected > 0
              ? "RevenueOS found weaker signals but none strong enough to interrupt someone over. A short list is the honest answer — check back tomorrow."
              : "Import your customer and transaction exports to start seeing opportunities."
          }
        />
      )}

      <div className="space-y-3">
        {data?.opportunities.map((opp) => (
          <OpportunityCard
            key={opp.id}
            opp={opp}
            handledAs={handled[opp.id]}
            onAct={(status) => act(opp, status)}
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

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={
        active
          ? "rounded-full border border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_14%,transparent)] px-3 py-1 text-[12px] font-medium text-[var(--ink)]"
          : "rounded-full border border-[var(--line)] px-3 py-1 text-[12px] text-[var(--ink-2)] transition-colors hover:border-[var(--line-strong)]"
      }
    >
      {children}
    </button>
  );
}

function OpportunityCard({
  opp,
  handledAs,
  onAct,
}: {
  opp: Opportunity;
  handledAs?: string;
  onAct: (status: string) => void;
}) {
  const [showWhy, setShowWhy] = useState(false);

  return (
    <Card className={handledAs ? "opacity-60 transition-opacity" : undefined}>
      {/* ---- Who ---- */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            href={`/customers/${encodeURIComponent(opp.customer_id)}`}
            className="text-[16px] font-semibold tracking-[-0.01em] hover:underline"
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
        {handledAs && <Badge color="var(--good)">{handledAs}</Badge>}
      </div>

      {/* ---- Why now ---- */}
      <p className="mt-3 text-[14px] leading-relaxed text-[var(--ink)]">{opp.why_now}</p>

      {/* ---- What, and why that ---- */}
      {opp.product && <ProductSuggestion product={opp.product} />}

      {/* ---- How to act ---- */}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[var(--line)] pt-4">
        <p className="text-[13px] font-medium text-[var(--ink)]">{opp.action}</p>
        {!handledAs && (
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" size="sm" onClick={() => onAct("Approved")}>
              Approve
            </Button>
            <Button size="sm" onClick={() => onAct("Scheduled")}>
              Schedule
            </Button>
            <Button size="sm" onClick={() => onAct("Ignored")}>
              Not now
            </Button>
          </div>
        )}
      </div>

      {/* ---- The evidence, one click away and never in the way ---- */}
      <button
        onClick={() => setShowWhy((v) => !v)}
        className="mt-3 flex items-center gap-1 text-[12px] text-[var(--ink-3)] transition-colors hover:text-[var(--ink-2)]"
      >
        {showWhy ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        {showWhy ? "Hide the detail" : "Why this customer, and what it's worth"}
      </button>

      {showWhy && (
        <div className="mt-3 space-y-2.5 rounded-lg bg-[var(--raised)] p-4 text-[12px] leading-relaxed text-[var(--ink-2)]">
          {opp.evidence && <p>{opp.evidence}</p>}
          <p>
            <span className="text-[var(--ink-3)]">If this converts: </span>
            <Value>{money(opp.influenced_value)}</Value> —{" "}
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
    <div className="mt-3 rounded-lg border border-[var(--line)] bg-[var(--raised)] p-4">
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
