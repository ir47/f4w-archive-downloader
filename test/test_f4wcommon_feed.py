"""Unit tests for f4wCommon/feed.py"""
from unittest import TestCase, main
from unittest.mock import MagicMock

from f4wCommon.feed import FEED_ACCEPT, FeedPoller, parse_feed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _feed(items_xml: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:media="http://search.yahoo.com/mrss/">
<channel>
    <title>Podcasts &#8211; F4W/WON</title>
    {items_xml}
</channel>
</rss>"""


def _item(
    title="WOR: Test episode",
    link="https://www.f4wonline.com/podcasts/wrestling-observer-radio/wor-test/",
    pub_date="Mon, 27 Jul 2026 08:11:00 +0000",
    creator="Bryan Alvarez",
    enclosure='<enclosure url="https://media001.f4wonline.com/dmdocuments/072626wo.mp3" length="0" type="audio/mpeg" />',
    categories=("Wrestling Observer Radio", "mainstory"),
    content="<p>A long enough paragraph of show notes to survive the minimum length filter.</p>",
    media='<media:content medium="image" type="image/jpeg" url="https://www.f4wonline.com/cover.jpg" />',
):
    category_xml = "".join(f"<category><![CDATA[{c}]]></category>" for c in categories)
    return f"""
    <item>
        <title>{title}</title>
        <link>{link}</link>
        <dc:creator><![CDATA[{creator}]]></dc:creator>
        <pubDate>{pub_date}</pubDate>
        {category_xml}
        <description><![CDATA[An excerpt.]]></description>
        <content:encoded><![CDATA[{content}]]></content:encoded>
        {enclosure}
        {media}
    </item>"""


def _response(status_code=200, text="", headers=None):
    return MagicMock(status_code=status_code, text=text, headers=headers or {})


# ---------------------------------------------------------------------------
# parse_feed
# ---------------------------------------------------------------------------

class TestParseFeed(TestCase):
    def test_returns_one_dict_per_item(self):
        items = parse_feed(_feed(_item() + _item(title="Second")))
        self.assertEqual(2, len(items))

    def test_extracts_core_fields(self):
        item = parse_feed(_feed(_item()))[0]
        self.assertEqual("WOR: Test episode", item["title"])
        self.assertEqual(
            "https://www.f4wonline.com/podcasts/wrestling-observer-radio/wor-test/",
            item["link"],
        )
        self.assertEqual("Bryan Alvarez", item["creator"])

    def test_extracts_enclosure(self):
        item = parse_feed(_feed(_item()))[0]
        self.assertEqual(
            "https://media001.f4wonline.com/dmdocuments/072626wo.mp3",
            item["enclosure_url"],
        )
        self.assertEqual("audio/mpeg", item["enclosure_type"])

    def test_extracts_categories_in_order(self):
        item = parse_feed(_feed(_item()))[0]
        self.assertEqual(["Wrestling Observer Radio", "mainstory"], item["categories"])

    def test_extracts_media_image(self):
        item = parse_feed(_feed(_item()))[0]
        self.assertEqual("https://www.f4wonline.com/cover.jpg", item["image_url"])

    def test_ignores_non_image_media_content(self):
        media = '<media:content type="video/mp4" url="https://example.com/clip.mp4" />'
        item = parse_feed(_feed(_item(media=media)))[0]
        self.assertIsNone(item["image_url"])

    def test_parses_pub_date(self):
        item = parse_feed(_feed(_item()))[0]
        self.assertEqual((2026, 7, 27), item["published"].timetuple()[:3])

    def test_keeps_feed_local_date_without_converting(self):
        # 23:30 in a +0100 feed is the 27th locally and the 27th here too;
        # converting to UTC would file it under the 26th.
        item = parse_feed(_feed(_item(pub_date="Mon, 27 Jul 2026 00:30:00 +0100")))[0]
        self.assertEqual(27, item["published"].day)

    def test_unparseable_pub_date_becomes_none(self):
        item = parse_feed(_feed(_item(pub_date="whenever")))[0]
        self.assertIsNone(item["published"])

    def test_missing_enclosure_leaves_url_none(self):
        item = parse_feed(_feed(_item(enclosure="")))[0]
        self.assertIsNone(item["enclosure_url"])
        self.assertEqual("", item["enclosure_type"])

    def test_decodes_numeric_character_references(self):
        item = parse_feed(_feed(_item(title="Kenny Omega &#038; CM Punk")))[0]
        self.assertEqual("Kenny Omega & CM Punk", item["title"])

    def test_feed_with_no_items_returns_empty_list(self):
        self.assertEqual([], parse_feed(_feed("")))

    def test_malformed_xml_returns_none(self):
        self.assertIsNone(parse_feed("<rss><channel><item>truncated"))

    def test_html_login_page_returns_none(self):
        self.assertIsNone(parse_feed("<html><body>Please log in</body></html>"))

    def test_every_key_present_on_a_bare_item(self):
        bare = "<item><title>T</title><link>https://example.com/</link></item>"
        item = parse_feed(_feed(bare))[0]
        for key in (
            "title", "link", "published", "creator", "summary", "content",
            "categories", "enclosure_url", "enclosure_type", "image_url",
        ):
            self.assertIn(key, item)


# ---------------------------------------------------------------------------
# FeedPoller
# ---------------------------------------------------------------------------

class TestFeedPoller(TestCase):
    def _poller(self, fetch_fn):
        return FeedPoller("https://example.com/feed/", MagicMock(), fetch_fn=fetch_fn)

    def _headers_of(self, fetch_fn):
        return fetch_fn.call_args.kwargs["headers"]

    def test_returns_parsed_items(self):
        fetch_fn = MagicMock(return_value=_response(text=_feed(_item())))
        self.assertEqual(1, len(self._poller(fetch_fn).poll()))

    def test_returns_none_when_fetch_fails(self):
        self.assertIsNone(self._poller(MagicMock(return_value=None)).poll())

    def test_returns_none_when_response_is_not_a_feed(self):
        fetch_fn = MagicMock(return_value=_response(text="<html>nope</html>"))
        self.assertIsNone(self._poller(fetch_fn).poll())

    def test_304_returns_empty_list(self):
        fetch_fn = MagicMock(return_value=_response(status_code=304))
        self.assertEqual([], self._poller(fetch_fn).poll())

    def test_requests_feed_content_type(self):
        fetch_fn = MagicMock(return_value=_response(text=_feed("")))
        self._poller(fetch_fn).poll()
        self.assertEqual(FEED_ACCEPT, self._headers_of(fetch_fn)["Accept"])

    def test_first_poll_sends_no_validators(self):
        fetch_fn = MagicMock(return_value=_response(text=_feed("")))
        self._poller(fetch_fn).poll()
        headers = self._headers_of(fetch_fn)
        self.assertNotIn("If-None-Match", headers)
        self.assertNotIn("If-Modified-Since", headers)

    def test_second_poll_sends_validators_from_the_first(self):
        headers = {"ETag": '"abc123"', "Last-Modified": "Mon, 27 Jul 2026 21:05:50 GMT"}
        fetch_fn = MagicMock(return_value=_response(text=_feed(""), headers=headers))
        poller = self._poller(fetch_fn)
        poller.poll()
        poller.poll()
        sent = self._headers_of(fetch_fn)
        self.assertEqual('"abc123"', sent["If-None-Match"])
        self.assertEqual("Mon, 27 Jul 2026 21:05:50 GMT", sent["If-Modified-Since"])

    def test_304_without_validators_keeps_the_previous_ones(self):
        responses = [
            _response(text=_feed(""), headers={"ETag": '"abc123"'}),
            _response(status_code=304),
            _response(text=_feed("")),
        ]
        fetch_fn = MagicMock(side_effect=responses)
        poller = self._poller(fetch_fn)
        poller.poll()
        poller.poll()
        poller.poll()
        self.assertEqual('"abc123"', self._headers_of(fetch_fn)["If-None-Match"])

    def test_failed_fetch_does_not_clear_validators(self):
        responses = [
            _response(text=_feed(""), headers={"ETag": '"abc123"'}),
            None,
            _response(text=_feed("")),
        ]
        fetch_fn = MagicMock(side_effect=responses)
        poller = self._poller(fetch_fn)
        poller.poll()
        poller.poll()
        poller.poll()
        self.assertEqual('"abc123"', self._headers_of(fetch_fn)["If-None-Match"])


if __name__ == "__main__":
    main()
