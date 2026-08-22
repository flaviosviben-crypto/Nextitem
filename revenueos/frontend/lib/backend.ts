/**
 * Where the RevenueOS API lives, resolved from the environment.
 *
 * Its own module because Next.js route files may only export route handlers,
 * and because this logic is worth testing directly: production once went down
 * inside it. Render's `fromService.property: host` hands back the service
 * *slug* ("revenueos-api-6bxb"), not a fully qualified domain. Prefixing that
 * with https:// yields a dotless URL with no DNS record anywhere, and every
 * request fails to connect.
 */
export function resolveBackend(env: NodeJS.ProcessEnv = process.env): string {
  const strip = (value: string) => value.trim().replace(/\/+$/, "");

  // Explicit and absolute. The escape hatch: set this to any origin — including
  // an internal address like http://revenueos-api-6bxb:10000 — and it is used
  // verbatim, with no interpretation and no code change.
  if (env.BACKEND_ORIGIN) return strip(env.BACKEND_ORIGIN);

  // A hostname supplied by the platform. BACKEND_HOST outranks BACKEND_URL
  // because only a host sets it, whereas BACKEND_URL is routinely localhost in
  // a developer's .env.local — which Next.js lets override the real environment.
  const host = env.BACKEND_HOST?.trim().replace(/^https?:\/\//, "").replace(/\/+$/, "");
  if (host) {
    // A dotless name is a Render service slug, not a domain. Its public address
    // is that slug under onrender.com — the same relationship the frontend
    // shows: slug "revenueos-web" is served at revenueos-web.onrender.com.
    return host.includes(".") ? `https://${host}` : `https://${host}.onrender.com`;
  }

  // A full origin, used by docker compose and local development.
  if (env.BACKEND_URL) return strip(env.BACKEND_URL);

  return "http://127.0.0.1:8000";
}

/** Which variable the origin came from, for error messages worth reading. */
export function backendSource(env: NodeJS.ProcessEnv = process.env): string {
  if (env.BACKEND_ORIGIN) return "BACKEND_ORIGIN";
  if (env.BACKEND_HOST) return "BACKEND_HOST";
  if (env.BACKEND_URL) return "BACKEND_URL";
  return "the local default";
}
