import json
from pathlib import Path

from frappe.tests import UnitTestCase

from pos_direct_print.core.receipt_hash import canonicalize, hash_receipt


class TestReceiptHash(UnitTestCase):
	def test_hash_vectors_match_javascript_contract(self):
		vectors = json.loads((Path(__file__).with_name("hash_vectors.json")).read_text())["vectors"]
		for vector in vectors:
			with self.subTest(vector=vector["name"]):
				self.assertEqual(canonicalize(vector["receipt"]), vector["canonical"])
				self.assertEqual(hash_receipt(vector["receipt"]), vector["hash"])

	def test_boolean_is_not_integer(self):
		self.assertEqual(canonicalize({"value": True}), '{"value":true}')

	def test_non_integer_float_is_preserved(self):
		self.assertEqual(canonicalize({"value": 1.5}), '{"value":1.5}')

	def test_empty_document_skeleton(self):
		document = {
			"schema_version": 1,
			"reference_doctype": "POS Invoice",
			"reference_name": "POS-INV-EMPTY",
			"locale": "id-ID",
			"currency": "IDR",
			"paper_profile": "58mm",
			"blocks": [],
			"metadata": {},
		}
		self.assertEqual(
			canonicalize(document),
			'{"blocks":[],"currency":"IDR","locale":"id-ID","metadata":{},'
			'"paper_profile":"58mm","reference_doctype":"POS Invoice",'
			'"reference_name":"POS-INV-EMPTY","schema_version":1}',
		)
