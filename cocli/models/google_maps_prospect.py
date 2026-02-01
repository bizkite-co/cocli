from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, UTC
import logging

from .types import AwareDatetime, PlaceID # Import the custom types
from .phone import OptionalPhone
from cocli.core.text_utils import slugify

logger = logging.getLogger(__name__)

class GoogleMapsProspect(BaseModel):
    """
    Standardized model for Google Maps prospects.
    Internal fields are strictly snake_case.
    The place_id is the primary unique identifier.
    """
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: "".join(word.capitalize() for word in s.split("_")),
        "extra": "ignore"
    }

    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    # Redundant GUID id removed. place_id is the anchor.
    keyword: Optional[str] = None
    name: Optional[str] = None
    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    municipality: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    phone_1: OptionalPhone = None
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
    place_id: PlaceID = Field(..., description="Google Maps Place ID is the primary anchor")
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
    company_slug: Optional[str] = None
    company_hash: Optional[str] = None
    processed_by: Optional[str] = "local-worker"

    @model_validator(mode='after')
    def validate_identity_tripod(self) -> 'GoogleMapsProspect':
        """Ensures the identity tripod and linking IDs are populated."""
        if not self.company_slug and self.name:
            self.company_slug = slugify(self.name)
        
        if not self.company_hash and self.name:
            from cocli.core.text_utils import calculate_company_hash
            self.company_hash = calculate_company_hash(self.name, self.street_address, self.zip)
            
        return self

    @model_validator(mode='before')
    @classmethod
    def clean_empty_values(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Convert empty strings to None for numeric and optional fields to handle CSV/USV input."""
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
        """Serializes the model to a single-line unit-separated string."""
        values = []
        dump = self.model_dump(by_alias=False)
        for field in self.__class__.model_fields.keys():
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
        return "\x1f".join(values) + "\n"

    @classmethod
    def from_usv(cls, usv_str: str) -> "GoogleMapsProspect":
        """Parses a unit-separated line into a GoogleMapsProspect object."""
        # Strip both Record Separator and Newline
        line = usv_str.strip("\x1e\n")
        if not line:
            raise ValueError("Empty unit-separated line")
            
        parts = line.split("\x1f")
        fields = list(cls.model_fields.keys())
        
        data: Dict[str, Any] = {}
        for i, field_name in enumerate(fields):
            if i < len(parts):
                val = parts[i]
                if val == "":
                    if field_name in ["created_at", "updated_at"]:
                        data[field_name] = datetime.now(UTC)
                    else:
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
                # Schema drift
                if field_name in ["created_at", "updated_at"]:
                    data[field_name] = datetime.now(UTC)
                else:
                    data[field_name] = None
        
        return cls.model_validate(data)