/**
 * A3-01..06 — receipt construction suite (A-AT-14, A-AT-18).
 *
 * Proves the ReceiptDocument is fully serializable with zero browser/printer
 * content, and that the receipt hash is deterministic over canonical content
 * and sensitive to material changes.
 */

import assert from "node:assert/strict";
import { test } from "node:test";

import { format as formatCurrency } from "../currency_formatter.mjs";
import {
  ReceiptBuilder,
  canonicalize,
  hashReceipt,
} from "../receipt_builder.mjs";
import {
  RECEIPT_SCHEMA_VERSION,
  validateReceipt,
} from "../receipt_document.mjs";
import { truncate, wrap } from "../text_wrapper.mjs";

function makeInvoice() {
  return {
    doctype: "POS Invoice",
    name: "POS-INV-0001",
    company: "PT. JUARA ROTI INDONESIA",
    posting_date: "2026-08-10",
    customer: "Walk-in",
    currency: "IDR",
    locale: "id-ID",
    grand_total: 152500,
    items: [
      { item_name: "Roti Sobek", qty: 2, amount: 40000 },
      { item_name: "Kopi Susu", qty: 1, amount: 22500 },
    ],
  };
}

function walkForNonPlain(value, path = "root") {
  const kind = typeof value;
  if (kind === "function" || kind === "symbol") {
    return [`${path}: ${kind}`];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item, i) => walkForNonPlain(item, `${path}[${i}]`));
  }
  if (value && kind === "object") {
    if (
      typeof value.nodeType === "number" ||
      typeof value.jquery === "string" ||
      typeof value.print === "function"
    ) {
      return [`${path}: browser/printer object`];
    }
    return Object.keys(value).flatMap((key) =>
      walkForNonPlain(value[key], `${path}.${key}`)
    );
  }
  return [];
}

// ---------------------------------------------------------------- A-AT-14

test("A-AT-14: ReceiptDocument is fully serializable with no browser/printer content", () => {
  const builder = new ReceiptBuilder();
  const document = builder.build(makeInvoice());

  assert.equal(document.schema_version, RECEIPT_SCHEMA_VERSION);
  assert.ok(Array.isArray(document.blocks) && document.blocks.length > 0);

  // Full JSON round trip preserves the document exactly.
  const roundTrip = JSON.parse(JSON.stringify(document));
  assert.deepEqual(roundTrip, document);

  // No function, DOM node, or printer-object anywhere in the tree.
  const violations = walkForNonPlain(document);
  assert.deepEqual(violations, []);

  // No iMin/browser reference leaks into metadata or blocks.
  const dump = JSON.stringify(document);
  assert.ok(!dump.toLowerCase().includes("imin"));
  assert.ok(!dump.includes("window.") && !dump.includes("document."));
});

test("receipt validation rejects unknown block categories and missing fields", () => {
  const builder = new ReceiptBuilder();
  const good = builder.build(makeInvoice());

  const missing = { ...good };
  delete missing.currency;
  assert.equal(validateReceipt(missing).valid, false);

  const badBlock = { ...good, blocks: [{ type: "LASER" }] };
  assert.equal(validateReceipt(badBlock).valid, false);

  const withFunction = {
    ...good,
    metadata: { sneaky: () => {} },
  };
  assert.equal(validateReceipt(withFunction).valid, false);
});

test("layout orders blocks by paper profile without printer calls", () => {
  const builder = new ReceiptBuilder();
  const narrow = builder.build(makeInvoice(), { paper_profile: "58mm" });
  const wide = builder.build(makeInvoice(), { paper_profile: "80mm" });

  // Same content, different wrapping: the narrow profile never exceeds its
  // logical width, the wide profile needs fewer lines for the same text.
  const textBlocks = (doc) =>
    doc.blocks.filter((b) => b.type === "TEXT").map((b) => b.text);
  assert.ok(textBlocks(narrow).every((t) => Array.from(t).length <= 32));
  assert.ok(
    textBlocks(wide).filter((t) => t.length > 0).length <=
      textBlocks(narrow).filter((t) => t.length > 0).length
  );
});

// ---------------------------------------------------------------- A-AT-18

test("A-AT-18: identical canonical content hashes equal; material change differs", () => {
  const builder = new ReceiptBuilder();
  const docA = builder.build(makeInvoice());

  // Structurally different construction order, same semantics.
  const builder2 = new ReceiptBuilder({ default_currency: "IDR" });
  const docB = builder2.build(makeInvoice());
  assert.equal(hashReceipt(docA), hashReceipt(docB));

  // Key-order independence of the canonical form.
  assert.equal(canonicalize({ b: 1, a: 2 }), canonicalize({ a: 2, b: 1 }));

  // A material change (total amount) must change the hash.
  const changed = builder.build({ ...makeInvoice(), grand_total: 999999 });
  assert.notEqual(hashReceipt(docA), hashReceipt(changed));
});

// ---------------------------------------------------- A3-04 text wrapper

test("wrap/truncate never split Unicode code points", () => {
  // Each emoji is one code point but two UTF-16 units; naive slicing would
  // produce lone surrogates.
  const emoji = "🧾🧾🧾🧾🧾";
  const lines = wrap(emoji, 2);
  assert.deepEqual(lines, ["🧾🧾", "🧾🧾", "🧾"]);
  for (const line of lines) {
    assert.ok(
      !/[\uD800-\uDBFF]$/.test(line) && !/^[\uDC00-\uDFFF]/.test(line),
      "no lone surrogate"
    );
  }

  const truncated = truncate("héllo wörld", 7);
  assert.equal(Array.from(truncated).length, 7);
  assert.ok(truncated.endsWith("…"));

  // Wrapping respects word boundaries.
  assert.deepEqual(wrap("aa bb cc", 5), ["aa bb", "cc"]);
});

// ------------------------------------------------- A3-05 currency formatter

test("currency formatting is deterministic and locale-explicit", () => {
  const a = formatCurrency(152500, "IDR", "id-ID");
  const b = formatCurrency(152500, "IDR", "id-ID");
  assert.equal(a, b);
  assert.equal(a, "IDR 152,500");

  // IDR carries zero decimals by explicit policy.
  assert.equal(formatCurrency(1500.75, "IDR", "id-ID"), "IDR 1,501");
  assert.equal(formatCurrency(-25000, "IDR", "id-ID"), "-IDR 25,000");
  assert.equal(formatCurrency(12.5, "USD", "en-US"), "USD 12.50");

  // No implicit locale: an explicit locale is mandatory.
  assert.throws(() => formatCurrency(10, "IDR", null), TypeError);
});
