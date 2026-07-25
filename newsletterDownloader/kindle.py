"""
kindle.py — F4WOnline Newsletter Downloader
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Wraps Calibre's `ebook-convert` CLI to turn a saved PDF/HTML newsletter issue
into a local ebook file (.epub by default).

Calibre (https://calibre-ebook.com) must be installed separately — it is not
a pip package, so `ebook-convert` is invoked as an external subprocess and is
expected to already be on PATH.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def calibre_available() -> bool:
    """Return True if Calibre's `ebook-convert` CLI is available on PATH."""
    return shutil.which("ebook-convert") is not None


def convert_to_ebook(source_path: Path, dest_path: Path, timeout: int = 120) -> bool:
    """
    Convert *source_path* (PDF or HTML) into an ebook at *dest_path* using
    Calibre's `ebook-convert`. The output format is inferred by `ebook-convert`
    from dest_path's extension (e.g. .epub).

    Returns True on success, False on non-zero exit or timeout. Never raises.
    """
    try:
        result = subprocess.run(
            ["ebook-convert", str(source_path), str(dest_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"  [fail] ebook-convert timed out converting {source_path.name}")
        return False

    if result.returncode != 0:
        print(f"  [fail] ebook-convert failed for {source_path.name}: {result.stderr.strip()}")
        return False

    print(f"  [ok]   {dest_path.name}")
    return True
