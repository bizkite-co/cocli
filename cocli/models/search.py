from pydantic import BaseModel, BeforeValidator
from typing import Optional, List, Any, Annotated

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
    name: Annotated[str, BeforeValidator(strip_quotes)]
    tags: List[str] = []
    display: str
    slug: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    unique_id: str
    average_rating: Optional[float] = None
    reviews_count: Optional[int] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    list_found_at: Optional[str] = None
    details_found_at: Optional[str] = None
    last_enriched: Optional[str] = None
