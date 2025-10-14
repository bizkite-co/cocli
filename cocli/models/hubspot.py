from pydantic import BaseModel, EmailStr
from typing import Optional


class HubspotContactCsv(BaseModel):
    """
    Represents a row in a HubSpot contact import CSV file.
    """
    firstname: Optional[str] = None
    lastname: Optional[str] = None
    email: EmailStr
    company: Optional[str] = None
    phone: Optional[str] = None
    website: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
