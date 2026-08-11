import { makeError } from "../core/errors.mjs";
import { resolvePaperProfile } from "./paper_profiles.mjs";

export function renderReceiptLines(receipt_document, profile) {
  const paper_profile = resolvePaperProfile(profile);
  const lines = [];
  let bold = false;

  for (const block of receipt_document?.blocks || []) {
    switch (block.type) {
      case "TEXT": {
        const nextBold = Boolean(block.bold);
        if (bold !== nextBold) {
          lines.push({ kind: "style", bold: nextBold });
          bold = nextBold;
        }
        lines.push({ kind: "text", text: block.text, bold: nextBold });
        break;
      }
      case "SEPARATOR":
        lines.push({
          kind: "text",
          text: String(block.char || "-").repeat(paper_profile.logical_width).slice(
            0,
            paper_profile.logical_width
          ),
        });
        break;
      case "COLUMNS":
        lines.push({
          kind: "text",
          text: renderColumns(block.columns, paper_profile.logical_width),
          bold: Boolean(bold),
        });
        break;
      case "FEED":
        lines.push({ kind: "feed" });
        break;
      case "SPACER":
      case "IMAGE":
      case "QR":
      case "CUT":
        throw makeError("PDP_RECEIPT_INVALID", { phase: "RECEIPT" });
      default:
        throw makeError("PDP_RECEIPT_INVALID", { phase: "RECEIPT" });
    }
  }

  return lines;
}

function renderColumns(columns, width) {
  const [left = {}, right = {}] = columns || [];
  const leftText = String(left.text ?? "");
  const rightText = String(right.text ?? "");
  return `${leftText}${" ".repeat(
    Math.max(1, width - leftText.length - rightText.length)
  )}${rightText}`;
}
