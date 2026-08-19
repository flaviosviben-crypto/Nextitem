/**
 * Server-side proxy from /api/* to the RevenueOS API.
 *
 * This deliberately replaces a next.config rewrite. Rewrites are compiled into
 * routes-manifest.json at *build* time, so the API address is frozen when the
 * bundle is built: a build that ran without the platform's variable set bakes
 * in localhost and no amount of restarting or re-configuring fixes it. A route
 * handler reads the environment on each request, so the deployed site points
 * wherever the platform says, and a changed backend takes effect on restart.
 *
 * The browser only ever calls this origin, which is why production needs no
 * CORS and no API URL in the client bundle.
 */
import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

function backendOrigin(): string {
  // BACKEND_HOST outranks BACKEND_URL: only a hosting platform sets it, while
  // BACKEND_URL is routinely localhost in a developer's .env.local — which Next
  // lets override the real environment.
  if (process.env.BACKEND_HOST) return `https://${process.env.BACKEND_HOST}`;
  return process.env.BACKEND_URL || "http://127.0.0.1:8000";
}

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
  const path = (ctx.params.path || []).join("/");
  const target = `${backendOrigin()}/api/${path}${req.nextUrl.search}`;

  const init: RequestInit = {
    method: req.method,
    headers: clean(req.headers),
    redirect: "manual",
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
    // Say which address failed. A generic 500 here is what turned an earlier
    // misconfiguration into an hour of guessing.
    const detail = err instanceof Error ? err.message : "unknown error";
    return Response.json(
      { detail: `RevenueOS API unreachable at ${backendOrigin()}: ${detail}` },
      { status: 502 },
    );
  }
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const PUT = proxy;
export const DELETE = proxy;
