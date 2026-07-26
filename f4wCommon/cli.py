"""
cli.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Argument-parser wiring and CLI-level helpers shared by every F4WOnline
downloader entry point.
"""

from __future__ import annotations

import sys
import argparse
import requests

from pathlib import Path
from datetime import datetime

from f4wCommon.auth import login
from f4wCommon.dates import DATE_FORMAT_IN, parse_date_arg


# Shown in --help and in the error message when a date fails to parse.
DATE_ARG_EXAMPLE = "January 1, 2025"

LOGIN_FAILED_MESSAGE = (
    "\n[error] Could not log in to F4WOnline.\n"
    "Please check your credentials and that your subscription is active.\n"
    "You can reset your password at: https://account.f4wonline.com/login?sendpass"
)


def add_common_arguments(
    parser: argparse.ArgumentParser,
    default_output: Path,
    item_noun: str,
    delay_aliases: tuple = (),
) -> None:
    """
    Add the arguments every downloader CLI shares.

    Args:
        parser:        The parser to add arguments to.
        default_output: Download root shown in --help.
        item_noun:      Singular noun for the thing being downloaded
                        ("episode", "issue"), interpolated into help text.
        delay_aliases:  Extra option strings accepted for --item-delay, hidden
                        from --help. Each downloader had its own spelling
                        (--episode-delay, --issue-delay) before the flag was
                        unified; these keep existing scripts working.
    """
    parser.add_argument(
        "--output", "-o",
        metavar="PATH",
        default=None,
        help=f"Root download directory (default: {default_output}).",
    )
    parser.add_argument(
        "--start",
        metavar="DATE",
        default=None,
        help=f"Only download {item_noun}s on or after this date, e.g. '{DATE_ARG_EXAMPLE}'.",
    )
    parser.add_argument(
        "--end",
        metavar="DATE",
        default=None,
        help=f"Only download {item_noun}s on or before this date, e.g. 'March 17, 2026'.",
    )
    parser.add_argument(
        "--max-pages",
        metavar="N",
        type=int,
        default=None,
        help="Limit archive index pages scraped (useful for testing).",
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
        help="Seconds to sleep between archive index page requests (default: 1.0).",
    )
    parser.add_argument(
        "--item-delay",
        metavar="SECONDS",
        dest="item_delay",
        type=float,
        default=0.5,
        help=f"Seconds to sleep between individual {item_noun} requests (default: 0.5).",
    )
    for alias in delay_aliases:
        # default=SUPPRESS so an unused alias doesn't clobber --item-delay's default.
        parser.add_argument(
            alias,
            metavar="SECONDS",
            dest="item_delay",
            type=float,
            default=argparse.SUPPRESS,
            help=argparse.SUPPRESS,
        )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=f"Re-download {item_noun}s that already exist on disk.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be downloaded without actually downloading.",
    )


def parse_cli_date(value: str | None) -> datetime | None:
    """Parse a --start/--end CLI date. Exits with an error message on bad input."""
    return parse_date_arg(value, DATE_FORMAT_IN, DATE_ARG_EXAMPLE)


def login_or_exit(session: requests.Session) -> None:
    """Authenticate *session*, or print recovery guidance and exit non-zero."""
    if not login(session):
        print(LOGIN_FAILED_MESSAGE)
        sys.exit(1)
