import copy
import unittest
from steward import Dataset, Conflict


class DatasetTests(unittest.TestCase):
    def setUp(self):
        self.data = Dataset.from_csv('name,age,group\n Ada ,12,A\nAda,12,A\nBo,,B\nBo,bad,C\n')

    def test_dirty_fixture_profile(self):
        result = self.data.profile()
        self.assertEqual(result["rows"], 4)
        self.assertEqual(result["columns"][0]["surrounding_whitespace"], 1)
        age = result["columns"][1]
        self.assertEqual(age["missing"], 1)
        self.assertEqual(age["compatible_nonempty"]["integer"], 2)

    def test_quality_rule_evaluation(self):
        issues = self.data.check({"age": {"required": True, "type": "integer", "min": 13}, "group": {"enum": ["A", "B"]}})
        self.assertEqual([(r["row"], r["column"], r["code"]) for r in issues], [(0,"age","below_min"),(1,"age","below_min"),(2,"age","missing"),(3,"age","type"),(3,"group","enum")])

    def test_exact_and_key_duplicates(self):
        self.assertEqual(self.data.duplicates(), [])
        self.assertEqual(self.data.duplicates(["group"]), [[0, 1]])
        other = Dataset(["key", "value"], [["a", "x"], ["a", "x"], ["a", "y"]])
        self.assertEqual(other.duplicates(), [[0, 1]])
        self.assertEqual(other.duplicates(["key"]), [[0,1,2]])

    def test_deterministic_reviewable_cleaning(self):
        first = self.data.propose(trim=["name"], missing={"age": "unknown"}, drop_duplicates=True)
        self.assertEqual(first, self.data.propose(trim=["name"], missing={"age": "unknown"}, drop_duplicates=True))
        self.assertEqual(first["removed_rows"], [1])
        self.assertEqual(first["changes"][0], {"row":0,"column":"name","before":" Ada ","after":"Ada","reasons":["trim"]})
        cleaned = self.data.apply(first)
        self.assertEqual(len(cleaned.rows), 3)
        self.assertEqual(cleaned.rows[1][1], "unknown")
        self.assertEqual(self.data.rows[0][0], " Ada ")

    def test_exact_undo_restores_duplicates_and_whitespace(self):
        proposal = self.data.propose(trim=["name"], missing={"age": ""}, drop_duplicates=True)
        cleaned = self.data.apply(proposal)
        self.assertEqual(cleaned.undo(proposal).snapshot(), self.data.snapshot())
        self.assertEqual(cleaned.undo(proposal).fingerprint, self.data.fingerprint)

    def test_stale_and_tampered_proposals_rejected(self):
        proposal = self.data.propose(trim=["name"])
        other = Dataset(self.data.headers, self.data.rows + [["New", "1", "A"]])
        with self.assertRaises(Conflict):
            other.apply(proposal)
        for key, value in [("changes", []), ("target", "fake"), ("original", {})]:
            altered = copy.deepcopy(proposal)
            altered[key] = value
            with self.assertRaises(Conflict):
                self.data.apply(altered)
        cleaned = self.data.apply(proposal)
        altered = copy.deepcopy(proposal)
        altered["original"]["rows"][0][0] = "invented"
        with self.assertRaises(Conflict):
            cleaned.undo(altered)

    def test_csv_unicode_multiline_and_bom_roundtrip(self):
        data = Dataset.from_csv('\ufeffname,note\r\nÉva,"line one\nline two, quoted"\r\n')
        self.assertEqual(data.headers[0], "name")
        self.assertEqual(Dataset.from_csv(data.to_csv()).snapshot(), data.snapshot())

    def test_spreadsheet_safe_export_is_explicit(self):
        data = Dataset(["=HEADER"], [["=DEMO()"], ["  +4"], ["ordinary"]])
        self.assertEqual(Dataset.from_csv(data.to_csv()).snapshot(), data.snapshot())
        safe = Dataset.from_csv(data.to_csv(spreadsheet_safe=True))
        self.assertEqual(safe.headers[0], "'=HEADER")
        self.assertEqual(safe.rows[0][0], "'=DEMO()")
        self.assertEqual(safe.rows[2][0], "ordinary")

    def test_bad_shapes_headers_rules_and_limits(self):
        for content in ["", "a,a\n1,2\n", "a,b\n1\n", "\n"]:
            with self.assertRaises(ValueError):
                Dataset.from_csv(content)
        for rule in [{"absent": {}}, {"age": {"typo": True}}, {"age": {"type": "number"}}, {"age": {"type":"integer", "min":2, "max":1}}, {"age":{"required":1}}]:
            with self.assertRaises(ValueError):
                self.data.check(rule)
        with self.assertRaises(ValueError):
            Dataset(["a"], [["a"]]*10001)

    def test_type_edges_and_numeric_bounds(self):
        data = Dataset(["value"], [["--1"], ["1.2"], ["+3"], ["NaN"], ["Infinity"], ["4"]])
        issues = data.check({"value":{"type":"integer", "max":3}})
        self.assertEqual([(r["row"],r["code"]) for r in issues], [(0,"type"),(1,"type"),(3,"type"),(4,"type"),(5,"above_max")])
        decimal = data.check({"value":{"type":"decimal"}})
        self.assertEqual([r["row"] for r in decimal], [0,3,4])
        dates = Dataset(["date"], [["2028-02-29"], ["2026-02-29"], ["20260101"]])
        self.assertEqual([r["row"] for r in dates.check({"date":{"type":"date"}})], [1,2])

    def test_empty_rows_and_unique_missing_semantics(self):
        empty = Dataset(["a"], [])
        self.assertEqual(empty.profile()["rows"], 0)
        self.assertEqual(empty.check({"a":{"required":True}}), [])
        values = Dataset(["a"], [[" x "], ["x"], [""], [" "]])
        self.assertEqual([i["row"] for i in values.check({"a":{"unique":True}})], [1])

    def test_defensive_copies_and_noop_plan(self):
        rows = self.data.rows
        rows[0][0] = "mutated"
        self.assertEqual(self.data.rows[0][0], " Ada ")
        proposal = self.data.propose()
        self.assertEqual(proposal["changes"], [])
        self.assertEqual(self.data.apply(proposal).fingerprint, self.data.fingerprint)


if __name__ == "__main__":
    unittest.main()
