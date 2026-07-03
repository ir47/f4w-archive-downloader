"""
util.py — F4WOnline Podcast Downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Shared helpers for authentication, scraping, downloading, and ID3 tagging.
"""

from __future__ import annotations

import getpass
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


# ---------------------------------------------------------------------------
# Site URLs
# ---------------------------------------------------------------------------

LOGIN_URL = "https://account.f4wonline.com/login"
CATEGORY_BASE = "https://www.f4wonline.com/category/podcasts/"
MEDIA_BASE = "https://media001.f4wonline.com/dmdocuments/"


# ---------------------------------------------------------------------------
# HTTP headers
# ---------------------------------------------------------------------------

REQUEST_HEADERS: dict = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Referer": "https://archive.f4wonline.com/",
}

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
DOWNLOAD_CHUNK_SIZE = 65536     # bytes per chunk when streaming MP3s
HTTP_TIMEOUT_PAGE = 15          # seconds — page fetches
HTTP_TIMEOUT_DOWNLOAD = 30      # seconds — MP3 downloads
HTTP_TIMEOUT_THUMBNAIL = 10     # seconds — thumbnail image fetches
HTTP_RETRY_COUNT = 3            # attempts before giving up on a page fetch
HTTP_RETRY_DELAY = 2.0          # base seconds between retries (multiplied by attempt)
MIN_DESCRIPTION_LENGTH = 40     # minimum paragraph character length to include in description


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def create_session() -> requests.Session:
    """Return a new requests Session with shared headers pre-applied."""
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session


def _find_input_name(form, candidates: list) -> str | None:
    """
    Search a BeautifulSoup form for an <input> whose name attribute contains
    one of the candidate strings (case-insensitive). Returns the first match,
    or None if no match is found.
    """
    for inp in form.find_all("input"):
        name = inp.get("name", "").lower()
        if any(candidate in name for candidate in candidates):
            return inp["name"]
    return None


def _prompt_credentials() -> tuple:
    """Prompt interactively for username/email and password. Password input is hidden."""
    print("\n--- F4WOnline Login ---")
    username = input("Username or email: ").strip()
    password = getpass.getpass("Password: ")
    return username, password


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
    print("Connecting to F4WOnline…")
    try:
        resp = session.get(LOGIN_URL, timeout=HTTP_TIMEOUT_PAGE)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[error] Could not reach the login page: {exc}")
        return False

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if not form:
        print("[error] Could not find a login form on the page. The site may have changed.")
        return False

    # Use form's action URL if present, otherwise POST back to the same URL.
    action = form.get("action", "").strip()
    post_url = action if action.startswith("http") else LOGIN_URL

    # Seed the payload with all hidden fields (CSRF tokens, redirect targets, etc.)
    payload = {}
    for inp in form.find_all("input"):
        if inp.get("type", "").lower() == "hidden":
            name = inp.get("name", "").strip()
            if name:
                payload[name] = inp.get("value", "")

    # Detect field names dynamically to avoid hardcoding names that could change.
    username_field = _find_input_name(form, ["email", "username", "user", "login"])
    password_field = _find_input_name(form, ["password", "pass", "pwd"])

    if not username_field or not password_field:
        print(
            "[warn] Could not detect form field names automatically. "
            "Falling back to 'username' and 'password'."
        )
        username_field = username_field or "username"
        password_field = password_field or "password"

    username, password = credentials if credentials is not None else _prompt_credentials()
    payload[username_field] = username
    payload[password_field] = password

    try:
        login_resp = session.post(
            post_url,
            data=payload,
            headers={**REQUEST_HEADERS, "Referer": LOGIN_URL},
            allow_redirects=True,
            timeout=HTTP_TIMEOUT_PAGE,
        )
        login_resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[error] Login request failed: {exc}")
        return False

    # A successful login redirects away from /login entirely.
    final_url = login_resp.url
    still_on_login = "login" in final_url.lower() and "account.f4wonline.com" in final_url

    response_soup = BeautifulSoup(login_resp.text, "html.parser")
    error_tag = response_soup.find(class_=re.compile(r"error|alert|notice|message", re.I))
    error_text = error_tag.get_text(strip=True) if error_tag else ""
    failure_keywords = ("invalid", "incorrect", "wrong password", "failed", "not found")
    keyword_match = any(kw in login_resp.text.lower() for kw in failure_keywords)

    if still_on_login or (error_text and keyword_match):
        print("[error] Login failed — please check your username and password.")
        if error_text:
            print(f"        Site message: {error_text}")
        print(f"        Reset your password at: {LOGIN_URL}?sendpass")
        return False

    f4w_cookies = [c for c in session.cookies if "f4wonline" in c.domain]
    if not f4w_cookies:
        print(
            "[warn] Login appeared to succeed but no session cookie was set.\n"
            "       Downloads may fail if the site requires authentication."
        )

    print("[ok]   Logged in successfully.\n")
    return True


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _fetch_page(url: str, session: requests.Session) -> requests.Response | None:
    """
    GET a URL using the authenticated session, retrying up to HTTP_RETRY_COUNT
    times on failure. Returns the response, or None if all attempts fail.
    """
    for attempt in range(HTTP_RETRY_COUNT):
        try:
            resp = session.get(url, headers=REQUEST_HEADERS, timeout=HTTP_TIMEOUT_PAGE)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            print(f"  [warn] Request failed ({exc}), attempt {attempt + 1}/{HTTP_RETRY_COUNT}")
            time.sleep(HTTP_RETRY_DELAY * (attempt + 1))
    return None


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
    url = _category_url(slug, 1)
    print(f"  [fetch] {url}")
    resp = _fetch_page(url, session)
    if resp is None:
        return 1
    soup = BeautifulSoup(resp.text, "html.parser")
    max_page = 1
    for a in soup.select("a[href*='/page/']"):
        m = re.search(r"/page/(\d+)/", a["href"])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page


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
        date_text = ""
        container = heading.find_parent("article") or heading.find_parent("div")
        if container:
            time_el = container.find("time")
            if time_el:
                dt_attr = time_el.get("datetime", "")
                m = re.match(r"(\d{4}-\d{2}-\d{2})", dt_attr)
                if m:
                    try:
                        dt = datetime.strptime(m.group(1), DATE_FORMAT_ISO)
                        date_text = dt.strftime(DATE_FORMAT_IN)
                    except ValueError:
                        pass

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
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.endswith(".mp3") and "f4wonline.com" in href:
            result["mp3_url"] = href
            break
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
    content_div = (
        soup.find("div", class_=re.compile(r"entry.content|post.content|article.content", re.I))
        or soup.find("article")
    )
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
    try:
        return datetime.strptime(date_str, DATE_FORMAT_IN)
    except (ValueError, TypeError):
        return None


def enrich_episode(episode: dict) -> dict:
    """
    Add parsed date fields to an episode dict in-place.

    Adds: year (str), month (str), day (str), datetime (datetime | None)
    Falls back to 'Unknown' / '00' when the date cannot be parsed.
    """
    dt = parse_episode_date(episode.get("date", ""))
    if dt:
        episode["year"] = dt.strftime("%Y")
        episode["month"] = dt.strftime("%B")
        episode["day"] = dt.strftime("%d")
        episode["datetime"] = dt
    else:
        episode["year"] = "Unknown"
        episode["month"] = "Unknown"
        episode["day"] = "00"
        episode["datetime"] = None
    return episode


# ---------------------------------------------------------------------------
# File system helpers
# ---------------------------------------------------------------------------

def sanitize_filename(name: str) -> str:
    """Replace characters that are invalid in file/folder names with underscores."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def build_download_path(base_path: Path, episode: dict, yearly: bool, monthly: bool) -> Path:
    """
    Construct the output directory for an episode.

    Structure (with both flags enabled):
        base_path / Show Name / Year / Month /
    """
    path = base_path / sanitize_filename(episode["show"])
    if yearly and episode.get("year"):
        path = path / episode["year"]
    if monthly and episode.get("month"):
        path = path / episode["month"]
    return path


def generate_download_directories(path: Path) -> bool:
    """Create the directory tree at path. Returns True on success, False on error."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as exc:
        print(f"[error] Could not create directory {path}: {exc}")
        return False


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
    if skip_existing and dest_path.exists():
        print(f"  [skip] Already exists: {dest_path.name}")
        return True

    try:
        resp = session.get(
            mp3_url,
            headers=DOWNLOAD_HEADERS,
            stream=True,
            timeout=HTTP_TIMEOUT_DOWNLOAD,
        )
        resp.raise_for_status()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                fh.write(chunk)

        size_mb = dest_path.stat().st_size / (1024 * 1024)
        print(f"  [ok]   {dest_path.name}  ({size_mb:.1f} MB)")
        return True

    except requests.RequestException as exc:
        print(f"  [fail] {mp3_url} — {exc}")
        return False


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