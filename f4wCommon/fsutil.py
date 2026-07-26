"""
fsutil.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Site-agnostic filename/directory helpers shared by every F4WOnline downloader.
"""

from __future__ import annotations

import re
from pathlib import Path


def sanitize_filename(name: str) -> str:
    """Replace characters that are invalid in file/folder names with underscores."""
    return re.sub(r'[\\/:*?"<>|]', "_", name).strip()


def generate_download_directories(path: Path) -> bool:
    """Create the directory tree at path. Returns True on success, False on error."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        return True
    except OSError as exc:
        print(f"[error] Could not create directory {path}: {exc}")
        return False


def build_hierarchical_path(
    base_path: Path,
    category: str,
    year: str | None,
    month: str | None,
    yearly: bool,
    monthly: bool,
) -> Path:
    """
    Construct an output directory of the form:

        base_path / Category / Year / Month /

    with the Year/Month segments only included when the corresponding flag
    is True and a value is available.
    """
    path = base_path / sanitize_filename(category)
    if yearly and year:
        path = path / year
    if monthly and month:
        path = path / month
    return path


def build_item_path(base_path: Path, item: dict, yearly: bool, monthly: bool) -> Path:
    """
    Construct the output directory for a scraped item (podcast episode or
    newsletter issue), reading the category from ``item["show"]`` and the
    date segments from the fields added by ``enrich_with_date``:

        base_path / Show Name / Year / Month /
    """
    return build_hierarchical_path(
        base_path, item.get("show", ""), item.get("year"), item.get("month"), yearly, monthly
    )


def item_filename(item: dict, extension: str) -> str:
    """Build the '<day>-<sanitized-title>.<ext>' filename for a scraped item."""
    return f"{item.get('day', '00')}-{sanitize_filename(item['title'])}.{extension}"
