from pydantic import Field, model_validator
from typing import Optional, Dict, Any, Annotated, List, ClassVar
from datetime import datetime, UTC
import logging

from .google_maps_idx import GoogleMapsIdx
from .google_maps_raw import GoogleMapsRawResult
from .phone import OptionalPhone
from ..core.text_utils import slugify

logger = logging.getLogger(__name__)

# Custom Types for validation and clarity
AwareDatetime = Annotated[datetime, "A datetime with timezone info"]

class GoogleMapsProspect(GoogleMapsIdx):
    """
    GOLD STANDARD MODEL: Standardized model for Google Maps prospects.
    
    SINGLE SOURCE OF TRUTH:
    1. Field definition order == USV Column Order.
    2. Model metadata == datapackage.json schema.
    """
    # Increment this when columns are added, removed, or reordered
    SCHEMA_VERSION: ClassVar[str] = "1.0.0"

    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: "".join(word.capitalize() for word in s.split("_")),
        "extra": "ignore"
    }

    # --- THE FIXED USV SEQUENCE (Identity first) ---
    # place_id (inherited)
    # company_slug (inherited)
    # name (inherited)
    phone: OptionalPhone = Field(None, alias="phone_1")
    
    # --- Metadata / Lifecycle ---
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    processed_by: Optional[str] = "local-worker"
    company_hash: Optional[str] = Field(None, description="Identity hash")
    
    # --- Enrichment Data ---
    keyword: Optional[str] = None
    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    municipality: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    phone_standard_format: OptionalPhone = None
    website: Optional[str] = None
    domain: Optional[str] = None
    first_category: Optional[str] = None
    second_category: Optional[str] = None
    claimed_google_my_business: Optional[str] = None
    reviews_count: Optional[int] = None
    average_rating: Optional[float] = None
    hours: Optional[str] = None
    saturday: Optional[str] = None
    sunday: Optional[str] = None
    monday: Optional[str] = None
    tuesday: Optional[str] = None
    wednesday: Optional[str] = None
    thursday: Optional[str] = None
    friday: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    coordinates: Optional[str] = None
    plus_code: Optional[str] = None
    
    # --- Extended Metadata ---
    menu_link: Optional[str] = None
    gmb_url: Optional[str] = None
    cid: Optional[str] = None
    google_knowledge_url: Optional[str] = None
    kgmid: Optional[str] = None
    image_url: Optional[str] = None
    favicon: Optional[str] = None
    review_url: Optional[str] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    reviews: Optional[str] = None
    quotes: Optional[str] = None
    uuid: Optional[str] = None
    discovery_phrase: Optional[str] = None
    discovery_tile_id: Optional[str] = None

    @classmethod
    def get_datapackage_fields(cls) -> List[Dict[str, str]]:
        """Generates Frictionless Data field definitions from the model."""
        fields = []
        for name, field in cls.model_fields.items():
            # Map Python types to JSON Schema/Frictionless types
            raw_type = field.annotation
            field_type = "string" # default
            
            type_str = str(raw_type)
            if "int" in type_str:
                field_type = "integer"
            elif "float" in type_str:
                field_type = "number"
            elif "datetime" in type_str:
                field_type = "datetime"
                
            fields.append({
                "name": name,
                "type": field_type,
                "description": field.description or ""
            })
        return fields

    @classmethod
    def from_raw(cls, raw: GoogleMapsRawResult) -> "GoogleMapsProspect":
        from cocli.core.text_utils import slugify, calculate_company_hash
        data = {
            "place_id": raw.Place_ID,
            "name": raw.Name,
            "keyword": raw.Keyword,
            "full_address": raw.Full_Address,
            "street_address": raw.Street_Address,
            "city": raw.City,
            "zip": raw.Zip,
            "municipality": raw.Municipality,
            "state": raw.State,
            "country": raw.Country,
            "timezone": raw.Timezone,
            "phone": raw.Phone_1,
            "phone_standard_format": raw.Phone_Standard_format,
            "website": raw.Website,
            "domain": raw.Domain,
            "first_category": raw.First_category,
            "second_category": raw.Second_category,
            "claimed_google_my_business": raw.Claimed_google_my_business,
            "reviews_count": raw.Reviews_count,
            "average_rating": raw.Average_rating,
            "hours": raw.Hours,
            "saturday": raw.Saturday,
            "sunday": raw.Sunday,
            "monday": raw.Monday,
            "tuesday": raw.Tuesday,
            "wednesday": raw.Wednesday,
            "thursday": raw.Thursday,
            "friday": raw.Friday,
            "latitude": raw.Latitude,
            "longitude": raw.Longitude,
            "coordinates": raw.Coordinates,
            "plus_code": raw.Plus_Code,
            "gmb_url": raw.GMB_URL,
            "cid": raw.CID,
            "image_url": raw.Image_URL,
            "favicon": raw.Favicon,
            "review_url": raw.Review_URL,
            "facebook_url": raw.Facebook_URL,
            "linkedin_url": raw.Linkedin_URL,
            "instagram_url": raw.Instagram_URL,
            "thumbnail_url": raw.Thumbnail_URL,
            "reviews": raw.Reviews,
            "quotes": raw.Quotes,
            "processed_by": raw.processed_by or "local-worker"
        }
        
        if data["name"]:
            name_str = str(data["name"])
            data["company_slug"] = slugify(name_str)
            data["company_hash"] = calculate_company_hash(
                name_str, 
                str(data["street_address"]) if data["street_address"] else None,
                str(data["zip"]) if data["zip"] else None
            )
            
        return cls(**data) # type: ignore

    @model_validator(mode='after')
    def validate_identity_tripod(self) -> 'GoogleMapsProspect':
        if not self.company_slug and self.name:
            self.company_slug = slugify(self.name)
        return self

    @model_validator(mode='before')
    @classmethod
    def clean_empty_values(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values
            
        nullable_fields = [
            'reviews_count', 'average_rating', 'latitude', 'longitude', 
            'version', 'company_slug', 'company_hash'
        ]
        for field in nullable_fields:
            if values.get(field) == '':
                values[field] = None
        return values

    def to_usv(self) -> str:
        """Serializes based on architectural sequence."""
        from ..core.utils import UNIT_SEP
        field_names = list(self.model_fields.keys())
        
        values = []
        dump = self.model_dump(by_alias=False)
        for field in field_names:
            val = dump.get(field)
            if val is None:
                values.append("")
            elif isinstance(val, (list, tuple)):
                sanitized_list = [str(v).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>") for v in val]
                values.append(";".join(sanitized_list))
            elif isinstance(val, datetime):
                values.append(val.isoformat())
            else:
                values.append(str(val).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>"))
        
        return UNIT_SEP.join(values) + "\n"

    @classmethod
    def from_usv(cls, usv_str: str) -> "GoogleMapsProspect":
        """Parses based on architectural sequence."""
        from ..core.utils import UNIT_SEP
        line = usv_str.strip("\x1e\n")
        if not line:
            raise ValueError("Empty unit-separated line")
            
        parts = line.split(UNIT_SEP)
        field_names = list(cls.model_fields.keys())
        
        data: Dict[str, Any] = {}
        for i, field_name in enumerate(field_names):
            if i < len(parts):
                val = parts[i]
                if val == "":
                    data[field_name] = None
                else:
                    if field_name in ["created_at", "updated_at"]:
                        try:
                            data[field_name] = datetime.fromisoformat(val)
                        except ValueError:
                            data[field_name] = datetime.now(UTC)
                    else:
                        data[field_name] = val
            else:
                data[field_name] = None
        
        return cls.model_validate(data)