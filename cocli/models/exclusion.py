from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

class Exclusion(BaseModel):
    domain: str
    campaign: str
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
