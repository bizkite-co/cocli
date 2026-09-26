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
        d = dict(self.details)
        if self.utm_campaign and "utm_campaign" not in d:
            d["utm_campaign"] = self.utm_campaign
        if self.utm_source and "utm_source" not in d:
            d["utm_source"] = self.utm_source
        if self.utm_medium and "utm_medium" not in d:
            d["utm_medium"] = self.utm_medium
        if self.utm_term and "utm_term" not in d:
            d["utm_term"] = self.utm_term
        import json
        try:
            details_str = json.dumps(d)
        except Exception:
            details_str = str(d)
        details_clean = details_str.replace("\x1f", " ").replace("\n", " ")
        return f"{ts_str}\x1f{self.campaign_name}\x1f{slug}\x1f{self.event_type}\x1f{self.source}\x1f{utm_c}\x1f{details_clean}\n"

    @classmethod
    def from_usv_row(cls, row: str) -> Optional[EngagementEvent]:
        """Parse a single USV line into an EngagementEvent."""
        parts = row.rstrip("\r\n").split("\x1f")
        if len(parts) < 5:
            return None
        ts_str = parts[0]
        try:
            ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        except Exception:
            ts = datetime.now(UTC)
        campaign_name = parts[1]
        company_slug = parts[2] or None
        event_type = parts[3]
        source = parts[4]
        utm_content = parts[5] if len(parts) > 5 and parts[5] else None
        details: dict[str, Any] = {}
        if len(parts) > 6 and parts[6]:
            import ast
            import json
            raw_details = parts[6]
            try:
                details = json.loads(raw_details)
            except Exception:
                try:
                    parsed = ast.literal_eval(raw_details)
                    if isinstance(parsed, dict):
                        details = parsed
                    else:
                        details = {"raw": raw_details}
                except Exception:
                    details = {"raw": raw_details}
        utm_campaign = details.get("utm_campaign")
        utm_source = details.get("utm_source")
        utm_medium = details.get("utm_medium")
        utm_term = details.get("utm_term")
        return cls(
            timestamp=ts,
            campaign_name=campaign_name,
            company_slug=company_slug,
            event_type=event_type,
            source=source,
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
            utm_content=utm_content,
            utm_term=utm_term,
            details=details,
        )


