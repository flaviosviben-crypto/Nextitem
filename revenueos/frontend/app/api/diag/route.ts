/**
 * What is actually deployed here, and can it reach the API?
 *
 * A static segment, so it wins over the /api/[...path] proxy and never leaves
 * this service. It exists because diagnosing production from the outside was
 * guesswork: a blank screen looks identical whether the API is asleep, the API
 * is broken, or the browser is running a build from three commits ago. One URL
 * now answers all three.
 */
import { backendSource, resolveBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  const origin = resolveBackend();
  const started = Date.now();

  let api: Record<string, unknown>;
  try {
    const res = await fetch(`${origin}/api/health`, {
      cache: "no-store",
      signal: typeof AbortSignal.timeout === "function"
        ? AbortSignal.timeout(100_000)
        : undefined,
    });
    const body = await res.json().catch(() => null);
    api = {
      reachable: true,
      status: res.status,
      took_ms: Date.now() - started,
      loaded: (body as { loaded?: boolean } | null)?.loaded ?? null,
      source: (body as { source?: string } | null)?.source ?? null,
    };
  } catch (err) {
    api = {
      reachable: false,
      took_ms: Date.now() - started,
      error: err instanceof Error ? `${err.name}: ${err.message}` : "unknown",
    };
  }

  return Response.json({
    service: "revenueos-web",
    // Render exposes the deployed commit; without it we cannot tell a stale
    // build from a broken one, which is the whole point of this endpoint.
    commit: process.env.RENDER_GIT_COMMIT?.slice(0, 7) ?? "unknown",
    branch: process.env.RENDER_GIT_BRANCH ?? "unknown",
    backend_origin: origin,
    backend_resolved_from: backendSource(),
    api,
  });
}
