/**
 * The retry policy, tested directly.
 *
 * A frontend deploy used to restart the API and drop the user straight into an
 * error screen. These cases pin what is retried and, just as importantly, what
 * is not.
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const src = readFileSync(new URL("../lib/retry.ts", import.meta.url), "utf8");
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { shouldRetry, retryDelay, MAX_ATTEMPTS, isTransientStatus } =
  await import("data:text/javascript," + encodeURIComponent(js));

test("a gateway error during a restart is retried", () => {
  for (const status of [502, 503, 504]) {
    assert.equal(shouldRetry({ method: "GET", attempt: 1, status }), true, String(status));
  }
});

test("a dropped connection is retried", () => {
  assert.equal(shouldRetry({ method: "GET", attempt: 1, status: undefined }), true);
});

test("an application error is never retried", () => {
  for (const status of [400, 401, 403, 404, 422, 500]) {
    assert.equal(shouldRetry({ method: "GET", attempt: 1, status }), false, String(status));
  }
});

test("writes are never retried, even on a gateway error", () => {
  // Replaying these could record a decision twice or upload a file twice.
  for (const method of ["POST", "PATCH", "PUT", "DELETE"]) {
    assert.equal(shouldRetry({ method, attempt: 1, status: 502 }), false, method);
  }
});

test("retrying stops, and the failure surfaces", () => {
  assert.equal(shouldRetry({ method: "GET", attempt: MAX_ATTEMPTS, status: 502 }), false);
  assert.equal(shouldRetry({ method: "GET", attempt: MAX_ATTEMPTS + 5, status: 502 }), false);
});

test("backoff is bounded and increasing", () => {
  const delays = [1, 2, 3].map(retryDelay);
  assert.ok(delays[0] < delays[1], "backoff should grow");
  assert.ok(Math.max(...delays) <= 1000, "and stay bounded");
});

test("only gateway statuses count as transient", () => {
  assert.equal(isTransientStatus(502), true);
  assert.equal(isTransientStatus(500), false);
});
