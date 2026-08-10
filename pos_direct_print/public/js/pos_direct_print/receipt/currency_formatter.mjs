/**
 * Currency formatter (A.12.12).
 *
 * Deterministic money formatting driven by explicit currency, locale, and
 * policy — never the browser's implicit locale or the user's environment.
 * Milestone A keeps formatting pure: fixed decimal places per currency and
 * explicit grouping, so the same inputs always yield the same string.
 */

// Explicit decimal policy. Unknown currencies default to 2 decimals
// (policy.default_decimals), never runtime introspection.
const CURRENCY_DECIMALS = Object.freeze({
  IDR: 0,
  JPY: 0,
  KRW: 0,
  VND: 0,
  USD: 2,
  EUR: 2,
  SGD: 2,
  MYR: 2,
  THB: 2,
  PHP: 2,
  CNY: 2,
  AUD: 2,
});

const DEFAULT_POLICY = Object.freeze({
  default_decimals: 2,
  group_separator: ",",
  decimal_separator: ".",
  symbol_position: "before", // "before" | "after"
  symbol_separator: " ",
});

/**
 * @param {number|string} amount
 * @param {string} currency explicit ISO currency code
 * @param {string} locale explicit locale tag (recorded in policy; the
 *   Milestone A formatter is locale-independent by construction)
 * @param {object} policy partial overrides of DEFAULT_POLICY
 * @returns {string}
 */
export function format(amount, currency, locale, policy = {}) {
  if (!currency || typeof currency !== "string") {
    throw new TypeError("currency is required");
  }
  if (!locale || typeof locale !== "string") {
    throw new TypeError("locale is required");
  }
  const options = { ...DEFAULT_POLICY, ...policy };

  const decimals =
    currency.toUpperCase() in CURRENCY_DECIMALS
      ? CURRENCY_DECIMALS[currency.toUpperCase()]
      : options.default_decimals;

  const numeric = typeof amount === "number" ? amount : Number(amount);
  if (!Number.isFinite(numeric)) {
    return `${currency.toUpperCase()} 0`;
  }

  const negative = numeric < 0;
  const fixed = Math.abs(numeric).toFixed(decimals);
  const [whole, fraction = ""] = fixed.split(".");
  const grouped = _group(whole, options.group_separator);
  const body = fraction
    ? `${grouped}${options.decimal_separator}${fraction}`
    : grouped;

  const symbol = currency.toUpperCase();
  const spaced = options.symbol_separator;
  const formatted =
    options.symbol_position === "after"
      ? `${body}${spaced}${symbol}`
      : `${symbol}${spaced}${body}`;
  return negative ? `-${formatted}` : formatted;
}

function _group(whole, separator) {
  if (!separator) {
    return whole;
  }
  let out = "";
  let count = 0;
  for (let i = whole.length - 1; i >= 0; i -= 1) {
    out = whole[i] + out;
    count += 1;
    if (count % 3 === 0 && i > 0) {
      out = separator + out;
    }
  }
  return out;
}
