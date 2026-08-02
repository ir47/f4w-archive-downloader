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

# Keep an already-downloaded archive current — watch the RSS feed and grab
# each new episode as it is published (Ctrl-C to stop):
python runner.py --all --watch

# One check of the feed, then exit — for running from cron or launchd:
python runner.py --all --watch --once
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
from podcastDownloader.feed import create_poller, episodes_from_feed
from f4wCommon.auth import login
from f4wCommon.http import create_session
from f4wCommon.dates import DATE_FORMAT_IN, enrich_with_date, in_date_range
from f4wCommon.cli import add_common_arguments, login_or_exit, parse_cli_date
from f4wCommon.pipeline import (
    DEFAULT_POLL_INTERVAL,
    filter_new_items,
    print_dry_run,
    print_summary,
    run_download_loop,
    run_watch_loop,
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

    add_common_arguments(
        parser,
        default_output=DEFAULT_DOWNLOAD_PATH,
        item_noun="episode",
        delay_aliases=("--episode-delay",),
    )

    watch = parser.add_argument_group("watch mode")
    watch.add_argument(
        "--watch", "-w",
        action="store_true",
        help=(
            "Follow the podcast RSS feed and download each new episode as it "
            "is published, checking every --poll-interval seconds until "
            "stopped. Use after downloading the archive to keep it current."
        ),
    )
    watch.add_argument(
        "--poll-interval",
        metavar="SECONDS",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help=f"Seconds between feed checks in watch mode (default: {DEFAULT_POLL_INTERVAL:.0f}).",
    )
    watch.add_argument(
        "--once",
        action="store_true",
        help="With --watch, check the feed once and exit instead of looping "
             "(for running under cron or launchd).",
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
    if not details.get("mp3_url"):
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
# Watch workflow
# ---------------------------------------------------------------------------

def _run_watch(args: argparse.Namespace) -> None:
    """
    Follow the RSS feed, downloading each episode that appears in it and is
    not already on disk.

    The first check downloads everything in the feed that is missing, which is
    what closes the gap between when an archive run finished and when the
    watch started. After that it only ever sees the handful published since.
    """
    output_root = Path(args.output) if args.output else DEFAULT_DOWNLOAD_PATH
    start_date = parse_cli_date(args.start)
    end_date = parse_cli_date(args.end)
    yearly = not args.no_yearly
    monthly = not args.no_monthly
    show_slug = args.show if not args.all else None

    if show_slug and show_slug not in SHOW_SLUGS:
        print(f"[warn] '{show_slug}' is not a recognised show slug.")
        _print_show_list()
        print("Continuing anyway — will watch any feed matching that value.\n")

    if args.max_pages:
        print("[warn] --max-pages does not apply to watch mode — the feed is a single "
              "page of the 50 most recent episodes.\n")

    overwrite = args.overwrite
    if overwrite and not args.once:
        # Left on, every check would re-download all fifty episodes in the
        # feed, forever. --once is bounded, so it can keep the flag.
        print("[warn] --overwrite is ignored by a looping watch (it would re-download "
              "the whole feed on every check). Use --watch --once to force one pass.\n")
        overwrite = False

    session = create_session()
    login_or_exit(session)

    poller = create_poller(session, show_slug)
    target = SHOW_SLUGS.get(show_slug, show_slug) if show_slug else "all shows"
    print(f"\nWatching {target} — {poller.url}")
    print(f"Saving to: {output_root}\n")

    # Set by the download pass, read by the next check: a cycle where
    # everything failed usually means the login has lapsed rather than that
    # every file is broken, and the session is only worth rebuilding then.
    state = {"reauth": False}

    def check():
        if state["reauth"]:
            state["reauth"] = False
            print("  [auth] Refreshing the login before retrying…")
            if not login(session):
                print("  [warn] Could not log back in — will retry on the next check.")
                return None

        items = poller.poll()
        if items is None:
            return None

        episodes, details_by_url = episodes_from_feed(items)
        episodes = [enrich_with_date(ep, DATE_FORMAT_IN) for ep in episodes]
        episodes = [ep for ep in episodes if in_date_range(ep, start_date, end_date)]
        if not overwrite:
            episodes = filter_new_items(episodes, output_root, "mp3", yearly, monthly)

        # Carried on the episode so the download pass can serve details back
        # without refetching the episode page the feed already described.
        for episode in episodes:
            episode["details"] = details_by_url.get(episode["url"], {})
        return episodes

    def download(episodes):
        print(f"  [new]  {len(episodes)} episode(s) to download.")
        counts = run_download_loop(
            episodes,
            session,
            output_root,
            extension="mp3",
            handler=_download_mp3_format,
            scrape_details=lambda url, _session: _feed_details(episodes, url),
            yearly=yearly,
            monthly=monthly,
            overwrite=overwrite,
            item_delay=args.item_delay,
        )
        success, _skipped, failed = counts
        state["reauth"] = failed > 0 and success == 0
        return counts

    if args.dry_run:
        episodes = check()
        if not episodes:
            print("Nothing new in the feed.")
            return
        print_dry_run(episodes, output_root, "mp3", yearly, monthly, item_noun="episode")
        return

    success, skipped, failed = run_watch_loop(
        check,
        download,
        poll_interval=args.poll_interval,
        once=args.once,
    )
    print_summary(success, skipped, failed, output_root)


def _feed_details(episodes: list, url: str) -> dict:
    """
    Serve an episode's details straight from the feed item it came from.

    Stands in for scrape_episode_details in watch mode: the feed already
    carried the MP3 URL, host, description, tags and artwork, so there is no
    episode page left to fetch.
    """
    for episode in episodes:
        if episode["url"] == url:
            return episode.get("details", {})
    return {}


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

    if args.watch:
        _run_watch(args)
    else:
        _run_downloads(args)


if __name__ == "__main__":
    main()
