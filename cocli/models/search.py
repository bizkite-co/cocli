from pydantic import BaseModel
from typing import Optional, List

class SearchResult(BaseModel):
    type: str
    name: str
    tags: List[str] = []
    display: str
    slug: Optional[str] = None
    domain: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    company_name: Optional[str] = None
    unique_id: str
