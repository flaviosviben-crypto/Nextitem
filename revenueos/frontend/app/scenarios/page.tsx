"use client";

import Link from "next/link";
import { useState } from "react";
import { FlaskConical, TrendingDown, TrendingUp } from "lucide-react";
import { post, useApi } from "@/lib/api";
import { count, cx, isKnown, money, percent } from "@/lib/format";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  Note,
  PageHeader,
  SectionHeader,
  Select,
  Skeleton,
  Value,
} from "@/components/ui";
import { Stat } from "@/components/data";

type Presets = {
  presets: { key: string; name: string; question: string }[];
  categories: string[];
  statuses: string[];
  segments: string[];
};

type Result = {
  available?: boolean;
  reason?: string;
  type: string;
  scenario: string;
  horizonDays?: number;
  products?: number;
  baselineUnits?: number;
  projectedUnits?: number;
  incrementalUnits?: number;
  baselineRevenue?: number;
  projectedRevenue?: number;
  revenueDelta?: number;
  baselineMargin?: number | null;
  projectedMargin?: number | null;
  marginDelta?: number | null;
  audience?: number;
  contacted?: number;
  expectedOrders?: number;
  expectedRevenue?: number;
  avgBasket?: number;
  avgConversion?: number;
  stockValue?: number | null;
  skus?: number;
  assumptions: string[];
  confidence: string;
  explanation: string;
  explanationMode: string;
  isEstimate: boolean;
};

export default function ScenariosPage() {
  const { data: presets } = useApi<Presets>("/scenarios/presets");
  const { data: workspace } = useApi<{ hasData: boolean }>("/workspace");

  const [type, setType] = useState("discount");
  const [discountPct, setDiscountPct] = useState(15);
  const [status, setStatus] = useState("At Risk");
  const [category, setCategory] = useState("");
  const [segment, setSegment] = useState("");
  const [contactRate, setContactRate] = useState(1);
  const [upliftPct, setUpliftPct] = useState(20);
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = { type };
      if (type === "discount") {
        payload.discountPct = discountPct;
        if (status) payload.status = status;
        if (category) payload.category = category;
      } else if (type === "outreach") {
        if (segment) payload.segment = segment;
        payload.contactRate = contactRate;
      } else {
        payload.category = category || presets?.categories[0];
        payload.upliftPct = upliftPct;
      }
      const response = await post<Result>("/scenarios/run", payload);
      if (response.available === false) {
        setError(response.reason ?? "That scenario cannot be modelled with this data.");
        setResult(null);
      } else {
        setResult(response);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not run that scenario.");
    } finally {
      setBusy(false);
    }
  };

  if (!workspace?.hasData) {
    return (
      <div>
        <PageHeader eyebrow="What-if modelling" title="Scenario Lab" />
        <EmptyState
          icon={<FlaskConical className="size-5" />}
          title="No data loaded"
          description="Scenarios are modelled from your own sales velocity and customer behaviour."
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
        eyebrow="What-if modelling"
        title="Scenario Lab"
        subtitle="Model a move before you make it. Everything here is a projection from an explicit model — the assumptions are always shown."
      />

      <Card>
        <SectionHeader title="Build a scenario" />
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="eyebrow mb-1.5 block">Scenario</label>
            <Select value={type} onChange={(event) => setType(event.target.value)}>
              <option value="discount">Apply a discount</option>
              <option value="outreach">Contact a group of customers</option>
              <option value="category_focus">Focus on a category</option>
            </Select>
          </div>

          {type === "discount" ? (
            <>
              <div>
                <label className="eyebrow mb-1.5 block">Discount</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={5}
                    max={60}
                    step={5}
                    value={discountPct}
                    onChange={(event) => setDiscountPct(Number(event.target.value))}
                    className="w-36 accent-[var(--color-accent)]"
                  />
                  <span className="num w-10 text-[13px] font-medium">{discountPct}%</span>
                </div>
              </div>
              <div>
                <label className="eyebrow mb-1.5 block">On products with status</label>
                <Select value={status} onChange={(event) => setStatus(event.target.value)}>
                  <option value="">Any status</option>
                  {presets?.statuses.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </Select>
              </div>
              <div>
                <label className="eyebrow mb-1.5 block">Category</label>
                <Select value={category} onChange={(event) => setCategory(event.target.value)}>
                  <option value="">All categories</option>
                  {presets?.categories.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </Select>
              </div>
            </>
          ) : type === "outreach" ? (
            <>
              <div>
                <label className="eyebrow mb-1.5 block">Segment</label>
                <Select value={segment} onChange={(event) => setSegment(event.target.value)}>
                  <option value="">Everyone</option>
                  {presets?.segments.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </Select>
              </div>
              <div>
                <label className="eyebrow mb-1.5 block">Share contacted</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={10}
                    max={100}
                    step={10}
                    value={contactRate * 100}
                    onChange={(event) => setContactRate(Number(event.target.value) / 100)}
                    className="w-36 accent-[var(--color-accent)]"
                  />
                  <span className="num w-10 text-[13px] font-medium">
                    {Math.round(contactRate * 100)}%
                  </span>
                </div>
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="eyebrow mb-1.5 block">Category</label>
                <Select value={category} onChange={(event) => setCategory(event.target.value)}>
                  {presets?.categories.map((value) => (
                    <option key={value} value={value}>{value}</option>
                  ))}
                </Select>
              </div>
              <div>
                <label className="eyebrow mb-1.5 block">Assumed uplift</label>
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min={5}
                    max={60}
                    step={5}
                    value={upliftPct}
                    onChange={(event) => setUpliftPct(Number(event.target.value))}
                    className="w-36 accent-[var(--color-accent)]"
                  />
                  <span className="num w-10 text-[13px] font-medium">{upliftPct}%</span>
                </div>
              </div>
            </>
          )}

          <Button variant="primary" onClick={run} loading={busy} className="ml-auto">
            Run scenario
          </Button>
        </div>
      </Card>

      {error ? <Note tone="warning">{error}</Note> : null}
      {busy && !result ? <Skeleton className="h-56 w-full" /> : null}

      {result ? (
        <div className="animate-fade-up space-y-4">
          <Card>
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="eyebrow mb-1">Projection · {result.confidence} confidence</div>
                <h2 className="text-[17px] font-semibold">{result.scenario}</h2>
              </div>
              <Badge tone="info">Estimate, not a measurement</Badge>
            </div>

            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              {result.type === "discount" ? (
                <>
                  <DeltaStat
                    label="Revenue impact"
                    value={result.revenueDelta}
                    baseline={result.baselineRevenue}
                  />
                  <DeltaStat
                    label="Margin impact"
                    value={result.marginDelta ?? null}
                    baseline={result.baselineMargin ?? null}
                  />
                  <Stat label="Units sold" hint={`baseline ${result.baselineUnits?.toFixed(0)}`}>
                    <Value known={isKnown(result.projectedUnits)}>
                      {result.projectedUnits?.toFixed(0)}
                    </Value>
                  </Stat>
                  <Stat label="Stock cleared" hint={`over ${result.horizonDays} days`}>
                    <Value known={isKnown(result.stockValue ?? result.projectedUnits)}>
                      {result.projectedUnits?.toFixed(0)} units
                    </Value>
                  </Stat>
                </>
              ) : result.type === "outreach" ? (
                <>
                  <Stat label="Customers contacted" hint={`from ${count(result.audience)} in the group`}>
                    {count(result.contacted)}
                  </Stat>
                  <Stat label="Expected orders">
                    <Value known={isKnown(result.expectedOrders)}>
                      {result.expectedOrders?.toFixed(0)}
                    </Value>
                  </Stat>
                  <Stat label="Expected revenue">
                    <Value known={isKnown(result.expectedRevenue)}>
                      {money(result.expectedRevenue)}
                    </Value>
                  </Stat>
                  <Stat label="Average conversion">
                    <Value known={isKnown(result.avgConversion)}>
                      {percent(result.avgConversion)}
                    </Value>
                  </Stat>
                </>
              ) : (
                <>
                  <DeltaStat
                    label="Revenue impact"
                    value={result.revenueDelta}
                    baseline={result.baselineRevenue}
                  />
                  <Stat label="Baseline (30d)">
                    <Value known={isKnown(result.baselineRevenue)}>
                      {money(result.baselineRevenue)}
                    </Value>
                  </Stat>
                  <Stat label="Projected (30d)">
                    <Value known={isKnown(result.projectedRevenue)}>
                      {money(result.projectedRevenue)}
                    </Value>
                  </Stat>
                  <Stat label="SKUs in category">{count(result.skus)}</Stat>
                </>
              )}
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-[1.2fr_1fr]">
            <Card>
              <SectionHeader
                title="What this means"
                subtitle={
                  result.explanationMode === "ai"
                    ? "Interpreted by Claude from the model output."
                    : "Composed from the model output."
                }
              />
              <p className="text-[13px] leading-relaxed text-[var(--color-ink-2)]">
                {result.explanation}
              </p>
            </Card>
            <Card>
              <SectionHeader title="Model assumptions" />
              <ul className="space-y-2">
                {result.assumptions.map((assumption, index) => (
                  <li
                    key={index}
                    className="flex gap-2 text-[12px] leading-relaxed text-[var(--color-ink-3)]"
                  >
                    <span className="mt-[7px] size-1 shrink-0 rounded-full bg-[var(--color-ink-4)]" />
                    {assumption}
                  </li>
                ))}
              </ul>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function DeltaStat({
  label,
  value,
  baseline,
}: {
  label: string;
  value: number | null | undefined;
  baseline: number | null | undefined;
}) {
  const known = isKnown(value);
  const positive = known && value >= 0;
  return (
    <div>
      <div className="eyebrow mb-1.5">{label}</div>
      <div
        className="num flex items-center gap-1.5 text-[16px] font-semibold leading-none"
        style={{
          color: known
            ? positive
              ? "var(--color-positive)"
              : "var(--color-danger)"
            : undefined,
        }}
      >
        {known ? (
          <>
            {positive ? (
              <TrendingUp className="size-3.5" />
            ) : (
              <TrendingDown className="size-3.5" />
            )}
            {positive ? "+" : ""}
            {money(value)}
          </>
        ) : (
          <Value known={false}>{null}</Value>
        )}
      </div>
      {isKnown(baseline) ? (
        <div className="mt-1.5 text-[11.5px] text-[var(--color-ink-4)]">
          baseline {money(baseline)}
        </div>
      ) : null}
    </div>
  );
}
