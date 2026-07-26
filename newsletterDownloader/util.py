"""
util.py — F4WOnline Newsletter Downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Scrapes the Wrestling Observer Newsletter archive on members.f4wonline.com,
saves each issue as a PDF and/or the raw scraped webpage, and builds the
output folder hierarchy. Confirmed working against the live site (login,
archive pagination, PDF/article-content selectors).
"""

from __future__ import annotations

import html
import re
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from f4wCommon.dates import DATE_FORMAT_IN
from f4wCommon.http import fetch_page, stream_download
from f4wCommon.scrape import find_content_container, get_total_pages, scrape_listing_page


# ---------------------------------------------------------------------------
# Site URLs
# ---------------------------------------------------------------------------

ARCHIVE_BASE = "https://members.f4wonline.com/wrestling-observer-newsletter/"

NEWSLETTER_CATEGORY_NAME = "Wrestling Observer Newsletter"


# ---------------------------------------------------------------------------
# Tunable defaults
# ---------------------------------------------------------------------------

DEFAULT_NEWSLETTER_DOWNLOAD_PATH = Path.home() / "Downloads" / "F4WNewsletters"

_PDF_LINK_RE = re.compile(r"f4wonline\.com.*\.pdf(?:\?.*)?$", re.I)
_SHARE_CLASS_RE = re.compile(r"share", re.I)
_PDF_LINK_TEXT_RE = re.compile(r"read this issue in pdf form", re.I)


# ---------------------------------------------------------------------------
# Archive scraping
# ---------------------------------------------------------------------------

def _archive_url(page: int = 1) -> str:
    """Build the archive index URL for a given page number."""
    if page == 1:
        return ARCHIVE_BASE
    return f"{ARCHIVE_BASE}page/{page}/"


def _get_total_pages(session: requests.Session) -> int:
    """
    Fetch page 1 of the newsletter archive and return the total page count
    by finding the highest page number in the pagination links.
    """
    return get_total_pages(_archive_url, session, fetch_fn=fetch_page)


def _parse_date_from_slug(url: str) -> str:
    """
    Fall back to parsing a date from the issue URL slug, e.g.
    '.../july-13-2026-observer-newsletter-.../' -> 'July 13, 2026'.

    Returns an empty string if no date-shaped prefix is found.
    """
    slug = url.rstrip("/").rsplit("/", 1)[-1]
    m = re.match(r"([a-z]+)-(\d{1,2})-(\d{4})", slug, re.I)
    if not m:
        return ""
    month, day, year = m.groups()
    try:
        dt = datetime.strptime(f"{month} {day}, {year}", DATE_FORMAT_IN)
        return dt.strftime(DATE_FORMAT_IN)
    except ValueError:
        return ""


def _scrape_archive_page(page: int, session: requests.Session) -> list:
    """
    Scrape one page of the newsletter archive.

    Returns a list of issue dicts: { title, url, date, show }
    """
    return scrape_listing_page(
        _archive_url(page),
        session,
        link_filter=lambda post_url: "/category/" not in post_url,
        extra_fields={"show": NEWSLETTER_CATEGORY_NAME},
        date_fallback=_parse_date_from_slug,
        item_noun="issue(s)",
        fetch_fn=fetch_page,
    )


def scrape_all_issues(
    session: requests.Session,
    max_pages: int | None = None,
    page_delay: float = 1.0,
) -> list:
    """
    Scrape all newsletter issue listings from the archive index.

    Returns:
        List of issue dicts: { title, url, date, show }
    """
    total = _get_total_pages(session)
    if max_pages:
        total = min(total, max_pages)

    print(f"\nScraping '{NEWSLETTER_CATEGORY_NAME}' — {total} page(s)…")

    all_issues = []
    for page in range(1, total + 1):
        all_issues.extend(_scrape_archive_page(page, session))
        time.sleep(page_delay)

    print(f"\nTotal issues found: {len(all_issues)}")
    return all_issues


# ---------------------------------------------------------------------------
# Issue detail scraping
# ---------------------------------------------------------------------------

def scrape_issue_details(issue_url: str, session: requests.Session) -> dict:
    """
    Fetch an individual newsletter issue page and return:

        pdf_url      — direct PDF download URL (str | None)
        html_content — full inner HTML of the article/content container,
                       not truncated (str | None)
    """
    result = {"pdf_url": None, "html_content": None}

    resp = fetch_page(issue_url, session)
    if resp is None:
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    # PDF URL — look for an anchor on the members/media domain ending in .pdf
    pdf_tag = soup.find("a", href=_PDF_LINK_RE)
    if pdf_tag:
        result["pdf_url"] = pdf_tag["href"]

    # Full article content — keep the entire inner HTML rather than a
    # 3-paragraph summary (unlike the podcast episode description scraper).
    content_div = find_content_container(soup)
    if content_div:
        result["html_content"] = content_div.decode_contents()

    return result


# ---------------------------------------------------------------------------
# Ebook cleanup
# ---------------------------------------------------------------------------

def clean_html_for_ebook(html_content: str) -> str:
    """
    Strip page-furniture that makes sense in a saved webpage but is noise in
    a converted ebook: social share-button widgets, and the "Click here to
    read this issue in PDF form" link paragraph.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    for widget in soup.find_all(class_=_SHARE_CLASS_RE):
        widget.decompose()

    for a in soup.find_all("a"):
        if _PDF_LINK_TEXT_RE.search(a.get_text(" ", strip=True)):
            (a.find_parent("p") or a).decompose()

    return soup.decode()


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

def save_html(html_content: str, dest_path: Path, title: str) -> bool:
    """Wrap html_content in a minimal standalone HTML document and write it to dest_path."""
    document = (
        "<!doctype html>\n"
        "<html><head><meta charset=\"utf-8\">"
        f"<title>{html.escape(title)}</title></head><body>\n"
        f"{html_content}\n"
        "</body></html>\n"
    )
    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(document, encoding="utf-8")
        print(f"  [ok]   {dest_path.name}")
        return True
    except OSError as exc:
        print(f"  [fail] Could not write {dest_path}: {exc}")
        return False


def download_pdf(pdf_url: str, dest_path: Path, session: requests.Session) -> bool:
    """Stream a newsletter PDF to dest_path using the authenticated session."""
    return stream_download(
        pdf_url, dest_path, session, skip_existing=False, expected_content_type="application/pdf"
    )


