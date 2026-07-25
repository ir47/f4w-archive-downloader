"""
scrape.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Site-agnostic scraping helpers for the WordPress/jnews-themed archive pages
shared by every F4WOnline downloader (podcasts, newsletters, ...).
"""

from __future__ import annotations

import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from f4wCommon.http import fetch_page as _default_fetch_page


_CONTENT_DIV_RE = re.compile(r"entry.content|post.content|article.content", re.I)


def find_content_container(soup: BeautifulSoup):
    """Find the main article/content container in a WordPress-themed page."""
    return soup.find("div", class_=_CONTENT_DIV_RE) or soup.find("article")


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
        return 1
    soup = BeautifulSoup(resp.text, "html.parser")
    max_page = 1
    for a in soup.select("a[href*='/page/']"):
        m = re.search(r"/page/(\d+)/", a["href"])
        if m:
            max_page = max(max_page, int(m.group(1)))
    return max_page
