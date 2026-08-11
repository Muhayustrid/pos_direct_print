"""Receipt canonical JSON and the B-AC-01 cross-language hash."""

import json


def canonicalize(value):
	"""Serialize receipt values exactly as the JavaScript builder does."""
	return _canonical(value)


def hash_receipt(document):
	"""Return FNV-1a lanes over UTF-16 code units from canonical JSON."""
	canonical = canonicalize(document)
	hash_low = 0x811C9DC5
	hash_high = 0x01000193
	for index in range(0, len(encoded := canonical.encode("utf-16-le")), 2):
		unit = encoded[index] | (encoded[index + 1] << 8)
		hash_low = _fnv_step(hash_low, unit & 0xFF)
		hash_high = _fnv_step(hash_high, (unit >> 8) & 0xFF)
	return f"pdpr1:{hash_low:08x}{hash_high:08x}"


def _canonical(value):
	if isinstance(value, dict):
		return (
			"{"
			+ ",".join(
				f"{json.dumps(key, ensure_ascii=False)}:{_canonical(value[key])}" for key in sorted(value)
			)
			+ "}"
		)
	if isinstance(value, list):
		return "[" + ",".join(_canonical(item) for item in value) + "]"
	if value is None:
		return "null"
	if isinstance(value, bool):
		return "true" if value else "false"
	if isinstance(value, int):
		return str(value)
	if isinstance(value, float):
		return str(int(value)) if value.is_integer() else repr(value)
	if isinstance(value, str):
		return json.dumps(value, ensure_ascii=False)
	raise TypeError(f"unsupported receipt value: {type(value).__name__}")


def _fnv_step(value, byte):
	return ((value ^ byte) * 0x01000193) & 0xFFFFFFFF
