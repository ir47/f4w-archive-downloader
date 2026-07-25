"""
util.py — F4WOnline Podcast Downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Podcast-specific scraping and ID3 tagging. Site-agnostic auth/HTTP/date/
filesystem helpers live in the shared f4wCommon package and are re-exported
here for backwards compatibility.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from mutagen.id3 import (
    APIC,   # Attached picture (thumbnail artwork)
    COMM,   # Comment (episode description)
    ID3,
    ID3NoHeaderError,
    TALB,   # Album (show name)
    TDRC,   # Recording date
    TCON,   # Genre / category
    TIT2,   # Title
    TPE1,   # Artist (host)
    TRCK,   # Track number (day-of-month for in-month ordering)
    WOAS,   # Official audio source URL (episode page URL)
)

from f4wCommon.auth import (
    DEFAULT_LOGIN_URL as LOGIN_URL,
    find_input_name as _find_input_name,
    login as _f4w_login,
    prompt_credentials as _prompt_credentials,
)
from f4wCommon.dates import enrich_with_date, parse_date
from f4wCommon.fsutil import (
    build_hierarchical_path,
    generate_download_directories,
    sanitize_filename,
)
from f4wCommon.http import (
    HTTP_RETRY_COUNT,
    HTTP_TIMEOUT_DOWNLOAD,
    REQUEST_HEADERS,
    create_session,
    fetch_page as _fetch_page,
    stream_download,
)
from f4wCommon.scrape import (
    extract_time_element_date,
    find_content_container,
    get_total_pages,
)


# ---------------------------------------------------------------------------
# Site URLs
# ---------------------------------------------------------------------------

CATEGORY_BASE = "https://www.f4wonline.com/category/podcasts/"
MEDIA_BASE = "https://media001.f4wonline.com/dmdocuments/"


# ---------------------------------------------------------------------------
# HTTP headers
# ---------------------------------------------------------------------------

DOWNLOAD_HEADERS: dict = {
    **REQUEST_HEADERS,
    "authority": "media001.f4wonline.com",
    "cache-control": "no-cache",
}


# ---------------------------------------------------------------------------
# Date formats
# ---------------------------------------------------------------------------

DATE_FORMAT_IN = "%B %d, %Y"   # e.g. "March 17, 2026"  — scraped dates
DATE_FORMAT_ISO = "%Y-%m-%d"   # e.g. "2026-03-17"       — ID3 tags and <time> attrs


# ---------------------------------------------------------------------------
# Known shows
# ---------------------------------------------------------------------------

# Maps each show's URL slug to its display name.
# Category URL pattern:  https://www.f4wonline.com/category/podcasts/SLUG/
# Pagination pattern:    https://www.f4wonline.com/category/podcasts/SLUG/page/N/
# Page counts are approximate and verified against the live site (March 2026).
SHOW_SLUGS: dict = {
    "wrestling-observer-radio":          "Wrestling Observer Radio",          # ~300 pages
    "wrestling-observer-live":           "Wrestling Observer Live",           # ~216 pages
    "bryan-and-vinny-show":              "Bryan and Vinny Show",              # ~191 pages
    "figure-four-daily":                 "Figure Four Daily",                 # ~167 pages
    "dragon-king":                       "Dragon King",                       # ~71  pages
    "wrestling-weekly":                  "Wrestling Weekly",                  # ~52  pages
    "after-dark":                        "After Dark",                        # ~39  pages
    "big-audio-nightmare":               "Big Audio Nightmare",               # ~36  pages
    "dr-keith":                          "Dr. Keith",                         # ~30  pages
    "punch-out":                         "Punch-Out",                         # ~22  pages
    "fight-game-podcast":                "Fight Game Podcast",                # ~18  pages
    "i-left-my-wallet":                  "I Left My Wallet",                  # ~12  pages
    "were-live-pal":                     "We're Live Pal",                    # ~9   pages
    "big-vinny-v-show":                  "Big Vinny V Show",                  # ~7   pages
    "pacific-rim-pro-wrestling-podcast": "Pacific Rim Pro Wrestling Podcast", # ~7   pages
    "mat-men":                           "Mat Men",                           # ~6   pages
    "portland-wrestlecast":              "Portland Wrestlecast",              # ~4   pages
}


# ---------------------------------------------------------------------------
# Tunable defaults
# ---------------------------------------------------------------------------

DEFAULT_DOWNLOAD_PATH = Path.home() / "Downloads" / "F4WPodcasts"
HTTP_TIMEOUT_THUMBNAIL = 10     # seconds — thumbnail image fetches
MIN_DESCRIPTION_LENGTH = 40     # minimum paragraph character length to include in description

_MP3_LINK_RE = re.compile(r"f4wonline\.com.*\.mp3$", re.I)


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def login(
    session: requests.Session,
    credentials: tuple[str, str] | None = None,
) -> bool:
    """
    Authenticate with F4WOnline and mutate *session* in-place.

    Pass ``credentials=(username, password)`` for non-interactive use (e.g. a
    web backend).  Omit it to fall back to the interactive stdin/getpass prompt.

    Returns True on success, False on failure.
    """
    return _f4w_login(session, login_url=LOGIN_URL, credentials=credentials, prompt_fn=_prompt_credentials)


# ---------------------------------------------------------------------------
# Category scraping
# ---------------------------------------------------------------------------

def _category_url(slug: str, page: int = 1) -> str:
    """Build the WordPress category archive URL for a show slug and page number."""
    if page == 1:
        return f"{CATEGORY_BASE}{slug}/"
    return f"{CATEGORY_BASE}{slug}/page/{page}/"


def _get_total_pages(slug: str, session: requests.Session) -> int:
    """
    Fetch page 1 of a show's category archive and return the total page count
    by finding the highest page number in the pagination links.
    """
    return get_total_pages(lambda page: _category_url(slug, page), session, fetch_fn=_fetch_page)


def _scrape_category_page(slug: str, page: int, session: requests.Session) -> list:
    """
    Scrape one page of a show's category archive.

    Returns a list of episode dicts: { title, url, date, show, show_slug }
    """
    url = _category_url(slug, page)
    print(f"  [fetch] {url}")
    resp = _fetch_page(url, session)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    show_name = SHOW_SLUGS.get(slug, slug.replace("-", " ").title())
    entries = []

    for heading in soup.select("h3 a[href], h2 a[href]"):
        post_url = heading["href"]

        # Accept any URL under /podcasts/ — some older episodes lack a show
        # subfolder (e.g. /podcasts/episode-title/ instead of
        # /podcasts/show-slug/episode-title/) but are still valid.
        if "/podcasts/" not in post_url:
            continue
        if "/category/" in post_url or "how-to-listen" in post_url:
            continue

        title = heading.get_text(strip=True)
        if not title:
            continue

        # Prefer the ISO datetime attribute on a <time> element for accuracy.
        container = heading.find_parent("article") or heading.find_parent("div")
        date_text = extract_time_element_date(container, DATE_FORMAT_ISO, DATE_FORMAT_IN)

        entries.append({
            "title": title,
            "url": post_url,
            "date": date_text,
            "show": show_name,
            "show_slug": slug,
        })

    print(f"  [parse] {len(entries)} episodes on page {page}")
    return entries


def scrape_all_episodes(
    session: requests.Session,
    show_filter: str | None = None,
    max_pages: int | None = None,
    page_delay: float = 1.0,
) -> list:
    """
    Scrape episode listings from WordPress category archive pages.

    If show_filter is a recognised slug (e.g. 'wrestling-observer-radio'),
    only that show's category is scraped. If None, all known shows are scraped.

    Args:
        session:      Authenticated requests Session.
        show_filter:  Show slug to restrict results. None scrapes all shows.
        max_pages:    Maximum pages to scrape per show (useful for testing).
        page_delay:   Seconds to sleep between page requests (be polite).

    Returns:
        List of episode dicts: { title, url, date, show, show_slug }
    """
    slugs = [show_filter] if show_filter else list(SHOW_SLUGS.keys())
    all_episodes = []

    for slug in slugs:
        show_name = SHOW_SLUGS.get(slug, slug)
        total = _get_total_pages(slug, session)
        if max_pages:
            total = min(total, max_pages)

        print(f"\nScraping '{show_name}' — {total} page(s)…")

        for page in range(1, total + 1):
            episodes = _scrape_category_page(slug, page, session)
            all_episodes.extend(episodes)
            time.sleep(page_delay)

    print(f"\nTotal episodes found: {len(all_episodes)}")
    return all_episodes


# ---------------------------------------------------------------------------
# Episode detail scraping
# ---------------------------------------------------------------------------

def scrape_episode_details(episode_url: str, session: requests.Session) -> dict:
    """
    Fetch an individual episode page and return a metadata dict:

        mp3_url       — direct MP3 download URL (str | None)
        host          — author / presenter name (str)
        description   — episode body text, up to 3 paragraphs (str)
        categories    — list of category / tag strings (list)
        thumbnail_url — featured image URL (str | None)

    All keys are always present; missing values default to empty string,
    empty list, or None as appropriate.
    """
    result = {
        "mp3_url": None,
        "host": "",
        "description": "",
        "categories": [],
        "thumbnail_url": None,
    }

    resp = _fetch_page(episode_url, session)
    if resp is None:
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    # MP3 URL — look for an anchor on the media server ending in .mp3
    mp3_tag = soup.find("a", href=_MP3_LINK_RE)
    if mp3_tag:
        result["mp3_url"] = mp3_tag["href"]
    if not result["mp3_url"]:
        m = re.search(
            r"https?://media\d+\.f4wonline\.com/dmdocuments/[^\s\"'<>]+\.mp3",
            resp.text,
        )
        if m:
            result["mp3_url"] = m.group(0)

    # Host / author — prefer rel="author" link, fall back to class-based search
    author_tag = (
        soup.find("a", rel="author")
        or soup.find(class_=re.compile(r"author", re.I))
    )
    if author_tag:
        result["host"] = author_tag.get_text(strip=True)

    # Description — first few substantial paragraphs from the article body
    content_div = find_content_container(soup)
    if content_div:
        paragraphs = [
            p.get_text(" ", strip=True)
            for p in content_div.find_all("p")
            if len(p.get_text(strip=True)) > MIN_DESCRIPTION_LENGTH
        ]
        result["description"] = "\n\n".join(paragraphs[:3])

    # Categories — collect from rel="category tag" anchors and common CSS selectors
    categories = []
    for a in soup.find_all("a", rel="category tag"):
        text = a.get_text(strip=True)
        if text:
            categories.append(text)
    for a in soup.select("span.cat-links a, .post-categories a, .tags a"):
        text = a.get_text(strip=True)
        if text and text not in categories:
            categories.append(text)
    result["categories"] = categories

    # Thumbnail — og:image is most reliable; fall back to first article image
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        result["thumbnail_url"] = og["content"]
    elif content_div:
        img = content_div.find("img", src=True)
        if img:
            result["thumbnail_url"] = img["src"]

    return result


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def parse_episode_date(date_str: str) -> datetime | None:
    """Parse a scraped date string like 'March 17, 2026' into a datetime."""
    return parse_date(date_str, DATE_FORMAT_IN)


def enrich_episode(episode: dict) -> dict:
    """
    Add parsed date fields to an episode dict in-place.

    Adds: year (str), month (str), day (str), datetime (datetime | None)
    Falls back to 'Unknown' / '00' when the date cannot be parsed.
    """
    return enrich_with_date(episode, DATE_FORMAT_IN)


# ---------------------------------------------------------------------------
# File system helpers
# ---------------------------------------------------------------------------

def build_download_path(base_path: Path, episode: dict, yearly: bool, monthly: bool) -> Path:
    """
    Construct the output directory for an episode.

    Structure (with both flags enabled):
        base_path / Show Name / Year / Month /
    """
    return build_hierarchical_path(
        base_path, episode["show"], episode.get("year"), episode.get("month"), yearly, monthly
    )


# ---------------------------------------------------------------------------
# Downloading
# ---------------------------------------------------------------------------

def download_podcast(
    mp3_url: str,
    dest_path: Path,
    session: requests.Session,
    skip_existing: bool = True,
) -> bool:
    """
    Stream an MP3 from mp3_url to dest_path using the authenticated session.

    Returns True on success (including skipped files), False on failure.
    """
    return stream_download(
        mp3_url, dest_path, session, headers=DOWNLOAD_HEADERS,
        timeout=HTTP_TIMEOUT_DOWNLOAD, skip_existing=skip_existing,
    )


# ---------------------------------------------------------------------------
# ID3 tagging
# ---------------------------------------------------------------------------

def _fetch_thumbnail(url: str) -> bytes | None:
    """Download a thumbnail image and return its raw bytes, or None on failure."""
    try:
        resp = requests.get(url, timeout=HTTP_TIMEOUT_THUMBNAIL)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


def _thumbnail_mime_type(url: str) -> str:
    """Infer the MIME type of a thumbnail image from its file extension."""
    url_lower = url.lower()
    if url_lower.endswith(".png"):
        return "image/png"
    if url_lower.endswith(".webp"):
        return "image/webp"
    return "image/jpeg"


def write_id3_tags(
    mp3_path: Path,
    episode: dict,
    details: dict,
    track_number: int | None = None,
) -> None:
    """
    Embed ID3v2 tags into a downloaded MP3 using mutagen.

    Tags written:
        TIT2  — episode title
        TPE1  — host / author
        TALB  — show name (album)
        TDRC  — recording date (YYYY-MM-DD)
        TCON  — categories as genre string
        COMM  — episode description as a comment
        TRCK  — track number (day-of-month for within-month ordering)
        WOAS  — episode page URL
        APIC  — thumbnail image as cover art (if available)
    """
    try:
        try:
            tags = ID3(mp3_path)
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TIT2(encoding=3, text=episode.get("title", "")))
        tags.add(TPE1(encoding=3, text=details.get("host", "")))
        tags.add(TALB(encoding=3, text=episode.get("show", "")))

        dt = episode.get("datetime")
        if dt:
            tags.add(TDRC(encoding=3, text=dt.strftime(DATE_FORMAT_ISO)))

        categories = details.get("categories", [])
        if categories:
            tags.add(TCON(encoding=3, text=", ".join(categories)))

        description = details.get("description", "")
        if description:
            tags.add(COMM(encoding=3, lang="eng", desc="", text=description))

        if track_number is not None:
            tags.add(TRCK(encoding=3, text=str(track_number)))

        post_url = episode.get("url", "")
        if post_url:
            tags.add(WOAS(url=post_url))

        thumbnail_url = details.get("thumbnail_url")
        if thumbnail_url:
            image_data = _fetch_thumbnail(thumbnail_url)
            if image_data:
                tags.add(APIC(
                    encoding=3,
                    mime=_thumbnail_mime_type(thumbnail_url),
                    type=3,         # 3 = Cover (front)
                    desc="Cover",
                    data=image_data,
                ))

        tags.save(mp3_path)
        print(
            f"  [tags] ID3 tags written "
            f"({len(categories)} categories, thumbnail={'yes' if thumbnail_url else 'no'})"
        )

    except Exception as exc:
        print(f"  [warn] Could not write ID3 tags to {mp3_path.name}: {exc}")