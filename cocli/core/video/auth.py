"""OAuth authentication for YouTube using Device Code Flow.

Design notes:
- Uses Google's Device Authorization Flow (no redirect URI needed)
- PasswordManager is an abstract interface for plugin support
- OnePasswordManager is the default implementation
- OAuth tokens stored in system keyring (not 1Password)
"""

import time
import logging
from abc import ABC, abstractmethod
from typing import Optional, Any
import requests
from rich.console import Console

from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret, set_op_secret
from cocli.core.video.keyring_manager import KeyringManager

logger = logging.getLogger(__name__)
console = Console()

DEVICE_AUTH_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube"


class PasswordManager(ABC):
    """Abstract interface for password manager plugins."""

    @abstractmethod
    def get_secret(self, path: str) -> Optional[str]:
        """Retrieve a secret from the password manager."""
        pass

    @abstractmethod
    def set_secret(self, path: str, value: str) -> bool:
        """Store a secret in the password manager."""
        pass


class OnePasswordManager(PasswordManager):
    """1Password implementation of PasswordManager."""

    def get_secret(self, path: str) -> Optional[str]:
        return get_op_secret(path)

    def set_secret(self, path: str, value: str) -> bool:
        return set_op_secret(path, value)


class DeviceCodeAuth:
    """Handle Google OAuth Device Code Flow."""

    def __init__(self, password_manager: Optional[PasswordManager] = None):
        self.password_manager = password_manager or OnePasswordManager()

    def get_device_code(self, client_id: str) -> dict[str, Any]:
        """Initiate device code flow."""
        console.print(f"[dim]Using scope: {SCOPE}[/dim]")
        console.print(f"[dim]Using client_id: {client_id}[/dim]")
        response = requests.post(
            DEVICE_AUTH_URL,
            data={
                "client_id": client_id,
                "scope": SCOPE,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        logger.debug(f"Device code response status: {response.status_code}")
        logger.debug(f"Device code response body: {response.text}")
        if response.status_code != 200:
            raise RuntimeError(
                f"Device code request failed: {response.status_code} - {response.text}"
            )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]

    def poll_for_token(
        self, device_code: str, client_id: str, client_secret: str, interval: int = 5
    ) -> Optional[dict[str, Any]]:
        """Poll for token exchange."""
        console.print("[dim]Polling for token exchange...[/dim]")

        while True:
            try:
                console.print("[dim]Sending token exchange request...[/dim]")
                response = requests.post(
                    TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "device_code": device_code,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30,
                )
                console.print(f"[dim]Response status: {response.status_code}[/dim]")
                console.print(f"[dim]Response body: {response.text[:500]}[/dim]")

                result = response.json()
                console.print(f"[dim]Parsed result keys: {result.keys()}[/dim]")

                if "access_token" in result:
                    console.print("[green]Received access token![/green]")
                    return result  # type: ignore[no-any-return]
                elif result.get("error") == "authorization_pending":
                    console.print(
                        f"[dim]Authorization pending, sleeping {interval}s...[/dim]"
                    )
                    time.sleep(interval)
                elif result.get("error") == "expired_token":
                    console.print("[red]Device code expired. Please try again.[/red]")
                    return None
                elif result.get("error") == "slow_down":
                    console.print(
                        f"[yellow]Slow down, sleeping {interval + 5}s...[/yellow]"
                    )
                    time.sleep(interval + 5)
                elif result.get("error") == "authorization_in_progress":
                    console.print(
                        f"[dim]Authorization in progress, sleeping {interval}s...[/dim]"
                    )
                    time.sleep(interval)
                else:
                    console.print(f"[red]Token exchange error: {result}[/red]")
                    logger.error(f"Token exchange error: {result}")
                    return None

            except requests.exceptions.Timeout:
                console.print("[yellow]Request timed out, retrying...[/yellow]")
                time.sleep(interval)
            except Exception as e:
                console.print(f"[red]Exception during token poll: {e}[/red]")
                logger.error(f"Exception during token poll: {e}")
                time.sleep(interval)

    def get_credentials_from_config(self, campaign: str) -> tuple[str, str, str, str]:
        """Get OAuth credentials from campaign config."""
        config = load_campaign_config(campaign)
        google_api_config = config.get("google_api_client", {})

        def get_key(key: str) -> str:
            path = google_api_config.get(key)
            if not path:
                raise ValueError(
                    f"Secret path for '{key}' not found in campaign '{campaign}' config"
                )
            secret = self.password_manager.get_secret(path)
            if not secret:
                raise ValueError(
                    f"Could not retrieve secret from password manager: {path}"
                )
            return secret

        return (
            get_key("client_id_path"),
            get_key("client_secret_path"),
            get_key("oauth_token_path"),
            get_key("refresh_token_path"),
        )

    def update_tokens(
        self, campaign: str, access_token: str, refresh_token: str
    ) -> bool:
        """Update OAuth tokens in keyring; best-effort 1Password write.

        Keyring is required (what ``video upload`` uses after ``video auth``).
        1Password write often hangs under WSL with no Hello UI — timeout and
        treat as optional so auth still succeeds.
        """
        console.print(
            f"[dim]update_tokens: Saving tokens for campaign={campaign}[/dim]"
        )

        keyring_mgr = KeyringManager()
        success = keyring_mgr.set_tokens(campaign, access_token, refresh_token)
        console.print(f"[dim]update_tokens: keyring set_tokens result={success}[/dim]")

        if not refresh_token:
            console.print(
                "[yellow]No refresh_token in OAuth response; "
                "existing refresh token left unchanged.[/yellow]"
            )
            return success

        config = load_campaign_config(campaign)
        google_api = config.get("google_api_client", {})
        access_path = google_api.get("oauth_token_path")
        refresh_path = google_api.get("refresh_token_path")
        if access_path and refresh_path:
            console.print(
                "[dim]update_tokens: attempting 1Password write "
                "(30s timeout; optional if it hangs)…[/dim]"
            )
            access_ok = self.password_manager.set_secret(access_path, access_token)
            refresh_ok = self.password_manager.set_secret(refresh_path, refresh_token)
            if access_ok and refresh_ok:
                console.print("[dim]update_tokens: 1Password write OK[/dim]")
            else:
                console.print(
                    "[yellow]1Password token write failed or timed out. "
                    "Keyring tokens were saved — you can still "
                    f"`cocli video upload -c {campaign}`.[/yellow]"
                )
        return success

    def authenticate(self, campaign: str) -> bool:
        """Run the full device code flow."""
        client_id, client_secret, _, _ = self.get_credentials_from_config(campaign)

        console.print("Initiating OAuth device code flow...")
        device_code_response = self.get_device_code(client_id)

        device_code = device_code_response["device_code"]
        user_code = device_code_response["user_code"]
        verification_url = device_code_response["verification_url"]
        interval = device_code_response.get("interval", 5)

        console.print(f"\n[cyan]To authorize, go to:[/cyan] {verification_url}")
        console.print(f"[cyan]Enter code:[/cyan] [bold]{user_code}[/bold]")
        console.print(
            "\n[dim]Waiting for authorization... (press Ctrl+C to cancel)[/dim]\n"
        )

        console.print("[dim]Calling poll_for_token...[/dim]")
        token_response = self.poll_for_token(
            device_code, client_id, client_secret, interval
        )
        console.print(
            f"[dim]poll_for_token returned: {token_response is not None}[/dim]"
        )

        if not token_response:
            print("[red]Failed to obtain access token[/red]")
            return False

        console.print("[dim]Extracting tokens...[/dim]")
        access_token = token_response["access_token"]
        refresh_token = token_response.get("refresh_token", "")

        console.print(f"[dim]Calling update_tokens for campaign={campaign}...[/dim]")
        if self.update_tokens(campaign, access_token, refresh_token):
            print("[green]Successfully updated OAuth tokens![/green]")
            return True
        else:
            print("[red]Failed to store OAuth tokens[/red]")
            return False
