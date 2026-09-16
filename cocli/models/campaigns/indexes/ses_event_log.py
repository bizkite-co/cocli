from __future__ import annotations
from typing import ClassVar, Literal, Optional
from datetime import datetime, UTC
from pydantic import Field
from .base import BaseIndexModel


class SesEventLogEntry(BaseIndexModel):
    """One bounce/complaint event ingested from the SQS queue subscribed
    to a campaign's outbound-sales SNS topic (see
    EmailEventsService.poll(), cdk CocliEmailEventsQueue). Append-only,
    same discipline as SendLogEntry; message_id joins back to it to
    determine which batch/initiative a bounce or complaint belongs to.
    """

    INDEX_NAME: ClassVar[str] = "ses-event-log"
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"
    SCHEMA_UPDATED_AT: ClassVar[str] = "2026-09-16T00:00:00+00:00"

    event_type: Literal["BOUNCE", "COMPLAINT"]
    message_id: str
    recipient: str
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # bounce.bounceType (Permanent/Transient/Undetermined) or
    # complaint.complaintFeedbackType - whichever the event carried.
    sub_type: Optional[str] = None
