"use client";

import useSWR, { SWRConfiguration, mutate as globalMutate } from "swr";

/**
 * All requests go to same-origin `/api/*`, which Next rewrites to FastAPI.
 * The API host never appears in the client bundle, and no key ever does.
 */
export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function parse(response: Response) {
  const text = await response.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!response.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : null) ?? `Request failed (${response.status})`;
    throw new ApiError(detail, response.status);
  }
  return body;
}

export async function api<T = unknown>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path.startsWith("/api") ? path : `/api${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  return (await parse(response)) as T;
}

export const post = <T = unknown>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const del = <T = unknown>(path: string) => api<T>(path, { method: "DELETE" });

export const upload = <T = unknown>(path: string, form: FormData) =>
  api<T>(path, { method: "POST", body: form });

const fetcher = <T,>(path: string) => api<T>(path);

export function useApi<T>(path: string | null, config?: SWRConfiguration) {
  const { data, error, isLoading, mutate } = useSWR<T>(path, fetcher<T>, {
    revalidateOnFocus: false,
    shouldRetryOnError: false,
    ...config,
  });
  return { data, error: error as ApiError | undefined, isLoading, mutate };
}

/** Refresh every view that depends on the loaded dataset. */
export function refreshWorkspace() {
  return globalMutate(
    (key) => typeof key === "string" && key.startsWith("/"),
    undefined,
    { revalidate: true },
  );
}

export function query(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
