// Physical values are calibration knobs, not derived constants. `text_size` is
// the iMin font pixel height: 24 pairs with 32 logical columns across 384 dots
// (12 dots per glyph). `final_feed` is a dot-row height passed to
// printAndFeedPaper, not a line count — the reference demo feeds 50-100 dots to
// clear the tear bar, so 4 was far too small to advance the paper.
//
// `page_format` and `text_width_dots` are null by default: both stay UNQUALIFIED
// on the reference device. The SDK documents no meaning for setPageFormat's
// style argument, and the head is natively 384 dots for 58mm, so sending either
// command only risks putting the printer in an unverified state. Set them on a
// profile once hardware UAT proves a device needs them.
const DEFAULTS = Object.freeze({
  key: "reference_58mm",
  width_mm: 58,
  logical_width: 32,
  page_format: null,
  text_width_dots: null,
  text_size: 24,
  final_feed: 100,
});

export function makePaperProfile({
  key = DEFAULTS.key,
  width_mm = DEFAULTS.width_mm,
  logical_width = DEFAULTS.logical_width,
  page_format = DEFAULTS.page_format,
  text_width_dots = DEFAULTS.text_width_dots,
  text_size = DEFAULTS.text_size,
  final_feed = DEFAULTS.final_feed,
} = {}) {
  return Object.freeze({
    key,
    width_mm,
    logical_width,
    page_format,
    text_width_dots,
    text_size,
    final_feed,
  });
}

export const TEST_PROFILE = makePaperProfile({ key: "test" });
export const REFERENCE_PROFILE = makePaperProfile();

const PROFILES = Object.freeze({
  [TEST_PROFILE.key]: TEST_PROFILE,
  [REFERENCE_PROFILE.key]: REFERENCE_PROFILE,
});

export function resolvePaperProfile(key_or_profile) {
  if (key_or_profile && typeof key_or_profile === "object") {
    return Object.isFrozen(key_or_profile) ? key_or_profile : REFERENCE_PROFILE;
  }
  return PROFILES[key_or_profile] || REFERENCE_PROFILE;
}
