"""
http.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Site-agnostic HTTP session, retrying fetch, and streaming download helpers
shared by every F4WOnline downloader (podcasts, newsletters, ...).
"""

from __future__ import annotations

import time
from pathlib import Path

import requests


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


# ---------------------------------------------------------------------------
# Tunable defaults
# ---------------------------------------------------------------------------

DOWNLOAD_CHUNK_SIZE = 65536     # bytes per chunk when streaming downloads
HTTP_TIMEOUT_PAGE = 15          # seconds — page fetches
HTTP_TIMEOUT_DOWNLOAD = 30      # seconds — file downloads
HTTP_RETRY_COUNT = 3            # attempts before giving up on a page fetch
HTTP_RETRY_DELAY = 2.0          # base seconds between retries (multiplied by attempt)


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def create_session() -> requests.Session:
    """Return a new requests Session with shared headers pre-applied."""
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)
    return session


# ---------------------------------------------------------------------------
# Page fetching
# ---------------------------------------------------------------------------

def fetch_page(
    url: str,
    session: requests.Session,
    headers: dict | None = None,
    timeout: int = HTTP_TIMEOUT_PAGE,
    retries: int = HTTP_RETRY_COUNT,
    retry_delay: float = HTTP_RETRY_DELAY,
) -> requests.Response | None:
    """
    GET a URL using the authenticated session, retrying up to *retries*
    times on failure. Returns the response, or None if all attempts fail.
    """
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=headers or REQUEST_HEADERS, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            print(f"  [warn] Request failed ({exc}), attempt {attempt + 1}/{retries}")
            time.sleep(retry_delay * (attempt + 1))
    return None


# ---------------------------------------------------------------------------
# Streaming download
# ---------------------------------------------------------------------------

def stream_download(
    url: str,
    dest_path: Path,
    session: requests.Session,
    headers: dict | None = None,
    timeout: int = HTTP_TIMEOUT_DOWNLOAD,
    skip_existing: bool = True,
    chunk_size: int = DOWNLOAD_CHUNK_SIZE,
) -> bool:
    """
    Stream a file from *url* to *dest_path* using the authenticated session.

    Returns True on success (including skipped files), False on failure.
    """
    if skip_existing and dest_path.exists():
        print(f"  [skip] Already exists: {dest_path.name}")
        return True

    try:
        resp = session.get(
            url,
            headers=headers or REQUEST_HEADERS,
            stream=True,
            timeout=timeout,
        )
        resp.raise_for_status()

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                fh.write(chunk)

        size_mb = dest_path.stat().st_size / (1024 * 1024)
        print(f"  [ok]   {dest_path.name}  ({size_mb:.1f} MB)")
        return True

    except requests.RequestException as exc:
        print(f"  [fail] {url} — {exc}")
        return False
