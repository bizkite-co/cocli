"""Models for cocli-native send/monitor mail (not a mail-client)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MailMessage(BaseModel):
    """One inbound or outbound message, keyed by RFC Message-ID when present."""

    message_id: str
    from_address: str
    to_addresses: list[str] = Field(default_factory=list)
    subject: str = ""
    date: Optional[datetime] = None
    body: str = ""
    folder: Optional[str] = None


class SendMailRequest(BaseModel):
    to_address: str
    subject: str
    body: str
    company_slug: Optional[str] = None
    from_address: Optional[str] = None


class SendMailResult(BaseModel):
    message_id: str
    to_address: str
    subject: str
    note_written: bool = False
    company_slug: Optional[str] = None


class PollMailResult(BaseModel):
    fetched: int = 0
    noted: int = 0
    skipped_seen: int = 0
    unmatched: int = 0
    notes: list[str] = Field(default_factory=list)


class EmailSettings(BaseModel):
    """Campaign ``[email]`` section. Optional; send/poll require the fields they use."""

    model_config = {"extra": "ignore"}

    from_address: Optional[str] = None
    reply_to: Optional[str] = None
    ses_region: str = "us-east-1"
    ses_configuration_set: Optional[str] = None
    imap_host: str = "outlook.office365.com"
    imap_user: Optional[str] = None
    token_cache: Optional[str] = None
    client_id: Optional[str] = None
    token_endpoint: str = (
        "https://login.microsoftonline.com/organizations/oauth2/v2.0/token"
    )
    monitored_addresses: list[str] = Field(default_factory=list)
    folders: list[str] = Field(default_factory=lambda: ["INBOX"])
