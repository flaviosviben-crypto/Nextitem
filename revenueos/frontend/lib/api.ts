"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || body.error || detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T,>(path: string) => request<T>(path),
  post: <T,>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T,>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T,>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T,>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

/** Fetch-on-mount with loading/error state and a manual refresh. */
export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState<string | null>(null);
  const latest = useRef(0);

  const load = useCallback(async () => {
    if (!path) {
      setLoading(false);
      return;
    }
    const ticket = ++latest.current;
    setLoading(true);
    setError(null);
    try {
      const result = await api.get<T>(path);
      if (ticket === latest.current) setData(result);
    } catch (err) {
      // Ignore results from a superseded request; only the newest may report.
      if (ticket === latest.current) {
        setError(err instanceof Error ? err.message : "Request failed");
      }
    } finally {
      if (ticket === latest.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, loading, error, refresh: load, setData };
}

// ------------------------------------------------------------------ types ---

export type ValueTier = "VIP" | "Promising" | "Standard";
export type Lifecycle = "Active" | "Due" | "At Risk" | "Lost";

export type Channel = { key: string; label: string; verb: string };

export type Eligibility = {
  status: "Actionable" | "Suppressed";
  reason: string | null;
  reason_code: string | null;
  channels: Channel[];
  preferred_channel: Channel | null;
  blocked: string[];
  days_since_contact: number | null;
};

export type MatchSignal = {
  name: string;
  label: string;
  score: number;
  weight: number;
  impact: number;
  reason: string;
  applicable: boolean;
};

export type ProductCard = {
  sku: string;
  name: string;
  category: string | null;
  brand: string | null;
  price: number | null;
  match_pct: number;
  why: string[];
  caveats: string[];
  missing_signals: string[];
  match_confidence: string;
  availability: string;
  stock: number | null;
  risk_class: string | null;
};

export type Opportunity = {
  id: string;
  customer_id: string;
  customer_name: string;
  value_tier: ValueTier | null;
  lifecycle: Lifecycle | null;
  segment: string | null;
  trigger: string;
  headline: string;
  why_now: string;
  evidence: string | null;
  product: ProductCard | null;
  alternatives: ProductCard[];
  action: string;
  eligibility: Eligibility;
  contactable: boolean;
  basket_value: number | null;
  influenced_value: number | null;
  incremental_value: number | null;
  value_basis: string;
  probability: number;
  probability_basis: string;
  priority: number;
  data_confidence: string | null;
  cycle_confidence: string | null;
};

export type OpportunityFeed = {
  opportunities: Opportunity[];
  shown: number;
  total_detected: number;
  suppressed: Opportunity[];
  suppressed_count: number;
  influenced_value: number;
  incremental_value: number;
  triggers: string[];
};

export type ActionRow = {
  id: string;
  customer_id: string;
  customer_name: string;
  value_tier: ValueTier | null;
  lifecycle: Lifecycle | null;
  trigger: string;
  reason: string;
  product: string | null;
  product_sku: string | null;
  match_pct: number | null;
  channel: string | null;
  contactable: boolean;
  influenced_value: number | null;
  incremental_value: number | null;
  realised_value?: number | null;
  priority: number;
  status: string;
  note: string | null;
  created_at: string;
  updated_at: string | null;
};

export type ActionCenter = {
  rows: ActionRow[];
  counts: Record<string, number>;
  total: number;
  statuses: string[];
  open: number;
  closed: number;
  converted_value: number;
  converted_value_basis: string;
};

export type Overview = {
  loaded: boolean;
  today?: {
    opportunities: number;
    note: string;
    influenced_value: number;
    value_basis: string;
    top: {
      id: string;
      customer_id: string;
      customer_name: string;
      value_tier: ValueTier | null;
      lifecycle: Lifecycle | null;
      headline: string;
      why_now: string;
      product: string | null;
      match_pct: number | null;
      channel: string | null;
    }[];
  };
  this_month?: {
    customers_contacted: number | null;
    conversions: number | null;
    conversion_rate: number | null;
    influenced_revenue: number | null;
    estimated_incremental_revenue: number | null;
  };
  base?: {
    customers: number | null;
    value: { tier: string; customers: number; total_spend: number; meaning: string }[];
    lifecycle: { stage: string; customers: number; meaning: string }[];
  };
  data_health?: number;
  compliance?: {
    actionable: number;
    suppressed: number;
    suppressed_by_reason: Record<string, number>;
    frequency_cap_days: number;
  };
  counts?: { customers: number; transactions: number; products: number };
};

export type Performance = {
  loaded: boolean;
  window_days: number;
  opportunities_generated: number;
  customers_contacted: number;
  conversions: number;
  ignored: number;
  open: number;
  untouched: number;
  conversion_rate: number | null;
  contacted_revenue: number;
  contacted_revenue_basis: string;
  influenced_revenue: number;
  influenced_revenue_basis: string;
  recorded_sales: number;
  recorded_sales_count: number;
  recorded_sales_basis: string;
  estimated_incremental_revenue: number;
  incremental_revenue_basis: string;
  measurement_caveat: string;
  attribution_note: string;
  by_trigger: {
    trigger: string;
    generated: number;
    contacted: number;
    converted: number;
    conversion_rate: number | null;
  }[];
};

export type CustomerRow = {
  customer_id: string;
  name: string;
  value_tier: ValueTier | null;
  lifecycle: Lifecycle | null;
  segment: string | null;
  value_tone?: string;
  lifecycle_tone?: string;
  customer_score: number | null;
  total_spend: number | null;
  order_count: number | null;
  avg_order_value: number | null;
  last_purchase: string | null;
  recency_days: number | null;
  cycle_days: number | null;
  cycle_position: number | null;
  cycle_confidence: string | null;
  store: string | null;
  top_category: string | null;
  contactable: boolean;
  suppression_reason: string | null;
  data_confidence: string;
  crm_record?: boolean;
  potential_annual_value: number | null;
  recommended_product: { sku: string; name: string; match_pct: number; price: number | null } | null;
};

export type Match = {
  sku: string;
  product_name: string;
  category: string | null;
  brand: string | null;
  price: number | null;
  stock: number | null;
  risk_class: string | null;
  match_pct: number;
  score: number;
  data_confidence: string;
  coverage: number;
  signals: MatchSignal[];
  why: string[];
  caveats: string[];
  missing_signals: string[];
  expected_value?: number | null;
};

export type CustomerDetail = {
  profile: Record<string, any>;
  why_contact: {
    headline: string;
    why_now: string | null;
    evidence: string | null;
    action: string;
    product: ProductCard | null;
    contactable: boolean;
  };
  value: {
    tier: ValueTier | null;
    basis: string | null;
    signals: string[];
    percentile: number | null;
  };
  lifecycle: {
    stage: Lifecycle | null;
    basis: string | null;
    confidence: string | null;
    cycle_days: number | null;
    cycle_basis: string | null;
    cycle_confidence: string | null;
    cycle_position: number | null;
  };
  eligibility: Eligibility | null;
  recommendations: Match[];
  timeline: {
    date: string | null;
    transaction_id: string | null;
    product: string | null;
    sku: string | null;
    category: string | null;
    brand: string | null;
    color: string | null;
    size: string | null;
    quantity: number | null;
    amount: number | null;
    discount: number | null;
    store: string | null;
  }[];
};

export type Summary = {
  loaded: boolean;
  source?: string;
  revenue_opportunity?: number;
  opportunities?: number;
  actionable_opportunities?: number;
  customers_to_contact?: number;
  data_health?: number;
  counts?: { customers: number; transactions: number; products: number };
  customers?: Record<string, number | null>;
  segments?: {
    value: { tier: string; customers: number; total_spend: number; meaning: string }[];
    lifecycle: { stage: string; customers: number; meaning: string }[];
    matrix: { value_tier: string; lifecycle: string; customers: number }[];
  };
};

export type Quality = {
  score: number;
  grade: string;
  summary: string;
  findings: { severity: string; title: string; detail: string; affected: number }[];
  capabilities: { name: string; available: boolean; reason: string; unlock: string }[];
  completeness: Record<string, { rows: number; fields: Record<string, number> }>;
};

export type ColumnMapping = {
  header: string;
  field: string | null;
  label: string | null;
  confidence: number;
  reason: string;
  status: "confident" | "review" | "unmapped";
  alternatives: { field: string; label: string; confidence: number }[];
  profile: Record<string, unknown>;
};
