from __future__ import annotations
from typing import ClassVar
from datetime import datetime, UTC
from pydantic import Field
from .base import BaseIndexModel


class PendingBatchEntry(BaseIndexModel):
    """One recipient in a prepared-but-not-yet-sent (or discarded) email
    batch: the subject/body are already fully rendered (post .format()
    substitution) at freeze time, so a template placeholder bug surfaces
    here, before anything is queued for review or send.

    Current state, not history: a batch's rows are removed once sent or
    discarded, same "static current-state index" discipline as
    LeadFilterEntry and to-call/to-call-invalid - what you review is
    exactly what gets sent, not a fresh re-render that could drift if
    company data changes in between.
    """

    INDEX_NAME: ClassVar[str] = "email-pending-batch"
    SCHEMA_VERSION: ClassVar[str] = "1.1.0"
    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-09-16T00:00:00+00:00"

    batch_id: str
    template_id: str
    company_slug: str
    recipient: str
    subject: str
    body: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # Added last, not inserted earlier: from_usv()/to_usv() are positional
    # (base.py) - keeping this last means any pending.usv row written
    # before this field existed still parses (missing trailing column ->
    # falls through to this default).
    initiative: str = "rta"
