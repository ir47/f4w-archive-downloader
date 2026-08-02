"""Unit tests for runner.py"""
import io
import shutil
import tempfile

from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch
from unittest import TestCase, main

from podcastDownloader.util import SHOW_SLUGS
from podcastDownloader.runner import (
    _build_parser,
    _print_show_list,
    _run_watch,
    main as main_entry,
)
from f4wCommon.pipeline import DEFAULT_POLL_INTERVAL


# ---------------------------------------------------------------------------
# _build_parser
# ---------------------------------------------------------------------------

class TestBuildParser(TestCase):
    def setUp(self):
        self.parser = _build_parser()

    def test_show_argument_accepted(self):
        args = self.parser.parse_args(["--show", "wrestling-observer-radio"])
        self.assertEqual("wrestling-observer-radio", args.show)

    def test_show_short_flag(self):
        args = self.parser.parse_args(["-s", "wor"])
        self.assertEqual("wor", args.show)

    def test_all_argument_accepted(self):
        args = self.parser.parse_args(["--all"])
        self.assertTrue(args.all)

    def test_all_short_flag(self):
        args = self.parser.parse_args(["-A"])
        self.assertTrue(args.all)

    def test_list_shows_argument_accepted(self):
        args = self.parser.parse_args(["--list-shows"])
        self.assertTrue(args.list_shows)

    def test_show_and_all_are_mutually_exclusive(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args(["--show", "wor", "--all"])

    def test_requires_one_target_argument(self):
        with self.assertRaises(SystemExit):
            self.parser.parse_args([])

    def test_output_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--output", "/tmp/pods"])
        self.assertEqual("/tmp/pods", args.output)

    def test_output_short_flag(self):
        args = self.parser.parse_args(["-s", "wor", "-o", "/tmp/pods"])
        self.assertEqual("/tmp/pods", args.output)

    def test_output_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.output)

    def test_start_date_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--start", "January 1, 2025"])
        self.assertEqual("January 1, 2025", args.start)

    def test_end_date_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--end", "March 17, 2026"])
        self.assertEqual("March 17, 2026", args.end)

    def test_start_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.start)

    def test_end_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.end)

    def test_max_pages_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--max-pages", "5"])
        self.assertEqual(5, args.max_pages)

    def test_max_pages_default_is_none(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertIsNone(args.max_pages)

    def test_no_yearly_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--no-yearly"])
        self.assertTrue(args.no_yearly)

    def test_no_yearly_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.no_yearly)

    def test_no_monthly_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--no-monthly"])
        self.assertTrue(args.no_monthly)

    def test_no_monthly_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.no_monthly)

    def test_page_delay_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--page-delay", "2.5"])
        self.assertAlmostEqual(2.5, args.page_delay)

    def test_page_delay_default(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertAlmostEqual(1.0, args.page_delay)

    def test_item_delay_argument(self):
        args = self.parser.parse_args(["--show", "wor", "--item-delay", "1.0"])
        self.assertAlmostEqual(1.0, args.item_delay)

    def test_item_delay_default(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertAlmostEqual(0.5, args.item_delay)

    def test_legacy_episode_delay_alias_still_accepted(self):
        args = self.parser.parse_args(["--show", "wor", "--episode-delay", "1.0"])
        self.assertAlmostEqual(1.0, args.item_delay)

    def test_legacy_alias_does_not_clobber_default(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertAlmostEqual(0.5, args.item_delay)

    def test_overwrite_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--overwrite"])
        self.assertTrue(args.overwrite)

    def test_overwrite_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.overwrite)

    def test_dry_run_flag(self):
        args = self.parser.parse_args(["--show", "wor", "--dry-run"])
        self.assertTrue(args.dry_run)

    def test_dry_run_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.dry_run)

    def test_watch_flag(self):
        args = self.parser.parse_args(["--all", "--watch"])
        self.assertTrue(args.watch)

    def test_watch_short_flag(self):
        args = self.parser.parse_args(["--all", "-w"])
        self.assertTrue(args.watch)

    def test_watch_default_is_false(self):
        args = self.parser.parse_args(["--show", "wor"])
        self.assertFalse(args.watch)

    def test_watch_accepts_a_single_show(self):
        args = self.parser.parse_args(["--show", "after-dark", "--watch"])
        self.assertEqual("after-dark", args.show)

    def test_once_flag(self):
        args = self.parser.parse_args(["--all", "--watch", "--once"])
        self.assertTrue(args.once)

    def test_once_default_is_false(self):
        args = self.parser.parse_args(["--all", "--watch"])
        self.assertFalse(args.once)

    def test_poll_interval_argument(self):
        args = self.parser.parse_args(["--all", "--watch", "--poll-interval", "300"])
        self.assertAlmostEqual(300.0, args.poll_interval)

    def test_poll_interval_default(self):
        args = self.parser.parse_args(["--all", "--watch"])
        self.assertAlmostEqual(DEFAULT_POLL_INTERVAL, args.poll_interval)


# ---------------------------------------------------------------------------
# main dispatch
# ---------------------------------------------------------------------------

@patch("podcastDownloader.runner._run_watch")
@patch("podcastDownloader.runner._run_downloads")
class TestMainDispatch(TestCase):
    def _main(self, argv):
        with patch("sys.argv", ["f4w-download"] + argv), patch("sys.stdout", new_callable=io.StringIO):
            main_entry()

    def test_watch_runs_the_watcher(self, downloads, watch):
        self._main(["--all", "--watch"])
        watch.assert_called_once()
        downloads.assert_not_called()

    def test_no_watch_runs_the_archive_download(self, downloads, watch):
        self._main(["--all"])
        downloads.assert_called_once()
        watch.assert_not_called()

    def test_list_shows_exits_before_either(self, downloads, watch):
        with self.assertRaises(SystemExit):
            self._main(["--list-shows"])
        downloads.assert_not_called()
        watch.assert_not_called()


# ---------------------------------------------------------------------------
# _run_watch
# ---------------------------------------------------------------------------

def _feed_item(**overrides):
    """A feed item in the shape f4wCommon.feed.parse_feed returns."""
    item = {
        "title": "WOR: Test episode",
        "link": "https://www.f4wonline.com/podcasts/wrestling-observer-radio/wor-test/",
        "published": datetime(2026, 7, 27, 8, 11),
        "creator": "Bryan Alvarez",
        "summary": "",
        "content": "<p>A long enough paragraph of show notes to clear the length filter.</p>",
        "categories": ["Wrestling Observer Radio"],
        "enclosure_url": "https://media001.f4wonline.com/dmdocuments/072626wo.mp3",
        "enclosure_type": "audio/mpeg",
        "image_url": "https://www.f4wonline.com/cover.jpg",
    }
    item.update(overrides)
    return item


@patch("podcastDownloader.runner.create_session", MagicMock())
@patch("podcastDownloader.runner.login_or_exit", MagicMock())
class TestRunWatch(TestCase):
    def setUp(self):
        # The patches have to outlive _run_watch: the check and download
        # callables it hands to the watch loop are driven by the tests
        # afterwards, and they still reach for the network when they run.
        self.tmpdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmpdir, ignore_errors=True)

        self.stdout = self._start(patch("sys.stdout", new_callable=io.StringIO))
        self.download_loop = self._start(
            patch("podcastDownloader.runner.run_download_loop", return_value=(1, 0, 0))
        )
        self.login = self._start(patch("podcastDownloader.runner.login", return_value=True))
        self.poller = MagicMock(url="https://www.f4wonline.com/category/podcasts/feed/")
        self.poller.poll.return_value = []
        self.create_poller = self._start(
            patch("podcastDownloader.runner.create_poller", return_value=self.poller)
        )
        self._start(
            patch("podcastDownloader.runner.run_watch_loop", side_effect=self._capture_callables)
        )
        self.check = None
        self.download = None
        self.watch_args = {}

    def _start(self, patcher):
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        return mock

    def _capture_callables(self, check, download, poll_interval, once):
        self.check, self.download = check, download
        self.watch_args = {"poll_interval": poll_interval, "once": once}
        return (0, 0, 0)

    def _run(self, argv, feed_items=None):
        if feed_items is not None:
            self.poller.poll.return_value = feed_items
        _run_watch(_build_parser().parse_args(argv + ["--output", self.tmpdir]))

    def _existing_download(self, name="27-WOR_ Test episode.mp3"):
        folder = Path(self.tmpdir) / "Wrestling Observer Radio" / "2026" / "July"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / name).touch()

    # -- wiring ------------------------------------------------------------

    def test_passes_the_poll_interval_through(self):
        self._run(["--all", "--watch", "--poll-interval", "60"])
        self.assertAlmostEqual(60.0, self.watch_args["poll_interval"])

    def test_passes_once_through(self):
        self._run(["--all", "--watch", "--once"])
        self.assertTrue(self.watch_args["once"])

    def test_watches_the_combined_feed_for_all(self):
        self._run(["--all", "--watch"])
        self.assertIsNone(self.create_poller.call_args.args[1])

    def test_watches_one_shows_feed(self):
        self._run(["--show", "after-dark", "--watch"])
        self.assertEqual("after-dark", self.create_poller.call_args.args[1])

    # -- the check callable -------------------------------------------------

    def test_check_converts_feed_items_into_episodes(self):
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        episodes = self.check()
        self.assertEqual(1, len(episodes))
        self.assertEqual("Wrestling Observer Radio", episodes[0]["show"])

    def test_check_returns_none_when_the_feed_fetch_fails(self):
        self._run(["--all", "--watch"], feed_items=None)
        self.poller.poll.return_value = None
        self.assertIsNone(self.check())

    def test_check_returns_empty_when_nothing_changed(self):
        self._run(["--all", "--watch"], feed_items=[])
        self.assertEqual([], self.check())

    def test_check_applies_the_date_filter(self):
        self._run(["--all", "--watch", "--start", "August 1, 2026"], feed_items=[_feed_item()])
        self.assertEqual([], self.check())

    def test_check_drops_episodes_already_on_disk(self):
        self._existing_download()
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        self.assertEqual([], self.check())

    def test_check_keeps_an_episode_whose_file_is_missing(self):
        self._existing_download("27-A different episode.mp3")
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        self.assertEqual(1, len(self.check()))

    # -- the download callable ---------------------------------------------

    def test_download_serves_details_from_the_feed_without_refetching(self):
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        episodes = self.check()
        self.download(episodes)

        scrape_details = self.download_loop.call_args.kwargs["scrape_details"]
        details = scrape_details(episodes[0]["url"], MagicMock())
        self.assertEqual(
            "https://media001.f4wonline.com/dmdocuments/072626wo.mp3", details["mp3_url"]
        )
        self.assertEqual("Bryan Alvarez", details["host"])

    def test_details_lookup_for_an_unknown_url_is_empty(self):
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        self.download(self.check())
        scrape_details = self.download_loop.call_args.kwargs["scrape_details"]
        self.assertEqual({}, scrape_details("https://example.com/other/", MagicMock()))

    def test_a_fully_failed_cycle_triggers_a_re_login(self):
        self.download_loop.return_value = (0, 0, 1)
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        self.download(self.check())
        self.check()
        self.login.assert_called_once()

    def test_a_partly_failed_cycle_does_not_re_login(self):
        self.download_loop.return_value = (1, 0, 1)
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        self.download(self.check())
        self.check()
        self.login.assert_not_called()

    def test_re_login_is_not_repeated_on_the_following_check(self):
        self.download_loop.return_value = (0, 0, 1)
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        self.download(self.check())
        self.check()
        self.check()
        self.login.assert_called_once()

    def test_failed_re_login_reports_the_check_as_failed(self):
        self.download_loop.return_value = (0, 0, 1)
        self.login.return_value = False
        self._run(["--all", "--watch"], feed_items=[_feed_item()])
        self.download(self.check())
        self.assertIsNone(self.check())

    # -- flag guards --------------------------------------------------------

    def test_overwrite_is_ignored_by_a_looping_watch(self):
        self._run(["--all", "--watch", "--overwrite"], feed_items=[_feed_item()])
        self.download(self.check())
        self.assertFalse(self.download_loop.call_args.kwargs["overwrite"])

    def test_overwrite_is_honoured_by_a_single_pass(self):
        self._run(["--all", "--watch", "--once", "--overwrite"], feed_items=[_feed_item()])
        self.download(self.check())
        self.assertTrue(self.download_loop.call_args.kwargs["overwrite"])

    def test_overwrite_single_pass_keeps_episodes_already_on_disk(self):
        self._existing_download()
        self._run(["--all", "--watch", "--once", "--overwrite"], feed_items=[_feed_item()])
        self.assertEqual(1, len(self.check()))

    def test_dry_run_downloads_nothing(self):
        with patch("podcastDownloader.runner.run_watch_loop") as watch_loop:
            self._run(["--all", "--watch", "--dry-run"], feed_items=[_feed_item()])
            watch_loop.assert_not_called()
        self.download_loop.assert_not_called()
        self.assertIn("27-WOR_ Test episode.mp3", self.stdout.getvalue())


# ---------------------------------------------------------------------------
# _print_show_list
# ---------------------------------------------------------------------------

class TestPrintShowList(TestCase):
    def test_all_slugs_present_in_output(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _print_show_list()
            output = mock_out.getvalue()
        for slug in SHOW_SLUGS:
            self.assertIn(slug, output, f"Slug '{slug}' missing from show list output")

    def test_all_display_names_present_in_output(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _print_show_list()
            output = mock_out.getvalue()
        for name in SHOW_SLUGS.values():
            self.assertIn(name, output, f"Show name '{name}' missing from show list output")

    def test_output_contains_header(self):
        with patch("sys.stdout", new_callable=io.StringIO) as mock_out:
            _print_show_list()
            output = mock_out.getvalue()
        self.assertIn("Available shows", output)


if __name__ == "__main__":
    main()
