"""Unit tests for f4wCommon/pipeline.py"""
import io
import tempfile

from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from f4wCommon.pipeline import print_dry_run, print_summary, run_download_loop


def _item(title="Ep One", day="17", show="Show A", year="2026", month="March"):
    return {
        "title": title,
        "url": f"https://example.com/{title.replace(' ', '-').lower()}/",
        "date": "March 17, 2026",
        "show": show,
        "year": year,
        "month": month,
        "day": day,
    }


@patch("f4wCommon.pipeline.time.sleep")
class TestRunDownloadLoop(TestCase):
    def _run(self, items, handler, tmpdir, scrape_details=None, **kwargs):
        return run_download_loop(
            items,
            MagicMock(),
            Path(tmpdir),
            extension="mp3",
            handler=handler,
            scrape_details=scrape_details or MagicMock(return_value={"ok": True}),
            **kwargs,
        )

    def test_counts_successful_download(self, _sleep):
        with tempfile.TemporaryDirectory() as tmpdir:
            counts = self._run([_item()], lambda *a: True, tmpdir)
        self.assertEqual((1, 0, 0), counts)

    def test_counts_failed_download(self, _sleep):
        with tempfile.TemporaryDirectory() as tmpdir:
            counts = self._run([_item()], lambda *a: False, tmpdir)
        self.assertEqual((0, 0, 1), counts)

    def test_counts_multiple_items(self, _sleep):
        items = [_item("A", day="01"), _item("B", day="02"), _item("C", day="03")]
        results = iter([True, False, True])
        with tempfile.TemporaryDirectory() as tmpdir:
            counts = self._run(items, lambda *a: next(results), tmpdir)
        self.assertEqual((2, 0, 1), counts)

    def test_skips_existing_file(self, _sleep):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "Show A" / "2026" / "March"
            dest.mkdir(parents=True)
            (dest / "17-Ep One.mp3").write_bytes(b"x")
            handler = MagicMock()
            counts = self._run([_item()], handler, tmpdir)
        self.assertEqual((0, 1, 0), counts)
        handler.assert_not_called()

    def test_overwrite_redownloads_existing_file(self, _sleep):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "Show A" / "2026" / "March"
            dest.mkdir(parents=True)
            (dest / "17-Ep One.mp3").write_bytes(b"x")
            counts = self._run([_item()], lambda *a: True, tmpdir, overwrite=True)
        self.assertEqual((1, 0, 0), counts)

    def test_scrape_details_called_with_item_url(self, _sleep):
        scrape = MagicMock(return_value={})
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run([_item()], lambda *a: True, tmpdir, scrape_details=scrape)
        self.assertEqual("https://example.com/ep-one/", scrape.call_args[0][0])

    def test_handler_receives_item_details_and_dest(self, _sleep):
        handler = MagicMock(return_value=True)
        scrape = MagicMock(return_value={"mp3_url": "x"})
        item = _item()
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run([item], handler, tmpdir, scrape_details=scrape)
            call_args = handler.call_args[0]
        self.assertIs(item, call_args[0])
        self.assertEqual({"mp3_url": "x"}, call_args[1])
        self.assertEqual("17-Ep One.mp3", call_args[2].name)

    def test_counts_failure_when_directory_creation_fails(self, _sleep):
        handler = MagicMock()
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("f4wCommon.pipeline.generate_download_directories", return_value=False):
                counts = self._run([_item()], handler, tmpdir)
        self.assertEqual((0, 0, 1), counts)
        handler.assert_not_called()

    def test_sleeps_after_every_item_including_skips(self, mock_sleep):
        items = [_item("A", day="01"), _item("B", day="02")]
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run(items, lambda *a: True, tmpdir, item_delay=0.25)
        self.assertEqual(2, mock_sleep.call_count)
        mock_sleep.assert_called_with(0.25)

    def test_empty_item_list_returns_zeros(self, _sleep):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual((0, 0, 0), self._run([], lambda *a: True, tmpdir))

    def test_respects_yearly_and_monthly_flags(self, _sleep):
        handler = MagicMock(return_value=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            self._run([_item()], handler, tmpdir, yearly=False, monthly=False)
            dest = handler.call_args[0][2]
        self.assertEqual(Path(tmpdir) / "Show A" / "17-Ep One.mp3", dest)


# ---------------------------------------------------------------------------
# print_dry_run / print_summary
# ---------------------------------------------------------------------------

class TestPrintDryRun(TestCase):
    def _capture(self, items, **kwargs):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            print_dry_run(items, Path("/downloads"), "mp3", True, True, **kwargs)
            return out.getvalue()

    def test_lists_full_destination_path(self):
        self.assertIn("/downloads/Show A/2026/March/17-Ep One.mp3", self._capture([_item()]))

    def test_lists_every_item(self):
        output = self._capture([_item("A", day="01"), _item("B", day="02")])
        self.assertIn("01-A.mp3", output)
        self.assertIn("02-B.mp3", output)

    def test_uses_item_noun_in_header(self):
        self.assertIn("issues that would be downloaded", self._capture([], item_noun="issue"))

    def test_empty_list_still_prints_header(self):
        self.assertIn("DRY RUN", self._capture([]))


class TestPrintSummary(TestCase):
    def _capture(self, success, skipped, failed):
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            print_summary(success, skipped, failed, Path("/downloads"))
            return out.getvalue()

    def test_reports_all_three_counts(self):
        output = self._capture(3, 2, 1)
        self.assertIn("Downloaded: 3", output)
        self.assertIn("Skipped: 2", output)
        self.assertIn("Failed: 1", output)

    def test_reports_output_root(self):
        self.assertIn("/downloads", self._capture(0, 0, 0))


if __name__ == "__main__":
    main()
