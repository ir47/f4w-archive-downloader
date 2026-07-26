"""Unit tests for runner.py"""
import io

from unittest.mock import patch
from unittest import TestCase, main

from podcastDownloader.util import SHOW_SLUGS
from podcastDownloader.runner import _build_parser, _print_show_list


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

    def test_item_delay_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--item-delay", "1.0"])
        self.assertAlmostEqual(1.0, args.item_delay)

    def test_item_delay_default(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertAlmostEqual(0.5, args.item_delay)

    def test_legacy_episode_delay_alias_still_accepted(self):
        args = self.parser.parse_args(["--show", "wor", "--episode-delay", "1.0"])
        self.assertAlmostEqual(1.0, args.item_delay)

    def test_legacy_alias_does_not_clobber_default(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertAlmostEqual(0.5, args.item_delay)

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
