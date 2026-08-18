"use client";

import Link from "next/link";
import { useState } from "react";
import { Check, Copy, Megaphone, Users } from "lucide-react";
import { post, useApi } from "@/lib/api";
import { count, isKnown, money, percent } from "@/lib/format";
import { SEGMENT_TONE } from "@/lib/theme";
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

type Template = {
  key: string;
  name: string;
  description: string;
  tone: string;
};

type Campaign = {
  id: string;
  name: string;
  audienceSize: number;
  selectionCriteria: string[];
  projection: {
    available: boolean;
    expectedRevenue: number | null;
    expectedOrders: number | null;
    avgBasket: number | null;
    avgConversion: number | null;
    assumptions: string[];
    confidence: string;
  };
  message: string;
  messageMode: string;
  products: { productId: string; name: string; brand: string; price: number | null; status: string }[];
  audience: {
    customerId: string;
    name: string;
    segment: string | null;
    totalSpend: number | null;
    daysOverdue: number | null;
    hasEmail: boolean;
    hasPhone: boolean;
    recommended: { productId: string; name: string; matchPct: number }[];
  }[];
};

export default function CampaignsPage() {
  const { data: templates } = useApi<{ templates: Template[] }>("/campaigns/templates");
  const { data: workspace } = useApi<{ hasData: boolean }>("/workspace");
  const [selected, setSelected] = useState<string>("");
  const [language, setLanguage] = useState("English");
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const build = async (templateKey: string) => {
    setSelected(templateKey);
    setBusy(true);
    setError(null);
    try {
      setCampaign(await post<Campaign>("/campaigns/build", { template: templateKey, language }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not build that campaign.");
      setCampaign(null);
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    if (!campaign) return;
    await navigator.clipboard.writeText(campaign.message);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  if (!workspace?.hasData) {
    return (
      <div>
        <PageHeader eyebrow="Outreach" title="Campaigns" />
        <EmptyState
          icon={<Megaphone className="size-5" />}
          title="No data loaded"
          description="Campaigns are built from your real customer base."
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
        eyebrow="Outreach"
        title="Campaigns"
        subtitle="Pick a play. RevenueOS builds the audience from your data, estimates what it is worth, picks the products, and drafts the message."
        action={
          <Select value={language} onChange={(event) => setLanguage(event.target.value)}>
            <option>English</option>
            <option>Italian</option>
            <option>French</option>
            <option>German</option>
            <option>Spanish</option>
          </Select>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {(templates?.templates ?? []).map((template) => (
          <Card
            key={template.key}
            interactive
            onClick={() => build(template.key)}
            className={
              selected === template.key ? "border-[var(--color-accent-line)]" : undefined
            }
          >
            <h3 className="text-[14px] font-semibold">{template.name}</h3>
            <p className="mt-1.5 text-[12.5px] leading-relaxed text-[var(--color-ink-3)]">
              {template.description}
            </p>
            <div className="mt-3.5">
              <Button
                size="sm"
                variant={selected === template.key ? "primary" : "secondary"}
                loading={busy && selected === template.key}
              >
                {busy && selected === template.key ? "Building…" : "Build campaign"}
              </Button>
            </div>
          </Card>
        ))}
      </div>

      {error ? <Note tone="danger">{error}</Note> : null}
      {busy && !campaign ? <Skeleton className="h-64 w-full" /> : null}

      {campaign ? (
        <div className="animate-fade-up space-y-4">
          <Card>
            <SectionHeader
              eyebrow="Campaign"
              title={campaign.name}
              subtitle={`${count(campaign.audienceSize)} customers selected`}
            />
            <div className="grid grid-cols-2 gap-6 sm:grid-cols-4">
              <Stat label="Audience">{count(campaign.audienceSize)}</Stat>
              <Stat label="Projected revenue" hint="estimate, not a forecast">
                <Value known={isKnown(campaign.projection.expectedRevenue)}>
                  {money(campaign.projection.expectedRevenue)}
                </Value>
              </Stat>
              <Stat label="Expected orders">
                <Value known={isKnown(campaign.projection.expectedOrders)}>
                  {campaign.projection.expectedOrders?.toFixed(0)}
                </Value>
              </Stat>
              <Stat label="Avg conversion">
                <Value known={isKnown(campaign.projection.avgConversion)}>
                  {percent(campaign.projection.avgConversion)}
                </Value>
              </Stat>
            </div>

            <div className="mt-5 border-t border-[var(--color-line)] pt-4">
              <div className="eyebrow mb-2">Why these customers</div>
              <div className="flex flex-wrap gap-1.5">
                {campaign.selectionCriteria.map((criterion) => (
                  <Badge key={criterion} size="sm">
                    {criterion}
                  </Badge>
                ))}
              </div>
            </div>

            {campaign.projection.assumptions?.length ? (
              <p className="mt-3 text-[11px] leading-relaxed text-[var(--color-ink-4)]">
                Estimate assumptions: {campaign.projection.assumptions.join(" ")}
              </p>
            ) : null}
          </Card>

          <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
            <Card>
              <SectionHeader
                title="Draft message"
                subtitle={
                  campaign.messageMode === "ai"
                    ? "Written by Claude from the campaign brief."
                    : "Composed from the campaign brief."
                }
                action={
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
                    onClick={copy}
                  >
                    {copied ? "Copied" : "Copy"}
                  </Button>
                }
              />
              <pre className="whitespace-pre-wrap rounded-[10px] border border-[var(--color-line)] bg-[var(--color-surface-2)] p-4 font-sans text-[12.5px] leading-relaxed text-[var(--color-ink-2)]">
                {campaign.message}
              </pre>
              <Note tone="info">
                RevenueOS does not send anything. Copy this into your own email or WhatsApp tool —
                sending requires an integration you configure yourself.
              </Note>

              {campaign.products.length ? (
                <div className="mt-4">
                  <div className="eyebrow mb-2">Featured products</div>
                  <div className="space-y-1.5">
                    {campaign.products.slice(0, 6).map((product) => (
                      <Link
                        key={product.productId}
                        href={`/inventory/${product.productId}`}
                        className="flex items-center justify-between gap-3 rounded-[9px] border border-[var(--color-line)] px-3 py-2 text-[12.5px] transition-colors hover:border-[var(--color-line-strong)]"
                      >
                        <span className="min-w-0 flex-1 truncate">{product.name}</span>
                        <span className="num shrink-0 text-[var(--color-ink-4)]">
                          {money(product.price)}
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              ) : null}
            </Card>

            <Card padded={false}>
              <div className="p-5 pb-3">
                <SectionHeader
                  title="Audience"
                  subtitle="Each with the piece RevenueOS would lead with for them."
                />
              </div>
              <div className="max-h-[520px] overflow-y-auto px-5 pb-5">
                <div className="space-y-1.5">
                  {campaign.audience.map((customer) => (
                    <Link
                      key={customer.customerId}
                      href={`/customers/${customer.customerId}`}
                      className="block rounded-[10px] border border-[var(--color-line)] px-3 py-2.5 transition-colors hover:border-[var(--color-line-strong)]"
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium">
                          {customer.name}
                        </span>
                        {customer.segment ? (
                          <Badge size="sm" tone={SEGMENT_TONE[customer.segment] ?? "neutral"}>
                            {customer.segment}
                          </Badge>
                        ) : null}
                        <span className="num shrink-0 text-[11.5px] text-[var(--color-ink-4)]">
                          {money(customer.totalSpend, { compact: true })}
                        </span>
                      </div>
                      {customer.recommended?.length ? (
                        <div className="mt-1 flex items-center gap-2 text-[11px] text-[var(--color-ink-4)]">
                          <span className="truncate">→ {customer.recommended[0].name}</span>
                          <span className="num shrink-0 text-[var(--color-accent)]">
                            {customer.recommended[0].matchPct}%
                          </span>
                        </div>
                      ) : null}
                      {!customer.hasEmail && !customer.hasPhone ? (
                        <div className="mt-1 text-[10.5px] text-[var(--color-warning)]">
                          No contact details on file
                        </div>
                      ) : null}
                    </Link>
                  ))}
                </div>
                {campaign.audienceSize > campaign.audience.length ? (
                  <p className="mt-3 text-center text-[11.5px] text-[var(--color-ink-4)]">
                    Showing {campaign.audience.length} of {count(campaign.audienceSize)}.
                  </p>
                ) : null}
              </div>
            </Card>
          </div>
        </div>
      ) : null}
    </div>
  );
}
