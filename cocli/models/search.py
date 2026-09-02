from __future__ import annotations
from pydantic import BaseModel
from typing import Optional, Any
from .phone import OptionalPhone
from .company_name import OptionalCompanyName
from .company_address import OptionalCompanyAddress

def strip_quotes(v: Any) -> str:
    if isinstance(v, str):
        v = v.strip()
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1].strip()
        if v.startswith("'") and v.endswith("'"):
            v = v[1:-1].strip()
    return str(v)

class SearchResult(BaseModel):
    type: str
    name: OptionalCompanyName = None
    tags: list[str] = []
    display: str
    slug: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    phone_number: OptionalPhone = None
    company_name: OptionalCompanyName = None
    unique_id: str
    average_rating: Optional[float] = None
    reviews_count: Optional[int] = None
    street_address: OptionalCompanyAddress = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    list_found_at: Optional[str] = None
    details_found_at: Optional[str] = None
    enqueued_at: Optional[str] = None
    last_enriched: Optional[str] = None
