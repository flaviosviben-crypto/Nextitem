/**
 * Regression tests for backend origin resolution.
 *
 * Production once went down because Render's `fromService.property: host`
 * returns a service *slug* ("revenueos-api-6bxb"), not a domain, and the proxy
 * prefixed it with https:// to make a dotless URL that resolves nowhere. The
 * first case below is that exact value. Everything here is a pure string
 * transform, so it is cheap to keep honest.
 *
 *   npm test
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const source = readFileSync(new URL("../lib/backend.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(
  source,
  { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } },
).outputText;
const { resolveBackend } = await import("data:text/javascript," + encodeURIComponent(compiled));

const cases = [
  ["a Render slug becomes its public address",
   { BACKEND_HOST: "revenueos-api-6bxb" }, "https://revenueos-api-6bxb.onrender.com"],
  ["a slug without a suffix too",
   { BACKEND_HOST: "revenueos-api" }, "https://revenueos-api.onrender.com"],
  ["a real domain is left alone",
   { BACKEND_HOST: "api.example.com" }, "https://api.example.com"],
  ["a scheme accidentally included is not doubled",
   { BACKEND_HOST: "https://api.example.com" }, "https://api.example.com"],
  ["an explicit origin wins, and may be internal",
   { BACKEND_ORIGIN: "http://revenueos-api-6bxb:10000", BACKEND_HOST: "revenueos-api-6bxb" },
   "http://revenueos-api-6bxb:10000"],
  ["a trailing slash is trimmed",
   { BACKEND_ORIGIN: "https://api.example.com/" }, "https://api.example.com"],
  ["a leaked localhost in .env.local cannot beat the platform",
   { BACKEND_HOST: "revenueos-api-6bxb", BACKEND_URL: "http://127.0.0.1:8000" },
   "https://revenueos-api-6bxb.onrender.com"],
  ["docker compose keeps its service address",
   { BACKEND_URL: "http://backend:8000" }, "http://backend:8000"],
  ["nothing set means a local backend",
   {}, "http://127.0.0.1:8000"],
];

for (const [name, env, expected] of cases) {
  test(name, () => assert.equal(resolveBackend(env), expected));
}

test("the resolved origin is always usable as a URL", () => {
  for (const [, env] of cases) {
    const url = new URL(resolveBackend(env));
    assert.match(url.protocol, /^https?:$/);
    // A dotless public hostname is the exact shape of the production outage.
    if (url.protocol === "https:") assert.ok(url.hostname.includes("."), `${url} has no domain`);
  }
});
