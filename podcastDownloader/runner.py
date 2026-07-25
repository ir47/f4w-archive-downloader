"""
runner.py — F4WOnline Podcast Downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Entry point and CLI for downloading F4WOnline podcasts.

Scrapes each show's WordPress category archive to discover episodes, visits
individual episode pages to extract the direct MP3 download link, downloads
the files into an organised folder hierarchy, and embeds ID3 metadata tags.

Usage examples
--------------
# Download all Wrestling Observer Radio episodes:
python runner.py --show wrestling-observer-radio

# Dry run — see what would be downloaded without downloading anything:
python runner.py --show wrestling-observer-radio --max-pages 1 --dry-run

# Download a specific show between two dates:
python runner.py --show bryan-and-vinny-show --start "January 1, 2025" --end "March 17, 2026"

# Download all shows to a custom folder without monthly sub-folders:
python runner.py --all --output ~/Podcasts --no-monthly

# Re-download episodes that already exist on disk:
python runner.py --show after-dark --overwrite
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from f4wCommon.dates import in_date_range, parse_date_arg

from podcastDownloader.util import (
    DATE_FORMAT_IN,
    DEFAULT_DOWNLOAD_PATH,
    SHOW_SLUGS,
    build_download_path,
    create_session,
    download_podcast,
    enrich_episode,
    generate_download_directories,
    login,
    sanitize_filename,
    scrape_all_episodes,
    scrape_episode_details,
    write_id3_tags,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="F4WOnline Podcast Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument(
        "--show", "-s",
        metavar="SHOW_SLUG",
        help=(
            "Slug of the show to download, e.g. 'wrestling-observer-radio'. "
            "Run with --list-shows to see all valid slugs."
        ),
    )
    target.add_argument(
        "--all", "-A",
        action="store_true",
        help="Download every episode from every show.",
    )
    target.add_argument(
        "--list-shows",
        action="store_true",
        help="Print all available show slugs and exit.",
    )

    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        default=None,
        help=f"Root download directory (default: {DEFAULT_DOWNLOAD_PATH}).",
    )
    parser.add_argument(
        "--start",
        metavar="DATE",
        default=None,
        help="Only download episodes on or after this date, e.g. 'January 1, 2025'.",
    )
    parser.add_argument(
        "--end",
        metavar="DATE",
        default=None,
        help="Only download episodes on or before this date, e.g. 'March 17, 2026'.",
    )
    parser.add_argument(
        "--max-pages",
        metavar="N",
        type=int,
        default=None,
        help="Limit pages scraped per show (useful for testing).",
    )
    parser.add_argument(
        "--no-yearly",
        action="store_true",
        help="Don't create per-year sub-folders.",
    )
    parser.add_argument(
        "--no-monthly",
        action="store_true",
        help="Don't create per-month sub-folders.",
    )
    parser.add_argument(
        "--page-delay",
        metavar="SECONDS",
        type=float,
        default=1.0,
        help="Seconds to sleep between index page requests (default: 1.0).",
    )
    parser.add_argument(
        "--episode-delay",
        metavar="SECONDS",
        type=float,
        default=0.5,
        help="Seconds to sleep between individual episode requests (default: 0.5).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download episodes that already exist on disk.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be downloaded without actually downloading.",
    )

    return parser


# ---------------------------------------------------------------------------
# Date filtering
# ---------------------------------------------------------------------------

def _parse_date_arg(value: str | None) -> datetime | None:
    """Parse a CLI date string. Exits with an error message on bad input."""
    return parse_date_arg(value, DATE_FORMAT_IN, "January 1, 2025")


_in_date_range = in_date_range


# ---------------------------------------------------------------------------
# Show listing
# ---------------------------------------------------------------------------

def _print_show_list() -> None:
    """Print all known show slugs and their display names."""
    print("Available shows:\n")
    for slug, name in SHOW_SLUGS.items():
        print(f"  {slug:<45} {name}")
    print()


# ---------------------------------------------------------------------------
# Download workflow
# ---------------------------------------------------------------------------

def _run_downloads(args: argparse.Namespace) -> None:
    # --- Auth ---
    session = create_session()
    if not login(session):
        print(
            "\n[error] Could not log in to F4WOnline.\n"
            "Please check your credentials and that your subscription is active.\n"
            "You can reset your password at: https://account.f4wonline.com/login?sendpass"
        )
        sys.exit(1)

    # --- Config ---
    output_root = Path(args.output) if args.output else DEFAULT_DOWNLOAD_PATH
    start_date = _parse_date_arg(args.start)
    end_date = _parse_date_arg(args.end)
    yearly = not args.no_yearly
    monthly = not args.no_monthly

    # --- Show slug validation ---
    show_filter = args.show if not args.all else None
    if show_filter and show_filter not in SHOW_SLUGS:
        print(f"[warn] '{show_filter}' is not a recognised show slug.")
        _print_show_list()
        print("Continuing anyway — will scrape any category URL containing that value.\n")

    # --- Scrape episode index ---
    episodes = scrape_all_episodes(
        session,
        show_filter=show_filter,
        max_pages=args.max_pages,
        page_delay=args.page_delay,
    )

    if not episodes:
        print("[warn] No episodes found. Check your --show value or network connection.")
        return

    # --- Enrich dates and apply date range filter ---
    episodes = [enrich_episode(ep) for ep in episodes]
    episodes = [ep for ep in episodes if _in_date_range(ep, start_date, end_date)]
    print(f"{len(episodes)} episode(s) after date filtering.")

    # --- Dry run ---
    if args.dry_run:
        print("\n--- DRY RUN: episodes that would be downloaded ---")
        for ep in episodes:
            folder = build_download_path(output_root, ep, yearly, monthly)
            filename = f"{ep.get('day', '00')}-{sanitize_filename(ep['title'])}.mp3"
            print(f"  {folder / filename}")
        return

    # --- Download loop ---
    success, skipped, failed = 0, 0, 0

    for i, episode in enumerate(episodes, 1):
        print(f"\n[{i}/{len(episodes)}] {episode['title']} ({episode['date']})")

        details = scrape_episode_details(episode["url"], session)

        if not details["mp3_url"]:
            print(f"  [fail] Could not find MP3 link on {episode['url']}")
            failed += 1
            continue

        folder = build_download_path(output_root, episode, yearly, monthly)
        generate_download_directories(folder)
        filename = f"{episode.get('day', '00')}-{sanitize_filename(episode['title'])}.mp3"
        dest = folder / filename

        if dest.exists() and not args.overwrite:
            print(f"  [skip] Already exists: {dest.name}")
            skipped += 1
            time.sleep(args.episode_delay)
            continue

        downloaded = download_podcast(details["mp3_url"], dest, session=session, skip_existing=False)

        if not downloaded or dest.stat().st_size == 0:
            failed += 1
        else:
            track_num = int(episode.get("day", 0)) or None
            write_id3_tags(dest, episode, details, track_number=track_num)
            success += 1

        time.sleep(args.episode_delay)

    # --- Summary ---
    print(f"\n{'=' * 50}")
    print(f"Done.  Downloaded: {success}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"Files saved to: {output_root}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== F4WOnline Podcast Downloader ===\n")
    parser = _build_parser()
    args = parser.parse_args()

    if args.list_shows:
        _print_show_list()
        sys.exit(0)

    _run_downloads(args)


if __name__ == "__main__":
    main()