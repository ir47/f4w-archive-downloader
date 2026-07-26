"""Unit tests for newsletterDownloader/kindle.py"""
import subprocess

from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from newsletterDownloader.kindle import calibre_available, convert_to_ebook


# ---------------------------------------------------------------------------
# calibre_available
# ---------------------------------------------------------------------------

class TestCalibreAvailable(TestCase):
    @patch("newsletterDownloader.kindle.shutil.which")
    def test_returns_true_when_found(self, mock_which):
        mock_which.return_value = "/usr/bin/ebook-convert"
        self.assertTrue(calibre_available())

    @patch("newsletterDownloader.kindle.shutil.which")
    def test_returns_false_when_not_found(self, mock_which):
        mock_which.return_value = None
        self.assertFalse(calibre_available())

    @patch("newsletterDownloader.kindle.shutil.which")
    def test_checks_for_ebook_convert(self, mock_which):
        mock_which.return_value = None
        calibre_available()
        mock_which.assert_called_once_with("ebook-convert")


# ---------------------------------------------------------------------------
# convert_to_ebook
# ---------------------------------------------------------------------------

class TestConvertToEbook(TestCase):
    @patch("newsletterDownloader.kindle.subprocess.run")
    def test_returns_true_on_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        result = convert_to_ebook(Path("/tmp/source.pdf"), Path("/tmp/dest.epub"))
        self.assertTrue(result)

    @patch("newsletterDownloader.kindle.subprocess.run")
    def test_invokes_ebook_convert_with_source_and_dest(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        convert_to_ebook(Path("/tmp/source.pdf"), Path("/tmp/dest.epub"))
        args = mock_run.call_args[0][0]
        self.assertEqual(["ebook-convert", "/tmp/source.pdf", "/tmp/dest.epub"], args)

    @patch("newsletterDownloader.kindle.subprocess.run")
    def test_returns_false_on_nonzero_exit(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="conversion error")
        result = convert_to_ebook(Path("/tmp/source.pdf"), Path("/tmp/dest.epub"))
        self.assertFalse(result)

    @patch("newsletterDownloader.kindle.subprocess.run")
    def test_returns_false_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ebook-convert", timeout=120)
        result = convert_to_ebook(Path("/tmp/source.pdf"), Path("/tmp/dest.epub"))
        self.assertFalse(result)

    @patch("newsletterDownloader.kindle.subprocess.run")
    def test_never_raises_on_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ebook-convert", timeout=120)
        try:
            convert_to_ebook(Path("/tmp/source.pdf"), Path("/tmp/dest.epub"))
        except subprocess.TimeoutExpired:
            self.fail("convert_to_ebook should not propagate TimeoutExpired")

    @patch("newsletterDownloader.kindle.subprocess.run")
    def test_respects_custom_timeout(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        convert_to_ebook(Path("/tmp/source.pdf"), Path("/tmp/dest.epub"), timeout=30)
        self.assertEqual(30, mock_run.call_args[1]["timeout"])


if __name__ == "__main__":
    main()
