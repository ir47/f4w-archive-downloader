"""Unit tests for runner.py"""
import io
from datetime import datetime
from unittest import TestCase, main
from unittest.mock import patch

from podcastDownloader.runner import (
    _build_parser,
    _in_date_range,
    _parse_date_arg,
    _print_show_list,
)
from podcastDownloader.util import SHOW_SLUGS


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------

class TestBuildParser(TestCase):
    def setUp(self):
        self.parser = _build_parser()

    def test_show_argument_accepted(self):
        args = self.parser.parse_args(["--show", "wrestling-observer-radio"])
        self.assertEqual("wrestling-observer-radio", args.show)

    def test_show_short_flag(self):
        args = self.parser.parse_args(["-s", "wor"])
        self.assertEqual("wor", args.show)

    def test_all_argument_accepted(self):
        args = self.parser.parse_args(["--all"])
        self.assertTrue(args.all)

    def test_all_short_flag(self):
        args = self.parser.parse_args(["-A"])
        self.assertTrue(args.all)

    def test_list_shows_argument_accepted(self):
        args = self.parser.parse_args(["--list-shows"])
        self.assertTrue(args.list_shows)

    def test_show_and_all_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--show", "wor", "--all"])

    def test_requires_one_target_argument(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args([])

    def test_output_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--output", "/tmp/pods"])
        self.assertEqual("/tmp/pods", args.output)

    def test_output_short_flag(self):
        args = self.parser.parse_args(["-s", "wor", "-o", "/tmp/pods"])
        self.assertEqual("/tmp/pods", args.output)

    def test_output_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.output)

    def test_start_date_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--start", "January 1, 2025"])
        self.assertEqual("January 1, 2025", args.start)

    def test_end_date_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--end", "March 17, 2026"])
        self.assertEqual("March 17, 2026", args.end)

    def test_start_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.start)

    def test_end_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.end)

    def test_max_pages_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--max-pages", "5"])
        self.assertEqual(5, args.max_pages)

    def test_max_pages_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.max_pages)

    def test_no_yearly_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--no-yearly"])
        self.assertTrue(args.no_yearly)

    def test_no_yearly_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.no_yearly)

    def test_no_monthly_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--no-monthly"])
        self.assertTrue(args.no_monthly)

    def test_no_monthly_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.no_monthly)

    def test_page_delay_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--page-delay", "2.5"])
        self.assertAlmostEqual(2.5, args.page_delay)

    def test_page_delay_default(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertAlmostEqual(1.0, args.page_delay)

    def test_episode_delay_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--episode-delay", "1.0"])
        self.assertAlmostEqual(1.0, args.episode_delay)

    def test_episode_delay_default(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertAlmostEqual(0.5, args.episode_delay)

    def test_overwrite_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--overwrite"])
        self.assertTrue(args.overwrite)

    def test_overwrite_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.overwrite)

    def test_dry_run_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_dry_run_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.dry_run)


# ---------------------------------------------------------------------------
# _parse_date_arg
# ---------------------------------------------------------------------------

class TestParseDateArg(TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(_parse_date_arg(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_parse_date_arg(""))

    def test_valid_date_parsed_correctly(self):
        result = _parse_date_arg("March 17, 2026")
        self.assertEqual(datetime(2026, 3, 17), result)

    def test_valid_date_january(self):
        result = _parse_date_arg("January 01, 2025")
        self.assertEqual(datetime(2025, 1, 1), result)

    def test_valid_date_december(self):
        result = _parse_date_arg("December 31, 2024")
        self.assertEqual(datetime(2024, 12, 31), result)

    def test_iso_format_exits(self):
        with self.assertRaises(SystemExit):
            _parse_date_arg("2026-03-17")

    def test_garbage_input_exits(self):
        with self.assertRaises(SystemExit):
            _parse_date_arg("not a date at all")

    def test_partial_date_exits(self):
        with self.assertRaises(SystemExit):
            _parse_date_arg("March 2026")


# ---------------------------------------------------------------------------
# _in_date_range
# ---------------------------------------------------------------------------

class TestInDateRange(TestCase):
    def _ep(self, dt):
        return {"datetime": dt}

    def test_none_datetime_returns_true(self):
        self.assertTrue(_in_date_range({"datetime": None}, None, None))

    def test_missing_datetime_key_returns_true(self):
        self.assertTrue(_in_date_range({}, None, None))

    def test_no_bounds_returns_true(self):
        self.assertTrue(_in_date_range(self._ep(datetime(2026, 3, 17)), None, None))

    def test_within_range_returns_true(self):
        ep = self._ep(datetime(2026, 3, 17))
        self.assertTrue(_in_date_range(ep, datetime(2026, 1, 1), datetime(2026, 12, 31)))

    def test_before_start_returns_false(self):
        ep = self._ep(datetime(2025, 12, 31))
        self.assertFalse(_in_date_range(ep, datetime(2026, 1, 1), None))

    def test_after_end_returns_false(self):
        ep = self._ep(datetime(2026, 4, 1))
        self.assertFalse(_in_date_range(ep, None, datetime(2026, 3, 31)))

    def test_on_start_boundary_returns_true(self):
        dt = datetime(2026, 1, 1)
        self.assertTrue(_in_date_range(self._ep(dt), dt, None))

    def test_on_end_boundary_returns_true(self):
        dt = datetime(2026, 12, 31)
        self.assertTrue(_in_date_range(self._ep(dt), None, dt))

    def test_only_start_with_future_episode(self):
        ep = self._ep(datetime(2026, 6, 1))
        self.assertTrue(_in_date_range(ep, datetime(2026, 1, 1), None))

    def test_only_end_with_past_episode(self):
        ep = self._ep(datetime(2026, 6, 1))
        self.assertTrue(_in_date_range(ep, None, datetime(2026, 12, 31)))

    def test_exactly_one_day_before_start(self):
        ep = self._ep(datetime(2025, 12, 31))
        self.assertFalse(_in_date_range(ep, datetime(2026, 1, 1), datetime(2026, 12, 31)))

    def test_exactly_one_day_after_end(self):
        ep = self._ep(datetime(2027, 1, 1))
        self.assertFalse(_in_date_range(ep, datetime(2026, 1, 1), datetime(2026, 12, 31)))


# ---------------------------------------------------------------------------
# _print_show_list
# ---------------------------------------------------------------------------

class TestPrintShowList(TestCase):
    def test_all_slugs_present_in_output(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _print_show_list()
            output = mock_out.getvalue()
        for slug in SHOW_SLUGS:
            self.assertIn(slug, output, f"Slug '{slug}' missing from show list output")

    def test_all_display_names_present_in_output(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _print_show_list()
            output = mock_out.getvalue()
        for name in SHOW_SLUGS.values():
            self.assertIn(name, output, f"Show name '{name}' missing from show list output")

    def test_output_contains_header(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _print_show_list()
            output = mock_out.getvalue()
        self.assertIn("Available shows", output)


if __name__ == "__main__":
    main()
