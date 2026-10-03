"""One immutable-at-creation record per actual outbound send, keyed by
an opaque GUID embedded in every link that email contains (the
testimonial-request CTA, the unsubscribe link, etc.) - the identifier
`cocli/application/personalized_outreach_service.py`'s own
`rendered-outreach/<company>/<template>` file can't provide, since
that file is keyed by (company, template) and gets overwritten by a
later send of the same template (e.g. after the template is edited),
losing any earlier send's own history.

Hash-sharded (sends/<sha256(guid)[:2]>/<guid>.md) - the same "lots of
independently-keyed records, avoid one giant directory" pattern this
project already uses for the domains/ and email-inbox/ stores, not a
new structural concept. Scoped per-campaign (unlike domains/, which is
global) since everything else about a send - the engagement log,
rendered-outreach, the send log itself - already lives under
campaigns/<campaign>/.

Deliberately allows write-back after creation (click/unsubscribe
fields) - this is the concrete reason a single hash-sharded FILE per
send, not just another row in the append-only email-send-log USV, is
the right shape: patching one field of one historical USV row would
mean rewriting the whole log; patching one small file is cheap and
safe.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

from ..core.paths import paths


class SendRecord(BaseModel):
    guid: str
    campaign_name: str
    initiative: str
    company_slug: str
    template_id: str
    recipient_email: str
    subject: str
    batch_id: Optional[str] = None
    message_id: Optional[str] = None
    sent_at: datetime
    clicked_at: Optional[datetime] = None
    click_count: int = 0
    unsubscribed_at: Optional[datetime] = None
    unsubscribe_reason: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @staticmethod
    def new_guid() -> str:
        # .hex (32 lowercase hex chars, no dashes) - shorter in a URL
        # query string than the dashed form, and dashes would need
        # percent-encoding-awareness everywhere this gets pasted anyway.
        return uuid.uuid4().hex

    @staticmethod
    def shard_for(guid: str) -> str:
        """The one place that decides how a guid maps to a shard - same
        2-hex-char sha256 prefix convention as DOMAIN_HASH_SHARD
        (station_defs/campaigns/indexes/__init__.py)."""
        return hashlib.sha256(guid.encode("utf-8")).hexdigest()[:2]

    @classmethod
    def _path(cls, campaign_name: str, guid: str) -> Path:
        return (
            paths.campaign(campaign_name).path
            / "sends"
            / cls.shard_for(guid)
            / f"{guid}.md"
        )

    @classmethod
    def get(cls, campaign_name: str, guid: str) -> Optional["SendRecord"]:
        path = cls._path(campaign_name, guid)
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8")
        if not (content.startswith("---") and "---" in content[3:]):
            return None
        parts = content.split("---", 2)
        try:
            data: dict[str, Any] = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            return None
        try:
            return cls(**data)
        except Exception:
            return None

    def save(self) -> Path:
        self.updated_at = datetime.now(UTC)
        path = self._path(self.campaign_name, self.guid)
        path.parent.mkdir(parents=True, exist_ok=True)
        frontmatter = yaml.dump(
            self.model_dump(mode="json"), sort_keys=False, default_flow_style=False, allow_unicode=True
        )
        path.write_text(f"---\n{frontmatter}---\n", encoding="utf-8")
        return path

    def mark_clicked(self) -> None:
        if self.clicked_at is None:
            self.clicked_at = datetime.now(UTC)
        self.click_count += 1

    def mark_unsubscribed(self, reason: str = "") -> None:
        self.unsubscribed_at = datetime.now(UTC)
        self.unsubscribe_reason = reason or None
