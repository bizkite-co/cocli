from typing import Optional, List
from pydantic import BaseModel, Field
from .phone import OptionalPhone

class ShopifyData(BaseModel):
    version: int = 1
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: OptionalPhone = None
    tags: List[str] = Field(default_factory=list)
    company_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    address_phone: OptionalPhone = None
