from pydantic import Field, model_validator
from typing import Optional, Dict, Any, Annotated, List, ClassVar
from datetime import datetime, UTC
from pathlib import Path
import logging

from .google_maps_idx import GoogleMapsIdx
from .google_maps_raw import GoogleMapsRawResult
from ...phone import OptionalPhone

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
    INDEX_NAME: ClassVar[str] = "google_maps_prospects"

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
    email: Optional[str] = Field(None, description="DEPRECATED: Google Maps does not provide email. Use website enrichment instead.")
    
    # --- Resource Discovery Extension ---
    is_value_resource: Optional[bool] = None
    fee_category: Optional[str] = None
    rationale: Optional[str] = None

    def merge_with_existing(self, existing: "GoogleMapsProspect") -> "GoogleMapsProspect":
        """
        Merges this (newly scraped) prospect with an existing one.
        Mandate: Only overwrite fields if the new value is NOT null/empty.
        """
        new_data = self.model_dump(exclude_unset=True)
        existing_data = existing.model_dump()
        
        merged_data = existing_data.copy()
        for key, val in new_data.items():
            # Only overwrite if new value is non-null and non-empty string
            if val is not None and val != "":
                merged_data[key] = val
        
        # Ensure updated_at is refreshed
        merged_data["updated_at"] = datetime.now(UTC)
        
        return self.__class__(**merged_data)

    @classmethod
    def get_by_place_id(cls, campaign_name: str, place_id: str) -> Optional["GoogleMapsProspect"]:
        """
        Attempts to find an existing prospect in the campaign index by Place ID.
        """
        from cocli.core.prospects_csv_manager import ProspectsIndexManager
        manager = ProspectsIndexManager(campaign_name)
        # Use DuckDB for fast lookup in checkpoint + WAL shards
        import duckdb
        con = duckdb.connect(database=':memory:')
        
        checkpoint = manager.index_dir / "prospects.checkpoint.usv"
        if not checkpoint.exists():
            return None
            
        try:
            # We only need to check the checkpoint for now as a baseline
            # In a full cluster, we might check local WAL shards too
            q = f"SELECT * FROM read_csv('{checkpoint}', delim='\x1f', header=False, auto_detect=True, all_varchar=True) WHERE column1 = '{place_id}' LIMIT 1"
            res = con.execute(q).df()
            if not res.empty:
                # USV columns are 1-indexed in DuckDB result here
                # Better to use USVDictReader for robustness if performance allows
                from cocli.utils.usv_utils import USVDictReader
                with open(checkpoint, "r", encoding="utf-8") as f:
                    reader = USVDictReader(f)
                    for r in reader:
                        if r.get("place_id") == place_id:
                            return cls.model_validate(r)
        except Exception:
            pass
        return None
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

    @classmethod
    def save_datapackage(cls, path: Path, resource_name: str = "google_maps_prospects", resource_path: str = "prospects.checkpoint.usv", force: bool = False, wasi_hash: Optional[str] = None) -> None:
        """Saves the datapackage.json to the specified directory."""
        super().save_datapackage(path, resource_name, resource_path, force=force, wasi_hash=wasi_hash)

    @classmethod
    def from_raw(cls, raw: GoogleMapsRawResult) -> "GoogleMapsProspect":
        from cocli.core.text_utils import slugify
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
            "processed_by": raw.processed_by or "local-worker",
            "list_found_at": raw.created_at,
            "details_found_at": raw.updated_at,
            "is_value_resource": raw.is_value_resource,
            "fee_category": raw.fee_category,
            "rationale": raw.rationale
        }
        
        if data["name"]:
            name_str = str(data["name"])
            data["company_slug"] = slugify(name_str)
            
        return cls(**data) # type: ignore

    @model_validator(mode='after')
    def extract_domain(self) -> 'GoogleMapsProspect':
        if self.website and not self.domain:
            from ....core.text_utils import extract_domain
            self.domain = extract_domain(self.website)
        return self

    @model_validator(mode='after')
    def validate_identity_tripod(self) -> 'GoogleMapsProspect':
        from cocli.core.text_utils import slugify, calculate_company_hash
        
        if not self.company_slug and self.name:
            self.company_slug = slugify(self.name)
            
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
            'version', 'company_slug', 'company_hash'
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
    def append_to_checkpoint(cls, campaign_name: str, prospect: "GoogleMapsProspect") -> None:
        """Appends a prospect to the campaign's main checkpoint USV."""
        from ....core.paths import paths
        checkpoint_path = paths.campaign(campaign_name).index(cls.INDEX_NAME).checkpoint
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(checkpoint_path, "a", encoding="utf-8") as f:
            f.write(prospect.to_usv())

    def save_enrichment(self) -> Path:
        """Saves this prospect data to the company's enrichment directory."""
        from ....core.paths import paths
        if not self.company_slug:
            raise ValueError("Cannot save enrichment without company_slug")
            
        enrichment_dir = paths.companies.entry(self.company_slug).path / "enrichments"
        enrichment_dir.mkdir(parents=True, exist_ok=True)
        
        # Save Datapackage for the enrichment
        self.save_datapackage(enrichment_dir, resource_name="google_maps", resource_path="google_maps.usv")
        
        usv_path = enrichment_dir / "google_maps.usv"
        # We overwrite the enrichment file with the latest scrape data
        with open(usv_path, "w", encoding="utf-8") as f:
            # We add a header to the enrichment USV for easy manual inspection, 
            # though our internal readers will skip it if they see 'created_at'.
            from cocli.utils.usv_utils import USVWriter
            writer = USVWriter(f)
            writer.writerow(list(self.model_fields.keys()))
            f.write(self.to_usv())
            
        return usv_path

    