from __future__ import annotations
from typing import ClassVar, Literal, Optional
from datetime import datetime, UTC
from pydantic import Field
from .base import BaseIndexModel


class SendLogEntry(BaseIndexModel):
    """One outreach send attempt: which batch/template it belongs to, who
    it went to, and whether it succeeded - the structured replacement for
    scattered per-company EmailNote markdown files, queryable by batch,
    template, or status instead of only by company.
    """

    INDEX_NAME: ClassVar[str] = "email-send-log"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-09-14T00:00:00+00:00"

    batch_id: str
    template_id: str
    company_slug: str
    recipient: str
    subject: str
    message_id: Optional[str] = None
    status: Literal["sent", "failed"]
    sent_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error: Optional[str] = None
