/**
 * When a failed request is worth trying again.
 *
 * A deploy restarts the API for a few seconds, and during that window the
 * platform answers 502. Turning the first one into a full error screen makes a
 * routine restart look like an outage. A couple of quiet retries cover it.
 *
 * Its own module, free of React, so the policy can be tested directly rather
 * than inferred from the behaviour of a component.
 */

/** Gateway errors: the platform, not the application, saying it cannot reach us. */
export const TRANSIENT_STATUSES = new Set([502, 503, 504]);

/** Three tries total. Beyond that a failure is real and must be shown. */
export const MAX_ATTEMPTS = 3;

/**
 * Only idempotent reads are retried.
 *
 * Replaying a write after a gateway error risks applying it twice — the first
 * attempt may have reached the server before the connection broke. A decision
 * or an upload is safer failed and visible than silently duplicated.
 */
const RETRYABLE_METHODS = new Set(["GET", "HEAD"]);

export function isTransientStatus(status: number): boolean {
  return TRANSIENT_STATUSES.has(status);
}

export function shouldRetry(opts: {
  method: string;
  attempt: number;
  /** Response status, or undefined when the request never completed. */
  status?: number;
}): boolean {
  const { method, attempt, status } = opts;
  if (attempt >= MAX_ATTEMPTS) return false;
  if (!RETRYABLE_METHODS.has(method.toUpperCase())) return false;
  // No status means the connection itself failed — exactly what a restart looks
  // like from the outside.
  if (status === undefined) return true;
  return isTransientStatus(status);
}

/** Bounded backoff: 400ms, then 1000ms. Long enough to matter, short enough to wait through. */
export function retryDelay(attempt: number): number {
  return [400, 1000][attempt - 1] ?? 1000;
}

export const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
