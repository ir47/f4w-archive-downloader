"""
feed.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Site-agnostic RSS fetching and parsing.

The F4WOnline archives are WordPress, so every category has a matching RSS
feed listing its 50 most recent posts. A feed carries far more than the
archive index pages do — the enclosure URL, author, full post body, tags and
featured image are all in the XML — so one feed request replaces an index
scrape plus a fetch of every individual post page.

Feeds also honour conditional GETs, which is what makes polling them cheap:
``FeedPoller`` remembers the ETag/Last-Modified of the last response and sends
them back, so a check that finds nothing new costs an empty 304 rather than a
full re-download of the feed.
"""

from __future__ import annotations

import requests

from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from f4wCommon.http import HTTP_TIMEOUT_PAGE, REQUEST_HEADERS, fetch_page as _default_fetch_page


# XML namespaces used by the WordPress feed extensions we read.
FEED_NAMESPACES: dict = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}

# Sent instead of the shared HTML Accept header when fetching a feed.
FEED_ACCEPT = "application/rss+xml, application/xml;q=0.9, */*;q=0.8"

HTTP_NOT_MODIFIED = 304

# Root elements a syndication feed is allowed to have: RSS 2.0, RDF/RSS 1.0
# and Atom respectively. Anything else is some other document.
FEED_ROOT_TAGS = frozenset({"rss", "RDF", "feed"})


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _local_name(tag: str) -> str:
    """Strip any '{namespace}' prefix from an element tag."""
    return tag.rsplit("}", 1)[-1]


def _text(node, path: str) -> str:
    """Return the stripped text of the first *path* child of *node*, or ""."""
    el = node.find(path, FEED_NAMESPACES)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_pub_date(raw: str) -> datetime | None:
    """
    Parse an RFC 2822 <pubDate> into a datetime, keeping the offset the feed
    published it with.

    Deliberately not converted to UTC or to local time: WordPress emits
    pubDate in the site's own timezone, which is the same clock the archive
    index pages date their posts by. Converting would drift an episode into
    the neighbouring day's folder for anything published near midnight, and
    the archive and watch paths would then disagree about where it belongs.
    """
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def _image_url(node) -> str | None:
    """Return the first <media:content> image URL on an item, if any."""
    for media in node.findall("media:content", FEED_NAMESPACES):
        mime = media.get("type", "")
        if mime.startswith("image/") or media.get("medium") == "image":
            url = media.get("url")
            if url:
                return url
    return None


def parse_feed(xml_text: str) -> list | None:
    """
    Parse RSS XML into a list of item dicts, or None if it will not parse.

    Each item dict has every key present, defaulting to "" / [] / None:

        title          — post title (str)
        link           — permalink to the post page (str)
        published      — publication datetime, feed-local (datetime | None)
        creator        — <dc:creator>, the post author (str)
        summary        — <description>, usually a truncated excerpt (str)
        content        — <content:encoded>, the full post body as HTML (str)
        categories     — category and tag names (list)
        enclosure_url  — attached media file, e.g. the MP3 (str | None)
        enclosure_type — that file's MIME type, e.g. 'audio/mpeg' (str)
        image_url      — featured image from <media:content> (str | None)

    None is reserved for "this response was not a feed" so that a caller
    polling on a timer can tell a broken response apart from a feed that
    genuinely has no items in it.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        print(f"  [warn] Could not parse feed XML: {exc}")
        return None

    # An error page or a redirect to the login form is often well-formed
    # enough to parse, and would then read as a feed that simply has no
    # episodes in it. Check the document really is a feed, so that a caller
    # polling on a timer reports a failure instead of a quiet "nothing new".
    if _local_name(root.tag) not in FEED_ROOT_TAGS:
        print(f"  [warn] Response is not a feed (root element <{root.tag}>)")
        return None

    items = []
    for node in root.iter("item"):
        enclosure = node.find("enclosure")
        items.append({
            "title": _text(node, "title"),
            "link": _text(node, "link"),
            "published": _parse_pub_date(_text(node, "pubDate")),
            "creator": _text(node, "dc:creator"),
            "summary": _text(node, "description"),
            "content": _text(node, "content:encoded"),
            "categories": [c.text.strip() for c in node.findall("category") if c.text],
            "enclosure_url": enclosure.get("url") if enclosure is not None else None,
            "enclosure_type": enclosure.get("type", "") if enclosure is not None else "",
            "image_url": _image_url(node),
        })

    return items


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------

class FeedPoller:
    """
    Repeatedly fetches one feed URL, using conditional GETs between checks.

    ``poll()`` distinguishes three outcomes:

        list  — the feed was re-fetched; these are its current items
        []    — the server answered 304, nothing has changed since last poll
        None  — the fetch or the parse failed; the feed state is unknown

    The validators live on the instance, so a poller has to be kept around
    across checks for the conditional request to do anything. A fresh poller
    simply fetches the feed in full the first time, as it must.
    """

    def __init__(
        self,
        url: str,
        session: requests.Session,
        fetch_fn=_default_fetch_page,
        timeout: int = HTTP_TIMEOUT_PAGE,
    ):
        self.url = url
        self.session = session
        self.etag: str | None = None
        self.last_modified: str | None = None
        self._fetch = fetch_fn
        self._timeout = timeout

    def _headers(self) -> dict:
        headers = {**REQUEST_HEADERS, "Accept": FEED_ACCEPT}
        if self.etag:
            headers["If-None-Match"] = self.etag
        if self.last_modified:
            headers["If-Modified-Since"] = self.last_modified
        return headers

    def poll(self) -> list | None:
        """Fetch the feed and return its items ([] if unchanged, None on failure)."""
        resp = self._fetch(self.url, self.session, headers=self._headers(), timeout=self._timeout)
        if resp is None:
            return None

        # Keep the previous validators when a 304 response omits them.
        self.etag = resp.headers.get("ETag", self.etag)
        self.last_modified = resp.headers.get("Last-Modified", self.last_modified)

        if resp.status_code == HTTP_NOT_MODIFIED:
            return []
        return parse_feed(resp.text)
