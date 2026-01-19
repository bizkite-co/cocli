from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from .domain import Domain
from .email_address import EmailAddress
from .phone import OptionalPhone

class WebsiteDomainCsv(BaseModel):
    domain: Domain
    company_name: Optional[str] = None
    phone: OptionalPhone = None
    email: Optional[EmailAddress] = None
    ip_address: Optional[str] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    address: Optional[str] = None
    about_us_url: Optional[str] = None
    contact_url: Optional[str] = None
    services_url: Optional[str] = None
    products_url: Optional[str] = None
    tags: List[str] = []
    scraper_version: Optional[int] = 1
    associated_company_folder: Optional[str] = None
    is_email_provider: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
