"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { isTransientStatus, retryDelay, shouldRetry, sleep } from "./retry";

const BASE = "/api";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

/** A sleeping free-plan API can take about a minute to wake; beyond this it is down. */
const REQUEST_TIMEOUT_MS = 115_000;

/**
 * A timeout signal where the browser supports one.
 *
 * AbortSignal.timeout arrived in Safari 16. Calling it unguarded would throw
 * before the request was even made, turning a nicety into a total outage for
 * anyone on an older browser — the opposite of the robustness intended here.
 */
function timeoutSignal(): AbortSignal | undefined {
  return typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
    ? AbortSignal.timeout(REQUEST_TIMEOUT_MS)
    : undefined;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method || "GET").toUpperCase();
  let res: Response | undefined;

  // A deploy restarts the API for a few seconds and the platform answers 502
  // meanwhile. Retrying a read quietly rides that out; see lib/retry for what
  // is deliberately *not* retried.
  for (let attempt = 1; ; attempt++) {
    let failure: unknown;
    try {
      res = await fetch(`${BASE}${path}`, {
        ...init,
        headers: {
          ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
          ...(init?.headers || {}),
        },
        cache: "no-store",
        signal: timeoutSignal(),
      });
    } catch (err) {
      failure = err;
      res = undefined;
    }

    const status = res?.status;
    if (res && !isTransientStatus(status!)) break;
    if (!shouldRetry({ method, attempt, status })) {
      if (res) break;   // transient, but out of attempts: report the response
      // A timeout or a dropped connection must become a message, never an
      // indefinite wait: the caller has no other way to tell the two apart.
      const timedOut = failure instanceof Error && failure.name === "TimeoutError";
      throw new ApiError(
        timedOut
          ? "The RevenueOS API did not respond in time. If it is hosted on a free plan it may be asleep — wait a moment and try again."
          : "Could not reach the RevenueOS API. Check that the API service is running.",
        0,
      );
    }
    await sleep(retryDelay(attempt));
  }

  if (!res) {
    throw new ApiError("Could not reach the RevenueOS API.", 0);
  }
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
  const json = await res.json();
  // Every screen that reasons about "today" — Overview, Opportunities, Action
  // Center, Customers — reads the same dataset snapshot date from its own
  // response body. Capturing whichever one a page happens to fetch first lets
  // the shell show it once, consistently, without a dedicated request.
  if (json && typeof json === "object" && typeof (json as { as_of?: unknown }).as_of === "string") {
    setAsOf((json as { as_of: string }).as_of);
  }
  return json as T;
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

/** How long a wait may stay silent before the UI owes the user an explanation. */
const SLOW_AFTER_MS = 5_000;

// A tiny store of "is anything taking suspiciously long", so the shell can say
// so once for the whole app. Every screen fetches, and a grid of grey blocks on
// every one of them is indistinguishable from an app that is simply broken.
let slowRequests = 0;
const slowListeners = new Set<() => void>();

function setSlowCount(next: number) {
  slowRequests = Math.max(0, next);
  slowListeners.forEach((fn) => fn());
}

export function subscribeApiSlow(fn: () => void): () => void {
  slowListeners.add(fn);
  return () => slowListeners.delete(fn);
}

export function apiIsSlow(): boolean {
  return slowRequests > 0;
}

// A tiny store of "what date is RevenueOS reasoning against right now", set
// from whichever response happens to carry it first. See the shell for where
// it is shown.
let lastAsOf: string | null = null;
const asOfListeners = new Set<() => void>();

function setAsOf(value: string) {
  if (value === lastAsOf) return;
  lastAsOf = value;
  asOfListeners.forEach((fn) => fn());
}

export function subscribeAsOf(fn: () => void): () => void {
  asOfListeners.add(fn);
  return () => asOfListeners.delete(fn);
}

export function getAsOf(): string | null {
  return lastAsOf;
}

/** Fetch-on-mount with loading/error state and a manual refresh. */
export function useApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(Boolean(path));
  const [error, setError] = useState<string | null>(null);
  // True once a request has run long enough that silence needs explaining.
  const [slow, setSlow] = useState(false);
  const latest = useRef(0);

  const load = useCallback(async () => {
    if (!path) {
      setLoading(false);
      return;
    }
    const ticket = ++latest.current;
    setLoading(true);
    setError(null);
    setSlow(false);
    let counted = false;
    const slowTimer = setTimeout(() => {
      if (ticket === latest.current) {
        setSlow(true);
        counted = true;
        setSlowCount(slowRequests + 1);
      }
    }, SLOW_AFTER_MS);
    try {
      const result = await api.get<T>(path);
      if (ticket === latest.current) setData(result);
    } catch (err) {
      // Ignore results from a superseded request; only the newest may report.
      if (ticket === latest.current) {
        setError(err instanceof Error ? err.message : "Request failed");
      }
    } finally {
      clearTimeout(slowTimer);
      if (counted) setSlowCount(slowRequests - 1);
      if (ticket === latest.current) {
        setLoading(false);
        setSlow(false);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...deps]);

  useEffect(() => {
    load();
  }, [load]);

  return { data, loading, slow, error, refresh: load, setData };
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

/** Detected is the universe the engine found; prioritized is today's workload. */
export type OpportunityCounts = {
  detected: number;
  /** How many were recommended today. Never shrinks when a decision is made. */
  prioritized_today: number;
  /** Still in the inbox. */
  awaiting_decision: number;
  /** Ruled on. awaiting_decision + decisions_made === prioritized_today. */
  decisions_made: number;
  held_back: number;
  not_contactable: number;
  daily_cap: number;
  priority_bar: number;
  /** False when the dataset itself cannot support product-level matching —
   *  distinct from a customer simply having no candidate above threshold. */
  product_matching_available: boolean;
};

/** A ready-to-use draft for one recommendation on one channel. */
export type OutreachDraft = {
  /** "message" is sent as written; "brief" is read before speaking. */
  kind: "message" | "brief";
  channel: string;
  subject: string | null;
  body: string | null;
  /** A natural opening for the advisor to have in mind before a call — the
   *  "Suggested call brief". Null for written channels; use `body` there. */
  brief: string | null;
  talking_points: string[];
  opportunity_id: string;
  customer_id: string;
  customer_name: string;
  /** "template" always works; "claude" means an AI rewrote the tone. */
  engine: "template" | "claude";
  /** False when no phone/email is on file — never offer to open a channel then. */
  contact_available: boolean;
  channel_permitted: boolean;
  deep_link: string | null;
  facts_used: string[];
  channels: { key: string; label: string; verb: string }[];
  blocked: string[];
  eligibility_status: string | null;
  eligibility_reason: string | null;
  status: string;
  contacted_at: string | null;
  sent_message: string | null;
  action: string | null;
  why_now: string | null;
  influenced_value: number | null;
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
  /** 3-5 concrete facts behind the card, honestly scoped to what this
   *  customer's data actually supports. */
  customer_evidence: string[];
  product: ProductCard | null;
  alternatives: ProductCard[];
  action: string;
  eligibility: Eligibility;
  contactable: boolean;
  basket_value: number | null;
  influenced_value: number | null;
  incremental_value: number | null;
  /** What basket_value actually is — traced from the same inputs the
   *  backend used, e.g. "Average of ... and the recommended piece's price." */
  value_basis: string;
  /** Machine-readable version of value_basis: blended | customer_history |
   *  crm_summary | product_price | null. */
  basket_source: string | null;
  probability: number;
  probability_basis: string;
  /** How much to trust the expected-value inputs — High/Medium/Limited. */
  value_confidence: string | null;
  value_confidence_basis: string | null;
  priority: number;
  data_confidence: string | null;
  cycle_confidence: string | null;
};

export type OpportunityFeed = OpportunityCounts & {
  opportunities: Opportunity[];
  shown: number;
  scope: string;
  suppressed: Opportunity[];
  suppressed_count: number;
  influenced_value: number;
  incremental_value: number;
  triggers: string[];
  /** The dataset snapshot date every relative date and lifecycle calculation
   *  here is computed against — never this request's wall-clock time. */
  as_of: string;
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
  /** Why the advisor set it aside. Present only on Ignored rows. */
  decline_reason?: string | null;
  decline_reason_label?: string | null;
  decline_note?: string | null;
  contact_channel?: string | null;
  contacted_at?: string | null;
  created_at: string;
  updated_at: string | null;
};

/** The structured reasons an advisor may give for "Not now". */
export const DECLINE_REASONS: { code: string; label: string }[] = [
  { code: "wrong_product", label: "Wrong product" },
  { code: "contacted_recently", label: "Contacted recently" },
  { code: "low_relevance", label: "Low relevance" },
  { code: "save_for_later", label: "Save for later" },
  { code: "other", label: "Other" },
];

export type ActionCenter = {
  rows: ActionRow[];
  counts: Record<string, number>;
  product_matching_available: boolean;
  /** Set-aside counts by reason code, for later analysis. */
  decline_reasons: Record<string, number>;
  decline_reason_labels: Record<string, string>;
  todays_list: number;
  awaiting_decision: number;
  detected_not_prioritized: number;
  detected: number;
  total: number;
  statuses: string[];
  open: number;
  closed: number;
  converted_value: number;
  converted_value_basis: string;
  as_of: string;
};

export type Overview = {
  loaded: boolean;
  /** Absent only when no data is loaded yet. */
  as_of?: string;
  today?: OpportunityCounts & {
    opportunities: number;
    note: string;
    relationship: string;
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

/** Shared shape of every advisor/store breakdown row on the Performance page. */
export type PerformanceGroupRow = {
  recommended: number;
  decisions_made: number;
  contacted: number;
  converted: number;
  conversion_rate: number | null;
  revenue_after_contact: number;
  estimated_incremental_revenue: number;
};

export type AdvisorPerformanceRow = PerformanceGroupRow & { advisor: string };
export type StorePerformanceRow = PerformanceGroupRow & { store: string };

export type ChannelPerformanceRow = {
  channel: string;
  channel_label: string;
  contacted: number;
  converted: number;
  conversion_rate: number | null;
  revenue_after_contact: number;
};

export type ReasonPerformanceRow = {
  trigger: string;
  recommended: number;
  contacted: number;
  converted: number;
  conversion_rate: number | null;
  revenue_after_contact: number;
};

export type Performance = {
  loaded: boolean;
  window_days: number;
  opportunities_detected: number;
  prioritized_today: number;
  customers_contacted: number;
  conversions: number;
  ignored: number;
  open: number;
  /** Every detected row nobody has ruled on: awaiting_decision + detected_not_recommended. */
  untouched: number;
  /** On today's list and still waiting on the advisor. */
  awaiting_decision: number;
  /** Recommended rows this window has ruled on, one way or another. */
  decisions_made: number;
  /** Detected, but never recommended — held back, not owed. */
  detected_not_recommended: number;
  /** Expected value sitting on today's recommended list. */
  prioritized_expected_value: number;
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
  by_trigger: ReasonPerformanceRow[];
  /** Reason/trigger is the finest grain RevenueOS records — always false today. */
  template_attribution_supported: boolean;
  template_attribution_note: string;

  /** Advisor / Team Performance. */
  by_advisor: AdvisorPerformanceRow[];
  /** False when no transaction in the dataset names an advisor at all. */
  advisor_data_available: boolean;
  /** Recommended rows in this window for a customer no transaction names an advisor for. */
  unattributed_recommendations_advisor: number;
  advisor_attribution_basis: string;

  by_store: StorePerformanceRow[];
  store_data_available: boolean;
  unattributed_recommendations_store: number;
  store_attribution_basis: string;

  /** Channel Performance — always all five channels, zeroed if unused. */
  by_channel: ChannelPerformanceRow[];
  /** Contacts recorded without going through the outreach flow, so no channel was stamped. */
  unspecified_channel_contacts: number;
  channel_basis: string;

  filters: {
    advisor: string | null;
    store: string | null;
    advisors: string[];
    stores: string[];
  };
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
  product_matching_available: boolean;
  why_contact: {
    headline: string;
    why_now: string | null;
    evidence: string | null;
    customer_evidence: string[];
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
