/**
 * Receipt layout (A.12.10).
 *
 * Logical receipt values -> ordered ReceiptDocument blocks per paper profile.
 * Pure transformation: no printer calls, no iMin, no browser APIs (A-DOD-10).
 * Exact thermal character-width policy belongs to Milestone D; here profiles
 * only carry logical widths that downstream wrapping consumes.
 */

import { format as formatCurrency } from "./currency_formatter.mjs";
import { wrap } from "./text_wrapper.mjs";

// Logical widths in characters per paper profile. These are layout
// defaults, not calibrated font metrics.
export const PAPER_PROFILES = Object.freeze({
  "58mm": { key: "58mm", logical_width: 32 },
  "80mm": { key: "80mm", logical_width: 48 },
});

export const DEFAULT_PAPER_PROFILE = "58mm";

/**
 * @param {object} view_model ReceiptViewModel: { title_lines, info_lines,
 *   items, totals_lines, footer_lines, currency, locale, symbol? }
 * @param {object|string} paper_profile profile object or profile key
 * @returns {Array<object>} ordered blocks (A.10.3 categories)
 */
export function layout(view_model, paper_profile = DEFAULT_PAPER_PROFILE) {
  const profile =
    typeof paper_profile === "string"
      ? PAPER_PROFILES[paper_profile] || PAPER_PROFILES[DEFAULT_PAPER_PROFILE]
      : { logical_width: 32, ...paper_profile };
  const width = profile.logical_width;

  const vm = view_model || {};
  const blocks = [];

  for (const line of vm.title_lines || []) {
    for (const wrapped of wrap(String(line), width)) {
      blocks.push(_textBlock(wrapped, { align: "center", bold: true }));
    }
  }

  if ((vm.title_lines || []).length > 0) {
    blocks.push(_separatorBlock());
  }

  for (const line of vm.info_lines || []) {
    for (const wrapped of wrap(String(line), width)) {
      blocks.push(_textBlock(wrapped, { align: "left" }));
    }
  }

  const items = vm.items || [];
  if (items.length > 0) {
    blocks.push(_separatorBlock());
    for (const item of items) {
      const label = `${item.quantity ?? 1} x ${item.item_name ?? ""}`;
      const amount = _money(item.amount, vm);
      const left_width = width - amount.length;
      for (const wrapped of wrap(label, Math.max(1, left_width))) {
        blocks.push(
          _columnsBlock([
            { text: wrapped, align: "left" },
            { text: amount, align: "right" },
          ])
        );
      }
    }
  }

  const totals = vm.totals_lines || [];
  if (totals.length > 0) {
    blocks.push(_separatorBlock());
    for (const total of totals) {
      blocks.push(
        _columnsBlock([
          { text: String(total.label), align: "left" },
          { text: _money(total.amount, vm), align: "right" },
        ])
      );
    }
  }

  const footer_lines = vm.footer_lines || [];
  if (footer_lines.length > 0) {
    blocks.push(_separatorBlock());
    for (const line of footer_lines) {
      for (const wrapped of wrap(String(line), width)) {
        blocks.push(_textBlock(wrapped, { align: "center" }));
      }
    }
  }

  if (blocks.length > 0) {
    blocks.push(_feedBlock(3));
  }
  return blocks;
}

function _money(amount, vm) {
  if (amount === null || amount === undefined) {
    return "";
  }
  return formatCurrency(amount, vm.currency || "IDR", vm.locale || "id-ID");
}

function _textBlock(text, style) {
  return { type: "TEXT", text, ...style };
}

function _separatorBlock(char = "-") {
  return { type: "SEPARATOR", char };
}

function _columnsBlock(columns) {
  return { type: "COLUMNS", columns };
}

function _feedBlock(lines) {
  return { type: "FEED", lines };
}
