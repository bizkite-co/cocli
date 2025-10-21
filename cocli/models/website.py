from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Optional, List, Dict, Any
from datetime import datetime
from .domain import Domain

class Website(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(datetime.UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(datetime.UTC))
    url: Domain # Called `domain` in the website CSV model

    @model_validator(mode='before')
    @classmethod
    def _populate_url_from_domain(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if 'domain' in values and 'url' not in values:
            values['url'] = values['domain']
        return values

    @computed_field
    def domain(self) -> Domain:
        return self.url

    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    address: Optional[str] = None
    personnel: List[str] = []
    description: Optional[str] = None
    about_us_url: Optional[str] = None
    contact_url: Optional[str] = None
    services_url: Optional[str] = None
    products_url: Optional[str] = None
    services: List[str] = []
    products: List[str] = []
    tags: List[str] = []
    scraper_version: Optional[int] = 1
    associated_company_folder: Optional[str] = None
    is_email_provider: bool = False