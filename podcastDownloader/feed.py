"""
feed.py — F4WOnline Podcast Downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Turns the site's podcast RSS feeds into the same episode and detail dicts the
archive scraper in util.py produces, so both can drive the shared download
pipeline unchanged.

Why the feed is worth a separate path: an <item> already carries the enclosure
MP3 URL, the author, the full post body, the tags and the featured image. The
archive path has to fetch each episode page to learn those, whereas one feed
request answers for the 50 most recent episodes at once. Nothing here needs an
authenticated session — the feed is public. Only downloading the MP3 itself
requires the login.

The feed only reaches back 50 episodes, so this is for keeping an already
downloaded archive current, not for building one.
"""

from __future__ import annotations

import re
import requests

from bs4 import BeautifulSoup

from podcastDownloader.util import (
    CATEGORY_BASE,
    DESCRIPTION_PARAGRAPHS,
    MIN_DESCRIPTION_LENGTH,
    MP3_URL_RE,
    SHOW_SLUGS,
)
from f4wCommon.dates import DATE_FORMAT_IN
from f4wCommon.feed import FeedPoller, parse_feed
from f4wCommon.scrape import extract_paragraphs


# ---------------------------------------------------------------------------
# Feed URLs
# ---------------------------------------------------------------------------

def feed_url(show_slug: str | None = None) -> str:
    """
    Build the RSS feed URL for one show, or for every podcast category when
    *show_slug* is None.

    The combined feed mixes all shows into one 50-item list, so a busy week of
    Wrestling Observer Live can push a quieter show off the end of it. That is
    only a problem for a watcher that checks in less often than the feed turns
    over, which the default poll interval is nowhere near.
    """
    if show_slug:
        return f"{CATEGORY_BASE}{show_slug}/feed/"
    return f"{CATEGORY_BASE}feed/"


def create_poller(session: requests.Session, show_slug: str | None = None) -> FeedPoller:
    """Return a FeedPoller for one show's feed, or the combined podcast feed."""
    return FeedPoller(feed_url(show_slug), session)


# ---------------------------------------------------------------------------
# Show resolution
# ---------------------------------------------------------------------------

def _normalize_show(text: str) -> str:
    """
    Reduce a show name or slug to a comparable key: lowercase, no leading
    'the', and every run of non-alphanumerics collapsed to a single hyphen.

    Needed because the two sources spell the same show differently — the feed
    tags episodes 'The Fight Game Podcast' where the slug is
    'fight-game-podcast'.
    """
    key = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return re.sub(r"^the-", "", key)


# Both the slug and the display name of every known show, keyed for lookup.
_SHOWS_BY_KEY: dict = {}
for _slug, _name in SHOW_SLUGS.items():
    _SHOWS_BY_KEY[_normalize_show(_slug)] = (_slug, _name)
    _SHOWS_BY_KEY[_normalize_show(_name)] = (_slug, _name)


def _slug_from_link(link: str) -> str | None:
    """
    Pull the show slug out of an episode permalink.

    Episode URLs are normally /podcasts/<show-slug>/<episode-slug>/, but some
    posts are filed straight under /podcasts/<episode-slug>/ with no show
    folder. Only treat the segment after 'podcasts' as a show when something
    follows it, or every one of those flat URLs would name a show after its
    own episode.
    """
    parts = [part for part in link.split("?")[0].split("/") if part]
    if "podcasts" not in parts:
        return None
    index = parts.index("podcasts")
    if index + 2 >= len(parts):
        return None
    return parts[index + 1]


def resolve_show(link: str, categories: list) -> tuple:
    """
    Work out ``(show_slug, show_name)`` for a feed item.

    Tries the permalink first, then the item's categories, so that flat
    /podcasts/<episode>/ URLs still land in the right show folder — the feed
    tags those with the show name even though the URL omits it.

    An unrecognised show falls back to its own name rather than being dropped:
    new shows get added to the site well before SHOW_SLUGS hears about them,
    and a watcher silently ignoring a new show is worse than one filing it
    under a name that needs tidying later.
    """
    slug = _slug_from_link(link)
    if slug:
        known = _SHOWS_BY_KEY.get(_normalize_show(slug))
        if known:
            return known

    for category in categories:
        known = _SHOWS_BY_KEY.get(_normalize_show(category))
        if known:
            return known

    # Categories lead with the parent 'Podcasts' term, then the show, then
    # free-form tags — so the second entry is the best guess at a new show.
    for category in categories:
        if _normalize_show(category) != "podcasts":
            return _normalize_show(category), category

    if slug:
        return slug, slug.replace("-", " ").title()
    return "podcasts", "Podcasts"


# ---------------------------------------------------------------------------
# Item conversion
# ---------------------------------------------------------------------------

def _mp3_url(item: dict) -> str | None:
    """Return an item's MP3 URL, from its enclosure or failing that its body."""
    url = item.get("enclosure_url")
    if url and item.get("enclosure_type", "").startswith("audio/"):
        return url
    if url and url.lower().split("?")[0].endswith(".mp3"):
        return url

    match = MP3_URL_RE.search(item.get("content") or "")
    if match:
        return match.group(0)
    return None


def _description(item: dict) -> str:
    """Extract plain-text description paragraphs from an item's HTML body."""
    body = item.get("content") or item.get("summary") or ""
    if not body:
        return ""
    soup = BeautifulSoup(body, "html.parser")
    text = extract_paragraphs(soup, MIN_DESCRIPTION_LENGTH, DESCRIPTION_PARAGRAPHS)
    if text:
        return text
    # <description> excerpts arrive as a bare sentence with no <p> wrapper.
    return soup.get_text(" ", strip=True)


def episode_from_item(item: dict) -> tuple:
    """
    Convert one parsed feed item into ``(episode, details)``, matching the
    shapes ``scrape_all_episodes`` and ``scrape_episode_details`` return so
    that the download pipeline cannot tell the two sources apart.

    Returns ``(None, None)`` for an item with no title, link or date — the
    pipeline names files after those, so there is nothing useful to do with
    an item missing any of them.
    """
    title = item.get("title", "").strip()
    link = item.get("link", "").strip()
    published = item.get("published")
    if not title or not link or published is None:
        return None, None

    categories = item.get("categories", [])
    show_slug, show_name = resolve_show(link, categories)

    episode = {
        "title": title,
        "url": link,
        "date": published.strftime(DATE_FORMAT_IN),
        "show": show_name,
        "show_slug": show_slug,
    }
    details = {
        "mp3_url": _mp3_url(item),
        "host": item.get("creator", ""),
        "description": _description(item),
        "categories": categories,
        "thumbnail_url": item.get("image_url"),
    }
    return episode, details


def episodes_from_feed(items: list) -> tuple:
    """
    Convert parsed feed items into ``(episodes, details_by_url)``.

    The details are keyed by episode URL so they can be served back to the
    pipeline through a ``scrape_details``-shaped lookup, which is what spares
    a watch run from fetching any episode pages at all.
    """
    episodes, details_by_url = [], {}
    for item in items:
        episode, details = episode_from_item(item)
        if episode is None:
            continue
        episodes.append(episode)
        details_by_url[episode["url"]] = details
    return episodes, details_by_url


def scrape_feed_episodes(session: requests.Session, show_slug: str | None = None) -> tuple:
    """
    Fetch and convert a feed in one shot, for a single non-repeating check.

    Returns ``(episodes, details_by_url)``, both empty if the feed could not
    be fetched or parsed. Use ``create_poller`` instead when checking
    repeatedly — this makes no conditional request.
    """
    poller = create_poller(session, show_slug)
    items = poller.poll()
    if not items:
        return [], {}
    return episodes_from_feed(items)


__all__ = [
    "create_poller",
    "episode_from_item",
    "episodes_from_feed",
    "feed_url",
    "parse_feed",
    "resolve_show",
    "scrape_feed_episodes",
]
