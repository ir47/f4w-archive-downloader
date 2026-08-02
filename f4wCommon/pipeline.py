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
import requests

from pathlib import Path
from datetime import datetime

from f4wCommon.fsutil import (
    build_item_path,
    generate_download_directories,
    item_filename,
)


# Seconds between feed checks in watch mode. Fifteen minutes is far below the
# rate the feed turns over (50 items spanning a couple of weeks), so nothing
# can fall off the end between checks, and an unchanged feed answers 304.
DEFAULT_POLL_INTERVAL = 900.0


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


def filter_new_items(
    items: list,
    output_root: Path,
    extension: str,
    yearly: bool = True,
    monthly: bool = True,
) -> list:
    """
    Return only the items whose destination file does not exist yet.

    ``run_download_loop`` already skips what is on disk, but a watcher re-reads
    the same feed every few minutes and would otherwise announce a skip for all
    fifty of its items on every check. Filtering first keeps an idle watch
    silent, and lets the caller see when a check found genuinely nothing.
    """
    return [
        item for item in items
        if not (
            build_item_path(output_root, item, yearly, monthly)
            / item_filename(item, extension)
        ).exists()
    ]


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


def run_watch_loop(
    check_fn,
    download_fn,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    once: bool = False,
    sleep_fn=time.sleep,
) -> tuple:
    """
    Check a source on a timer, downloading whatever it turns up, until
    interrupted. Returns the cumulative ``(success, skipped, failed)``.

    Args:
        check_fn:      callable() -> list | None. Items currently available,
                       [] if nothing has changed, None if the check failed.
                       The two empty cases are reported differently but both
                       simply wait for the next round.
        download_fn:   callable(items) -> (success, skipped, failed). Gets
                       every item the check returned, not only new ones —
                       deciding what is already on disk is the download
                       loop's job, and it is the one place that can tell.
        poll_interval: Seconds to wait between checks.
        once:          Check once and return, for running under cron/launchd
                       rather than as a resident process.

    Ctrl-C is caught rather than raised so a long-running watch still reports
    its tally on the way out.
    """
    totals = [0, 0, 0]

    try:
        while True:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n[{timestamp}] Checking for new releases…")

            items = check_fn()
            if items is None:
                print("  [warn] Check failed — will try again next time round.")
            elif not items:
                print("  [none] Nothing new.")
            else:
                counts = download_fn(items)
                totals = [total + count for total, count in zip(totals, counts)]

            if once:
                break

            print(f"  [wait] Next check in {poll_interval:.0f}s.  Ctrl-C to stop.")
            sleep_fn(poll_interval)

    except KeyboardInterrupt:
        print("\n\n[stop] Interrupted — shutting down.")

    return tuple(totals)


def print_summary(success: int, skipped: int, failed: int, output_root: Path) -> None:
    """Print the end-of-run tally."""
    print(f"\n{'=' * 50}")
    print(f"Done.  Downloaded: {success}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"Files saved to: {output_root}")
