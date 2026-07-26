"""
auth.py — F4WOnline shared helpers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Site-agnostic login/authentication flow shared by every F4WOnline downloader.
"""

from __future__ import annotations

import getpass
import os
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from f4wCommon.http import REQUEST_HEADERS, HTTP_TIMEOUT_PAGE


DEFAULT_LOGIN_URL = "https://account.f4wonline.com/login"


def find_input_name(form, candidates: list, input_types: list | None = None) -> str | None:
    """
    Search a BeautifulSoup form for an <input> whose name attribute contains
    one of the candidate strings (case-insensitive). Returns the first match,
    or None if no match is found.

    Pass *input_types* (e.g. ["text", "email"]) to only consider inputs of
    those types — otherwise a hidden field whose name happens to match a
    candidate (e.g. a "login_token" CSRF field matching the "login"
    candidate) could be mistaken for the real username/password input. An
    input with no explicit type= attribute is treated as "text" per the
    HTML spec.
    """
    for inp in form.find_all("input"):
        if input_types is not None:
            inp_type = inp.get("type", "text").lower()
            if inp_type not in input_types:
                continue
        name = inp.get("name", "").lower()
        if any(candidate in name for candidate in candidates):
            return inp["name"]
    return None


def prompt_credentials() -> tuple:
    """Prompt interactively for username/email and password. Password input is hidden."""
    print("\n--- F4WOnline Login ---")
    username = input("Username or email: ").strip()
    password = getpass.getpass("Password: ")
    return username, password


def login(
    session: requests.Session,
    login_url: str = DEFAULT_LOGIN_URL,
    credentials: tuple[str, str] | None = None,
    prompt_fn=prompt_credentials,
) -> bool:
    """
    Authenticate with F4WOnline and mutate *session* in-place.

    Pass ``credentials=(username, password)`` for non-interactive use (e.g. a
    web backend).  Omit it to fall back, in order, to the F4W_USERNAME/
    F4W_PASSWORD environment variables (handy for local testing via a
    gitignored .env file) and then to *prompt_fn* (defaults to the
    interactive stdin/getpass prompt); callers can inject their own prompt
    function, e.g. to keep an existing patch point intact.

    Returns True on success, False on failure.
    """
    print("Connecting to F4WOnline…")
    try:
        resp = session.get(login_url, timeout=HTTP_TIMEOUT_PAGE)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[error] Could not reach the login page: {exc}")
        return False

    soup = BeautifulSoup(resp.text, "html.parser")
    form = soup.find("form")
    if not form:
        print("[error] Could not find a login form on the page. The site may have changed.")
        return False

    # Use form's action URL if present (resolved against login_url, so a
    # relative action like "/login/check" works, not just absolute ones),
    # otherwise POST back to the same URL.
    action = form.get("action", "").strip()
    post_url = urljoin(login_url, action) if action else login_url

    # Seed the payload with all hidden fields (CSRF tokens, redirect targets, etc.)
    payload = {}
    for inp in form.find_all("input"):
        if inp.get("type", "").lower() == "hidden":
            name = inp.get("name", "").strip()
            if name:
                payload[name] = inp.get("value", "")

    # Detect field names dynamically to avoid hardcoding names that could
    # change. Restrict to visible text/email/password inputs so a hidden
    # CSRF field (e.g. "login_token") can't be mistaken for the real one.
    username_field = find_input_name(form, ["email", "username", "user", "login"], input_types=["text", "email"])
    password_field = find_input_name(form, ["password", "pass", "pwd"], input_types=["password"])

    if not username_field or not password_field:
        print(
            "[warn] Could not detect form field names automatically. "
            "Falling back to 'username' and 'password'."
        )
        username_field = username_field or "username"
        password_field = password_field or "password"

    if credentials is None:
        env_username = os.environ.get("F4W_USERNAME")
        env_password = os.environ.get("F4W_PASSWORD")
        if env_username and env_password:
            credentials = (env_username, env_password)

    username, password = credentials if credentials is not None else prompt_fn()
    payload[username_field] = username
    payload[password_field] = password

    try:
        login_resp = session.post(
            post_url,
            data=payload,
            headers={**REQUEST_HEADERS, "Referer": login_url},
            allow_redirects=True,
            timeout=HTTP_TIMEOUT_PAGE,
        )
        login_resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"[error] Login request failed: {exc}")
        return False

    # A successful login redirects away from /login entirely.
    final_url = login_resp.url
    still_on_login = "login" in final_url.lower() and "account.f4wonline.com" in final_url

    response_soup = BeautifulSoup(login_resp.text, "html.parser")
    error_tag = response_soup.find(class_=re.compile(r"error|alert|notice|message", re.I))
    error_text = error_tag.get_text(strip=True) if error_tag else ""
    failure_keywords = ("invalid", "incorrect", "wrong password", "failed", "not found")
    keyword_match = any(kw in login_resp.text.lower() for kw in failure_keywords)

    if still_on_login or (error_text and keyword_match):
        print("[error] Login failed — please check your username and password.")
        if error_text:
            print(f"        Site message: {error_text}")
        print(f"        Reset your password at: {login_url}?sendpass")
        return False

    f4w_cookies = [c for c in session.cookies if "f4wonline" in c.domain]
    if not f4w_cookies:
        print(
            "[warn] Login appeared to succeed but no session cookie was set.\n"
            "       Downloads may fail if the site requires authentication."
        )

    print("[ok]   Logged in successfully.\n")
    return True
