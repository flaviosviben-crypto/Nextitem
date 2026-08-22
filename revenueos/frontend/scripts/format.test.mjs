/**
 * Display reconciliation for "Expected value", tested directly.
 *
 * The Opportunities card shows a recommended product's price and match %
 * right beside "Expected value". Neither is an input to the figure — the
 * real inputs are basket_value and probability, which the backend computes
 * but the card used to leave unexposed. Multiplying the two adjacent numbers
 * (e.g. €986 price × 35% match) does not reproduce the displayed total; these
 * tests pin that the breakdown we now show is built from the true inputs and
 * actually reads back to the displayed expected value.
 *
 *   npm test
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import ts from "typescript";

const src = readFileSync(new URL("../lib/format.ts", import.meta.url), "utf8");
const js = ts.transpileModule(src, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
}).outputText;
const { money, expectedValueBreakdown } =
  await import("data:text/javascript," + encodeURIComponent(js));

test("the breakdown states the true basket value and probability, not price and match %", () => {
  const line = expectedValueBreakdown(798.0, 0.15, 119.7);
  assert.match(line, /798/, "must name the basket value used");
  assert.match(line, /15%/, "must name the probability used");
  assert.match(line, /119\.7|119,70/, "must name the expected value it reconciles to");
  // The number a reader could otherwise construct from what the card shows
  // beside "Expected value" — price × match % — must not appear here.
  assert.doesNotMatch(line, /986/);
  assert.doesNotMatch(line, /35%/);
});

test("the breakdown always multiplies out to the stated expected value", () => {
  const cases = [
    { basket: 798.0, probability: 0.15, expected: 119.7 },
    { basket: 1050.5, probability: 0.32, expected: round2(1050.5 * 0.32) },
    { basket: 250, probability: 0.6, expected: 150 },
  ];
  for (const { basket, probability, expected } of cases) {
    const line = expectedValueBreakdown(basket, probability, expected);
    assert.equal(round2(basket * probability), expected, "fixture must itself reconcile");
    assert.ok(line.includes(money(expected, true)), line);
  }
});

test("missing history yields no breakdown, never a misleading zero", () => {
  assert.equal(expectedValueBreakdown(null, 0.15, null), null);
  assert.equal(expectedValueBreakdown(undefined, undefined, undefined), null);
});

function round2(n) {
  return Math.round(n * 100) / 100;
}
