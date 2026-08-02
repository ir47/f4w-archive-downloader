"""Unit tests for podcastDownloader/feed.py"""
from datetime import datetime, timezone
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from podcastDownloader.feed import (
    _mp3_url,
    create_poller,
    episode_from_item,
    episodes_from_feed,
    feed_url,
    resolve_show,
    scrape_feed_episodes,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parsed_item(**overrides):
    """A feed item in the shape f4wCommon.feed.parse_feed returns."""
    item = {
        "title": "WOR: Test episode",
        "link": "https://www.f4wonline.com/podcasts/wrestling-observer-radio/wor-test/",
        "published": datetime(2026, 7, 27, 8, 11, tzinfo=timezone.utc),
        "creator": "Bryan Alvarez",
        "summary": "An excerpt.",
        "content": "<p>A long enough paragraph of show notes to clear the length filter.</p>",
        "categories": ["Wrestling Observer Radio", "mainstory"],
        "enclosure_url": "https://media001.f4wonline.com/dmdocuments/072626wo.mp3",
        "enclosure_type": "audio/mpeg",
        "image_url": "https://www.f4wonline.com/cover.jpg",
    }
    item.update(overrides)
    return item


# ---------------------------------------------------------------------------
# feed_url
# ---------------------------------------------------------------------------

class TestFeedUrl(TestCase):
    def test_combined_feed_when_no_slug(self):
        self.assertEqual("https://www.f4wonline.com/category/podcasts/feed/", feed_url())

    def test_per_show_feed(self):
        self.assertEqual(
            "https://www.f4wonline.com/category/podcasts/after-dark/feed/",
            feed_url("after-dark"),
        )

    def test_create_poller_targets_that_url(self):
        self.assertEqual(feed_url("dr-keith"), create_poller(MagicMock(), "dr-keith").url)


# ---------------------------------------------------------------------------
# resolve_show
# ---------------------------------------------------------------------------

class TestResolveShow(TestCase):
    def test_reads_slug_from_permalink(self):
        slug, name = resolve_show(
            "https://www.f4wonline.com/podcasts/bryan-and-vinny-show/bv-episode/", []
        )
        self.assertEqual(("bryan-and-vinny-show", "Bryan and Vinny Show"), (slug, name))

    def test_permalink_wins_over_categories(self):
        slug, _name = resolve_show(
            "https://www.f4wonline.com/podcasts/after-dark/ad-episode/",
            ["Podcasts", "Wrestling Observer Radio"],
        )
        self.assertEqual("after-dark", slug)

    def test_flat_url_falls_back_to_categories(self):
        # /podcasts/<episode>/ with no show folder — the show is only in the tags.
        slug, name = resolve_show(
            "https://www.f4wonline.com/podcasts/wor-dave-goes-to-arena-mexico/",
            ["Podcasts", "Wrestling Observer Radio", "cmll"],
        )
        self.assertEqual(("wrestling-observer-radio", "Wrestling Observer Radio"), (slug, name))

    def test_category_name_matched_despite_leading_the(self):
        # The feed tags these 'The Fight Game Podcast'; the slug has no 'the'.
        slug, name = resolve_show(
            "https://www.f4wonline.com/podcasts/fight-game-aew-recap/",
            ["Podcasts", "The Fight Game Podcast"],
        )
        self.assertEqual(("fight-game-podcast", "Fight Game Podcast"), (slug, name))

    def test_resolves_to_the_same_name_the_archive_scraper_uses(self):
        # Both paths must agree, or the same show gets two output folders.
        from podcastDownloader.util import SHOW_SLUGS
        for slug, name in SHOW_SLUGS.items():
            resolved_slug, resolved_name = resolve_show(
                f"https://www.f4wonline.com/podcasts/{slug}/an-episode/", []
            )
            self.assertEqual((slug, name), (resolved_slug, resolved_name))

    def test_unknown_show_uses_its_category_name(self):
        slug, name = resolve_show(
            "https://www.f4wonline.com/podcasts/brand-new-show/first-episode/",
            ["Podcasts", "Brand New Show"],
        )
        self.assertEqual(("brand-new-show", "Brand New Show"), (slug, name))

    def test_unknown_show_with_no_categories_uses_its_slug(self):
        slug, name = resolve_show(
            "https://www.f4wonline.com/podcasts/brand-new-show/first-episode/", []
        )
        self.assertEqual(("brand-new-show", "Brand New Show"), (slug, name))

    def test_unresolvable_item_does_not_raise(self):
        self.assertEqual(("podcasts", "Podcasts"), resolve_show("https://example.com/", []))


# ---------------------------------------------------------------------------
# _mp3_url
# ---------------------------------------------------------------------------

class TestMp3Url(TestCase):
    def test_uses_audio_enclosure(self):
        url = _mp3_url(_parsed_item())
        self.assertEqual("https://media001.f4wonline.com/dmdocuments/072626wo.mp3", url)

    def test_accepts_mp3_enclosure_with_wrong_mime_type(self):
        item = _parsed_item(enclosure_type="application/octet-stream")
        self.assertTrue(_mp3_url(item).endswith(".mp3"))

    def test_ignores_non_audio_enclosure(self):
        item = _parsed_item(
            enclosure_url="https://www.f4wonline.com/cover.jpg",
            enclosure_type="image/jpeg",
            content="<p>no link here</p>",
        )
        self.assertIsNone(_mp3_url(item))

    def test_falls_back_to_a_link_in_the_body(self):
        item = _parsed_item(
            enclosure_url=None,
            enclosure_type="",
            content='<p><a href="https://media001.f4wonline.com/dmdocuments/072626wo.mp3">Right Click Save As</a></p>',
        )
        self.assertEqual("https://media001.f4wonline.com/dmdocuments/072626wo.mp3", _mp3_url(item))

    def test_returns_none_when_there_is_no_audio_anywhere(self):
        item = _parsed_item(enclosure_url=None, enclosure_type="", content="<p>Coming soon.</p>")
        self.assertIsNone(_mp3_url(item))


# ---------------------------------------------------------------------------
# episode_from_item
# ---------------------------------------------------------------------------

class TestEpisodeFromItem(TestCase):
    def test_episode_matches_the_scraper_shape(self):
        episode, _details = episode_from_item(_parsed_item())
        self.assertEqual(
            {"title", "url", "date", "show", "show_slug"}, set(episode)
        )

    def test_details_match_the_scraper_shape(self):
        _episode, details = episode_from_item(_parsed_item())
        self.assertEqual(
            {"mp3_url", "host", "description", "categories", "thumbnail_url"}, set(details)
        )

    def test_date_is_formatted_for_the_shared_date_parser(self):
        from f4wCommon.dates import DATE_FORMAT_IN, enrich_with_date
        episode, _details = episode_from_item(_parsed_item())
        enriched = enrich_with_date(dict(episode), DATE_FORMAT_IN)
        self.assertEqual(("2026", "July", "27"), (enriched["year"], enriched["month"], enriched["day"]))

    def test_carries_host_and_artwork_through(self):
        _episode, details = episode_from_item(_parsed_item())
        self.assertEqual("Bryan Alvarez", details["host"])
        self.assertEqual("https://www.f4wonline.com/cover.jpg", details["thumbnail_url"])

    def test_description_is_plain_text(self):
        _episode, details = episode_from_item(_parsed_item())
        self.assertNotIn("<p>", details["description"])
        self.assertIn("show notes", details["description"])

    def test_short_paragraphs_are_dropped_from_the_description(self):
        item = _parsed_item(content="<p>Short.</p><p>" + "x" * 60 + "</p>")
        _episode, details = episode_from_item(item)
        self.assertNotIn("Short.", details["description"])

    def test_description_falls_back_to_unwrapped_text(self):
        item = _parsed_item(content="", summary="A bare excerpt with no paragraph tags.")
        _episode, details = episode_from_item(item)
        self.assertEqual("A bare excerpt with no paragraph tags.", details["description"])

    def test_item_without_a_date_is_rejected(self):
        self.assertEqual((None, None), episode_from_item(_parsed_item(published=None)))

    def test_item_without_a_title_is_rejected(self):
        self.assertEqual((None, None), episode_from_item(_parsed_item(title="")))

    def test_item_without_a_link_is_rejected(self):
        self.assertEqual((None, None), episode_from_item(_parsed_item(link="")))


# ---------------------------------------------------------------------------
# episodes_from_feed
# ---------------------------------------------------------------------------

class TestEpisodesFromFeed(TestCase):
    def test_details_are_keyed_by_episode_url(self):
        episodes, details = episodes_from_feed([_parsed_item()])
        self.assertEqual(set(details), {episodes[0]["url"]})

    def test_skips_unusable_items_but_keeps_the_rest(self):
        episodes, _details = episodes_from_feed([
            _parsed_item(),
            _parsed_item(published=None),
            _parsed_item(title="Another", link="https://www.f4wonline.com/podcasts/x/y/"),
        ])
        self.assertEqual(2, len(episodes))

    def test_empty_feed_yields_nothing(self):
        self.assertEqual(([], {}), episodes_from_feed([]))


# ---------------------------------------------------------------------------
# scrape_feed_episodes
# ---------------------------------------------------------------------------

class TestScrapeFeedEpisodes(TestCase):
    @patch("podcastDownloader.feed.create_poller")
    def test_returns_converted_episodes(self, create):
        create.return_value = MagicMock(poll=MagicMock(return_value=[_parsed_item()]))
        episodes, details = scrape_feed_episodes(MagicMock())
        self.assertEqual(1, len(episodes))
        self.assertEqual(1, len(details))

    @patch("podcastDownloader.feed.create_poller")
    def test_failed_fetch_yields_nothing(self, create):
        create.return_value = MagicMock(poll=MagicMock(return_value=None))
        self.assertEqual(([], {}), scrape_feed_episodes(MagicMock()))


if __name__ == "__main__":
    main()
