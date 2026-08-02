"""Unit tests for f4wCommon/pipeline.py"""
import io
import tempfile

from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from f4wCommon.pipeline import (
    filter_new_items,
    print_dry_run,
    print_summary,
    run_download_loop,
    run_watch_loop,
)


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


class TestFilterNewItems(TestCase):
    def _existing(self, tmpdir, item):
        path = Path(tmpdir) / item["show"] / item["year"] / item["month"]
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{item['day']}-{item['title']}.mp3").touch()

    def test_keeps_items_not_on_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            items = [_item(title="Ep One"), _item(title="Ep Two")]
            self.assertEqual(2, len(filter_new_items(items, Path(tmpdir), "mp3")))

    def test_drops_items_already_on_disk(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            downloaded, fresh = _item(title="Ep One"), _item(title="Ep Two")
            self._existing(tmpdir, downloaded)
            remaining = filter_new_items([downloaded, fresh], Path(tmpdir), "mp3")
        self.assertEqual(["Ep Two"], [item["title"] for item in remaining])

    def test_respects_the_folder_layout_flags(self):
        # Written flat, so the default year/month layout must not find it.
        with tempfile.TemporaryDirectory() as tmpdir:
            item = _item()
            flat = Path(tmpdir) / item["show"]
            flat.mkdir(parents=True)
            (flat / f"{item['day']}-{item['title']}.mp3").touch()
            self.assertEqual(1, len(filter_new_items([item], Path(tmpdir), "mp3")))
            self.assertEqual(
                0, len(filter_new_items([item], Path(tmpdir), "mp3", yearly=False, monthly=False))
            )

    def test_empty_input_yields_empty_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertEqual([], filter_new_items([], Path(tmpdir), "mp3"))


class TestRunWatchLoop(TestCase):
    def _run(self, check_fn, download_fn=None, **kwargs):
        kwargs.setdefault("once", True)
        kwargs.setdefault("sleep_fn", MagicMock())
        with patch("sys.stdout", new_callable=io.StringIO) as out:
            counts = run_watch_loop(
                check_fn, download_fn or MagicMock(return_value=(0, 0, 0)), **kwargs
            )
        return counts, out.getvalue()

    def test_once_checks_a_single_time(self):
        check = MagicMock(return_value=[])
        self._run(check)
        check.assert_called_once()

    def test_once_does_not_sleep(self):
        sleep = MagicMock()
        self._run(MagicMock(return_value=[]), sleep_fn=sleep)
        sleep.assert_not_called()

    def test_items_are_handed_to_the_downloader(self):
        items = [_item()]
        download = MagicMock(return_value=(1, 0, 0))
        self._run(MagicMock(return_value=items), download)
        download.assert_called_once_with(items)

    def test_returns_the_download_counts(self):
        counts, _out = self._run(MagicMock(return_value=[_item()]), MagicMock(return_value=(1, 2, 3)))
        self.assertEqual((1, 2, 3), counts)

    def test_nothing_new_skips_the_downloader(self):
        download = MagicMock()
        self._run(MagicMock(return_value=[]), download)
        download.assert_not_called()

    def test_failed_check_skips_the_downloader(self):
        download = MagicMock()
        _counts, output = self._run(MagicMock(return_value=None), download)
        download.assert_not_called()
        self.assertIn("Check failed", output)

    def test_failed_check_is_reported_differently_from_nothing_new(self):
        _counts, nothing_new = self._run(MagicMock(return_value=[]))
        self.assertIn("Nothing new", nothing_new)

    def test_loops_until_interrupted(self):
        check = MagicMock(side_effect=[[], [], KeyboardInterrupt()])
        self._run(check, once=False)
        self.assertEqual(3, check.call_count)

    def test_sleeps_between_checks(self):
        sleep = MagicMock()
        self._run(MagicMock(side_effect=[[], KeyboardInterrupt()]), once=False,
                  sleep_fn=sleep, poll_interval=42)
        sleep.assert_called_once_with(42)

    def test_totals_accumulate_across_checks(self):
        check = MagicMock(side_effect=[[_item()], [_item()], KeyboardInterrupt()])
        download = MagicMock(side_effect=[(1, 2, 3), (10, 20, 30)])
        counts, _out = self._run(check, download, once=False)
        self.assertEqual((11, 22, 33), counts)

    def test_interrupt_while_sleeping_still_returns_totals(self):
        check = MagicMock(return_value=[_item()])
        download = MagicMock(return_value=(1, 0, 0))
        counts, output = self._run(
            check, download, once=False, sleep_fn=MagicMock(side_effect=KeyboardInterrupt())
        )
        self.assertEqual((1, 0, 0), counts)
        self.assertIn("Interrupted", output)

    def test_a_failed_check_does_not_end_the_watch(self):
        check = MagicMock(side_effect=[None, [_item()], KeyboardInterrupt()])
        counts, _out = self._run(check, MagicMock(return_value=(1, 0, 0)), once=False)
        self.assertEqual((1, 0, 0), counts)


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
