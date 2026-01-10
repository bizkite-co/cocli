from pydantic import BaseModel, EmailStr
from typing import Optional
from .phone import OptionalPhone


class HubspotContactCsv(BaseModel):
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: EmailStr
    company: Optional[str] = None
    phone: OptionalPhone = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
