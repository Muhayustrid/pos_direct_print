import assert from "node:assert/strict";
import { test } from "node:test";

import { ReceiptBuilder } from "../receipt_builder.mjs";
import {
  REFERENCE_PROFILE,
  TEST_PROFILE,
  makePaperProfile,
  resolvePaperProfile,
} from "../paper_profiles.mjs";
import { renderReceiptLines } from "../receipt_lines.mjs";

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
    items: [{ item_name: "Roti Sobek", qty: 2, amount: 40000 }],
  };
}

test("paper profiles are frozen and expose the reference defaults", () => {
  const profile = makePaperProfile();

  assert.deepEqual(profile, {
    key: "reference_58mm",
    width_mm: 58,
    logical_width: 32,
    page_format: null,
    text_width_dots: null,
    text_size: 24,
    final_feed: 100,
  });
  assert.equal(Object.isFrozen(profile), true);
  assert.equal(Object.isFrozen(REFERENCE_PROFILE), true);
  assert.equal(resolvePaperProfile(TEST_PROFILE), TEST_PROFILE);
  assert.equal(resolvePaperProfile("unknown"), REFERENCE_PROFILE);
});

test("receipt renderer preserves block order and emits bold style changes", () => {
  const document = new ReceiptBuilder().build(makeInvoice(), {
    paper_profile: TEST_PROFILE,
  });
  const lines = renderReceiptLines(document, TEST_PROFILE);

  assert.equal(lines[0].kind, "style");
  assert.deepEqual(lines[0], { kind: "style", bold: true });
  assert.equal(lines[1].kind, "text");
  assert.equal(lines[1].bold, true);
  assert.ok(lines.some((line) => line.kind === "style" && line.bold === false));
  assert.deepEqual(
    lines.filter((line) => line.kind === "feed"),
    [{ kind: "feed" }]
  );
  assert.equal(lines.at(-1).kind, "feed");

  const columnLines = lines.filter(
    (line) => line.kind === "text" && line.text.includes("IDR")
  );
  assert.ok(columnLines.length > 0);
  assert.ok(
    columnLines.every((line) => line.text.length === TEST_PROFILE.logical_width)
  );
  assert.ok(
    lines
      .filter((line) => line.kind === "text")
      .some((line) => line.text === "-".repeat(TEST_PROFILE.logical_width))
  );
  assert.ok(
    lines
      .filter((line) => line.kind === "text")
      .some((line) => line.text === "Thank you")
  );
  assert.deepEqual(
    lines.slice(0, 4).map((line) => line.kind),
    ["style", "text", "text", "style"]
  );
  assert.ok(lines.findIndex((line) => line.kind === "feed") > 0);
  assert.ok(
    lines.every(
      (line) => line.kind !== "feed" || Object.keys(line).length === 1
    )
  );
  assert.ok(
    lines.every(
      (line) => line.kind !== "style" || typeof line.bold === "boolean"
    )
  );
  assert.ok(
    lines.every((line) => line.kind !== "text" || typeof line.text === "string")
  );
  assert.ok(
    lines.every(
      (line) =>
        line.kind !== "text" || line.text.length <= TEST_PROFILE.logical_width
    )
  );
  assert.ok(lines.some((line) => line.kind === "text" && line.bold === false));
  assert.ok(lines.some((line) => line.kind === "style" && line.bold === true));
  assert.ok(lines.some((line) => line.kind === "style" && line.bold === false));
  assert.ok(lines.at(-1).kind === "feed");
  assert.ok(lines.at(-2).kind === "text");
  assert.ok(lines.at(-2).text === "Thank you");
  assert.ok(lines.at(-2).bold === false);
  assert.ok(lines.at(-3).kind === "style" || lines.at(-3).kind === "text");
  assert.ok(lines.length > 10);
  assert.ok(lines.filter((line) => line.kind === "feed").length === 1);
  assert.ok(lines.filter((line) => line.kind === "style").length >= 2);
  assert.ok(lines.filter((line) => line.kind === "text").length >= 8);
  assert.ok(lines.every((line) => !line.text?.includes("\n")));
  assert.deepEqual(renderReceiptLines(document, TEST_PROFILE), lines);
});

test("receipt renderer rejects unsupported receipt blocks", () => {
  const document = new ReceiptBuilder().build(makeInvoice());
  const imageDocument = {
    ...document,
    blocks: [...document.blocks, { type: "IMAGE", src: "logo" }],
  };

  assert.throws(
    () => renderReceiptLines(imageDocument, REFERENCE_PROFILE),
    (error) => error.code === "PDP_RECEIPT_INVALID" && error.phase === "RECEIPT"
  );
});
