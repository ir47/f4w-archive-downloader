"""
dates.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Site-agnostic date parsing/enrichment shared by every F4WOnline downloader.
"""

from __future__ import annotations

import sys

from datetime import datetime


# ---------------------------------------------------------------------------
# Date formats
# ---------------------------------------------------------------------------

# Both F4WOnline archives render dates the same way, so these are shared.
DATE_FORMAT_IN = "%B %d, %Y"    # e.g. "March 17, 2026" — scraped dates
DATE_FORMAT_ISO = "%Y-%m-%d"    # e.g. "2026-03-17"     — <time> attrs, ID3 tags


def parse_date(date_str: str | None, fmt: str) -> datetime | None:
    """Parse a scraped date string using *fmt*, e.g. '%B %d, %Y'."""
    try:
        return datetime.strptime(date_str, fmt)
    except (ValueError, TypeError):
        return None


def enrich_with_date(
    item: dict,
    fmt: str,
    date_key: str = "date",
    unknown: str = "Unknown",
) -> dict:
    """
    Add parsed date fields to *item* in-place, reading the raw date string
    from ``item[date_key]``.

    Adds: year (str), month (str), day (str), datetime (datetime | None)
    Falls back to *unknown* / '00' when the date cannot be parsed.
    """
    dt = parse_date(item.get(date_key, ""), fmt)
    if dt:
        item["year"] = dt.strftime("%Y")
        item["month"] = dt.strftime("%B")
        item["day"] = dt.strftime("%d")
        item["datetime"] = dt
    else:
        item["year"] = unknown
        item["month"] = unknown
        item["day"] = "00"
        item["datetime"] = None
    return item


def parse_date_arg(value: str | None, fmt: str, example: str) -> datetime | None:
    """
    Parse a CLI date argument using *fmt*. Exits the process with an error
    message (showing *example* as the expected format) on bad input.
    """
    if not value:
        return None
    try:
        return datetime.strptime(value, fmt)
    except ValueError:
        print(f"[error] Could not parse date '{value}'. Expected format: '{example}'.")
        sys.exit(1)


def in_date_range(item: dict, start: datetime | None, end: datetime | None) -> bool:
    """Return True if item['datetime'] falls within [start, end] (either bound optional)."""
    dt = item.get("datetime")
    if dt is None:
        return True  # can't determine date — include by default
    if start and dt < start:
        return False
    if end and dt > end:
        return False
    return True
