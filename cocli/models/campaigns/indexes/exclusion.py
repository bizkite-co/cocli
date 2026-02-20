from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Exclusion(BaseModel):
    domain: Optional[str] = None
    company_slug: Optional[str] = None
    campaign: str
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
