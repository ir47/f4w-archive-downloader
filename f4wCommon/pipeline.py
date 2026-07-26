"""
pipeline.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
The download workflow shared by every F4WOnline downloader: report what a dry
run would fetch, then loop over scraped items resolving each one's destination,
fetching its detail page, and delegating the actual save to a format handler.

A *handler* has the signature ``(item, details, dest, session) -> bool`` and
owns everything format-specific (writing an MP3 plus ID3 tags, saving a PDF,
converting to an ebook). Returning False marks the item failed.
"""

from __future__ import annotations

import time
from pathlib import Path

import requests

from f4wCommon.fsutil import (
    build_item_path,
    generate_download_directories,
    item_filename,
)


def print_dry_run(
    items: list,
    output_root: Path,
    extension: str,
    yearly: bool,
    monthly: bool,
    item_noun: str = "item",
) -> None:
    """Print the destination path each item would be written to."""
    print(f"\n--- DRY RUN: {item_noun}s that would be downloaded ---")
    for item in items:
        folder = build_item_path(output_root, item, yearly, monthly)
        print(f"  {folder / item_filename(item, extension)}")


def run_download_loop(
    items: list,
    session: requests.Session,
    output_root: Path,
    extension: str,
    handler,
    scrape_details,
    yearly: bool = True,
    monthly: bool = True,
    overwrite: bool = False,
    item_delay: float = 0.5,
) -> tuple:
    """
    Download every item in *items*, returning ``(success, skipped, failed)``.

    For each item: build its destination path, skip it when it already exists
    (unless *overwrite*), create the folder, fetch its detail page via
    ``scrape_details(url, session)``, then hand off to *handler*.

    Sleeps *item_delay* seconds after every item — including skipped and
    failed ones — to stay polite to the site.
    """
    success, skipped, failed = 0, 0, 0

    for i, item in enumerate(items, 1):
        print(f"\n[{i}/{len(items)}] {item['title']} ({item['date']})")

        folder = build_item_path(output_root, item, yearly, monthly)
        dest = folder / item_filename(item, extension)

        if dest.exists() and not overwrite:
            print(f"  [skip] Already exists: {dest.name}")
            skipped += 1
        elif not generate_download_directories(folder):
            failed += 1
        else:
            details = scrape_details(item["url"], session)
            if handler(item, details, dest, session):
                success += 1
            else:
                failed += 1

        time.sleep(item_delay)

    return success, skipped, failed


def print_summary(success: int, skipped: int, failed: int, output_root: Path) -> None:
    """Print the end-of-run tally."""
    print(f"\n{'=' * 50}")
    print(f"Done.  Downloaded: {success}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"Files saved to: {output_root}")
