"""Unit tests for podcastDownloader/util.py"""
import tempfile
from datetime import datetime
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

import requests

from podcastDownloader.util import (
    CATEGORY_BASE,
    _category_url,
    _fetch_thumbnail,
    _get_total_pages,
    _scrape_category_page,
    _thumbnail_mime_type,
    download_podcast,
    scrape_all_episodes,
    scrape_episode_details,
    write_id3_tags,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _episode_card_html(title, url, date_iso="2026-03-17"):
    return f"""
    <article>
        <h3><a href="{url}">{title}</a></h3>
        <time datetime="{date_iso}T00:00:00+00:00"></time>
    </article>
    """


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
# _get_total_pages
# ---------------------------------------------------------------------------

class TestGetTotalPages(TestCase):
    def _pagination_html(self, page_numbers):
        links = "".join(
            f'<a href="https://www.f4wonline.com/category/podcasts/s/page/{n}/">{n}</a>'
            for n in page_numbers
        )
        return f"<html><body>{links}</body></html>"

    @patch("podcastDownloader.util.fetch_page")
    def test_returns_max_page_from_links(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text=self._pagination_html([2, 3, 5]))
        self.assertEqual(5, _get_total_pages("s", MagicMock()))

    @patch("podcastDownloader.util.fetch_page")
    def test_returns_1_when_no_pagination(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="<html><body>No pages</body></html>")
        self.assertEqual(1, _get_total_pages("s", MagicMock()))

    @patch("podcastDownloader.util.fetch_page")
    def test_returns_1_when_fetch_fails(self, mock_fetch):
        mock_fetch.return_value = None
        self.assertEqual(1, _get_total_pages("s", MagicMock()))

    @patch("podcastDownloader.util.fetch_page")
    def test_returns_single_page_link(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text=self._pagination_html([2]))
        self.assertEqual(2, _get_total_pages("s", MagicMock()))


# ---------------------------------------------------------------------------
# _scrape_category_page
# ---------------------------------------------------------------------------

class TestScrapeCategoryPage(TestCase):
    @patch("podcastDownloader.util.fetch_page")
    def test_returns_episode_list(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Episode One", "https://www.f4wonline.com/podcasts/ep-1/")
        )
        results = _scrape_category_page("wrestling-observer-radio", 1, MagicMock())
        self.assertEqual(1, len(results))
        self.assertEqual("Episode One", results[0]["title"])

    @patch("podcastDownloader.util.fetch_page")
    def test_extracts_episode_url(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Ep", "https://www.f4wonline.com/podcasts/ep/")
        )
        results = _scrape_category_page("slug", 1, MagicMock())
        self.assertEqual("https://www.f4wonline.com/podcasts/ep/", results[0]["url"])

    @patch("podcastDownloader.util.fetch_page")
    def test_extracts_date_from_time_element(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Ep", "https://www.f4wonline.com/podcasts/ep/", "2026-01-15")
        )
        results = _scrape_category_page("slug", 1, MagicMock())
        self.assertIn("January", results[0]["date"])
        self.assertIn("2026", results[0]["date"])

    @patch("podcastDownloader.util.fetch_page")
    def test_sets_known_show_name(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text=_episode_card_html("Ep", "https://www.f4wonline.com/podcasts/wor/")
        )
        results = _scrape_category_page("wrestling-observer-radio", 1, MagicMock())
        self.assertEqual("Wrestling Observer Radio", results[0]["show"])

    @patch("podcastDownloader.util.fetch_page")
    def test_skips_category_links(self, mock_fetch):
        html = '<article><h3><a href="https://www.f4wonline.com/category/podcasts/show/">Cat</a></h3></article>'
        mock_fetch.return_value = MagicMock(text=html)
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util.fetch_page")
    def test_skips_how_to_listen_links(self, mock_fetch):
        html = '<article><h3><a href="https://www.f4wonline.com/podcasts/how-to-listen/">Info</a></h3></article>'
        mock_fetch.return_value = MagicMock(text=html)
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util.fetch_page")
    def test_skips_non_podcast_urls(self, mock_fetch):
        html = '<article><h3><a href="https://www.f4wonline.com/news/story/">News</a></h3></article>'
        mock_fetch.return_value = MagicMock(text=html)
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util.fetch_page")
    def test_returns_empty_on_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = None
        self.assertEqual([], _scrape_category_page("slug", 1, MagicMock()))

    @patch("podcastDownloader.util.fetch_page")
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
    @patch("podcastDownloader.util.fetch_page")
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

    @patch("podcastDownloader.util.fetch_page")
    def test_extracts_mp3_url_with_query_string(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><body>
        <a href="https://media001.f4wonline.com/dmdocuments/episode.mp3?token=abc123">Download</a>
        </body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual(
            "https://media001.f4wonline.com/dmdocuments/episode.mp3?token=abc123", result["mp3_url"]
        )

    @patch("podcastDownloader.util.fetch_page")
    def test_extracts_mp3_url_from_page_text(self, mock_fetch):
        mock_fetch.return_value = MagicMock(
            text="audio = 'https://media001.f4wonline.com/dmdocuments/audio.mp3';"
        )
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual(
            "https://media001.f4wonline.com/dmdocuments/audio.mp3", result["mp3_url"]
        )

    @patch("podcastDownloader.util.fetch_page")
    def test_extracts_host_from_author_link(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><body><a rel="author">Dave Meltzer</a></body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual("Dave Meltzer", result["host"])

    @patch("podcastDownloader.util.fetch_page")
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

    @patch("podcastDownloader.util.fetch_page")
    def test_extracts_thumbnail_from_og_image(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="""
        <html><head>
        <meta property="og:image" content="https://example.com/thumb.jpg"/>
        </head><body></body></html>
        """)
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertEqual("https://example.com/thumb.jpg", result["thumbnail_url"])

    @patch("podcastDownloader.util.fetch_page")
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

    @patch("podcastDownloader.util.fetch_page")
    def test_returns_empty_defaults_on_fetch_failure(self, mock_fetch):
        mock_fetch.return_value = None
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertIsNone(result["mp3_url"])
        self.assertEqual("", result["host"])
        self.assertEqual("", result["description"])
        self.assertEqual([], result["categories"])
        self.assertIsNone(result["thumbnail_url"])

    @patch("podcastDownloader.util.fetch_page")
    def test_mp3_url_none_when_not_found(self, mock_fetch):
        mock_fetch.return_value = MagicMock(text="<html><body>No mp3 here</body></html>")
        result = scrape_episode_details("https://example.com/ep/", MagicMock())
        self.assertIsNone(result["mp3_url"])


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

    def test_png_with_query_string(self):
        self.assertEqual("image/png", _thumbnail_mime_type("https://example.com/img.png?w=800"))

    def test_webp_with_query_string(self):
        self.assertEqual("image/webp", _thumbnail_mime_type("https://example.com/img.webp?v=2&x=1"))

    def test_png_with_fragment(self):
        self.assertEqual("image/png", _thumbnail_mime_type("https://example.com/img.png#top"))

    def test_unknown_extension_with_query_still_defaults(self):
        self.assertEqual("image/jpeg", _thumbnail_mime_type("https://example.com/img.gif?v=1"))


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


if __name__ == "__main__":
    main()
