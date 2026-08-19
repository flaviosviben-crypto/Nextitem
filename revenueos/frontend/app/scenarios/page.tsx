"use client";

import { useState } from "react";
import { Page, PageHeader } from "@/components/Shell";
import { Button, Card, EstimateNote, SectionTitle, Skeleton, inputClass } from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { money, num, pct } from "@/lib/format";

type Options = { segments: string[]; categories: string[]; risk_classes: string[] };

type Result = Record<string, any> & { assumptions?: string[]; scenario?: string; estimate?: boolean };

export default function ScenarioLabPage() {
  const options = useApi<Options>("/scenarios/options");
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [riskClass, setRiskClass] = useState("");
  const [discount, setDiscount] = useState(15);
  const [segment, setSegment] = useState("");
  const [conversion, setConversion] = useState(12);
  const [category, setCategory] = useState("");
  const [lift, setLift] = useState(25);

  const run = async (path: string, body: unknown) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await api.post<Result>(path, body));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not run this scenario");
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Scenario Lab"
        title="What if"
        subtitle="Model a decision before you make it. Every output is a projection from your own numbers, with its assumptions stated — not a forecast to bank on."
      />

      {error && (
        <Card className="mb-4 border-[color-mix(in_srgb,var(--critical)_40%,transparent)]">
          <p className="text-[13px] text-[var(--critical)]">{error}</p>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-[1fr_1.15fr]">
        <div className="space-y-4">
          <Card>
            <SectionTitle title="Discount a group of products" hint="What it does to revenue, margin and cover." />
            <div className="space-y-3">
              <label className="block">
                <span className="eyebrow">Products</span>
                <select
                  value={riskClass}
                  onChange={(e) => setRiskClass(e.target.value)}
                  className={`${inputClass} mt-1.5 w-full`}
                >
                  <option value="">Choose a health class…</option>
                  {options.data?.risk_classes.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="eyebrow">Discount: {discount}%</span>
                <input
                  type="range"
                  min={5}
                  max={50}
                  step={5}
                  value={discount}
                  onChange={(e) => setDiscount(Number(e.target.value))}
                  className="mt-2 w-full accent-[var(--accent)]"
                />
              </label>
              <Button
                variant="primary"
                disabled={busy || !riskClass}
                onClick={() => run("/scenarios/discount", { risk_class: riskClass, discount_pct: discount })}
              >
                Model discount
              </Button>
            </div>
          </Card>

          <Card>
            <SectionTitle title="Contact a segment" hint="Expected orders and revenue from outreach." />
            <div className="space-y-3">
              <label className="block">
                <span className="eyebrow">Segment</span>
                <select
                  value={segment}
                  onChange={(e) => setSegment(e.target.value)}
                  className={`${inputClass} mt-1.5 w-full`}
                >
                  <option value="">Choose a segment…</option>
                  {options.data?.segments.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="eyebrow">Assumed conversion: {conversion}%</span>
                <input
                  type="range"
                  min={2}
                  max={40}
                  step={1}
                  value={conversion}
                  onChange={(e) => setConversion(Number(e.target.value))}
                  className="mt-2 w-full accent-[var(--accent)]"
                />
              </label>
              <Button
                variant="primary"
                disabled={busy || !segment}
                onClick={() =>
                  run("/scenarios/outreach", { segment, conversion_rate: conversion / 100 })
                }
              >
                Model outreach
              </Button>
            </div>
          </Card>

          <Card>
            <SectionTitle title="Focus a category" hint="A week of merchandising attention." />
            <div className="space-y-3">
              <label className="block">
                <span className="eyebrow">Category</span>
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className={`${inputClass} mt-1.5 w-full`}
                >
                  <option value="">Choose a category…</option>
                  {options.data?.categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="eyebrow">Assumed lift: {lift}%</span>
                <input
                  type="range"
                  min={5}
                  max={60}
                  step={5}
                  value={lift}
                  onChange={(e) => setLift(Number(e.target.value))}
                  className="mt-2 w-full accent-[var(--accent)]"
                />
              </label>
              <Button
                variant="primary"
                disabled={busy || !category}
                onClick={() => run("/scenarios/category", { category, attention_lift: lift / 100 })}
              >
                Model focus week
              </Button>
            </div>
          </Card>
        </div>

        <Card>
          <SectionTitle title="Projection" hint="Modelled outcome, not a promise." />
          {busy ? (
            <div className="space-y-2">
              {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-6 w-full" />)}
            </div>
          ) : !result ? (
            <p className="py-16 text-center text-[13px] text-[var(--ink-3)]">
              Choose a scenario on the left to see its projected effect.
            </p>
          ) : (
            <div className="fade-in">
              <p className="mb-4 text-[14px] font-medium">{result.scenario}</p>
              <div className="space-y-2 text-[13px]">
                {Object.entries(result)
                  .filter(
                    ([key]) =>
                      !["scenario", "assumptions", "estimate", "error"].includes(key),
                  )
                  .map(([key, value]) => (
                    <div key={key} className="flex items-baseline justify-between gap-4 border-b border-[var(--line)] pb-2">
                      <span className="text-[var(--ink-2)]">{key.replace(/_/g, " ")}</span>
                      <span className="num text-right font-medium">{formatValue(key, value)}</span>
                    </div>
                  ))}
              </div>
              {result.assumptions && (
                <div className="mt-5 rounded-lg border border-dashed border-[var(--line)] p-3.5">
                  <div className="eyebrow mb-2">Assumptions</div>
                  <ul className="space-y-1.5">
                    {result.assumptions.map((a: string, i: number) => (
                      <li key={i} className="text-[12px] leading-relaxed text-[var(--ink-2)]">
                        {a}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <EstimateNote>
                These figures are projections from your historical data under the assumptions
                above. Treat them as a comparison between options, not a forecast.
              </EstimateNote>
            </div>
          )}
        </Card>
      </div>
    </Page>
  );
}

function formatValue(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (/revenue|margin|value|delta|basket/i.test(key)) return money(value);
    if (/conversion|rate/i.test(key)) return pct(value);
    return num(value, Number.isInteger(value) ? 0 : 1);
  }
  return String(value);
}
