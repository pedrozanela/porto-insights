// "vitest" mínimo sobre node:test + node:assert — só os matchers que os testes usam (mesma API).
// Mapeado no lugar do pacote "vitest" por hooks.mjs: os testes rodam no Node puro, sem npm.
import assert from "node:assert/strict";

export { describe, it } from "node:test";

export function expect(actual) {
  return {
    toBe: (expected) => assert.equal(actual, expected),
    toEqual: (expected) => assert.deepEqual(actual, expected),
    // igual ao vitest: |actual - expected| < 10^-digits / 2
    toBeCloseTo: (expected, digits = 2) =>
      assert.ok(Math.abs(actual - expected) < 10 ** -digits / 2, `${actual} não está perto de ${expected}`),
  };
}
