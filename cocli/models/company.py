from pydantic import BaseModel
from typing import Optional, List

class Company(BaseModel):
    name: str
    slug: str
    domain: Optional[str] = None
    phone_number: Optional[str] = None
    tags: List[str] = []
    categories: List[str] = []
    description: Optional[str] = None