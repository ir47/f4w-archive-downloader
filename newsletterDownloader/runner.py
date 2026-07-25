"""
runner.py — F4WOnline Newsletter Downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Entry point and CLI for downloading Wrestling Observer Newsletter issues from
members.f4wonline.com.

Scrapes the newsletter archive to discover issues, visits individual issue
pages to find a PDF link and/or the full article HTML, and saves each issue
in the requested --format: the original PDF, the raw scraped webpage, or a
Calibre-converted Kindle ebook (.epub).

Usage examples
--------------
# Download all newsletter issues as PDFs:
python -m newsletterDownloader.runner --format pdf

# Download issues between two dates as saved webpages:
python -m newsletterDownloader.runner --format html --start "January 1, 2025" --end "March 17, 2026"

# Dry run — see what would be downloaded without downloading anything:
python -m newsletterDownloader.runner --format pdf --max-pages 1 --dry-run

# Convert issues to Kindle-ready .epub files (requires Calibre installed):
python -m newsletterDownloader.runner --format kindle --output ~/Newsletters
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

from f4wCommon.auth import login
from f4wCommon.dates import in_date_range, parse_date_arg
from f4wCommon.fsutil import generate_download_directories
from f4wCommon.http import create_session

from newsletterDownloader.kindle import calibre_available, convert_to_ebook
from newsletterDownloader.util import (
    DATE_FORMAT_IN,
    DEFAULT_NEWSLETTER_DOWNLOAD_PATH,
    build_newsletter_path,
    clean_html_for_ebook,
    download_pdf,
    enrich_issue,
    newsletter_filename,
    save_html,
    scrape_all_issues,
    scrape_issue_details,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="F4WOnline Newsletter Downloader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--format",
        choices=["pdf", "html", "kindle"],
        default="pdf",
        help="Output format for each issue: the original PDF, the raw scraped "
             "webpage, or a Calibre-converted Kindle ebook (default: pdf).",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        default=None,
        help=f"Root download directory (default: {DEFAULT_NEWSLETTER_DOWNLOAD_PATH}).",
    )
    parser.add_argument(
        "--start",
        metavar="DATE",
        default=None,
        help="Only download issues on or after this date, e.g. 'January 1, 2025'.",
    )
    parser.add_argument(
        "--end",
        metavar="DATE",
        default=None,
        help="Only download issues on or before this date, e.g. 'March 17, 2026'.",
    )
    parser.add_argument(
        "--max-pages",
        metavar="N",
        type=int,
        default=None,
        help="Limit archive pages scraped (useful for testing).",
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
        help="Seconds to sleep between archive page requests (default: 1.0).",
    )
    parser.add_argument(
        "--issue-delay",
        metavar="SECONDS",
        type=float,
        default=0.5,
        help="Seconds to sleep between individual issue requests (default: 0.5).",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-download issues that already exist on disk.",
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
# Format-specific extensions / dispatch
# ---------------------------------------------------------------------------


def _download_pdf_format(issue: dict, details: dict, dest: Path, session) -> bool:
    if not details["pdf_url"]:
        print(f"  [fail] Could not find a PDF link on {issue['url']}")
        return False
    return download_pdf(details["pdf_url"], dest, session)


def _download_html_format(issue: dict, details: dict, dest: Path, session) -> bool:
    if not details["html_content"]:
        print(f"  [fail] Could not find article content on {issue['url']}")
        return False
    return save_html(details["html_content"], dest, issue["title"])


def _download_kindle_format(issue: dict, details: dict, dest: Path, session) -> bool:
    """
    Convert the issue to a Kindle-ready .epub, preferring the scraped HTML as
    the conversion source and falling back to the PDF. WON newsletters are
    laid out in dense multi-column PDFs, and Calibre's PDF reflow interleaves
    text across columns line-by-line rather than column-by-column, garbling
    sentences; the scraped HTML is normal single-column reflowable text and
    converts cleanly. The intermediate PDF/HTML is discarded after conversion.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        if details["html_content"]:
            scratch = Path(tmpdir) / "source.html"
            cleaned = clean_html_for_ebook(details["html_content"])
            if not save_html(cleaned, scratch, issue["title"]):
                return False
        elif details["pdf_url"]:
            scratch = Path(tmpdir) / "source.pdf"
            if not download_pdf(details["pdf_url"], scratch, session):
                return False
        else:
            print(f"  [fail] No PDF or article content found on {issue['url']}")
            return False

        return convert_to_ebook(scratch, dest)


# Maps --format to (file extension, handler function).
_FORMATS = {
    "pdf": ("pdf", _download_pdf_format),
    "html": ("html", _download_html_format),
    "kindle": ("epub", _download_kindle_format),
}


# ---------------------------------------------------------------------------
# Download workflow
# ---------------------------------------------------------------------------

def _run_downloads(args: argparse.Namespace) -> None:
    # --- Environment check (fail fast, before login/scraping) ---
    if args.format == "kindle" and not calibre_available():
        print(
            "\n[error] Calibre's `ebook-convert` was not found on PATH.\n"
            "Install Calibre from https://calibre-ebook.com/download, ensure "
            "`ebook-convert` is on PATH, then retry."
        )
        sys.exit(1)

    # --- Auth ---
    # f4wCommon.auth.login() falls back to F4W_USERNAME/F4W_PASSWORD env vars
    # (e.g. from a local, gitignored .env file) before prompting interactively.
    session = create_session()
    if not login(session):
        print(
            "\n[error] Could not log in to F4WOnline.\n"
            "Please check your credentials and that your subscription is active.\n"
            "You can reset your password at: https://account.f4wonline.com/login?sendpass"
        )
        sys.exit(1)

    # --- Config ---
    output_root = Path(args.output) if args.output else DEFAULT_NEWSLETTER_DOWNLOAD_PATH
    start_date = _parse_date_arg(args.start)
    end_date = _parse_date_arg(args.end)
    yearly = not args.no_yearly
    monthly = not args.no_monthly
    extension, handler = _FORMATS[args.format]

    # --- Scrape issue index ---
    issues = scrape_all_issues(session, max_pages=args.max_pages, page_delay=args.page_delay)

    if not issues:
        print("[warn] No issues found. Check your network connection or the archive URL.")
        return

    # --- Enrich dates and apply date range filter ---
    issues = [enrich_issue(issue) for issue in issues]
    issues = [issue for issue in issues if _in_date_range(issue, start_date, end_date)]
    print(f"{len(issues)} issue(s) after date filtering.")

    # --- Dry run ---
    if args.dry_run:
        print("\n--- DRY RUN: issues that would be downloaded ---")
        for issue in issues:
            folder = build_newsletter_path(output_root, issue, yearly, monthly)
            filename = newsletter_filename(issue, extension)
            print(f"  {folder / filename}")
        return

    # --- Download loop ---
    success, skipped, failed = 0, 0, 0

    for i, issue in enumerate(issues, 1):
        print(f"\n[{i}/{len(issues)}] {issue['title']} ({issue['date']})")

        folder = build_newsletter_path(output_root, issue, yearly, monthly)
        filename = newsletter_filename(issue, extension)
        dest = folder / filename

        if dest.exists() and not args.overwrite:
            print(f"  [skip] Already exists: {dest.name}")
            skipped += 1
            time.sleep(args.issue_delay)
            continue

        if not generate_download_directories(folder):
            failed += 1
            time.sleep(args.issue_delay)
            continue

        details = scrape_issue_details(issue["url"], session)

        if handler(issue, details, dest, session):
            success += 1
        else:
            failed += 1

        time.sleep(args.issue_delay)

    # --- Summary ---
    print(f"\n{'=' * 50}")
    print(f"Done.  Downloaded: {success}  |  Skipped: {skipped}  |  Failed: {failed}")
    print(f"Files saved to: {output_root}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== F4WOnline Newsletter Downloader ===\n")
    parser = _build_parser()
    args = parser.parse_args()
    _run_downloads(args)


if __name__ == "__main__":
    main()
