from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field
from .phone import OptionalPhone

class ShopifyData(BaseModel):
    version: int = 1
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: OptionalPhone = None
    tags: list[str] = Field(default_factory=list)
    company_name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    country: Optional[str] = None
    address_phone: OptionalPhone = None
