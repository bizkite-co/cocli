from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, UTC


class DoNotCallEntry(BaseModel):
    """A person-level do-not-call obligation, keyed by normalized phone
    number. Shared/global by design (not per-campaign) - the obligation
    follows the person's phone number, not a specific campaign or company.
    See DoNotCallManager for the normalization/storage rules."""

    phone: str
    reason: Optional[str] = None
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
