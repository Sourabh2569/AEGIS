"""Complete Kite Connect's daily login flow and refresh the access token.

Kite Connect access tokens expire every day -- there is no long-lived
refresh token on the standard plan, so this has to be re-run each trading
morning before ingestion. It cannot be fully automated: Zerodha's login page
requires your password and 2FA, which only you can enter.

What this script does automate: catching the post-login redirect (so you
don't have to copy a request_token out of a broken-redirect URL bar by
hand), exchanging it for an access_token, verifying it actually works
against your real account, and writing it into your local .env.

Usage:
    PYTHONPATH=packages/auth python infrastructure/scripts/kite_login.py

Requires MARKET_DATA_PROVIDER_API_KEY and MARKET_DATA_PROVIDER_CLIENT_SECRET
already set in .env (from your Kite Connect developer app). The app's
Redirect URL must be exactly http://127.0.0.1:8765/kite/callback.
"""

from __future__ import annotations

import os
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CALLBACK_HOST = "127.0.0.1"
CALLBACK_PORT = 8765
CALLBACK_PATH = "/kite/callback"
ENV_PATH = Path(".env")


def load_env_value(key: str) -> str:
    if not ENV_PATH.exists():
        raise SystemExit(f"{ENV_PATH} not found. Run this from the AEGIS repo root.")
    for line in ENV_PATH.read_text().splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip()
    return os.getenv(key, "")


def write_env_value(key: str, value: str) -> None:
    lines = ENV_PATH.read_text().splitlines()
    pattern = re.compile(rf"^{re.escape(key)}=.*$")
    updated = False
    for i, line in enumerate(lines):
        if pattern.match(line):
            lines[i] = f"{key}={value}"
            updated = True
            break
    if not updated:
        lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


class _CallbackHandler(BaseHTTPRequestHandler):
    request_token: str | None = None

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return
        params = parse_qs(parsed.query)
        token = params.get("request_token", [None])[0]
        status = params.get("status", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if token and status == "success":
            _CallbackHandler.request_token = token
            self.wfile.write(b"<html><body>Login captured. You can close this tab.</body></html>")
        else:
            self.wfile.write(b"<html><body>Login failed or was cancelled.</body></html>")

    def log_message(self, format: str, *args: object) -> None:
        pass  # keep stdout clean for our own prints


def wait_for_request_token() -> str:
    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), _CallbackHandler)
    print(
        f"Waiting for the login redirect on http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH} ..."
    )
    while _CallbackHandler.request_token is None:
        server.handle_request()
    server.server_close()
    return _CallbackHandler.request_token


def main() -> None:
    from kiteconnect import KiteConnect

    api_key = load_env_value("MARKET_DATA_PROVIDER_API_KEY")
    api_secret = load_env_value("MARKET_DATA_PROVIDER_CLIENT_SECRET")
    if not api_key or not api_secret:
        raise SystemExit(
            "Set MARKET_DATA_PROVIDER_API_KEY and MARKET_DATA_PROVIDER_CLIENT_SECRET in "
            ".env first (from your Kite Connect developer app)."
        )

    client = KiteConnect(api_key=api_key)
    login_url = client.login_url()
    print(f"\nOpen this URL and log in with your Zerodha credentials:\n\n  {login_url}\n")
    webbrowser.open(login_url)

    request_token = wait_for_request_token()
    print("Got request_token, exchanging for an access_token...")

    session = client.generate_session(request_token, api_secret=api_secret)
    access_token = session["access_token"]

    client.set_access_token(access_token)
    profile = client.profile()
    print(f"Verified: logged in as {profile.get('user_name', profile.get('user_id'))}")

    write_env_value("MARKET_DATA_PROVIDER_ACCESS_TOKEN", access_token)
    print(
        f"\nWrote MARKET_DATA_PROVIDER_ACCESS_TOKEN to {ENV_PATH}. Restart the API to pick it up."
    )


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("\nCancelled.")
