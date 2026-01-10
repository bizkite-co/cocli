from typing import Optional, List
from pydantic import BaseModel, Field
from .phone import PhoneNumber

class ShopifyData(BaseModel):
    version: int = 1
    id: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[PhoneNumber] = None
    tags: List[str] = Field(default_factory=list)
    company_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    address_phone: Optional[PhoneNumber] = None
