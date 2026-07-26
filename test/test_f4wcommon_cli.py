"""Unit tests for f4wCommon/cli.py"""
import argparse

from pathlib import Path
from datetime import datetime
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from f4wCommon.cli import add_common_arguments, login_or_exit, parse_cli_date


def _parser(item_noun="item", delay_aliases=()):
    parser = argparse.ArgumentParser()
    add_common_arguments(
        parser,
        default_output=Path("/downloads"),
        item_noun=item_noun,
        delay_aliases=delay_aliases,
    )
    return parser


# ---------------------------------------------------------------------------
# add_common_arguments
# ---------------------------------------------------------------------------

class TestAddCommonArguments(TestCase):
    def setUp(self):
        self.parser = _parser()

    def test_output_default_is_none(self):
        self.assertIsNone(self.parser.parse_args([]).output)

    def test_output_short_flag(self):
        self.assertEqual("/tmp/x", self.parser.parse_args(["-o", "/tmp/x"]).output)

    def test_start_and_end_default_to_none(self):
        args = self.parser.parse_args([])
        self.assertIsNone(args.start)
        self.assertIsNone(args.end)

    def test_max_pages_parsed_as_int(self):
        self.assertEqual(5, self.parser.parse_args(["--max-pages", "5"]).max_pages)

    def test_no_yearly_and_no_monthly_default_false(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.no_yearly)
        self.assertFalse(args.no_monthly)

    def test_no_yearly_flag(self):
        self.assertTrue(self.parser.parse_args(["--no-yearly"]).no_yearly)

    def test_page_delay_default(self):
        self.assertAlmostEqual(1.0, self.parser.parse_args([]).page_delay)

    def test_item_delay_default(self):
        self.assertAlmostEqual(0.5, self.parser.parse_args([]).item_delay)

    def test_item_delay_parsed_as_float(self):
        self.assertAlmostEqual(2.5, self.parser.parse_args(["--item-delay", "2.5"]).item_delay)

    def test_overwrite_and_dry_run_default_false(self):
        args = self.parser.parse_args([])
        self.assertFalse(args.overwrite)
        self.assertFalse(args.dry_run)

    def test_item_noun_appears_in_help(self):
        parser = _parser(item_noun="episode")
        self.assertIn("episode", parser.format_help())


class TestDelayAliases(TestCase):
    def setUp(self):
        self.parser = _parser(delay_aliases=("--episode-delay",))

    def test_alias_sets_item_delay(self):
        self.assertAlmostEqual(3.0, self.parser.parse_args(["--episode-delay", "3.0"]).item_delay)

    def test_alias_absent_leaves_default_intact(self):
        # default=SUPPRESS on the alias must not clobber --item-delay's default.
        self.assertAlmostEqual(0.5, self.parser.parse_args([]).item_delay)

    def test_primary_flag_still_works_alongside_alias(self):
        self.assertAlmostEqual(1.5, self.parser.parse_args(["--item-delay", "1.5"]).item_delay)

    def test_alias_hidden_from_help(self):
        self.assertNotIn("--episode-delay", self.parser.format_help())

    def test_multiple_aliases_all_accepted(self):
        parser = _parser(delay_aliases=("--episode-delay", "--issue-delay"))
        self.assertAlmostEqual(4.0, parser.parse_args(["--issue-delay", "4.0"]).item_delay)


# ---------------------------------------------------------------------------
# parse_cli_date
# ---------------------------------------------------------------------------

class TestParseCliDate(TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(parse_cli_date(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_cli_date(""))

    def test_valid_date_parsed(self):
        self.assertEqual(datetime(2026, 3, 17), parse_cli_date("March 17, 2026"))

    def test_iso_format_exits(self):
        with self.assertRaises(SystemExit):
            parse_cli_date("2026-03-17")

    def test_garbage_exits(self):
        with self.assertRaises(SystemExit):
            parse_cli_date("not a date at all")

    def test_partial_date_exits(self):
        with self.assertRaises(SystemExit):
            parse_cli_date("March 2026")


# ---------------------------------------------------------------------------
# login_or_exit
# ---------------------------------------------------------------------------

class TestLoginOrExit(TestCase):
    @patch("f4wCommon.cli.login", return_value=True)
    def test_returns_normally_on_success(self, _login):
        login_or_exit(MagicMock())  # should not raise

    @patch("f4wCommon.cli.login", return_value=False)
    def test_exits_on_failure(self, _login):
        with self.assertRaises(SystemExit):
            login_or_exit(MagicMock())

    @patch("f4wCommon.cli.login", return_value=True)
    def test_passes_session_through(self, mock_login):
        session = MagicMock()
        login_or_exit(session)
        mock_login.assert_called_once_with(session)


if __name__ == "__main__":
    main()
