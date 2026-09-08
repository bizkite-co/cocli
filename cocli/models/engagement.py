from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class EngagementEvent(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    campaign_name: str
    company_slug: Optional[str] = None
    event_type: str  # e.g., email_reply, call_logged, cta_click, demo_video_start, calculator_interactive_use
    source: str = "gtm"  # imap, call, gtm, webhook
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_content: Optional[str] = None
    utm_term: Optional[str] = None
    details: dict[str, Any] = Field(default_factory=dict)

    def to_usv_row(self) -> str:
        """Format as a single USV line with \x1f separators and \n ending."""
        ts_str = self.timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")
        slug = self.company_slug or ""
        utm_c = self.utm_content or ""
        details_str = str(self.details).replace("\x1f", " ").replace("\n", " ")
        return f"{ts_str}\x1f{self.campaign_name}\x1f{slug}\x1f{self.event_type}\x1f{self.source}\x1f{utm_c}\x1f{details_str}\n"
