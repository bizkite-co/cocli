from typing import Optional, Any
from pydantic import BaseModel, Field, BeforeValidator
from typing_extensions import Annotated

def empty_to_none(v: Any) -> Any:
    if isinstance(v, str) and not v.strip():
        return None
    return v

# Apply empty_to_none to numeric and optional fields
OptionalInt = Annotated[Optional[int], BeforeValidator(empty_to_none)]
OptionalFloat = Annotated[Optional[float], BeforeValidator(empty_to_none)]
OptionalStr = Annotated[Optional[str], BeforeValidator(empty_to_none)]

class GoogleMapsRawResult(BaseModel):
    """
    EXTREMELY STRICT model that matches Google Maps scraper output exactly.
    NO internal logic, NO paper clips, NO snake_case transformation here.
    This is the landing zone for raw scraper data.
    """
    Keyword: str = ""
    Name: OptionalStr = None
    Full_Address: OptionalStr = None
    Street_Address: OptionalStr = None
    City: OptionalStr = None
    Zip: OptionalStr = None
    Municipality: OptionalStr = None
    State: OptionalStr = None
    Country: OptionalStr = None
    Timezone: OptionalStr = None
    Phone_1: OptionalStr = None
    Phone_Standard_format: OptionalStr = None
    Website: OptionalStr = None
    Domain: OptionalStr = None
    First_category: OptionalStr = None
    Second_category: OptionalStr = None
    Claimed_google_my_business: OptionalStr = None
    Reviews_count: OptionalInt = None
    Average_rating: OptionalFloat = None
    Hours: OptionalStr = None
    Saturday: OptionalStr = None
    Sunday: OptionalStr = None
    Monday: OptionalStr = None
    Tuesday: OptionalStr = None
    Wednesday: OptionalStr = None
    Thursday: OptionalStr = None
    Friday: OptionalStr = None
    Latitude: OptionalFloat = None
    Longitude: OptionalFloat = None
    Coordinates: OptionalStr = None
    Plus_Code: OptionalStr = None
    Place_ID: str = Field(..., description="The raw Place ID from Google")
    GMB_URL: OptionalStr = None
    CID: OptionalStr = None
    Image_URL: OptionalStr = None
    Favicon: OptionalStr = None
    Review_URL: OptionalStr = None
    Facebook_URL: OptionalStr = None
    Linkedin_URL: OptionalStr = None
    Instagram_URL: OptionalStr = None
    Thumbnail_URL: OptionalStr = None
    Reviews: OptionalStr = None
    Quotes: OptionalStr = None
    processed_by: OptionalStr = None
    created_at: OptionalStr = None
    updated_at: OptionalStr = None
    
    # --- Resource Discovery Extension ---
    is_value_resource: Optional[bool] = None
    fee_category: OptionalStr = None
    rationale: OptionalStr = None
