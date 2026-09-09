"""AWS SES Account-Level Suppression List & Unsubscribe Service."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SesSuppressionService:
    """
    AWS SES account-level suppression list manager.
    Conforms to SesSuppressionProtocol.
    """

    def __init__(self, region: str = "us-east-1", profile: Optional[str] = None) -> None:
        self.region = region
        self.profile = profile
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            session = boto3.Session(profile_name=self.profile) if self.profile else boto3.Session()
            self._client = session.client("sesv2", region_name=self.region)
        return self._client

    def suppress_email(self, email: str, reason: str = "COMPLAINT") -> bool:
        """Add email address to AWS SES account-level suppression list."""
        client = self._get_client()
        valid_reason = "BOUNCE" if reason.upper() == "BOUNCE" else "COMPLAINT"
        try:
            client.put_suppressed_destination(EmailAddress=email, Reason=valid_reason)
            logger.info("Suppressed %s in AWS SES (%s)", email, valid_reason)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not suppress %s in AWS SES: %s", email, exc)
            return False

    def is_suppressed(self, email: str) -> bool:
        """Check if an email address is in the AWS SES suppression list."""
        client = self._get_client()
        try:
            resp = client.get_suppressed_destination(EmailAddress=email)
            return bool(resp and resp.get("SuppressedDestination"))
        except Exception:  # noqa: BLE001
            return False

    def unsuppress_email(self, email: str) -> bool:
        """Remove email address from AWS SES account-level suppression list."""
        client = self._get_client()
        try:
            client.delete_suppressed_destination(EmailAddress=email)
            logger.info("Removed %s from AWS SES suppression list", email)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not remove %s from AWS SES suppression list: %s", email, exc)
            return False

    def list_suppressed(self, limit: int = 100) -> list[dict[str, Any]]:
        """List suppressed destinations from AWS SES."""
        client = self._get_client()
        try:
            resp = client.list_suppressed_destinations(PageSize=min(limit, 1000))
            summaries = resp.get("SuppressedDestinationSummaries", [])
            return [
                {
                    "email": s.get("EmailAddress"),
                    "reason": s.get("Reason"),
                    "last_updated": str(s.get("LastUpdateTime")),
                }
                for s in summaries
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not list AWS SES suppressed destinations: %s", exc)
            return []
