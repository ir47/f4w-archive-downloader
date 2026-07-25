"""Unit tests for f4wCommon/dates.py"""
from datetime import datetime
from unittest import TestCase, main

from f4wCommon.dates import enrich_with_date, in_date_range, parse_date, parse_date_arg


FMT = "%B %d, %Y"


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------

class TestParseDate(TestCase):
    def test_valid_date(self):
        self.assertEqual(datetime(2026, 3, 17), parse_date("March 17, 2026", FMT))

    def test_valid_date_january(self):
        self.assertEqual(datetime(2025, 1, 1), parse_date("January 01, 2025", FMT))

    def test_invalid_format_returns_none(self):
        self.assertIsNone(parse_date("2026-03-17", FMT))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_date("not a date", FMT))

    def test_none_returns_none(self):
        self.assertIsNone(parse_date(None, FMT))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_date("", FMT))

    def test_respects_custom_format(self):
        self.assertEqual(datetime(2026, 7, 13), parse_date("2026-07-13", "%Y-%m-%d"))


# ---------------------------------------------------------------------------
# enrich_with_date
# ---------------------------------------------------------------------------

class TestEnrichWithDate(TestCase):
    def test_enriches_valid_date(self):
        item = {"date": "March 17, 2026", "title": "Ep"}
        enrich_with_date(item, FMT)
        self.assertEqual("2026", item["year"])
        self.assertEqual("March", item["month"])
        self.assertEqual("17", item["day"])
        self.assertIsInstance(item["datetime"], datetime)

    def test_fallback_on_invalid_date(self):
        item = {"date": "bad date"}
        enrich_with_date(item, FMT)
        self.assertEqual("Unknown", item["year"])
        self.assertEqual("Unknown", item["month"])
        self.assertEqual("00", item["day"])
        self.assertIsNone(item["datetime"])

    def test_fallback_on_missing_date_key(self):
        item = {}
        enrich_with_date(item, FMT)
        self.assertEqual("Unknown", item["year"])
        self.assertIsNone(item["datetime"])

    def test_returns_same_dict(self):
        item = {"date": "March 17, 2026"}
        self.assertIs(item, enrich_with_date(item, FMT))

    def test_day_padded_with_zero(self):
        item = {"date": "March 05, 2026"}
        enrich_with_date(item, FMT)
        self.assertEqual("05", item["day"])

    def test_custom_date_key(self):
        item = {"published": "March 17, 2026"}
        enrich_with_date(item, FMT, date_key="published")
        self.assertEqual("2026", item["year"])

    def test_custom_unknown_value(self):
        item = {"date": "bad date"}
        enrich_with_date(item, FMT, unknown="N/A")
        self.assertEqual("N/A", item["year"])


# ---------------------------------------------------------------------------
# parse_date_arg
# ---------------------------------------------------------------------------

class TestParseDateArg(TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(parse_date_arg(None, FMT, "January 1, 2025"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_date_arg("", FMT, "January 1, 2025"))

    def test_valid_date_parsed_correctly(self):
        result = parse_date_arg("March 17, 2026", FMT, "January 1, 2025")
        self.assertEqual(datetime(2026, 3, 17), result)

    def test_garbage_input_exits(self):
        with self.assertRaises(SystemExit):
            parse_date_arg("not a date at all", FMT, "January 1, 2025")

    def test_respects_custom_format(self):
        result = parse_date_arg("2026-07-13", "%Y-%m-%d", "2025-01-01")
        self.assertEqual(datetime(2026, 7, 13), result)


# ---------------------------------------------------------------------------
# in_date_range
# ---------------------------------------------------------------------------

class TestInDateRange(TestCase):
    def test_missing_datetime_key_returns_true(self):
        self.assertTrue(in_date_range({}, None, None))

    def test_none_datetime_returns_true(self):
        self.assertTrue(in_date_range({"datetime": None}, None, None))

    def test_no_bounds_returns_true(self):
        self.assertTrue(in_date_range({"datetime": datetime(2026, 3, 17)}, None, None))

    def test_before_start_returns_false(self):
        item = {"datetime": datetime(2025, 12, 31)}
        self.assertFalse(in_date_range(item, datetime(2026, 1, 1), None))

    def test_after_end_returns_false(self):
        item = {"datetime": datetime(2026, 4, 1)}
        self.assertFalse(in_date_range(item, None, datetime(2026, 3, 31)))

    def test_within_range_returns_true(self):
        item = {"datetime": datetime(2026, 3, 17)}
        self.assertTrue(in_date_range(item, datetime(2026, 1, 1), datetime(2026, 12, 31)))

    def test_on_start_boundary_returns_true(self):
        dt = datetime(2026, 1, 1)
        self.assertTrue(in_date_range({"datetime": dt}, dt, None))

    def test_on_end_boundary_returns_true(self):
        dt = datetime(2026, 12, 31)
        self.assertTrue(in_date_range({"datetime": dt}, None, dt))


if __name__ == "__main__":
    main()
