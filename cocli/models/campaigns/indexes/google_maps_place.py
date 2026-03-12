from pydantic import Field, model_validator, BeforeValidator
from typing import Optional, Dict, Any, Annotated, List, Protocol, runtime_checkable
from datetime import datetime, UTC
from pathlib import Path
import logging

from .google_maps_idx import GoogleMapsIdx, strip_quotes
from ...phone import OptionalPhone

logger = logging.getLogger(__name__)

# Custom Types for validation and clarity
AwareDatetime = Annotated[datetime, "A datetime with timezone info"]

def safe_float(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if hasattr(v, "__class__") and "MagicMock" in str(v.__class__):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

def safe_int(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    if hasattr(v, "__class__") and "MagicMock" in str(v.__class__):
        return None
    try:
        return int(float(v)) # handle "1.0"
    except (ValueError, TypeError):
        return None

SafeFloat = Annotated[Optional[float], BeforeValidator(safe_float)]
SafeInt = Annotated[Optional[int], BeforeValidator(safe_int)]

@runtime_checkable
class GoogleMapsPlaceProtocol(Protocol):
    """
    ARCHITECTURAL CONTRACT: The standard interface for any Google Maps record.
    Any model representing a 'Place' must implement these core fields and methods.
    """
    place_id: str
    slug: str
    name: str
    phone: OptionalPhone
    created_at: datetime
    updated_at: datetime
    version: int
    processed_by: Optional[str]
    company_hash: Optional[str]

    @property
    def company_slug(self) -> str: ...
    
    # Core Physicality
    full_address: Optional[str]
    city: Optional[str]
    zip: Optional[str]
    state: Optional[str]
    website: Optional[str]
    domain: Optional[str]
    first_category: Optional[str]
    gmb_url: Optional[str]
    average_rating: Optional[float]
    reviews_count: Optional[int]
    latitude: Optional[float]
    longitude: Optional[float]
    
    def to_usv(self) -> str: ...
    def save_enrichment(self) -> Path: ...
    @classmethod
    def model_validate(cls, obj: Any) -> "GoogleMapsPlaceProtocol": ...

class GoogleMapsPlace(GoogleMapsIdx):
    """
    BASE MODEL: Standardized identity and physical data for any Google Maps place.
    Contains the first 56 columns of the canonical USV format.
    """
    model_config = {
        "populate_by_name": True,
        "alias_generator": lambda s: "".join(word.capitalize() for word in s.split("_")),
        "extra": "ignore"
    }

    # --- THE FIXED USV SEQUENCE (Identity first) ---
    # place_id (inherited)
    # slug (inherited)
    # name (inherited)
    phone: OptionalPhone = Field(None, alias="phone_1")
    
    # --- Metadata / Lifecycle ---
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))
    version: int = 1
    processed_by: Annotated[Optional[str], BeforeValidator(strip_quotes)] = "local-worker"
    company_hash: Annotated[Optional[str], BeforeValidator(strip_quotes)] = Field(None, description="Identity hash")
    
    # --- Enrichment Data ---
    keyword: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    full_address: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    street_address: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    city: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    zip: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    municipality: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    state: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    country: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    timezone: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    phone_standard_format: OptionalPhone = None
    website: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    domain: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    first_category: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    second_category: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    claimed_google_my_business: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    reviews_count: SafeInt = None
    average_rating: SafeFloat = None
    hours: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    saturday: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    sunday: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    monday: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    tuesday: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    wednesday: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    thursday: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    friday: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    latitude: SafeFloat = None
    longitude: SafeFloat = None
    coordinates: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    plus_code: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    
    # --- Extended Metadata ---
    menu_link: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    gmb_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    cid: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    google_knowledge_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    kgmid: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    image_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    favicon: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    review_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    facebook_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    linkedin_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    instagram_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    thumbnail_url: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    reviews: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    quotes: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    uuid: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    discovery_phrase: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    discovery_tile_id: Annotated[Optional[str], BeforeValidator(strip_quotes)] = None
    email: Annotated[Optional[str], BeforeValidator(strip_quotes)] = Field(None, description="DEPRECATED: Google Maps does not provide email. Use website enrichment instead.")

    @model_validator(mode='after')
    def extract_domain(self) -> 'GoogleMapsPlace':
        if self.website and not self.domain:
            from ....core.text_utils import extract_domain
            self.domain = extract_domain(self.website)
        return self

    @model_validator(mode='after')
    def validate_identity_tripod(self) -> 'GoogleMapsPlace':
        from cocli.core.text_utils import slugify, calculate_company_hash
        
        if not self.slug and self.name:
            self.slug = slugify(self.name)
            
        if self.name and not self.company_hash:
            self.company_hash = calculate_company_hash(
                self.name,
                self.street_address,
                self.zip
            )
        return self

    @model_validator(mode='before')
    @classmethod
    def recover_lat_lon_from_tile_id(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values
            
        lat = values.get("latitude")
        tile_id = values.get("discovery_tile_id")
        
        # If lat/lon missing but tile_id present (format: lat_lon_phrase)
        if (lat is None or lat == "") and tile_id:
            try:
                parts = str(tile_id).split("_")
                if len(parts) >= 2:
                    values["latitude"] = float(parts[0])
                    values["longitude"] = float(parts[1])
            except (ValueError, TypeError):
                pass
        return values

    @model_validator(mode='before')
    @classmethod
    def sanitize_identity(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values
            
        # Cleanup leading slashes in company_hash (found in legacy-recovery data)
        company_hash = values.get("company_hash")
        if company_hash and isinstance(company_hash, str) and company_hash.startswith("/"):
            values["company_hash"] = company_hash.lstrip("/")
            
        return values

    @model_validator(mode='before')
    @classmethod
    def hydrate_address_components(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values
            
        full_addr = values.get("full_address")
        if full_addr and not values.get("street_address"):
            from ....core.text_utils import parse_address_components
            addr_data = parse_address_components(full_addr)
            for key, val in addr_data.items():
                if val and not values.get(key):
                    values[key] = val
        return values

    @model_validator(mode='before')
    @classmethod
    def clean_empty_values(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(values, dict):
            return values
            
        nullable_fields = [
            'reviews_count', 'average_rating', 'latitude', 'longitude', 
            'version', 'slug', 'company_hash'
        ]
        for field in nullable_fields:
            if values.get(field) == '':
                values[field] = None
        return values

    def to_usv(self) -> str:
        """
        STRICT CANONICAL SERIALIZATION: Ensures field order matches datapackage.json.
        """
        from cocli.core.constants import UNIT_SEP
        field_names = list(self.__class__.model_fields.keys())
        dump = self.model_dump(by_alias=False)
        
        values = []
        for field in field_names:
            val = dump.get(field)
            if val is None:
                values.append("")
            elif isinstance(val, datetime):
                values.append(val.isoformat())
            else:
                # Sanitize newlines and separators
                s_val = str(val).replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>").replace(UNIT_SEP, " ")
                values.append(s_val)
        
        return UNIT_SEP.join(values) + "\n"

    @classmethod
    def get_datapackage_fields(cls) -> List[Dict[str, Any]]:
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
                
            f_def: Dict[str, Any] = {
                "name": name,
                "type": field_type,
                "description": field.description or ""
            }
            
            # Explicitly flag deprecated fields for Frictionless consumers
            if "DEPRECATED" in (field.description or ""):
                f_def["deprecated"] = True
                
            fields.append(f_def)
        return fields

    def save_enrichment(self) -> Path:
        """Saves this place data to the company's enrichment directory."""
        from ....core.paths import paths
        if not self.slug:
            raise ValueError("Cannot save enrichment without slug")
            
        enrichment_dir = paths.companies.entry(self.slug).path / "enrichments"
        enrichment_dir.mkdir(parents=True, exist_ok=True)
        
        # Save Datapackage for the enrichment
        self.save_datapackage(enrichment_dir, resource_name="google_maps", resource_path="google_maps.usv")
        
        usv_path = enrichment_dir / "google_maps.usv"
        # We overwrite the enrichment file with the latest scrape data
        with open(usv_path, "w", encoding="utf-8") as f:
            from cocli.utils.usv_utils import USVWriter
            writer = USVWriter(f)
            writer.writerow(list(self.model_fields.keys()))
            f.write(self.to_usv())
            
        return usv_path
