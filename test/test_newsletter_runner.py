"""Unit tests for newsletterDownloader/runner.py"""
from datetime import datetime
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from newsletterDownloader.runner import (
    _build_parser,
    _download_html_format,
    _download_kindle_format,
    _download_pdf_format,
    _in_date_range,
    _parse_date_arg,
    _run_downloads,
)


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------

class TestBuildParser(TestCase):
    def setUp(self):
        self.parser = _build_parser()

    def test_format_default_is_pdf(self):
        args = self.parser.parse_args([])
        self.assertEqual("pdf", args.format)

    def test_format_accepts_html(self):
        args = self.parser.parse_args(["--format", "html"])
        self.assertEqual("html", args.format)

    def test_format_accepts_kindle(self):
        args = self.parser.parse_args(["--format", "kindle"])
        self.assertEqual("kindle", args.format)

    def test_format_rejects_invalid_choice(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--format", "docx"])

    def test_output_argument(self):
        args = self.parser.parse_args(["--output", "/tmp/newsletters"])
        self.assertEqual("/tmp/newsletters", args.output)

    def test_start_date_argument(self):
        args = self.parser.parse_args(["--start", "January 1, 2025"])
        self.assertEqual("January 1, 2025", args.start)

    def test_end_date_argument(self):
        args = self.parser.parse_args(["--end", "March 17, 2026"])
        self.assertEqual("March 17, 2026", args.end)

    def test_max_pages_argument(self):
        args = self.parser.parse_args(["--max-pages", "5"])
        self.assertEqual(5, args.max_pages)

    def test_no_yearly_flag(self):
        args = self.parser.parse_args(["--no-yearly"])
        self.assertTrue(args.no_yearly)

    def test_no_monthly_flag(self):
        args = self.parser.parse_args(["--no-monthly"])
        self.assertTrue(args.no_monthly)

    def test_issue_delay_default(self):
        args = self.parser.parse_args([])
        self.assertAlmostEqual(0.5, args.issue_delay)

    def test_issue_delay_argument(self):
        args = self.parser.parse_args(["--issue-delay", "2.0"])
        self.assertAlmostEqual(2.0, args.issue_delay)

    def test_overwrite_flag(self):
        args = self.parser.parse_args(["--overwrite"])
        self.assertTrue(args.overwrite)

    def test_dry_run_flag(self):
        args = self.parser.parse_args(["--dry-run"])
        self.assertTrue(args.dry_run)


# ---------------------------------------------------------------------------
# _parse_date_arg / _in_date_range
# ---------------------------------------------------------------------------

class TestParseDateArg(TestCase):
    def test_none_returns_none(self):
        self.assertIsNone(_parse_date_arg(None))

    def test_valid_date_parsed_correctly(self):
        self.assertEqual(datetime(2026, 7, 13), _parse_date_arg("July 13, 2026"))

    def test_garbage_input_exits(self):
        with self.assertRaises(SystemExit):
            _parse_date_arg("not a date at all")


class TestInDateRange(TestCase):
    def test_missing_datetime_key_returns_true(self):
        self.assertTrue(_in_date_range({}, None, None))

    def test_before_start_returns_false(self):
        issue = {"datetime": datetime(2025, 12, 31)}
        self.assertFalse(_in_date_range(issue, datetime(2026, 1, 1), None))

    def test_within_range_returns_true(self):
        issue = {"datetime": datetime(2026, 7, 13)}
        self.assertTrue(_in_date_range(issue, datetime(2026, 1, 1), datetime(2026, 12, 31)))


# ---------------------------------------------------------------------------
# Format handlers
# ---------------------------------------------------------------------------

class TestDownloadPdfFormat(TestCase):
    def test_fails_when_no_pdf_url(self):
        issue = {"url": "https://members.f4wonline.com/x/"}
        details = {"pdf_url": None, "html_content": None}
        self.assertFalse(_download_pdf_format(issue, details, MagicMock(), MagicMock()))

    @patch("newsletterDownloader.runner.download_pdf")
    def test_downloads_when_pdf_url_present(self, mock_download):
        mock_download.return_value = True
        issue = {"url": "https://members.f4wonline.com/x/"}
        details = {"pdf_url": "https://members.f4wonline.com/x.pdf", "html_content": None}
        self.assertTrue(_download_pdf_format(issue, details, MagicMock(), MagicMock()))
        mock_download.assert_called_once()


class TestDownloadHtmlFormat(TestCase):
    def test_fails_when_no_html_content(self):
        issue = {"url": "https://members.f4wonline.com/x/", "title": "Issue"}
        details = {"pdf_url": None, "html_content": None}
        self.assertFalse(_download_html_format(issue, details, MagicMock(), MagicMock()))

    @patch("newsletterDownloader.runner.save_html")
    def test_saves_when_html_content_present(self, mock_save):
        mock_save.return_value = True
        issue = {"url": "https://members.f4wonline.com/x/", "title": "Issue"}
        details = {"pdf_url": None, "html_content": "<p>Body</p>"}
        self.assertTrue(_download_html_format(issue, details, MagicMock(), MagicMock()))
        mock_save.assert_called_once()


class TestDownloadKindleFormat(TestCase):
    def test_fails_when_no_pdf_or_html(self):
        issue = {"url": "https://members.f4wonline.com/x/", "title": "Issue"}
        details = {"pdf_url": None, "html_content": None}
        self.assertFalse(_download_kindle_format(issue, details, MagicMock(), MagicMock()))

    @patch("newsletterDownloader.runner.convert_to_ebook")
    @patch("newsletterDownloader.runner.save_html")
    def test_prefers_html_source_when_available(self, mock_save, mock_convert):
        mock_save.return_value = True
        mock_convert.return_value = True
        issue = {"url": "https://members.f4wonline.com/x/", "title": "Issue"}
        details = {"pdf_url": "https://members.f4wonline.com/x.pdf", "html_content": "<p>Body</p>"}
        self.assertTrue(_download_kindle_format(issue, details, MagicMock(), MagicMock()))
        mock_save.assert_called_once()
        mock_convert.assert_called_once()

    @patch("newsletterDownloader.runner.convert_to_ebook")
    @patch("newsletterDownloader.runner.clean_html_for_ebook")
    @patch("newsletterDownloader.runner.save_html")
    def test_cleans_html_before_saving_for_conversion(self, mock_save, mock_clean, mock_convert):
        mock_clean.return_value = "<p>Cleaned</p>"
        mock_save.return_value = True
        mock_convert.return_value = True
        issue = {"url": "https://members.f4wonline.com/x/", "title": "Issue"}
        details = {"pdf_url": None, "html_content": "<p>Raw with share buttons</p>"}
        self.assertTrue(_download_kindle_format(issue, details, MagicMock(), MagicMock()))
        mock_clean.assert_called_once_with("<p>Raw with share buttons</p>")
        mock_save.assert_called_once_with("<p>Cleaned</p>", mock_save.call_args[0][1], "Issue")

    @patch("newsletterDownloader.runner.convert_to_ebook")
    @patch("newsletterDownloader.runner.download_pdf")
    def test_falls_back_to_pdf_when_no_html(self, mock_download, mock_convert):
        mock_download.return_value = True
        mock_convert.return_value = True
        issue = {"url": "https://members.f4wonline.com/x/", "title": "Issue"}
        details = {"pdf_url": "https://members.f4wonline.com/x.pdf", "html_content": None}
        self.assertTrue(_download_kindle_format(issue, details, MagicMock(), MagicMock()))
        mock_download.assert_called_once()
        mock_convert.assert_called_once()

    @patch("newsletterDownloader.runner.convert_to_ebook")
    @patch("newsletterDownloader.runner.save_html")
    def test_fails_when_conversion_fails(self, mock_save, mock_convert):
        mock_save.return_value = True
        mock_convert.return_value = False
        issue = {"url": "https://members.f4wonline.com/x/", "title": "Issue"}
        details = {"pdf_url": None, "html_content": "<p>Body</p>"}
        self.assertFalse(_download_kindle_format(issue, details, MagicMock(), MagicMock()))


# ---------------------------------------------------------------------------
# _run_downloads — environment / auth gating
# ---------------------------------------------------------------------------

class TestRunDownloadsGating(TestCase):
    @patch("newsletterDownloader.runner.calibre_available")
    def test_exits_before_login_when_calibre_missing_for_kindle_format(self, mock_calibre):
        mock_calibre.return_value = False
        args = _build_parser().parse_args(["--format", "kindle"])
        with patch("newsletterDownloader.runner.login") as mock_login:
            with self.assertRaises(SystemExit):
                _run_downloads(args)
            mock_login.assert_not_called()

    @patch("newsletterDownloader.runner.create_session")
    @patch("newsletterDownloader.runner.login")
    def test_exits_when_login_fails(self, mock_login, mock_create_session):
        mock_login.return_value = False
        args = _build_parser().parse_args(["--format", "pdf"])
        with self.assertRaises(SystemExit):
            _run_downloads(args)

    @patch("newsletterDownloader.runner.scrape_all_issues")
    @patch("newsletterDownloader.runner.create_session")
    @patch("newsletterDownloader.runner.login")
    def test_returns_without_error_when_no_issues_found(self, mock_login, mock_create_session, mock_scrape):
        mock_login.return_value = True
        mock_scrape.return_value = []
        args = _build_parser().parse_args(["--format", "pdf"])
        _run_downloads(args)  # should not raise

    @patch("newsletterDownloader.runner.scrape_all_issues")
    @patch("newsletterDownloader.runner.create_session")
    @patch("newsletterDownloader.runner.login")
    def test_calls_login_with_no_explicit_credentials(self, mock_login, mock_create_session, mock_scrape):
        # Env-var/prompt fallback now lives in f4wCommon.auth.login itself
        # (see test_f4wcommon_auth.py) — the runner just calls login(session).
        mock_login.return_value = True
        mock_scrape.return_value = []
        args = _build_parser().parse_args(["--format", "pdf"])
        _run_downloads(args)
        mock_login.assert_called_once_with(mock_create_session.return_value)

    @patch("newsletterDownloader.runner.scrape_issue_details")
    @patch("newsletterDownloader.runner.generate_download_directories")
    @patch("newsletterDownloader.runner.scrape_all_issues")
    @patch("newsletterDownloader.runner.create_session")
    @patch("newsletterDownloader.runner.login")
    def test_skips_issue_when_directory_creation_fails(
        self, mock_login, mock_create_session, mock_scrape_issues, mock_gen_dirs, mock_scrape_details
    ):
        mock_login.return_value = True
        mock_scrape_issues.return_value = [
            {"title": "Issue", "url": "https://members.f4wonline.com/x/", "date": "July 13, 2026"}
        ]
        mock_gen_dirs.return_value = False
        args = _build_parser().parse_args(["--format", "pdf"])
        _run_downloads(args)  # should not raise
        mock_scrape_details.assert_not_called()


if __name__ == "__main__":
    main()
