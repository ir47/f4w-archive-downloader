"""Unit tests for f4wCommon/fsutil.py"""
import tempfile

from pathlib import Path
from unittest.mock import patch
from unittest import TestCase, main

from f4wCommon.fsutil import (
    build_hierarchical_path,
    build_item_path,
    generate_download_directories,
    item_filename,
    sanitize_filename,
)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename(TestCase):
    def test_replaces_backslash(self):
        self.assertEqual("a_b", sanitize_filename("a\\b"))

    def test_replaces_forward_slash(self):
        self.assertEqual("a_b", sanitize_filename("a/b"))

    def test_replaces_colon(self):
        self.assertEqual("a_b", sanitize_filename("a:b"))

    def test_replaces_asterisk(self):
        self.assertEqual("a_b", sanitize_filename("a*b"))

    def test_replaces_question_mark(self):
        self.assertEqual("a_b", sanitize_filename("a?b"))

    def test_replaces_angle_brackets(self):
        self.assertEqual("a_b_c", sanitize_filename("a<b>c"))

    def test_replaces_pipe(self):
        self.assertEqual("a_b", sanitize_filename("a|b"))

    def test_replaces_double_quote(self):
        self.assertEqual("a_b", sanitize_filename('a"b'))

    def test_normal_name_unchanged(self):
        self.assertEqual("Wrestling Observer Radio", sanitize_filename("Wrestling Observer Radio"))

    def test_strips_surrounding_whitespace(self):
        self.assertEqual("name", sanitize_filename("  name  "))

    def test_multiple_bad_chars(self):
        self.assertEqual("Show_ Episode_1", sanitize_filename("Show: Episode/1"))


# ---------------------------------------------------------------------------
# generate_download_directories
# ---------------------------------------------------------------------------

class TestGenerateDownloadDirectories(TestCase):
    def test_creates_nested_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            target = Path(tmpdir) / "a" / "b" / "c"
            generate_download_directories(target)
            self.assertTrue(target.exists())

    def test_returns_true_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = generate_download_directories(Path(tmpdir) / "new")
            self.assertTrue(result)

    def test_returns_true_when_directory_already_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.assertTrue(generate_download_directories(Path(tmpdir)))

    @patch("pathlib.Path.mkdir", side_effect=OSError("Permission denied"))
    def test_returns_false_on_oserror(self, _mock_mkdir):
        self.assertFalse(generate_download_directories(Path("/fake/path")))


# ---------------------------------------------------------------------------
# build_hierarchical_path
# ---------------------------------------------------------------------------

class TestBuildHierarchicalPath(TestCase):
    base = Path("/downloads")

    def test_base_only(self):
        path = build_hierarchical_path(self.base, "Show A", None, None, yearly=False, monthly=False)
        self.assertEqual(self.base / "Show A", path)

    def test_with_yearly(self):
        path = build_hierarchical_path(self.base, "Show A", "2026", "March", yearly=True, monthly=False)
        self.assertEqual(self.base / "Show A" / "2026", path)

    def test_with_monthly(self):
        path = build_hierarchical_path(self.base, "Show A", "2026", "March", yearly=False, monthly=True)
        self.assertEqual(self.base / "Show A" / "March", path)

    def test_with_yearly_and_monthly(self):
        path = build_hierarchical_path(self.base, "Show A", "2026", "March", yearly=True, monthly=True)
        self.assertEqual(self.base / "Show A" / "2026" / "March", path)

    def test_sanitizes_category_name_with_colon(self):
        path = build_hierarchical_path(self.base, "Show: A", None, None, yearly=False, monthly=False)
        self.assertEqual(self.base / "Show_ A", path)

    def test_unknown_year_still_included_when_yearly(self):
        path = build_hierarchical_path(self.base, "Show A", "Unknown", None, yearly=True, monthly=False)
        self.assertEqual(self.base / "Show A" / "Unknown", path)


# ---------------------------------------------------------------------------
# build_item_path
# ---------------------------------------------------------------------------

class TestBuildItemPath(TestCase):
    base = Path("/downloads")

    def _item(self, show="Wrestling Observer Radio", year="2026", month="March"):
        return {"show": show, "year": year, "month": month}

    def test_base_only(self):
        path = build_item_path(self.base, self._item(), yearly=False, monthly=False)
        self.assertEqual(self.base / "Wrestling Observer Radio", path)

    def test_with_yearly(self):
        path = build_item_path(self.base, self._item(), yearly=True, monthly=False)
        self.assertEqual(self.base / "Wrestling Observer Radio" / "2026", path)

    def test_with_monthly(self):
        path = build_item_path(self.base, self._item(), yearly=False, monthly=True)
        self.assertEqual(self.base / "Wrestling Observer Radio" / "March", path)

    def test_with_yearly_and_monthly(self):
        path = build_item_path(self.base, self._item(), yearly=True, monthly=True)
        self.assertEqual(self.base / "Wrestling Observer Radio" / "2026" / "March", path)

    def test_sanitizes_show_name_with_colon(self):
        path = build_item_path(self.base, self._item(show="Show: Special"), yearly=False, monthly=False)
        self.assertNotIn(":", str(path))

    def test_unknown_year_still_included_when_yearly(self):
        path = build_item_path(self.base, self._item(year="Unknown"), yearly=True, monthly=False)
        self.assertIn("Unknown", str(path))

    def test_missing_date_fields_omit_segments(self):
        path = build_item_path(self.base, {"show": "Show A"}, yearly=True, monthly=True)
        self.assertEqual(self.base / "Show A", path)

    def test_newsletter_category_shape(self):
        item = {"show": "Wrestling Observer Newsletter", "year": "2026", "month": "July"}
        path = build_item_path(self.base, item, yearly=True, monthly=True)
        self.assertEqual(self.base / "Wrestling Observer Newsletter" / "2026" / "July", path)


# ---------------------------------------------------------------------------
# item_filename
# ---------------------------------------------------------------------------

class TestItemFilename(TestCase):
    def test_builds_expected_filename(self):
        item = {"day": "13", "title": "Observer Newsletter: July 13"}
        self.assertEqual("13-Observer Newsletter_ July 13.pdf", item_filename(item, "pdf"))

    def test_defaults_day_to_00_when_missing(self):
        self.assertEqual("00-Issue.epub", item_filename({"title": "Issue"}, "epub"))

    def test_sanitizes_title(self):
        self.assertEqual("05-Show_Ep.mp3", item_filename({"day": "05", "title": "Show/Ep"}, "mp3"))

    def test_respects_extension(self):
        self.assertEqual("01-A.mp3", item_filename({"day": "01", "title": "A"}, "mp3"))


if __name__ == "__main__":
    main()
