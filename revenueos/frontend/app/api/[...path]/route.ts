/**
 * Server-side proxy from /api/* to the RevenueOS API.
 *
 * This replaces a next.config rewrite on purpose. Rewrites are compiled into
 * routes-manifest.json at *build* time, so the API address is frozen when the
 * bundle is built: a build that ran without the platform's variable set bakes
 * in localhost and no amount of restarting fixes it. A route handler reads the
 * environment per request instead.
 *
 * The browser only ever calls this origin, which is why production needs no
 * CORS and no API URL in the client bundle.
 */
import { NextRequest } from "next/server";

import { backendSource, resolveBackend } from "@/lib/backend";

export const dynamic = "force-dynamic";

/** A free-plan API sleeps after 15 minutes; waking it can take about a minute. */
const TIMEOUT_MS = 100_000;

// Hop-by-hop and body-shape headers. fetch() has already decoded the payload,
// so forwarding the original encoding or length would describe it incorrectly.
const STRIP = new Set([
  "host", "connection", "keep-alive", "transfer-encoding",
  "content-encoding", "content-length",
]);

function clean(source: Headers): Headers {
  const out = new Headers();
  source.forEach((value, key) => {
    if (!STRIP.has(key.toLowerCase())) out.append(key, value);
  });
  return out;
}

async function proxy(req: NextRequest, ctx: { params: { path: string[] } }) {
  const origin = resolveBackend();
  const path = (ctx.params.path || []).join("/");
  const target = `${origin}/api/${path}${req.nextUrl.search}`;

  const init: RequestInit = {
    method: req.method,
    headers: clean(req.headers),
    redirect: "manual",
    signal: AbortSignal.timeout(TIMEOUT_MS),
  };
  if (req.method !== "GET" && req.method !== "HEAD") {
    // Buffering keeps CSV uploads (multipart) intact and avoids needing a
    // streaming duplex handshake that not every runtime supports.
    init.body = await req.arrayBuffer();
  }

  try {
    const res = await fetch(target, init);
    return new Response(res.body, { status: res.status, headers: clean(res.headers) });
  } catch (err) {
    const reason = err instanceof Error ? err.message : "unknown error";
    const timedOut = err instanceof Error && err.name === "TimeoutError";
    // Name the origin and how it was derived. A bare "fetch failed" is what made
    // the last misconfiguration take a round trip to diagnose.
    const source = backendSource();
    return Response.json(
      {
        detail: timedOut
          ? `The RevenueOS API at ${origin} did not respond within ${TIMEOUT_MS / 1000}s. ` +
            "A sleeping free-plan service can take about a minute to wake — try again."
          : `RevenueOS API unreachable at ${origin} (from ${source}): ${reason}`,
        backend_origin: origin,
        resolved_from: source,
      },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
