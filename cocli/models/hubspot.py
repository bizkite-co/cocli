from pydantic import BaseModel, EmailStr
from typing import Optional
from .phone import PhoneNumber


class HubspotContactCsv(BaseModel):
    """
    Represents a row in a HubSpot contact import CSV file.
    """
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: EmailStr
    company: Optional[str] = None
    phone: Optional[PhoneNumber] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
