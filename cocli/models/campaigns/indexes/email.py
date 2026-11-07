# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional, Union

from pydantic import Field, field_validator

from ...base import BaseUsvModel
from ...email_address import EmailAddress


class EmailEntry(BaseUsvModel):
    """
    Represents an entry in the campaign-specific email index.
    """
    email: Union[EmailAddress, str] # Allow string fallback for legacy junk
    domain: str
    company_slug: Optional[str] = None
    source: str  # e.g., "website_scraper", "shopify_import", "manual"
    found_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    first_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(UTC))
    verification_status: str = "unknown"
    tags: list[str] = Field(default_factory=list)

    @field_validator("email", mode="before")
    @classmethod
    def validate_email_lenient(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return EmailAddress(v)
            except Exception:
                return v # Return as raw string if it fails validation
        return v
