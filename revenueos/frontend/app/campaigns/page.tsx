"use client";

import Link from "next/link";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { Page, PageHeader } from "@/components/Shell";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  EstimateNote,
  SectionTitle,
  Skeleton,
  Td,
  Th,
  Value,
} from "@/components/ui";
import { api, useApi } from "@/lib/api";
import { matchColor, money, num } from "@/lib/format";

type Template = { id: string; name: string; goal: string; criteria: string };

type Campaign = {
  id: string;
  name: string;
  goal: string;
  criteria: string;
  audience_size: number;
  contactable: number;
  estimated_value: number;
  rationale?: string;
  message?: string | null;
  engine?: string;
  note?: string;
  audience: {
    customer_id: string;
    name: string;
    segment: string | null;
    total_spend: number | null;
    contactable: boolean;
    product: { sku: string; name: string; match_pct: number; price: number | null } | null;
    expected_value: number | null;
  }[];
  products: { sku: string; name: string; price: number | null; stock: number | null }[];
};

export default function CampaignsPage() {
  const templates = useApi<{ templates: Template[] }>("/campaigns/templates");
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const build = async (template: Template) => {
    setBusy(template.id);
    setError(null);
    try {
      const result = await api.post<Campaign>("/campaigns/build", {
        template: template.id,
        limit: 40,
        contactable_only: true,
      });
      setCampaign(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not build this campaign");
    } finally {
      setBusy(null);
    }
  };

  return (
    <Page>
      <PageHeader
        eyebrow="Campaigns"
        title="Campaign builder"
        subtitle="Pick a goal; RevenueOS selects the audience from computed signals, estimates the value, and drafts the outreach. Nothing is sent from here."
      />

      {error && (
        <Card className="mb-4 border-[color-mix(in_srgb,var(--critical)_40%,transparent)]">
          <p className="text-[13px] text-[var(--critical)]">{error}</p>
        </Card>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {templates.loading
          ? [0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[168px] w-full" />)
          : templates.data?.templates.map((t) => (
              <Card key={t.id} className="flex flex-col">
                <h3 className="text-[14px] font-semibold">{t.name}</h3>
                <p className="mt-1.5 flex-1 text-[12.5px] leading-relaxed text-[var(--ink-2)]">
                  {t.goal}
                </p>
                <p className="mt-2.5 text-[11.5px] leading-snug text-[var(--ink-3)]">{t.criteria}</p>
                <Button
                  className="mt-4 w-full"
                  variant={campaign?.id === t.id ? "primary" : "secondary"}
                  disabled={busy !== null}
                  onClick={() => build(t)}
                >
                  {busy === t.id ? "Building…" : "Build audience"}
                </Button>
              </Card>
            ))}
      </div>

      {campaign && (
        <div className="fade-in mt-5 grid gap-5 lg:grid-cols-[1fr_1.6fr]">
          <div className="space-y-5">
            <Card>
              <SectionTitle title={campaign.name} hint={campaign.goal} />
              <div className="grid grid-cols-3 gap-3">
                <Metric label="Audience" value={num(campaign.audience_size)} />
                <Metric label="Contactable" value={num(campaign.contactable)} />
                <Metric label="Est. value" value={money(campaign.estimated_value)} />
              </div>
              <EstimateNote>
                Value is each matched product&apos;s price multiplied by a modelled conversion
                likelihood, and only counts customers with consent on file.
              </EstimateNote>
            </Card>

            {campaign.rationale && (
              <Card>
                <div className="mb-2 flex items-center gap-2">
                  <div className="eyebrow">Why this audience</div>
                  {campaign.engine === "claude" && (
                    <span className="inline-flex items-center gap-1 text-[10.5px] text-[var(--ink-3)]">
                      <Sparkles size={10} /> AI
                    </span>
                  )}
                </div>
                <p className="text-[13px] leading-relaxed text-[var(--ink-2)]">{campaign.rationale}</p>
              </Card>
            )}

            {campaign.message && (
              <Card>
                <div className="eyebrow mb-2">Draft message</div>
                <p className="whitespace-pre-wrap rounded-lg bg-[var(--raised)] p-3.5 text-[13px] leading-relaxed">
                  {campaign.message}
                </p>
                <p className="mt-2.5 text-[11px] text-[var(--ink-3)]">
                  A starting point to adapt per customer — RevenueOS does not send messages.
                </p>
              </Card>
            )}

            {campaign.products.length > 0 && (
              <Card>
                <SectionTitle title="Products in play" />
                <ul className="space-y-2">
                  {campaign.products.map((p) => (
                    <li key={p.sku} className="flex items-center justify-between gap-3 text-[13px]">
                      <Link
                        href={`/inventory/${encodeURIComponent(p.sku)}`}
                        className="truncate hover:text-[var(--accent)]"
                      >
                        {p.name}
                      </Link>
                      <span className="num shrink-0 text-[var(--ink-2)]">{money(p.price)}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>

          <Card padded={false}>
            <div className="p-5 pb-3">
              <SectionTitle
                title="Selected customers"
                hint="Each one matched individually, with their own best product."
              />
            </div>
            {campaign.audience.length === 0 ? (
              <EmptyState
                title="No customers match"
                body={campaign.note || "No customer currently meets this campaign's criteria."}
              />
            ) : (
              <div className="max-h-[560px] overflow-auto">
                <table className="w-full">
                  <thead>
                    <tr>
                      <Th>Customer</Th>
                      <Th>Segment</Th>
                      <Th>Recommended</Th>
                      <Th align="right">Match</Th>
                      <Th align="right">Est. value</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {campaign.audience.map((a) => (
                      <tr key={a.customer_id} className="row-link">
                        <Td>
                          <Link
                            href={`/customers/${encodeURIComponent(a.customer_id)}`}
                            className="font-medium hover:text-[var(--accent)]"
                          >
                            {a.name}
                          </Link>
                        </Td>
                        <Td><span className="text-[var(--ink-2)]">{a.segment || "—"}</span></Td>
                        <Td>
                          <span className="block max-w-[220px] truncate text-[12.5px] text-[var(--ink-2)]">
                            {a.product?.name || "—"}
                          </span>
                        </Td>
                        <Td align="right">
                          {a.product ? (
                            <span style={{ color: matchColor(a.product.match_pct) }}>
                              {a.product.match_pct}%
                            </span>
                          ) : (
                            <Value>{null}</Value>
                          )}
                        </Td>
                        <Td align="right">
                          <Value>{a.expected_value != null ? money(a.expected_value) : null}</Value>
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </Page>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="eyebrow">{label}</div>
      <div className="num mt-1 text-[17px] font-semibold">{value}</div>
    </div>
  );
}
