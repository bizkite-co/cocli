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
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    about_us_url: Optional[str] = None
    contact_url: Optional[str] = None
    email: Optional[str] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None