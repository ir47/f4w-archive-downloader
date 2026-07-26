"""Unit tests for f4wCommon/auth.py"""
import requests

from bs4 import BeautifulSoup
from unittest import TestCase, main
from unittest.mock import MagicMock, patch

from f4wCommon.auth import find_input_name, login


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_form(input_names):
    """Build a BeautifulSoup <form> with the given input names."""
    html = "<form>" + "".join(
        f'<input name="{n}" type="text"/>' for n in input_names
    ) + "</form>"
    return BeautifulSoup(html, "html.parser").find("form")


def _make_typed_form(inputs):
    """Build a BeautifulSoup <form> from a list of (name, type) tuples."""
    html = "<form>" + "".join(
        f'<input name="{name}" type="{itype}"/>' for name, itype in inputs
    ) + "</form>"
    return BeautifulSoup(html, "html.parser").find("form")


# ---------------------------------------------------------------------------
# find_input_name
# ---------------------------------------------------------------------------

class TestFindInputName(TestCase):
    def test_finds_by_email_candidate(self):
        form = _make_form(["user_email", "user_password"])
        self.assertEqual("user_email", find_input_name(form, ["email"]))

    def test_finds_by_password_candidate(self):
        form = _make_form(["user_email", "user_password"])
        self.assertEqual("user_password", find_input_name(form, ["pass"]))

    def test_returns_none_when_no_match(self):
        form = _make_form(["foo", "bar"])
        self.assertIsNone(find_input_name(form, ["email"]))

    def test_case_insensitive(self):
        form = _make_form(["USER_EMAIL"])
        self.assertEqual("USER_EMAIL", find_input_name(form, ["email"]))

    def test_returns_first_match(self):
        form = _make_form(["username", "user_login"])
        self.assertEqual("username", find_input_name(form, ["user"]))

    def test_empty_form_returns_none(self):
        form = BeautifulSoup("<form></form>", "html.parser").find("form")
        self.assertIsNone(find_input_name(form, ["email"]))

    def test_input_types_excludes_hidden_field_matching_candidate(self):
        # A hidden CSRF field named "login_token" would match the "login"
        # candidate by substring alone — input_types must exclude it.
        form = _make_typed_form([("login_token", "hidden"), ("user_email", "text")])
        result = find_input_name(form, ["email", "login"], input_types=["text", "email"])
        self.assertEqual("user_email", result)

    def test_input_types_matches_email_type(self):
        form = _make_typed_form([("username", "email")])
        result = find_input_name(form, ["user"], input_types=["text", "email"])
        self.assertEqual("username", result)

    def test_input_types_treats_missing_type_as_text(self):
        html = '<form><input name="user_email"/></form>'
        form = BeautifulSoup(html, "html.parser").find("form")
        result = find_input_name(form, ["email"], input_types=["text", "email"])
        self.assertEqual("user_email", result)

    def test_input_types_none_does_not_filter(self):
        form = _make_typed_form([("login_token", "hidden")])
        result = find_input_name(form, ["login"])
        self.assertEqual("login_token", result)


# ---------------------------------------------------------------------------
# login
# ---------------------------------------------------------------------------

@patch.dict("os.environ", {}, clear=True)
class TestLogin(TestCase):
    _LOGIN_FORM_HTML = """
    <html><body>
    <form action="https://account.f4wonline.com/login" method="post">
        <input name="user_email" type="text"/>
        <input name="user_password" type="password"/>
        <input name="_token" type="hidden" value="abc123"/>
    </form>
    </body></html>
    """

    def _mock_session(self, get_html, post_url, post_html, cookies=None):
        session = MagicMock()
        session.get.return_value = MagicMock(text=get_html)
        session.post.return_value = MagicMock(url=post_url, text=post_html)
        session.cookies = cookies or []
        return session

    def test_returns_false_when_login_page_unreachable(self):
        session = MagicMock()
        session.get.side_effect = requests.RequestException("refused")
        self.assertFalse(login(session, prompt_fn=lambda: ("u", "p")))

    def test_returns_false_when_no_form_on_page(self):
        session = MagicMock()
        session.get.return_value = MagicMock(text="<html><body><p>No form</p></body></html>")
        self.assertFalse(login(session, prompt_fn=lambda: ("u", "p")))

    def test_returns_false_when_still_on_login_page_after_post(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://account.f4wonline.com/login",
            post_html="",
        )
        self.assertFalse(login(session, prompt_fn=lambda: ("u", "p")))

    def test_returns_true_on_successful_redirect(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome!</body></html>",
        )
        self.assertTrue(login(session, prompt_fn=lambda: ("u", "p")))

    def test_returns_false_when_error_keyword_in_response(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html='<html><body><p class="error">Invalid username or password</p></body></html>',
        )
        self.assertFalse(login(session, prompt_fn=lambda: ("u", "wrong")))

    def test_posts_hidden_fields_as_payload(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome</body></html>",
        )
        login(session, prompt_fn=lambda: ("u", "p"))
        call_kwargs = session.post.call_args
        payload = call_kwargs[1]["data"] if "data" in call_kwargs[1] else call_kwargs[0][1]
        self.assertIn("_token", payload)
        self.assertEqual("abc123", payload["_token"])

    def test_uses_explicit_credentials_without_calling_prompt_fn(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome</body></html>",
        )
        prompt_fn = MagicMock()
        self.assertTrue(login(session, credentials=("u", "p"), prompt_fn=prompt_fn))
        prompt_fn.assert_not_called()

    def test_resolves_relative_form_action(self):
        html = """
        <html><body>
        <form action="/login/check" method="post">
            <input name="user_email" type="text"/>
            <input name="user_password" type="password"/>
        </form>
        </body></html>
        """
        session = self._mock_session(
            get_html=html,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome</body></html>",
        )
        login(session, prompt_fn=lambda: ("u", "p"))
        post_url = session.post.call_args[0][0]
        self.assertEqual("https://account.f4wonline.com/login/check", post_url)

    def test_uses_custom_login_url(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://members.f4wonline.com/dashboard",
            post_html="<html><body>Welcome</body></html>",
        )
        login(session, login_url="https://members.f4wonline.com/login", prompt_fn=lambda: ("u", "p"))
        session.get.assert_called_once_with("https://members.f4wonline.com/login", timeout=15)

    @patch.dict("os.environ", {"F4W_USERNAME": "env@example.com", "F4W_PASSWORD": "envpass"})
    def test_uses_env_credentials_without_calling_prompt_fn(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome</body></html>",
        )
        prompt_fn = MagicMock()
        self.assertTrue(login(session, prompt_fn=prompt_fn))
        prompt_fn.assert_not_called()
        payload = session.post.call_args[1]["data"]
        self.assertEqual("env@example.com", payload["user_email"])
        self.assertEqual("envpass", payload["user_password"])

    @patch.dict("os.environ", {"F4W_USERNAME": "env@example.com"})
    def test_ignores_partial_env_credentials(self):
        session = self._mock_session(
            get_html=self._LOGIN_FORM_HTML,
            post_url="https://www.f4wonline.com/dashboard",
            post_html="<html><body>Welcome</body></html>",
        )
        login(session, prompt_fn=lambda: ("u", "p"))
        payload = session.post.call_args[1]["data"]
        self.assertEqual("u", payload["user_email"])

    def test_explicit_credentials_take_priority_over_env(self):
        with patch.dict("os.environ", {"F4W_USERNAME": "env@example.com", "F4W_PASSWORD": "envpass"}):
            session = self._mock_session(
                get_html=self._LOGIN_FORM_HTML,
                post_url="https://www.f4wonline.com/dashboard",
                post_html="<html><body>Welcome</body></html>",
            )
            login(session, credentials=("explicit@example.com", "explicitpass"))
            payload = session.post.call_args[1]["data"]
            self.assertEqual("explicit@example.com", payload["user_email"])


if __name__ == "__main__":
    main()
