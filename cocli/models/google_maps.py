from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, UTC

class GoogleMapsData(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    id: Optional[str] = None
    Keyword: Optional[str] = None
    Name: Optional[str] = None
    Full_Address: Optional[str] = None
    Street_Address: Optional[str] = None
    City: Optional[str] = None
    Zip: Optional[str] = None
    Municipality: Optional[str] = None
    State: Optional[str] = None
    Country: Optional[str] = None
    Timezone: Optional[str] = None
    Phone_1: Optional[str] = None
    Phone_Standard_format: Optional[str] = None
    Website: Optional[str] = None
    Domain: Optional[str] = None
    First_category: Optional[str] = None
    Second_category: Optional[str] = None
    Claimed_google_my_business: Optional[str] = None
    Reviews_count: Optional[int] = None
    Average_rating: Optional[float] = None
    Hours: Optional[str] = None
    Saturday: Optional[str] = None
    Sunday: Optional[str] = None
    Monday: Optional[str] = None
    Tuesday: Optional[str] = None
    Wednesday: Optional[str] = None
    Thursday: Optional[str] = None
    Friday: Optional[str] = None
    Latitude: Optional[float] = None
    Longitude: Optional[float] = None
    Coordinates: Optional[str] = None
    Plus_Code: Optional[str] = None
    Place_ID: Optional[str] = None
    Menu_Link: Optional[str] = None
    GMB_URL: Optional[str] = None
    CID: Optional[str] = None
    Google_Knowledge_URL: Optional[str] = None
    Kgmid: Optional[str] = None
    Image_URL: Optional[str] = None
    Favicon: Optional[str] = None
    Review_URL: Optional[str] = None
    Facebook_URL: Optional[str] = None
    Linkedin_URL: Optional[str] = None
    Instagram_URL: Optional[str] = None
    Thumbnail_URL: Optional[str] = None
    Reviews: Optional[str] = None
    Quotes: Optional[str] = None
    Uuid: Optional[str] = None