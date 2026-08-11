const DEFAULTS = Object.freeze({
  key: "reference_58mm",
  width_mm: 58,
  logical_width: 32,
  page_format: 1,
  text_width_dots: 384,
  final_feed: 4,
});

export function makePaperProfile({
  key = DEFAULTS.key,
  width_mm = DEFAULTS.width_mm,
  logical_width = DEFAULTS.logical_width,
  page_format = DEFAULTS.page_format,
  text_width_dots = DEFAULTS.text_width_dots,
  final_feed = DEFAULTS.final_feed,
} = {}) {
  return Object.freeze({
    key,
    width_mm,
    logical_width,
    page_format,
    text_width_dots,
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
