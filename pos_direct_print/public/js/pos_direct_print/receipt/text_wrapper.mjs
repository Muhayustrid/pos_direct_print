/**
 * Text wrapper contract (A.12.11).
 *
 * Deterministic wrap/truncate over logical character widths. Iteration is
 * code-point based (never UTF-16 code units), so Unicode code points are
 * never split. The precise thermal character-width policy belongs to
 * Milestone D — here width means "code points per line".
 */

/**
 * @param {string} text
 * @param {number} max_width logical width in code points (>= 1)
 * @param {object} policy { break_long_words = true }
 * @returns {string[]} ordered lines
 */
export function wrap(text, max_width, policy = {}) {
  const value = String(text ?? "");
  if (!Number.isInteger(max_width) || max_width < 1) {
    return [value];
  }
  const break_long_words = policy.break_long_words !== false;

  const lines = [];
  for (const paragraph of value.split("\n")) {
    const words = paragraph.split(/\s+/).filter((w) => w.length > 0);
    if (words.length === 0) {
      lines.push("");
      continue;
    }
    let current = [];
    let current_len = 0;
    const flush = () => {
      lines.push(current.join(""));
      current = [];
      current_len = 0;
    };

    for (const word of words) {
      let chars = Array.from(word);
      while (chars.length > 0) {
        if (current_len === 0) {
          const take = Math.min(max_width, chars.length);
          current = chars.slice(0, take);
          current_len = take;
          chars = chars.slice(take);
          if (current_len === max_width && chars.length > 0) {
            flush();
          }
        } else {
          // One code point reserved for the separating space.
          const room = max_width - current_len - 1;
          if (chars.length <= room) {
            current.push(" ", ...chars);
            current_len += 1 + chars.length;
            chars = [];
          } else if (!break_long_words || room <= 0) {
            flush();
          } else {
            current.push(" ", ...chars.slice(0, room));
            chars = chars.slice(room);
            flush();
          }
        }
      }
    }
    if (current.length > 0) {
      flush();
    }
  }
  return lines;
}

/**
 * @param {string} text
 * @param {number} max_width logical width in code points
 * @param {object} policy { ellipsis = "…" }
 * @returns {string}
 */
export function truncate(text, max_width, policy = {}) {
  const value = String(text ?? "");
  const ellipsis =
    policy.ellipsis === undefined ? "…" : String(policy.ellipsis);
  const chars = Array.from(value);
  if (!Number.isInteger(max_width) || chars.length <= max_width) {
    return value;
  }
  const keep = Math.max(0, max_width - Array.from(ellipsis).length);
  return chars.slice(0, keep).join("") + ellipsis;
}
