"""Unit tests for f4wCommon/http.py"""
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

import requests

from f4wCommon.http import (
    HTTP_RETRY_COUNT,
    create_session,
    fetch_page,
    stream_download,
)


# ---------------------------------------------------------------------------
# create_session
# ---------------------------------------------------------------------------

class TestCreateSession(TestCase):
    def test_returns_requests_session(self):
        self.assertIsInstance(create_session(), requests.Session)

    def test_session_has_user_agent(self):
        session = create_session()
        self.assertIn("Mozilla", session.headers.get("User-Agent", ""))

    def test_session_has_accept_header(self):
        self.assertIn("Accept", create_session().headers)

    def test_session_has_referer_header(self):
        self.assertIn("Referer", create_session().headers)


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------

class TestFetchPage(TestCase):
    @patch("f4wCommon.http.time.sleep")
    def test_returns_response_on_success(self, _sleep):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.get.return_value = mock_resp
        self.assertIs(mock_resp, fetch_page("https://example.com", mock_session))

    @patch("f4wCommon.http.time.sleep")
    def test_returns_none_after_all_retries_fail(self, _sleep):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("timeout")
        self.assertIsNone(fetch_page("https://example.com", mock_session))

    @patch("f4wCommon.http.time.sleep")
    def test_retries_then_succeeds(self, _sleep):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.get.side_effect = [requests.RequestException("err"), mock_resp]
        self.assertIs(mock_resp, fetch_page("https://example.com", mock_session))

    @patch("f4wCommon.http.time.sleep")
    def test_calls_raise_for_status(self, _sleep):
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_session.get.return_value = mock_resp
        fetch_page("https://example.com", mock_session)
        mock_resp.raise_for_status.assert_called_once()

    @patch("f4wCommon.http.time.sleep")
    def test_retries_exactly_http_retry_count_times(self, _sleep):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("err")
        fetch_page("https://example.com", mock_session)
        self.assertEqual(HTTP_RETRY_COUNT, mock_session.get.call_count)

    @patch("f4wCommon.http.time.sleep")
    def test_respects_custom_retries_argument(self, _sleep):
        mock_session = MagicMock()
        mock_session.get.side_effect = requests.RequestException("err")
        fetch_page("https://example.com", mock_session, retries=5)
        self.assertEqual(5, mock_session.get.call_count)


# ---------------------------------------------------------------------------
# stream_download
# ---------------------------------------------------------------------------

class TestStreamDownload(TestCase):
    def _streaming_session(self, content=b"FAKE"):
        mock_resp = MagicMock()
        mock_resp.iter_content.return_value = [content]
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        return mock_session

    def test_skips_existing_file_and_returns_true(self):
        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
            dest = Path(f.name)
            f.write(b"existing")
        try:
            mock_session = MagicMock()
            result = stream_download("https://example.com/f.bin", dest, mock_session, skip_existing=True)
            self.assertTrue(result)
            mock_session.get.assert_not_called()
        finally:
            dest.unlink(missing_ok=True)

    def test_returns_true_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "f.bin"
            result = stream_download("https://example.com/f.bin", dest, self._streaming_session())
            self.assertTrue(result)

    def test_writes_correct_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "f.bin"
            stream_download("https://example.com/f.bin", dest, self._streaming_session(b"CONTENT"))
            self.assertEqual(b"CONTENT", dest.read_bytes())

    def test_returns_false_on_request_exception(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "f.bin"
            mock_session = MagicMock()
            mock_session.get.side_effect = requests.RequestException("error")
            result = stream_download("https://example.com/f.bin", dest, mock_session)
            self.assertFalse(result)

    def test_creates_parent_directory_if_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "subdir" / "f.bin"
            stream_download("https://example.com/f.bin", dest, self._streaming_session())
            self.assertTrue(dest.exists())


if __name__ == "__main__":
    main()
