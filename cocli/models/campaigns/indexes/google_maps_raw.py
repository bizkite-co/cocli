from typing import Optional
from pydantic import BaseModel, Field

class GoogleMapsRawResult(BaseModel):
    """
    EXTREMELY STRICT model that matches Google Maps scraper output exactly.
    NO internal logic, NO paper clips, NO snake_case transformation here.
    This is the landing zone for raw scraper data.
    """
    Keyword: str = ""
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
    Place_ID: str = Field(..., description="The raw Place ID from Google")
    GMB_URL: Optional[str] = None
    CID: Optional[str] = None
    Image_URL: Optional[str] = None
    Favicon: Optional[str] = None
    Review_URL: Optional[str] = None
    Facebook_URL: Optional[str] = None
    Linkedin_URL: Optional[str] = None
    Instagram_URL: Optional[str] = None
    Thumbnail_URL: Optional[str] = None
    Reviews: Optional[str] = None
    Quotes: Optional[str] = None
    processed_by: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
