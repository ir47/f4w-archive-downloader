"""Unit tests for f4wCommon/scrape.py"""
from bs4 import BeautifulSoup
from unittest import TestCase, main
from unittest.mock import MagicMock

from f4wCommon.scrape import (
    extract_time_element_date,
    find_content_container,
    get_total_pages,
)


# ---------------------------------------------------------------------------
# find_content_container
# ---------------------------------------------------------------------------

class TestFindContentContainer(TestCase):
    def test_finds_entry_content_div(self):
        soup = BeautifulSoup('<div class="entry-content"><p>Body</p></div>', "html.parser")
        result = find_content_container(soup)
        self.assertEqual("Body", result.get_text(strip=True))

    def test_finds_post_content_div(self):
        soup = BeautifulSoup('<div class="post-content"><p>Body</p></div>', "html.parser")
        self.assertIsNotNone(find_content_container(soup))

    def test_falls_back_to_article_tag(self):
        soup = BeautifulSoup('<article><p>Body</p></article>', "html.parser")
        result = find_content_container(soup)
        self.assertEqual("article", result.name)

    def test_returns_none_when_nothing_matches(self):
        soup = BeautifulSoup('<div class="sidebar"><p>Not it</p></div>', "html.parser")
        self.assertIsNone(find_content_container(soup))


# ---------------------------------------------------------------------------
# extract_time_element_date
# ---------------------------------------------------------------------------

class TestExtractTimeElementDate(TestCase):
    ISO = "%Y-%m-%d"
    OUT = "%B %d, %Y"

    def test_extracts_and_reformats_date(self):
        soup = BeautifulSoup('<article><time datetime="2026-01-15T00:00:00+00:00"></time></article>', "html.parser")
        result = extract_time_element_date(soup.find("article"), self.ISO, self.OUT)
        self.assertEqual("January 15, 2026", result)

    def test_returns_empty_string_when_no_time_element(self):
        soup = BeautifulSoup('<article><p>No time here</p></article>', "html.parser")
        result = extract_time_element_date(soup.find("article"), self.ISO, self.OUT)
        self.assertEqual("", result)

    def test_returns_empty_string_when_container_is_none(self):
        self.assertEqual("", extract_time_element_date(None, self.ISO, self.OUT))

    def test_returns_empty_string_on_malformed_datetime_attr(self):
        soup = BeautifulSoup('<article><time datetime="not-a-date"></time></article>', "html.parser")
        result = extract_time_element_date(soup.find("article"), self.ISO, self.OUT)
        self.assertEqual("", result)


# ---------------------------------------------------------------------------
# get_total_pages
# ---------------------------------------------------------------------------

class TestGetTotalPages(TestCase):
    def _pagination_html(self, page_numbers):
        links = "".join(f'<a href="https://example.com/page/{n}/">{n}</a>' for n in page_numbers)
        return f"<html><body>{links}</body></html>"

    def test_returns_max_page_from_links(self):
        fetch_fn = MagicMock(return_value=MagicMock(text=self._pagination_html([2, 3, 5])))
        result = get_total_pages(lambda p: f"https://example.com/page/{p}/", MagicMock(), fetch_fn=fetch_fn)
        self.assertEqual(5, result)

    def test_returns_1_when_no_pagination(self):
        fetch_fn = MagicMock(return_value=MagicMock(text="<html><body>No pages</body></html>"))
        result = get_total_pages(lambda p: "https://example.com/", MagicMock(), fetch_fn=fetch_fn)
        self.assertEqual(1, result)

    def test_returns_1_when_fetch_fails(self):
        fetch_fn = MagicMock(return_value=None)
        result = get_total_pages(lambda p: "https://example.com/", MagicMock(), fetch_fn=fetch_fn)
        self.assertEqual(1, result)

    def test_calls_page_url_fn_with_page_1(self):
        page_url_fn = MagicMock(return_value="https://example.com/")
        fetch_fn = MagicMock(return_value=MagicMock(text="<html></html>"))
        get_total_pages(page_url_fn, MagicMock(), fetch_fn=fetch_fn)
        page_url_fn.assert_called_once_with(1)


if __name__ == "__main__":
    main()
