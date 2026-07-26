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

import sys
import argparse
import tempfile

from pathlib import Path

from newsletterDownloader.util import (
    DEFAULT_NEWSLETTER_DOWNLOAD_PATH,
    clean_html_for_ebook,
    download_pdf,
    save_html,
    scrape_all_issues,
    scrape_issue_details,
)
from f4wCommon.http import create_session
from f4wCommon.dates import DATE_FORMAT_IN, enrich_with_date, in_date_range
from newsletterDownloader.kindle import calibre_available, convert_to_ebook
from f4wCommon.cli import add_common_arguments, login_or_exit, parse_cli_date
from f4wCommon.pipeline import print_dry_run, print_summary, run_download_loop


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

    add_common_arguments(
        parser,
        default_output=DEFAULT_NEWSLETTER_DOWNLOAD_PATH,
        item_noun="issue",
        delay_aliases=("--issue-delay",),
    )
    return parser


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

    # --- Config (validate before touching the network or prompting for credentials) ---
    output_root = Path(args.output) if args.output else DEFAULT_NEWSLETTER_DOWNLOAD_PATH
    start_date = parse_cli_date(args.start)
    end_date = parse_cli_date(args.end)
    yearly = not args.no_yearly
    monthly = not args.no_monthly
    extension, handler = _FORMATS[args.format]

    # --- Auth ---
    # f4wCommon.auth.login() falls back to F4W_USERNAME/F4W_PASSWORD env vars
    # (e.g. from a local, gitignored .env file) before prompting interactively.
    session = create_session()
    login_or_exit(session)

    # --- Scrape issue index ---
    issues = scrape_all_issues(session, max_pages=args.max_pages, page_delay=args.page_delay)

    if not issues:
        print("[warn] No issues found. Check your network connection or the archive URL.")
        return

    # --- Enrich dates and apply date range filter ---
    issues = [enrich_with_date(issue, DATE_FORMAT_IN) for issue in issues]
    issues = [issue for issue in issues if in_date_range(issue, start_date, end_date)]
    print(f"{len(issues)} issue(s) after date filtering.")

    # --- Dry run ---
    if args.dry_run:
        print_dry_run(issues, output_root, extension, yearly, monthly, item_noun="issue")
        return

    # --- Download loop ---
    success, skipped, failed = run_download_loop(
        issues,
        session,
        output_root,
        extension=extension,
        handler=handler,
        scrape_details=scrape_issue_details,
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
    print("=== F4WOnline Newsletter Downloader ===\n")
    parser = _build_parser()
    args = parser.parse_args()
    _run_downloads(args)


if __name__ == "__main__":
    main()
