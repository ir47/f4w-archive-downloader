"""
scrape.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Site-agnostic scraping helpers for the WordPress/jnews-themed archive pages
shared by every F4WOnline downloader (podcasts, newsletters, ...).
"""

from __future__ import annotations

import re
import requests

from bs4 import BeautifulSoup
from datetime import datetime

from f4wCommon.dates import DATE_FORMAT_IN, DATE_FORMAT_ISO
from f4wCommon.http import fetch_page as _default_fetch_page


_CONTENT_DIV_RE = re.compile(r"entry.content|post.content|article.content", re.I)


def find_content_container(soup: BeautifulSoup):
    """Find the main article/content container in a WordPress-themed page."""
    return soup.find("div", class_=_CONTENT_DIV_RE) or soup.find("article")


def extract_paragraphs(container, min_length: int = 0, limit: int | None = None) -> str:
    """
    Join the text of the substantial <p> tags inside *container*, blank-line
    separated. Paragraphs of *min_length* characters or fewer are dropped
    (they are almost always bylines, ad slugs or "Right Click Save As"), and
    at most *limit* are kept. Returns "" when *container* is None.
    """
    if container is None:
        return ""
    paragraphs = [
        p.get_text(" ", strip=True)
        for p in container.find_all("p")
        if len(p.get_text(strip=True)) > min_length
    ]
    if limit is not None:
        paragraphs = paragraphs[:limit]
    return "\n\n".join(paragraphs)


def extract_time_element_date(container, iso_fmt: str, out_fmt: str) -> str:
    """
    Given a container tag, find a nested <time datetime="..."> element and
    reformat its ISO date into out_fmt. Returns "" if no valid <time>
    element is found.
    """
    if container is None:
        return ""
    time_el = container.find("time")
    if not time_el:
        return ""
    dt_attr = time_el.get("datetime", "")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", dt_attr)
    if not m:
        return ""
    try:
        dt = datetime.strptime(m.group(1), iso_fmt)
        return dt.strftime(out_fmt)
    except ValueError:
        return ""


def scrape_listing_page(
    url: str,
    session: requests.Session,
    link_filter,
    extra_fields: dict | None = None,
    date_fallback=None,
    item_noun: str = "item(s)",
    fetch_fn=_default_fetch_page,
) -> list:
    """
    Scrape one page of a paginated WordPress archive index.

    Returns a list of dicts: ``{ title, url, date, **extra_fields }``, one per
    heading link that passes *link_filter*.

    Args:
        url:           The archive page URL to fetch.
        session:       Authenticated requests Session.
        link_filter:   callable(post_url) -> bool. Returning False skips the link.
        extra_fields:  Static keys merged into every entry (e.g. the show name).
        date_fallback: Optional callable(post_url) -> str, consulted only when
                       the listing has no usable <time> element.
        item_noun:     Plural noun used in the progress log line.
        fetch_fn:      Injectable page-fetch function.
    """
    print(f"  [fetch] {url}")
    resp = fetch_fn(url, session)
    if resp is None:
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    entries = []

    for heading in soup.select("h3 a[href], h2 a[href]"):
        post_url = heading["href"]
        if not link_filter(post_url):
            continue

        title = heading.get_text(strip=True)
        if not title:
            continue

        # Prefer the ISO datetime attribute on a <time> element for accuracy.
        container = heading.find_parent("article") or heading.find_parent("div")
        date_text = extract_time_element_date(container, DATE_FORMAT_ISO, DATE_FORMAT_IN)
        if not date_text and date_fallback is not None:
            date_text = date_fallback(post_url)

        entries.append({
            "title": title,
            "url": post_url,
            "date": date_text,
            **(extra_fields or {}),
        })

    print(f"  [parse] {len(entries)} {item_noun}")
    return entries


def get_total_pages(page_url_fn, session: requests.Session, fetch_fn=_default_fetch_page) -> int:
    """
    Fetch page 1 of a paginated WordPress archive and return the total page
    count by finding the highest page number in the pagination links.

    page_url_fn: callable taking a page number and returning that page's URL.
    fetch_fn:    injectable page-fetch function (defaults to f4wCommon.http.fetch_page).
    """
    url = page_url_fn(1)
    print(f"  [fetch] {url}")
    resp = fetch_fn(url, session)
    if resp is None:
        print(f"  [warn] Could not fetch {url} to count pages — assuming 1 page. "
              "If the site is reachable, this run will look successful but miss everything past page 1.")
        return 1
    soup = BeautifulSoup(resp.text, "html.parser")
    max_page = 1
    for a in soup.select("a[href*='/page/']"):
        m = re.search(r"/page/(\d+)/", a["href"])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page
