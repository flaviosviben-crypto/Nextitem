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

export type Summary = {
  loaded: boolean;
  source?: string;
  revenue_opportunity?: number;
  opportunities?: number;
  customers_to_contact?: number;
  high_confidence_matches?: number;
  data_health?: number;
  counts?: { customers: number; transactions: number; products: number };
  customers?: Record<string, number | null>;
  inventory?: Record<string, any>;
  segments?: SegmentRow[];
};

export type SegmentRow = {
  segment: string;
  customers: number;
  share: number;
  total_value: number | null;
  avg_value: number | null;
  annual_potential: number | null;
  tone: string;
  play: string;
};

export type CustomerRow = {
  customer_id: string;
  name: string;
  segment: string | null;
  segment_tone?: string;
  customer_score: number | null;
  total_spend: number | null;
  order_count: number | null;
  avg_order_value: number | null;
  last_purchase: string | null;
  recency_days: number | null;
  cadence_days: number | null;
  overdue_ratio: number | null;
  store: string | null;
  top_category: string | null;
  contactable: boolean;
  data_confidence: string;
  crm_record?: boolean;
  potential_annual_value: number | null;
  recommended_product: { sku: string; name: string; match_pct: number; price: number | null } | null;
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

export type Match = {
  sku: string;
  product_name: string;
  category: string | null;
  brand: string | null;
  price: number | null;
  stock: number | null;
  risk_class: string | null;
  customer_id?: string;
  customer_name?: string;
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

export type Product = {
  sku: string;
  product_name: string;
  category: string | null;
  brand: string | null;
  color: string | null;
  size: string | null;
  season: string | null;
  price: number | null;
  cost: number | null;
  margin_rate: number | null;
  stock: number | null;
  stock_value: number | null;
  days_in_stock: number | null;
  units_sold: number;
  revenue: number;
  buyers: number;
  sell_through: number | null;
  velocity_per_month: number | null;
  weeks_of_cover: number | null;
  risk_score: number | null;
  risk_class: string;
  risk_reason: string;
  risk_drivers: { driver: string; points: number; detail: string }[];
  recommended_action: string;
  last_sold: string | null;
};

export type Opportunity = {
  id: string;
  type: string;
  title: string;
  explanation: string;
  impact: number | null;
  expected_value: number | null;
  impact_basis: string;
  probability: number;
  urgency: number;
  confidence: number;
  score: number;
  action: string;
  entities: {
    type: string;
    id: string;
    name: string;
    detail?: string;
    value?: number | null;
    match_pct?: number | null;
    suggested_product?: string | null;
    contactable?: boolean;
    matched_customers?: number;
    top_match?: string | null;
  }[];
  customer_ids?: string[];
  product_skus?: string[];
};

export type Briefing = {
  loaded: boolean;
  headline?: {
    revenue_opportunity: number | null;
    customers_to_contact: number | null;
    products_at_risk: number | null;
    at_risk_value: number | null;
    high_confidence_matches: number | null;
    data_health: number | null;
  };
  priorities?: (Opportunity & { detail: string; customer_count: number })[];
  contact_today?: {
    customer_id: string;
    name: string;
    segment: string | null;
    reason: string;
    value: number | null;
    contactable: boolean;
    product: { sku: string; name: string; match_pct: number } | null;
  }[];
  counts?: { customers: number; transactions: number; products: number };
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
