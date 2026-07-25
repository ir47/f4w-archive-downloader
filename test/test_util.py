"""Unit tests for util.py"""
import io
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

import requests
from bs4 import BeautifulSoup

from podcastDownloader.util import (
    CATEGORY_BASE,
    HTTP_RETRY_COUNT,
    SHOW_SLUGS,
    _category_url,
    _fetch_page,
    _fetch_thumbnail,
    _find_input_name,
    _get_total_pages,
    _scrape_category_page,
    _thumbnail_mime_type,
    build_download_path,
    create_session,
    download_podcast,
    enrich_episode,
    generate_download_directories,
    login,
    parse_episode_date,
    sanitize_filename,
    scrape_all_episodes,
    scrape_episode_details,
    write_id3_tags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_form(input_names):
    """Build a BeautifulSoup <form> with the given input names."""
    html = "<form>" + "".join(
        f'<input name="{n}" type="text"/>' for n in input_names
    ) + "</form>"
    return BeautifulSoup(html, "html.parser").find("form")


def _episode_card_html(title, url, date_iso="2026-03-17"):
    return f"""
    <article>
        <h3><a href="{url}">{title}</a></h3>
        <time datetime="{date_iso}T00:00:00+00:00"></time>
    </article>
    """


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------

class TestCreateSession(TestCase):
    def test_returns_requests_session(self):
        self.assertIsInstance(create_session(), requests.Session)

    def test_session_has_user_agent(self):
        session = create_session()
        self.assertIn("Mozilla", session.headers.get("User-Agent", ""))

    def test_session_has_accept_header(self):
        self.assertIn("Accept", create_session().headers)

    def test_session_has_referer_header(self):
        self.assertIn("Referer", create_session().headers)


# ---------------------------------------------------------------------------
# _find_input_name
# ---------------------------------------------------------------------------

class TestFindInputName(TestCase):
    def test_finds_by_email_candidate(self):
        form = _make_form(["email_address"])
        self.assertEqual("email_address", _find_input_name(form, ["email"]))

    def test_finds_by_password_candidate(self):
        form = _make_form(["user_password"])
        self.assertEqual("user_password", _find_input_name(form, ["password", "pass"]))

    def test_returns_none_when_no_match(self):
        form = _make_form(["fullname", "address"])
        self.assertIsNone(_find_input_name(form, ["email", "username"]))

    def test_case_insensitive(self):
        form = _make_form(["EMAIL"])
        self.assertEqual("EMAIL", _find_input_name(form, ["email"]))

    def test_returns_first_match(self):
        form = _make_form(["username", "user_email"])
        self.assertEqual("username", _find_input_name(form, ["user"]))

    def test_empty_form_returns_none(self):
        form = BeautifulSoup("<form></form>", "html.parser").find("form")
        self.assertIsNone(_find_input_name(form, ["email"]))


# ---------------------------------------------------------------------------
# _category_url
# ---------------------------------------------------------------------------

class TestCategoryUrl(TestCase):
    def test_page_1_returns_base_url(self):
        url = _category_url("wrestling-observer-radio", 1)
        self.assertEqual(f"{CATEGORY_BASE}wrestling-observer-radio/", url)

    def test_page_1_has_no_page_segment(self):
        self.assertNotIn("/page/", _category_url("wrestling-observer-radio", 1))

    def test_page_n_includes_page_segment(self):
        self.assertIn("/page/3/", _category_url("wrestling-observer-radio", 3))

    def test_slug_present_in_url(self):
        self.assertIn("dragon-king", _category_url("dragon-king", 1))

    def test_default_page_equals_page_1(self):
        self.assertEqual(_category_url("dragon-king"), _category_url("dragon-king", 1))


# ---------------------------------------------------------------------------
# _fetch_page
# ---------------------------------------------------------------------------

class TestFetchPage(TestCase):
    @patch("podcastDownloader.util.time.sleep")
    def test_returns_response_on_success(self, _sleep):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.get.return_value = mock_resp
        self.assertIs(mock_resp, _fetch_page("https://example.com", mock_session))

    @patch("podcastDownloader.util.time.sleep")
    def test_returns_none_after_all_retries_fail(self, _sleep):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("timeout")
        self.assertIsNone(_fetch_page("https://example.com", mock_session))

    @patch("podcastDownloader.util.time.sleep")
    def test_retries_then_succeeds(self, _sleep):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.get.side_effect = [requests.RequestException("err"), mock_resp]
        self.assertIs(mock_resp, _fetch_page("https://example.com", mock_session))

    @patch("podcastDownloader.util.time.sleep")
    def test_calls_raise_for_status(self, _sleep):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.get.return_value = mock_resp
        _fetch_page("https://example.com", mock_session)
        mock_resp.raise_for_status.assert_called_once()

    @patch("podcastDownloader.util.time.sleep")
    def test_retries_exactly_http_retry_count_times(self, _sleep):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("err")
        _fetch_page("https://example.com", mock_session)
        self.assertEqual(HTTP_RETRY_COUNT, mock_session.get.call_count)


# ---------------------------------------------------------------------------
# _get_total_pages
# ---------------------------------------------------------------------------

class TestGetTotalPages(TestCase):
    def _pagination_html(self, page_numbers):
        links = "".join(
            f'<a href="https://www.f4wonline.com/category/podcasts/s/page/{n}/">{n}</a>'
            for n in page_numbers
        )
        return f"<html><body>{links}</body></html>"

    @patch("podcastDownloader.util._fetch_page")
    def test_returns_max_page_from_links(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text=self._pagination_html([2, 3, 5]))
        self.assertEqual(5, _get_total_pages("s", MagicMock()))

    @patch("podcastDownloader.util._fetch_page")
    def test_returns_1_when_no_pagination(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="<html><body>No pages</body></html>")
        self.assertEqual(1, _get_total_pages("s", MagicMock()))

    @patch("podcastDownloader.util._fetch_page")
    def test_returns_1_when_fetch_fails(self, mock_fetch):
        mock_fetch.return_value = None
        self.assertEqual(1, _get_total_pages("s", MagicMock()))

    @patch("podcastDownloader.util._fetch_page")
    def test_returns_single_page_link(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text=self._pagination_html([2]))
        self.assertEqual(2, _get_total_pages("s", MagicMock()))


# ---------------------------------------------------------------------------
# _scrape_category_page
# ---------------------------------------------------------------------------

class TestScrapeCategoryPage(TestCase):
    @patch("podcastDownloader.util._fetch_page")
    def test_returns_episode_list(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Episode One", "https://www.f4wonline.com/podcasts/ep-1/")
        )
        results = _scrape_category_page("wrestling-observer-radio", 1, MagicMock())
        self.assertEqual(1, len(results))
        self.assertEqual("Episode One", results[0]["title"])

    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_episode_url(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Ep", "https://www.f4wonline.com/podcasts/ep/")
        )
        results = _scrape_category_page("slug", 1, MagicMock())
        self.assertEqual("https://www.f4wonline.com/podcasts/ep/", results[0]["url"])

    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_date_from_time_element(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Ep", "https://www.f4wonline.com/podcasts/ep/", "2026-01-15")
        )
        results = _scrape_category_page("slug", 1, MagicMock())
        self.assertIn("January", results[0]["date"])
        self.assertIn("2026", results[0]["date"])

    @patch("podcastDownloader.util._fetch_page")
    def test_sets_known_show_name(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Ep", "https://www.f4wonline.com/podcasts/wor/")
        )
        results = _scrape_category_page("wrestling-observer-radio", 1, MagicMock())
        self.assertEqual("Wrestling Observer Radio", results[0]["show"])

    @patch("podcastDownloader.util._fetch_page")
    def test_skips_category_links(self, mock_fetch):
        html = '<article><h3><a href="https://www.f4wonline.com/category/podcasts/show/">Cat</a></h3></article>'
        mock_fetch.return_value = MagicMock(text=html)
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util._fetch_page")
    def test_skips_how_to_listen_links(self, mock_fetch):
        html = '<article><h3><a href="https://www.f4wonline.com/podcasts/how-to-listen/">Info</a></h3></article>'
        mock_fetch.return_value = MagicMock(text=html)
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util._fetch_page")
    def test_skips_non_podcast_urls(self, mock_fetch):
        html = '<article><h3><a href="https://www.f4wonline.com/news/story/">News</a></h3></article>'
        mock_fetch.return_value = MagicMock(text=html)
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util._fetch_page")
    def test_returns_empty_on_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = None
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util._fetch_page")
    def test_show_slug_recorded_on_episode(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Ep", "https://www.f4wonline.com/podcasts/ep/")
        )
        results = _scrape_category_page("dragon-king", 1, MagicMock())
        self.assertEqual("dragon-king", results[0]["show_slug"])


# ---------------------------------------------------------------------------
# scrape_all_episodes
# ---------------------------------------------------------------------------

class TestScrapeAllEpisodes(TestCase):
    def _ep(self, title="Ep"):
        return {"title": title, "url": "https://x.com/", "date": "", "show": "Show", "show_slug": "s"}

    @patch("podcastDownloader.util.time.sleep")
    @patch("podcastDownloader.util._scrape_category_page")
    @patch("podcastDownloader.util._get_total_pages")
    def test_scrapes_single_show(self, mock_pages, mock_scrape, _sleep):
        mock_pages.return_value = 1
        mock_scrape.return_value = [self._ep("Ep1")]
        results = scrape_all_episodes(MagicMock(), show_filter="wrestling-observer-radio", max_pages=1)
        self.assertEqual(1, len(results))
        self.assertEqual("Ep1", results[0]["title"])

    @patch("podcastDownloader.util.time.sleep")
    @patch("podcastDownloader.util._scrape_category_page")
    @patch("podcastDownloader.util._get_total_pages")
    def test_respects_max_pages(self, mock_pages, mock_scrape, _sleep):
        mock_pages.return_value = 10
        mock_scrape.return_value = [self._ep()]
        scrape_all_episodes(MagicMock(), show_filter="wrestling-observer-radio", max_pages=2)
        self.assertEqual(2, mock_scrape.call_count)

    @patch("podcastDownloader.util.time.sleep")
    @patch("podcastDownloader.util._scrape_category_page")
    @patch("podcastDownloader.util._get_total_pages")
    def test_combines_episodes_across_pages(self, mock_pages, mock_scrape, _sleep):
        mock_pages.return_value = 2
        mock_scrape.side_effect = [[self._ep("A")], [self._ep("B")]]
        results = scrape_all_episodes(MagicMock(), show_filter="wrestling-observer-radio")
        self.assertEqual(2, len(results))

    @patch("podcastDownloader.util.time.sleep")
    @patch("podcastDownloader.util._scrape_category_page")
    @patch("podcastDownloader.util._get_total_pages")
    @patch("podcastDownloader.util.SHOW_SLUGS", {"show-a": "Show A", "show-b": "Show B"})
    def test_scrapes_all_shows_when_no_filter(self, mock_pages, mock_scrape, _sleep):
        mock_pages.return_value = 1
        mock_scrape.return_value = [self._ep()]
        scrape_all_episodes(MagicMock(), show_filter=None, max_pages=1)
        self.assertEqual(2, mock_pages.call_count)

    @patch("podcastDownloader.util.time.sleep")
    @patch("podcastDownloader.util._scrape_category_page")
    @patch("podcastDownloader.util._get_total_pages")
    def test_sleeps_between_pages(self, mock_pages, mock_scrape, mock_sleep):
        mock_pages.return_value = 2
        mock_scrape.return_value = []
        scrape_all_episodes(MagicMock(), show_filter="wrestling-observer-radio", page_delay=0.5)
        self.assertTrue(mock_sleep.called)


# ---------------------------------------------------------------------------
# scrape_episode_details
# ---------------------------------------------------------------------------

class TestScrapeEpisodeDetails(TestCase):
    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_mp3_url_from_anchor(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><body>
        <a href="https://media001.f4wonline.com/dmdocuments/episode.mp3">Download</a>
        </body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual(
            "https://media001.f4wonline.com/dmdocuments/episode.mp3", result["mp3_url"]
        )

    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_mp3_url_from_page_text(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text="audio = 'https://media001.f4wonline.com/dmdocuments/audio.mp3';"
        )
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual(
            "https://media001.f4wonline.com/dmdocuments/audio.mp3", result["mp3_url"]
        )

    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_host_from_author_link(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><body><a rel="author">Dave Meltzer</a></body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual("Dave Meltzer", result["host"])

    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_categories(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><body>
        <a rel="category tag">Wrestling Observer Radio</a>
        <a rel="category tag">Podcasts</a>
        </body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertIn("Wrestling Observer Radio", result["categories"])
        self.assertIn("Podcasts", result["categories"])

    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_thumbnail_from_og_image(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><head>
        <meta property="og:image" content="https://example.com/thumb.jpg"/>
        </head><body></body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual("https://example.com/thumb.jpg", result["thumbnail_url"])

    @patch("podcastDownloader.util._fetch_page")
    def test_extracts_description_from_article(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><body>
        <article>
          <p>This is the first paragraph with enough characters to pass the minimum length check.</p>
          <p>This is the second paragraph with enough characters to pass the minimum length check too.</p>
        </article>
        </body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertIn("first paragraph", result["description"])

    @patch("podcastDownloader.util._fetch_page")
    def test_returns_empty_defaults_on_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = None
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertIsNone(result["mp3_url"])
        self.assertEqual("", result["host"])
        self.assertEqual("", result["description"])
        self.assertEqual([], result["categories"])
        self.assertIsNone(result["thumbnail_url"])

    @patch("podcastDownloader.util._fetch_page")
    def test_mp3_url_none_when_not_found(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="<html><body>No mp3 here</body></html>")
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertIsNone(result["mp3_url"])


# ---------------------------------------------------------------------------
# parse_episode_date
# ---------------------------------------------------------------------------

class TestParseEpisodeDate(TestCase):
    def test_valid_date(self):
        self.assertEqual(datetime(2026, 3, 17), parse_episode_date("March 17, 2026"))

    def test_valid_date_january(self):
        self.assertEqual(datetime(2025, 1, 1), parse_episode_date("January 01, 2025"))

    def test_valid_date_december(self):
        self.assertEqual(datetime(2024, 12, 31), parse_episode_date("December 31, 2024"))

    def test_invalid_format_returns_none(self):
        self.assertIsNone(parse_episode_date("2026-03-17"))

    def test_garbage_returns_none(self):
        self.assertIsNone(parse_episode_date("not a date"))

    def test_none_returns_none(self):
        self.assertIsNone(parse_episode_date(None))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_episode_date(""))


# ---------------------------------------------------------------------------
# enrich_episode
# ---------------------------------------------------------------------------

class TestEnrichEpisode(TestCase):
    def test_enriches_valid_date(self):
        ep = {"date": "March 17, 2026", "title": "Ep"}
        enrich_episode(ep)
        self.assertEqual("2026", ep["year"])
        self.assertEqual("March", ep["month"])
        self.assertEqual("17", ep["day"])
        self.assertIsInstance(ep["datetime"], datetime)

    def test_fallback_on_invalid_date(self):
        ep = {"date": "bad date"}
        enrich_episode(ep)
        self.assertEqual("Unknown", ep["year"])
        self.assertEqual("Unknown", ep["month"])
        self.assertEqual("00", ep["day"])
        self.assertIsNone(ep["datetime"])

    def test_fallback_on_missing_date_key(self):
        ep = {}
        enrich_episode(ep)
        self.assertEqual("Unknown", ep["year"])
        self.assertIsNone(ep["datetime"])

    def test_returns_same_dict(self):
        ep = {"date": "March 17, 2026"}
        self.assertIs(ep, enrich_episode(ep))

    def test_day_padded_with_zero(self):
        ep = {"date": "March 05, 2026"}
        enrich_episode(ep)
        self.assertEqual("05", ep["day"])


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename(TestCase):
    def test_replaces_backslash(self):
        self.assertEqual("a_b", sanitize_filename("a\\b"))

    def test_replaces_forward_slash(self):
        self.assertEqual("a_b", sanitize_filename("a/b"))

    def test_replaces_colon(self):
        self.assertEqual("a_b", sanitize_filename("a:b"))

    def test_replaces_asterisk(self):
        self.assertEqual("a_b", sanitize_filename("a*b"))

    def test_replaces_question_mark(self):
        self.assertEqual("a_b", sanitize_filename("a?b"))

    def test_replaces_angle_brackets(self):
        self.assertEqual("a_b_c", sanitize_filename("a<b>c"))

    def test_replaces_pipe(self):
        self.assertEqual("a_b", sanitize_filename("a|b"))

    def test_replaces_double_quote(self):
        self.assertEqual("a_b", sanitize_filename('a"b'))

    def test_normal_name_unchanged(self):
        self.assertEqual("Wrestling Observer Radio", sanitize_filename("Wrestling Observer Radio"))

    def test_strips_surrounding_whitespace(self):
        self.assertEqual("name", sanitize_filename("  name  "))

    def test_multiple_bad_chars(self):
        self.assertEqual("Show_ Episode_1", sanitize_filename("Show: Episode/1"))


# ---------------------------------------------------------------------------
# build_download_path
# ---------------------------------------------------------------------------

class TestBuildDownloadPath(TestCase):
    def _ep(self, show="Wrestling Observer Radio", year="2026", month="March"):
        return {"show": show, "year": year, "month": month}

    def test_base_only(self):
        path = build_download_path(Path("/base"), self._ep(), yearly=False, monthly=False)
        self.assertEqual(Path("/base/Wrestling Observer Radio"), path)

    def test_with_yearly(self):
        path = build_download_path(Path("/base"), self._ep(), yearly=True, monthly=False)
        self.assertEqual(Path("/base/Wrestling Observer Radio/2026"), path)

    def test_with_monthly(self):
        path = build_download_path(Path("/base"), self._ep(), yearly=False, monthly=True)
        self.assertEqual(Path("/base/Wrestling Observer Radio/March"), path)

    def test_with_yearly_and_monthly(self):
        path = build_download_path(Path("/base"), self._ep(), yearly=True, monthly=True)
        self.assertEqual(Path("/base/Wrestling Observer Radio/2026/March"), path)

    def test_sanitizes_show_name_with_colon(self):
        ep = self._ep(show="Show: Special")
        path = build_download_path(Path("/base"), ep, yearly=False, monthly=False)
        self.assertNotIn(":", str(path))

    def test_unknown_year_still_included_when_yearly(self):
        ep = self._ep(year="Unknown")
        path = build_download_path(Path("/base"), ep, yearly=True, monthly=False)
        self.assertIn("Unknown", str(path))


# ---------------------------------------------------------------------------
# generate_download_directories
# ---------------------------------------------------------------------------

class TestGenerateDownloadDirectories(TestCase):
    def test_creates_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "a" / "b" / "c"
            generate_download_directories(target)
            self.assertTrue(target.exists())

    def test_returns_true_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_download_directories(Path(tmpdir) / "new")
            self.assertTrue(result)

    def test_returns_true_when_directory_already_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(generate_download_directories(Path(tmpdir)))

    @patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied"))
    def test_returns_false_on_oserror(self, _mock_mkdir):
        self.assertFalse(generate_download_directories(Path("/fake/path")))


# ---------------------------------------------------------------------------
# download_podcast
# ---------------------------------------------------------------------------

class TestDownloadPodcast(TestCase):
    def _streaming_session(self, content=b"FAKEMP3"):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [content]
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        return mock_session

    def test_skips_existing_file_and_returns_true(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            dest = Path(f.name)
            f.write(b"existing")
        try:
            mock_session = MagicMock()
            result = download_podcast("https://example.com/ep.mp3", dest, mock_session, skip_existing=True)
            self.assertTrue(result)
            mock_session.get.assert_not_called()
        finally:
            dest.unlink(missing_ok=True)

    def test_downloads_even_if_file_exists_when_skip_false(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            dest = Path(f.name)
        try:
            download_podcast("https://example.com/ep.mp3", dest, self._streaming_session(), skip_existing=False)
            self._streaming_session().get.assert_not_called()  # fresh mock just to confirm flow
        finally:
            dest.unlink(missing_ok=True)

    def test_returns_true_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "episode.mp3"
            result = download_podcast("https://example.com/ep.mp3", dest, self._streaming_session())
            self.assertTrue(result)

    def test_writes_correct_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "episode.mp3"
            download_podcast("https://example.com/ep.mp3", dest, self._streaming_session(b"CONTENT"))
            self.assertEqual(b"CONTENT", dest.read_bytes())

    def test_returns_false_on_request_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "episode.mp3"
            mock_session = MagicMock()
            mock_session.get.side_effect = requests.RequestException("error")
            result = download_podcast("https://example.com/ep.mp3", dest, mock_session)
            self.assertFalse(result)

    def test_creates_parent_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "subdir" / "episode.mp3"
            download_podcast("https://example.com/ep.mp3", dest, self._streaming_session())
            self.assertTrue(dest.exists())


# ---------------------------------------------------------------------------
# _fetch_thumbnail
# ---------------------------------------------------------------------------

class TestFetchThumbnail(TestCase):
    @patch("podcastDownloader.util.requests.get")
    def test_returns_bytes_on_success(self, mock_get):
        mock_get.return_value = MagicMock(content=b"\xff\xd8\xff")
        self.assertEqual(b"\xff\xd8\xff", _fetch_thumbnail("https://example.com/thumb.jpg"))

    @patch("podcastDownloader.util.requests.get")
    def test_returns_none_on_request_exception(self, mock_get):
        mock_get.side_effect = requests.RequestException("timeout")
        self.assertIsNone(_fetch_thumbnail("https://example.com/thumb.jpg"))

    @patch("podcastDownloader.util.requests.get")
    def test_calls_raise_for_status(self, mock_get):
        mock_resp = MagicMock(content=b"data")
        mock_get.return_value = mock_resp
        _fetch_thumbnail("https://example.com/thumb.jpg")
        mock_resp.raise_for_status.assert_called_once()


# ---------------------------------------------------------------------------
# _thumbnail_mime_type
# ---------------------------------------------------------------------------

class TestThumbnailMimeType(TestCase):
    def test_png(self):
        self.assertEqual("image/png", _thumbnail_mime_type("https://example.com/img.png"))

    def test_webp(self):
        self.assertEqual("image/webp", _thumbnail_mime_type("https://example.com/img.webp"))

    def test_jpg_defaults_to_jpeg(self):
        self.assertEqual("image/jpeg", _thumbnail_mime_type("https://example.com/img.jpg"))

    def test_jpeg(self):
        self.assertEqual("image/jpeg", _thumbnail_mime_type("https://example.com/img.jpeg"))

    def test_unknown_extension_defaults_to_jpeg(self):
        self.assertEqual("image/jpeg", _thumbnail_mime_type("https://example.com/img.gif"))

    def test_uppercase_png(self):
        self.assertEqual("image/png", _thumbnail_mime_type("https://example.com/img.PNG"))

    def test_uppercase_webp(self):
        self.assertEqual("image/webp", _thumbnail_mime_type("https://example.com/img.WEBP"))


# ---------------------------------------------------------------------------
# write_id3_tags
# ---------------------------------------------------------------------------

class TestWriteId3Tags(TestCase):
    def _episode(self):
        return {
            "title": "WOR Episode 1",
            "show": "Wrestling Observer Radio",
            "url": "https://www.f4wonline.com/podcasts/wor/",
            "datetime": datetime(2026, 3, 17),
            "day": "17",
        }

    def _details(self, thumbnail_url=None):
        return {
            "host": "Dave Meltzer",
            "description": "A detailed show description.",
            "categories": ["Wrestling", "Podcasts"],
            "thumbnail_url": thumbnail_url,
        }

    def _temp_mp3(self):
        """Create a temp file that mutagen can write ID3 tags into."""
        f = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        f.write(b"\x00" * 128)
        f.close()
        return Path(f.name)

    def test_writes_title_tag(self):
        from mutagen.id3 import ID3
        dest = self._temp_mp3()
        try:
            write_id3_tags(dest, self._episode(), self._details())
            self.assertEqual("WOR Episode 1", str(ID3(dest)["TIT2"]))
        finally:
            dest.unlink(missing_ok=True)

    def test_writes_artist_tag(self):
        from mutagen.id3 import ID3
        dest = self._temp_mp3()
        try:
            write_id3_tags(dest, self._episode(), self._details())
            self.assertEqual("Dave Meltzer", str(ID3(dest)["TPE1"]))
        finally:
            dest.unlink(missing_ok=True)

    def test_writes_album_tag(self):
        from mutagen.id3 import ID3
        dest = self._temp_mp3()
        try:
            write_id3_tags(dest, self._episode(), self._details())
            self.assertEqual("Wrestling Observer Radio", str(ID3(dest)["TALB"]))
        finally:
            dest.unlink(missing_ok=True)

    def test_writes_track_number(self):
        from mutagen.id3 import ID3
        dest = self._temp_mp3()
        try:
            write_id3_tags(dest, self._episode(), self._details(), track_number=17)
            self.assertEqual("17", str(ID3(dest)["TRCK"]))
        finally:
            dest.unlink(missing_ok=True)

    def test_no_track_tag_when_track_number_is_none(self):
        from mutagen.id3 import ID3
        dest = self._temp_mp3()
        try:
            write_id3_tags(dest, self._episode(), self._details(), track_number=None)
            self.assertNotIn("TRCK", ID3(dest))
        finally:
            dest.unlink(missing_ok=True)

    @patch("podcastDownloader.util._fetch_thumbnail")
    def test_fetches_thumbnail_when_url_provided(self, mock_fetch):
        mock_fetch.return_value = b"\xff\xd8\xff"
        dest = self._temp_mp3()
        try:
            write_id3_tags(dest, self._episode(), self._details("https://example.com/t.jpg"))
            mock_fetch.assert_called_once_with("https://example.com/t.jpg")
        finally:
            dest.unlink(missing_ok=True)

    def test_does_not_raise_on_nonexistent_file(self):
        write_id3_tags(Path("/nonexistent/episode.mp3"), self._episode(), self._details())


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

class TestLogin(TestCase):
    _LOGIN_FORM_HTML = """
    <html><body>
    <form action="https://account.f4wonline.com/login" method="post">
        <input name="user_email" type="text"/>
        <input name="user_password" type="password"/>
        <input name="_token" type="hidden" value="abc123"/>
    </form>
    </body></html>
    """

    def _mock_session(self, get_html, post_url, post_html, cookies=None):
        session = MagicMock()
        session.get.return_value = MagicMock(text=get_html)
        session.post.return_value = MagicMock(url=post_url, text=post_html)
        session.cookies = cookies or []
        return session

    @patch("podcastDownloader.util._prompt_credentials", return_value=("user@example.com", "pass"))
    def test_returns_false_when_login_page_unreachable(self, _creds):
        session = MagicMock()
        session.get.side_effect = requests.RequestException("refused")
        self.assertFalse(login(session))

    @patch("podcastDownloader.util._prompt_credentials", return_value=("user@example.com", "pass"))
    def test_returns_false_when_no_form_on_page(self, _creds):
        session = MagicMock()
        session.get.return_value = MagicMock(text="<html><body><p>No form</p></body></html>")
        self.assertFalse(login(session))

    @patch("podcastDownloader.util._prompt_credentials", return_value=("user@example.com", "pass"))
    def test_returns_false_when_still_on_login_page_after_post(self, _creds):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://account.f4wonline.com/login",
            post_html="",
        )
        self.assertFalse(login(session))

    @patch("podcastDownloader.util._prompt_credentials", return_value=("user@example.com", "pass"))
    def test_returns_true_on_successful_redirect(self, _creds):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome!</body></html>",
        )
        self.assertTrue(login(session))

    @patch("podcastDownloader.util._prompt_credentials", return_value=("user@example.com", "wrong"))
    def test_returns_false_when_error_keyword_in_response(self, _creds):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html='<html><body><p class="error">Invalid username or password</p></body></html>',
        )
        self.assertFalse(login(session))

    @patch("podcastDownloader.util._prompt_credentials", return_value=("user@example.com", "pass"))
    def test_posts_hidden_fields_as_payload(self, _creds):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome</body></html>",
        )
        login(session)
        call_kwargs = session.post.call_args
        payload = call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs[0][1]
        self.assertIn("_token", payload)
        self.assertEqual("abc123", payload["_token"])


if __name__ == "__main__":
    main()
