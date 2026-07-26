"""Unit tests for newsletterDownloader/util.py"""
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from newsletterDownloader.util import (
    ARCHIVE_BASE,
    NEWSLETTER_CATEGORY_NAME,
    _archive_url,
    _get_total_pages,
    _parse_date_from_slug,
    _scrape_archive_page,
    clean_html_for_ebook,
    download_pdf,
    save_html,
    scrape_all_issues,
    scrape_issue_details,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _issue_card_html(title, url, date_iso="2026-07-13"):
    return f"""
    <article>
        <h3><a href="{url}">{title}</a></h3>
        <time datetime="{date_iso}T00:00:00+00:00"></time>
    </article>
    """


# ---------------------------------------------------------------------------
# _archive_url
# ---------------------------------------------------------------------------

class TestArchiveUrl(TestCase):
    def test_page_1_returns_base_url(self):
        self.assertEqual(ARCHIVE_BASE, _archive_url(1))

    def test_page_1_has_no_page_segment(self):
        self.assertNotIn("/page/", _archive_url(1))

    def test_page_n_includes_page_segment(self):
        self.assertIn("/page/3/", _archive_url(3))

    def test_default_page_equals_page_1(self):
        self.assertEqual(_archive_url(), _archive_url(1))


# ---------------------------------------------------------------------------
# _parse_date_from_slug
# ---------------------------------------------------------------------------

class TestParseDateFromSlug(TestCase):
    def test_extracts_date_from_typical_slug(self):
        url = "https://members.f4wonline.com/wrestling-observer-newsletter/july-13-2026-observer-newsletter-kenny-omega/"
        self.assertEqual("July 13, 2026", _parse_date_from_slug(url))

    def test_returns_empty_string_when_no_date_prefix(self):
        url = "https://members.f4wonline.com/wrestling-observer-newsletter/how-to-listen/"
        self.assertEqual("", _parse_date_from_slug(url))

    def test_handles_trailing_slash(self):
        url = "https://members.f4wonline.com/wrestling-observer-newsletter/march-05-2026-issue/"
        self.assertEqual("March 05, 2026", _parse_date_from_slug(url))


# ---------------------------------------------------------------------------
# _get_total_pages
# ---------------------------------------------------------------------------

class TestGetTotalPages(TestCase):
    def _pagination_html(self, page_numbers):
        links = "".join(
            f'<a href="https://members.f4wonline.com/wrestling-observer-newsletter/page/{n}/">{n}</a>'
            for n in page_numbers
        )
        return f"<html><body>{links}</body></html>"

    @patch("newsletterDownloader.util.fetch_page")
    def test_returns_max_page_from_links(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text=self._pagination_html([2, 3, 5]))
        self.assertEqual(5, _get_total_pages(MagicMock()))

    @patch("newsletterDownloader.util.fetch_page")
    def test_returns_1_when_no_pagination(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="<html><body>No pages</body></html>")
        self.assertEqual(1, _get_total_pages(MagicMock()))

    @patch("newsletterDownloader.util.fetch_page")
    def test_returns_1_when_fetch_fails(self, mock_fetch):
        mock_fetch.return_value = None
        self.assertEqual(1, _get_total_pages(MagicMock()))


# ---------------------------------------------------------------------------
# _scrape_archive_page
# ---------------------------------------------------------------------------

class TestScrapeArchivePage(TestCase):
    @patch("newsletterDownloader.util.fetch_page")
    def test_returns_issue_list(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_issue_card_html("July 13, 2026 Observer Newsletter",
                                   "https://members.f4wonline.com/wrestling-observer-newsletter/issue-1/")
        )
        results = _scrape_archive_page(1, MagicMock())
        self.assertEqual(1, len(results))
        self.assertEqual("July 13, 2026 Observer Newsletter", results[0]["title"])

    @patch("newsletterDownloader.util.fetch_page")
    def test_extracts_date_from_time_element(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_issue_card_html("Issue", "https://members.f4wonline.com/wrestling-observer-newsletter/issue-1/",
                                   "2026-01-15")
        )
        results = _scrape_archive_page(1, MagicMock())
        self.assertIn("January", results[0]["date"])
        self.assertIn("2026", results[0]["date"])

    @patch("newsletterDownloader.util.fetch_page")
    def test_falls_back_to_slug_date_when_no_time_element(self, mock_fetch):
        html = (
            '<article><h3><a href="https://members.f4wonline.com/wrestling-observer-newsletter/'
            'july-13-2026-observer-newsletter-issue/">Issue</a></h3></article>'
        )
        mock_fetch.return_value = MagicMock(text=html)
        results = _scrape_archive_page(1, MagicMock())
        self.assertEqual("July 13, 2026", results[0]["date"])

    @patch("newsletterDownloader.util.fetch_page")
    def test_sets_show_name(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_issue_card_html("Issue", "https://members.f4wonline.com/wrestling-observer-newsletter/issue-1/")
        )
        results = _scrape_archive_page(1, MagicMock())
        self.assertEqual(NEWSLETTER_CATEGORY_NAME, results[0]["show"])

    @patch("newsletterDownloader.util.fetch_page")
    def test_skips_category_links(self, mock_fetch):
        html = '<article><h3><a href="https://members.f4wonline.com/category/newsletters/">Cat</a></h3></article>'
        mock_fetch.return_value = MagicMock(text=html)
        self.assertEqual([], _scrape_archive_page(1, MagicMock()))

    @patch("newsletterDownloader.util.fetch_page")
    def test_returns_empty_on_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = None
        self.assertEqual([], _scrape_archive_page(1, MagicMock()))


# ---------------------------------------------------------------------------
# scrape_all_issues
# ---------------------------------------------------------------------------

class TestScrapeAllIssues(TestCase):
    def _issue(self, title="Issue"):
        return {"title": title, "url": "https://members.f4wonline.com/x/", "date": "", "show": NEWSLETTER_CATEGORY_NAME}

    @patch("newsletterDownloader.util.time.sleep")
    @patch("newsletterDownloader.util._get_total_pages")
    @patch("newsletterDownloader.util._scrape_archive_page")
    def test_respects_max_pages(self, mock_scrape, mock_pages, _sleep):
        mock_pages.return_value = 10
        mock_scrape.return_value = [self._issue()]
        results = scrape_all_issues(MagicMock(), max_pages=2)
        self.assertEqual(2, len(results))

    @patch("newsletterDownloader.util.time.sleep")
    @patch("newsletterDownloader.util._get_total_pages")
    @patch("newsletterDownloader.util._scrape_archive_page")
    def test_combines_issues_across_pages(self, mock_scrape, mock_pages, _sleep):
        mock_pages.return_value = 3
        mock_scrape.return_value = [self._issue(), self._issue()]
        results = scrape_all_issues(MagicMock())
        self.assertEqual(6, len(results))

    @patch("newsletterDownloader.util._get_total_pages")
    @patch("newsletterDownloader.util._scrape_archive_page")
    def test_sleeps_between_pages(self, mock_scrape, mock_pages):
        mock_pages.return_value = 2
        mock_scrape.return_value = []
        with patch("newsletterDownloader.util.time.sleep") as mock_sleep:
            scrape_all_issues(MagicMock(), page_delay=0.25)
            self.assertEqual(2, mock_sleep.call_count)
            mock_sleep.assert_called_with(0.25)


# ---------------------------------------------------------------------------
# scrape_issue_details
# ---------------------------------------------------------------------------

class TestScrapeIssueDetails(TestCase):
    @patch("newsletterDownloader.util.fetch_page")
    def test_extracts_pdf_url_from_anchor(self, mock_fetch):
        html = '<article><a href="https://members.f4wonline.com/files/issue.pdf">Download</a></article>'
        mock_fetch.return_value = MagicMock(text=html)
        details = scrape_issue_details("https://members.f4wonline.com/x/", MagicMock())
        self.assertEqual("https://members.f4wonline.com/files/issue.pdf", details["pdf_url"])

    @patch("newsletterDownloader.util.fetch_page")
    def test_extracts_pdf_url_with_query_string(self, mock_fetch):
        html = (
            '<article><a href="https://members.f4wonline.com/files/issue.pdf?token=abc123">'
            "Download</a></article>"
        )
        mock_fetch.return_value = MagicMock(text=html)
        details = scrape_issue_details("https://members.f4wonline.com/x/", MagicMock())
        self.assertEqual(
            "https://members.f4wonline.com/files/issue.pdf?token=abc123", details["pdf_url"]
        )

    @patch("newsletterDownloader.util.fetch_page")
    def test_pdf_url_none_when_not_found(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="<article><p>No pdf here</p></article>")
        details = scrape_issue_details("https://members.f4wonline.com/x/", MagicMock())
        self.assertIsNone(details["pdf_url"])

    @patch("newsletterDownloader.util.fetch_page")
    def test_extracts_full_html_content_not_truncated(self, mock_fetch):
        paragraphs = "".join(f"<p>Paragraph number {i} with enough content to matter here.</p>" for i in range(5))
        html = f'<div class="entry-content">{paragraphs}</div>'
        mock_fetch.return_value = MagicMock(text=html)
        details = scrape_issue_details("https://members.f4wonline.com/x/", MagicMock())
        self.assertEqual(5, details["html_content"].count("<p>"))

    @patch("newsletterDownloader.util.fetch_page")
    def test_html_content_none_when_no_container_found(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="<html><body>nothing</body></html>")
        details = scrape_issue_details("https://members.f4wonline.com/x/", MagicMock())
        self.assertIsNone(details["html_content"])

    @patch("newsletterDownloader.util.fetch_page")
    def test_returns_empty_defaults_on_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = None
        details = scrape_issue_details("https://members.f4wonline.com/x/", MagicMock())
        self.assertIsNone(details["pdf_url"])
        self.assertIsNone(details["html_content"])


# ---------------------------------------------------------------------------
# clean_html_for_ebook
# ---------------------------------------------------------------------------

class TestCleanHtmlForEbook(TestCase):
    _SAMPLE = """
    <div class="jeg_share_button share-float jeg_sticky_share clearfix share-normal">
    <div class="jeg_share_float_container"><div class="jeg_sharelist">
    <a class="jeg_btn-facebook"><span>Share on Facebook</span></a><a class="jeg_btn-twitter"><span>Share on Twitter</span></a>
    </div></div> </div>
    <div class="content-inner">
    <p class="has-text-align-center"><a href="https://example.com/issue.pdf"><strong>Click here to read this issue in PDF form</strong></a></p>
    <p>Real article paragraph one.</p>
    <p>The reality is that shareholders were unhappy with the deal.</p>
    </div>
    """

    def test_removes_share_widget(self):
        result = clean_html_for_ebook(self._SAMPLE)
        self.assertNotIn("jeg_share_button", result)
        self.assertNotIn("Share on Facebook", result)

    def test_removes_pdf_link_paragraph(self):
        result = clean_html_for_ebook(self._SAMPLE)
        self.assertNotIn("read this issue in pdf form", result.lower())

    def test_keeps_real_article_paragraphs(self):
        result = clean_html_for_ebook(self._SAMPLE)
        self.assertIn("Real article paragraph one.", result)

    def test_does_not_strip_unrelated_text_containing_share_substring(self):
        result = clean_html_for_ebook(self._SAMPLE)
        self.assertIn("shareholders were unhappy", result)

    def test_handles_content_with_no_matching_elements(self):
        result = clean_html_for_ebook("<p>Just a normal paragraph.</p>")
        self.assertIn("Just a normal paragraph.", result)


# ---------------------------------------------------------------------------
# save_html
# ---------------------------------------------------------------------------

class TestSaveHtml(TestCase):
    def test_writes_wrapped_document(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "issue.html"
            self.assertTrue(save_html("<p>Body text</p>", dest, "My Issue"))
            content = dest.read_text(encoding="utf-8")
            self.assertIn("<title>My Issue</title>", content)
            self.assertIn("<p>Body text</p>", content)

    def test_creates_parent_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "subdir" / "issue.html"
            save_html("<p>Body</p>", dest, "Title")
            self.assertTrue(dest.exists())

    def test_escapes_title_ampersand_and_angle_brackets(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "issue.html"
            save_html("<p>Body</p>", dest, "Rhodes & Punk <Live>")
            content = dest.read_text(encoding="utf-8")
            self.assertIn("<title>Rhodes &amp; Punk &lt;Live&gt;</title>", content)
            self.assertNotIn("<title>Rhodes & Punk <Live></title>", content)

    @patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied"))
    def test_returns_false_on_oserror(self, _mock_mkdir):
        self.assertFalse(save_html("<p>Body</p>", Path("/fake/issue.html"), "Title"))


# ---------------------------------------------------------------------------
# download_pdf
# ---------------------------------------------------------------------------

class TestDownloadPdf(TestCase):
    def test_delegates_to_stream_download(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "issue.pdf"
            mock_resp = MagicMock()
            mock_resp.iter_content.return_value = [b"PDFDATA"]
            mock_session = MagicMock()
            mock_session.get.return_value = mock_resp
            result = download_pdf("https://example.com/issue.pdf", dest, mock_session)
            self.assertTrue(result)
            self.assertEqual(b"PDFDATA", dest.read_bytes())


if __name__ == "__main__":
    main()
