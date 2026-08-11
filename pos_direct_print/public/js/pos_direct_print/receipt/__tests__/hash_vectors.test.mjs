import assert from "node:assert/strict";
import { test } from "node:test";

import vectors from "../../../../../core/hash_vectors.json" with { type: "json" };

import {
  canonicalize,
  hashReceipt,
} from "../receipt_builder.mjs";

for (const vector of vectors.vectors) {
  test(`cross-language hash vector: ${vector.name}`, () => {
    assert.equal(canonicalize(vector.receipt), vector.canonical);
    assert.equal(hashReceipt(vector.receipt), vector.hash);

    const mutated = {
      ...vector.receipt,
      reference_name: `${vector.receipt.reference_name}-changed`,
    };
    assert.notEqual(hashReceipt(mutated), vector.hash);
  });
}
