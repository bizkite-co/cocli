"""Public-client Microsoft OAuth for IMAP/SMTP. No mutt-setup, no 1Password."""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

from cocli.core.config import get_cocli_app_data_dir
from cocli.models.mail import EmailSettings

logger = logging.getLogger(__name__)

DEFAULT_SCOPE = (
    "offline_access https://outlook.office.com/IMAP.AccessAsUser.All "
    "https://outlook.office.com/SMTP.Send"
)
DEFAULT_AUTHORIZE = "https://login.microsoftonline.com/organizations/oauth2/v2.0/authorize"
DEFAULT_REDIRECT = "http://localhost:8400"


def default_token_cache_path(imap_user: str) -> Path:
    safe = imap_user.strip().replace("/", "_")
    return get_cocli_app_data_dir() / "email-tokens" / f"{safe}.json"


def resolve_token_cache_path(settings: EmailSettings) -> Path:
    if settings.token_cache:
        return Path(settings.token_cache).expanduser()
    if not settings.imap_user:
        raise ValueError("campaign [email].imap_user is required when token_cache is unset")
    return default_token_cache_path(settings.imap_user)


class FileOAuthTokenStore:
    """0600 JSON cache; refreshes via the public-client token endpoint."""

    def __init__(
        self,
        cache_path: Path,
        client_id: str,
        token_endpoint: str,
    ) -> None:
        self.cache_path = cache_path
        self.client_id = client_id
        self.token_endpoint = token_endpoint

    def get_access_token(self) -> str:
        data = self._load()
        exp_raw = data.get("access_token_expiration")
        token = data.get("access_token") or ""
        if token and exp_raw:
            try:
                exp = datetime.fromisoformat(str(exp_raw))
                if datetime.now() < exp:
                    return token
            except ValueError:
                pass
        refresh = data.get("refresh_token")
        if not refresh:
            raise RuntimeError(
                f"OAuth cache {self.cache_path} has no usable access or refresh token"
            )
        refreshed = self._refresh(str(refresh))
        self._save(refreshed)
        return refreshed["access_token"]

    def save_tokens(self, data: dict[str, str]) -> None:
        self._save(data)

    def _load(self) -> dict[str, str]:
        if not self.cache_path.is_file():
            raise FileNotFoundError(f"OAuth token cache not found: {self.cache_path}")
        raw = json.loads(self.cache_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise RuntimeError(f"OAuth token cache is not an object: {self.cache_path}")
        return {str(k): str(v) if v is not None else "" for k, v in raw.items()}

    def _save(self, data: dict[str, str]) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(json.dumps(data), encoding="utf-8")
        self.cache_path.chmod(0o600)

    def _refresh(self, refresh_token: str) -> dict[str, str]:
        body = urllib.parse.urlencode(
            {
                "client_id": self.client_id,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode()
        req = urllib.request.Request(self.token_endpoint, body)
        with urllib.request.urlopen(req) as response:
            payload = json.loads(response.read())
        access = str(payload["access_token"])
        expires_in = int(payload.get("expires_in", 3600))
        new_refresh = str(payload.get("refresh_token", refresh_token))
        exp = (datetime.now() + timedelta(seconds=expires_in)).isoformat()
        return {
            "access_token": access,
            "refresh_token": new_refresh,
            "access_token_expiration": exp,
        }


def build_authorize_url(settings: EmailSettings) -> str:
    if not settings.client_id:
        raise ValueError("campaign [email].client_id is required to authorize")
    params = {
        "client_id": settings.client_id,
        "scope": DEFAULT_SCOPE,
        "response_type": "code",
        "redirect_uri": DEFAULT_REDIRECT,
        "prompt": "consent",
        "login_hint": settings.imap_user or "",
    }
    return DEFAULT_AUTHORIZE + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def authorize_public_client(settings: EmailSettings, *, open_browser: bool = True) -> Path:
    """Browser + localhost redirect; writes the token cache. Public client (no secret)."""
    if not settings.client_id:
        raise ValueError("campaign [email].client_id is required to authorize")
    cache_path = resolve_token_cache_path(settings)
    parsed = urllib.parse.urlparse(DEFAULT_REDIRECT)
    port = parsed.port
    if not port:
        raise ValueError("redirect URI must include a port")
    auth_url = build_authorize_url(settings)
    code = _wait_for_auth_code(
        auth_url, port, settings.imap_user or "", open_browser=open_browser
    )
    token_body = {
        "client_id": settings.client_id,
        "scope": DEFAULT_SCOPE,
        "redirect_uri": redirect,
        "grant_type": "authorization_code",
        "code": code,
    }
    req = urllib.request.Request(
        settings.token_endpoint,
        urllib.parse.urlencode(token_body).encode(),
    )
    try:
        with urllib.request.urlopen(req) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"Token endpoint HTTP {e.code}: {body}") from e
    expires_in = int(payload.get("expires_in", 3600))
    tokens = {
        "access_token": str(payload["access_token"]),
        "refresh_token": str(payload.get("refresh_token") or ""),
        "access_token_expiration": (
            datetime.now() + timedelta(seconds=expires_in)
        ).isoformat(),
    }
    store = FileOAuthTokenStore(cache_path, settings.client_id, settings.token_endpoint)
    store.save_tokens(tokens)
    logger.info("Wrote OAuth token cache %s", cache_path)
    return cache_path


def _wait_for_auth_code(
    auth_url: str, port: int, account: str, *, open_browser: bool = True
) -> str:
    class StoppableHTTPServer(HTTPServer):
        auth_code: Optional[str] = None

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path.startswith("/favicon.ico"):
                self.send_response(204)
                self.end_headers()
                return
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = query.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            if code:
                self.server.auth_code = code  # type: ignore[attr-defined]
                self.wfile.write(
                    b"<html><body><h1>Authorization successful.</h1><p>You can close this window.</p></body></html>"
                )
            else:
                self.wfile.write(b"<html><body><h1>Authorization failed.</h1></body></html>")
            threading.Timer(1, self.server.shutdown).start()

        def log_message(self, fmt: str, *args: object) -> None:
            logger.info(fmt, *args)

    httpd = StoppableHTTPServer(("localhost", port), Handler)
    logger.info("Starting OAuth callback server on http://localhost:%s for %s", port, account)
    logger.info("Authorize URL: %s", auth_url)
    if open_browser:
        webbrowser.open(auth_url)
    httpd.serve_forever()
    code = httpd.auth_code
    if not code:
        raise RuntimeError("No authorization code received")
    return code
