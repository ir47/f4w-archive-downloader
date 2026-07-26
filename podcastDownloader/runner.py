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

import sys
import argparse

from pathlib import Path

from podcastDownloader.util import (
    DEFAULT_DOWNLOAD_PATH,
    SHOW_SLUGS,
    download_podcast,
    scrape_all_episodes,
    scrape_episode_details,
    write_id3_tags,
)
from f4wCommon.http import create_session
from f4wCommon.dates import DATE_FORMAT_IN, enrich_with_date, in_date_range
from f4wCommon.cli import add_common_arguments, login_or_exit, parse_cli_date
from f4wCommon.pipeline import print_dry_run, print_summary, run_download_loop


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

    add_common_arguments(
        parser,
        default_output=DEFAULT_DOWNLOAD_PATH,
        item_noun="episode",
        delay_aliases=("--episode-delay",),
    )
    return parser


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
# Format handler
# ---------------------------------------------------------------------------

def _download_mp3_format(episode: dict, details: dict, dest: Path, session) -> bool:
    """Download the episode MP3 and embed its ID3 tags."""
    if not details["mp3_url"]:
        print(f"  [fail] Could not find MP3 link on {episode['url']}")
        return False

    if not download_podcast(details["mp3_url"], dest, session=session, skip_existing=False):
        return False

    # Track number is the day-of-month, so episodes sort within their folder.
    track_num = int(episode.get("day", 0)) or None
    write_id3_tags(dest, episode, details, track_number=track_num)
    return True


# ---------------------------------------------------------------------------
# Download workflow
# ---------------------------------------------------------------------------

def _run_downloads(args: argparse.Namespace) -> None:
    # --- Config (validate before touching the network or prompting for credentials) ---
    output_root = Path(args.output) if args.output else DEFAULT_DOWNLOAD_PATH
    start_date = parse_cli_date(args.start)
    end_date = parse_cli_date(args.end)
    yearly = not args.no_yearly
    monthly = not args.no_monthly

    # --- Auth ---
    session = create_session()
    login_or_exit(session)

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
    episodes = [enrich_with_date(ep, DATE_FORMAT_IN) for ep in episodes]
    episodes = [ep for ep in episodes if in_date_range(ep, start_date, end_date)]
    print(f"{len(episodes)} episode(s) after date filtering.")

    # --- Dry run ---
    if args.dry_run:
        print_dry_run(episodes, output_root, "mp3", yearly, monthly, item_noun="episode")
        return

    # --- Download loop ---
    success, skipped, failed = run_download_loop(
        episodes,
        session,
        output_root,
        extension="mp3",
        handler=_download_mp3_format,
        scrape_details=scrape_episode_details,
        yearly=yearly,
        monthly=monthly,
        overwrite=args.overwrite,
        item_delay=args.item_delay,
    )
    print_summary(success, skipped, failed, output_root)


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
