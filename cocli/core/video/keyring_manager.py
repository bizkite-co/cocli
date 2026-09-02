"""Keyring-based password manager for OAuth tokens.

This is used ONLY for OAuth access_token and refresh_token.
All other secrets (client_id, client_secret, etc.) remain in 1Password.
"""
from __future__ import annotations

import keyring
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SERVICE_NAME = "cocli-youtube"


class KeyringManager:
    """Manages OAuth tokens in system keyring."""

    def get_access_token(self, campaign: str) -> Optional[str]:
        """Get access token from keyring."""
        try:
            account = f"{campaign}_access_token"
            return keyring.get_password(SERVICE_NAME, account)
        except Exception as e:
            logger.error(f"Failed to get access token from keyring: {e}")
            return None

    def set_access_token(self, campaign: str, token: str) -> bool:
        """Store access token in keyring."""
        try:
            account = f"{campaign}_access_token"
            keyring.set_password(SERVICE_NAME, account, token)
            return True
        except Exception as e:
            logger.error(f"Failed to store access token in keyring: {e}")
            return False

    def get_refresh_token(self, campaign: str) -> Optional[str]:
        """Get refresh token from keyring."""
        try:
            account = f"{campaign}_refresh_token"
            return keyring.get_password(SERVICE_NAME, account)
        except Exception as e:
            logger.error(f"Failed to get refresh token from keyring: {e}")
            return None

    def set_refresh_token(self, campaign: str, token: str) -> bool:
        """Store refresh token in keyring."""
        try:
            account = f"{campaign}_refresh_token"
            keyring.set_password(SERVICE_NAME, account, token)
            return True
        except Exception as e:
            logger.error(f"Failed to store refresh token in keyring: {e}")
            return False

    def get_tokens(self, campaign: str) -> tuple[Optional[str], Optional[str]]:
        """Get both access and refresh tokens."""
        return self.get_access_token(campaign), self.get_refresh_token(campaign)

    def set_tokens(self, campaign: str, access_token: str, refresh_token: str) -> bool:
        """Store both access and refresh tokens."""
        access_ok = self.set_access_token(campaign, access_token)
        refresh_ok = self.set_refresh_token(campaign, refresh_token)
        return access_ok and refresh_ok
