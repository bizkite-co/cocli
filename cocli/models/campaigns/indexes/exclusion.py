from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Exclusion(BaseModel):
    domain: Optional[str] = None
    company_slug: Optional[str] = None
    campaign: str
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
