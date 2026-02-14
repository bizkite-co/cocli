import re
from pathlib import Path
from typing import Optional, List, Any, Iterator, Dict
import logging
from datetime import datetime, UTC

import yaml
from pydantic import BaseModel, Field, BeforeValidator, ValidationError, model_validator
from typing_extensions import Annotated

from .email_address import EmailAddress
from .phone import OptionalPhone
from .email import EmailEntry
from .place_id import PlaceID
from .company_slug import CompanySlug
from ..core.config import get_companies_dir, get_campaign

logger = logging.getLogger(__name__)

def split_categories(v: Any) -> List[str]:
    if isinstance(v, str):
        return [cat.strip() for cat in v.split(';') if cat.strip()]
    if isinstance(v, list):
        return [cat.strip() for item in v for cat in item.split(';') if cat.strip()]
    return []

class Company(BaseModel):
    name: str
    domain: Optional[str] = None
    type: str = "N/A"
    tags: list[str] = Field(default_factory=list)
    slug: CompanySlug 
    company_hash: Optional[str] = None
    description: Optional[str] = None
    visits_per_day: Optional[int] = None

    # New fields for enrichment
    # id: Optional[str] = None # Removed as per feedback
    keywords: List[str] = Field(default_factory=list)
    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None

    phone_1: OptionalPhone = None
    phone_number: OptionalPhone = None
    phone_from_website: OptionalPhone = None
    email: Optional[EmailAddress] = None
    website_url: Optional[str] = None
    all_emails: List[EmailAddress] = Field(default_factory=list)
    email_contexts: Dict[str, str] = Field(default_factory=dict)
    tech_stack: List[str] = Field(default_factory=list)

    categories: Annotated[List[str], BeforeValidator(split_categories)] = Field(default_factory=list)

    reviews_count: Optional[int] = None
    average_rating: Optional[float] = None
    business_status: Optional[str] = None
    hours: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    about_us_url: Optional[str] = None
    contact_url: Optional[str] = None
    
    services: List[str] = Field(default_factory=list)
    products: List[str] = Field(default_factory=list)

    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    place_id: Optional[PlaceID] = None
    last_enriched: Optional[datetime] = None
    enrichment_ttl_days: int = 30
    processed_by: Optional[str] = "local-worker"

    @property
    def gmb_url(self) -> Optional[str]:
        """Constructs a Google Maps search URL from the place_id."""
        if self.place_id:
            return f"https://www.google.com/maps/search/?api=1&query=google&query_place_id={self.place_id}"
        return None

    @model_validator(mode='after')
    def populate_identifiers(self) -> 'Company':
        if not self.company_hash and self.name:
            from cocli.core.text_utils import calculate_company_hash
            self.company_hash = calculate_company_hash(self.name, self.street_address, self.zip_code)
        return self

    @model_validator(mode='after')
    def parse_full_address(self) -> 'Company':
        if self.full_address and (not self.city or not self.state or not self.zip_code):
            # Regex to capture city, state, and zip from a standard US address
            match = re.search(r"([^,]+),\s*([A-Z]{2})\s*(\d{5}(?:-\d{4})?)", self.full_address)
            if match:
                city, state, zip_code = match.groups()
                if not self.city:
                    self.city = city.strip()
                if not self.state:
                    self.state = state.strip()
                if not self.zip_code:
                    self.zip_code = zip_code.strip()
        return self

    @classmethod
    def get_all(cls) -> Iterator["Company"]:
        """Iterates through all company directories and yields Company objects."""
        companies_dir = get_companies_dir()
        for company_dir in sorted(companies_dir.iterdir()):
            if company_dir.is_dir():
                company = cls.from_directory(company_dir)
                if company:
                    logger.debug(f"Yielding company with slug: {company.slug}") # Debug print
                    yield company

    @classmethod
    def get(cls, slug: str) -> Optional["Company"]:
        """Retrieves a single company by its slug."""
        companies_dir = get_companies_dir()
        company_dir = companies_dir / slug
        if company_dir.is_dir():
            return cls.from_directory(company_dir)
        return None

    @classmethod
    def from_directory(cls, company_dir: Path) -> Optional["Company"]:
        logger = logging.getLogger(__name__)
        # logger.debug(f"Starting from_directory for {company_dir}")
        try:
            index_path = company_dir / "_index.md"
            tags_path = company_dir / "tags.lst"

            if not index_path.exists():
                logger.warning(f"Skipping {company_dir.name}: _index.md not found.") # More explicit message
                return None

            # logger.info(f"Start reading indexes: {index_path}")
            content = index_path.read_text()
            # logger.info(f"Finished reading indexes: {index_path}")
            frontmatter_data: dict[str, Any] = {}
            markdown_content = ""

            if content.startswith("---") and "---" in content[3:]:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    frontmatter_str = parts[1]
                    markdown_content = parts[2]
                    try:
                        frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                    except yaml.YAMLError as e: # Catch YAML errors specifically
                        logger.warning(f"Skipping {company_dir.name}: YAML error in _index.md: {e}")
                        return None

            # Load tags from tags.lst (Source of Truth)
            tags = []
            if tags_path.exists():
                tags = [t.strip() for t in tags_path.read_text().strip().split('\n') if t.strip()]
            
            # If tags.lst was missing/empty, fall back to YAML tags
            if not tags and "tags" in frontmatter_data:
                tags = frontmatter_data["tags"]
                if isinstance(tags, str):
                    tags = [tags]

            # --- RESILIENCE: Filter anomalous emails from frontmatter before loading ---
            from cocli.core.text_utils import is_valid_email
            if "email" in frontmatter_data and frontmatter_data["email"]:
                email_val = str(frontmatter_data["email"]).strip()
                if not is_valid_email(email_val) or email_val.startswith('[') or email_val == 'None' or email_val == 'null':
                    frontmatter_data["email"] = None
            
            if "all_emails" in frontmatter_data and isinstance(frontmatter_data["all_emails"], list):
                cleaned_emails = []
                for email_val in frontmatter_data["all_emails"]:
                    if isinstance(email_val, str):
                        e_str = email_val.strip()
                        if is_valid_email(e_str) and not e_str.startswith('['):
                            cleaned_emails.append(e_str)
                    elif isinstance(email_val, list) and len(email_val) > 0 and isinstance(email_val[0], str):
                        # Handle legacy list-in-list
                        e_str = email_val[0].strip()
                        if is_valid_email(e_str):
                            cleaned_emails.append(e_str)
                frontmatter_data["all_emails"] = cleaned_emails
            # --------------------------------------------------------------------------

            # Prepare data for model instantiation
            model_data = frontmatter_data
            model_data["tags"] = tags
            model_data["slug"] = company_dir.name
            if "description" not in model_data or model_data["description"] is None:
                 model_data["description"] = markdown_content.strip()

            # Ensure name is present
            if "name" not in model_data:
                model_data["name"] = company_dir.name

            # Ensure place_id is correctly mapped from frontmatter if it exists
            if "place_id" in frontmatter_data:
                model_data["place_id"] = frontmatter_data["place_id"]

            try:
                return cls(**model_data)
            except ValidationError as e:
                logging.error(f"Skipping {company_dir.name}: Validation error loading company: {e}") # More explicit message
                return None
            except Exception as e:
                logging.error(f"Skipping {company_dir.name}: Unexpected error loading company: {e}") # More explicit message
                return None
        except Exception as e:
            logging.error(f"Error in from_directory for {company_dir}: {e}")
            raise Exception("from_directory") from e

    def merge_with(self, other: 'Company') -> None:
        """Merges data from another company instance into this one."""
        # Special handling for name: only overwrite if current name looks like a slug/domain
        # and new name looks more like a real name.
        if other.name and other.name != self.name:
            # If current name is just the slug/domain, and other name is different, use other name
            if self.name == self.slug or (self.domain and self.name == self.domain):
                self.name = other.name

        # Simple fields: only overwrite if this one is empty or None
        for field in [
            "domain", "description", "visits_per_day", "full_address", 
            "street_address", "city", "zip_code", "state", "country", "timezone",
            "phone_1", "phone_number", "phone_from_website", "email", "website_url",
            "reviews_count", "average_rating", "business_status", "hours",
            "latitude", "longitude",
            "facebook_url", "linkedin_url", "instagram_url", "twitter_url", 
            "youtube_url", "about_us_url", "contact_url", "meta_description", 
            "meta_keywords", "place_id", "last_enriched", "processed_by"
        ]:
            new_val = getattr(other, field)
            current_val = getattr(self, field)
            if new_val is not None and (current_val is None or current_val == '' or current_val == 'N/A'):
                setattr(self, field, new_val)
        
        # List fields: merge unique values
        for field in ["tags", "all_emails", "tech_stack", "categories", "services", "products", "keywords"]:
            existing = getattr(self, field) or []
            new_vals = getattr(other, field) or []
            # Use a list comprehension to preserve order while ensuring uniqueness
            merged = list(existing)
            for val in new_vals:
                if val and val not in merged:
                    merged.append(val)
            setattr(self, field, merged)
        
        # Dict fields: merge keys
        if other.email_contexts:
            if self.email_contexts is None:
                self.email_contexts = {}
            self.email_contexts.update(other.email_contexts)

    def save(self, email_sync: bool = True, base_dir: Optional[Path] = None) -> None:
        """Saves the company data to _index.md and tags to tags.lst."""
        companies_dir = base_dir or get_companies_dir()
        company_dir = companies_dir / self.slug
        company_dir.mkdir(parents=True, exist_ok=True)
        
        index_path = company_dir / "_index.md"
        tags_path = company_dir / "tags.lst"
        
        # 1. Update tags.lst (Primary Source of Truth)
        if self.tags:
            unique_tags = sorted(list(set([t.strip() for t in self.tags if t.strip()])))
            tags_path.write_text("\n".join(unique_tags) + "\n")
            # Ensure model tags match the cleaned list
            self.tags = unique_tags

        # 2. Update YAML index (keeping tags in YAML for reporting speed)
        # We don't want to save the description twice (YAML and Markdown body)
        data = self.model_dump(mode="json", exclude_none=True)
        description = data.pop("description", "")
        
        with open(index_path, 'w') as f:
            f.write("---\n")
            yaml.safe_dump(data, f, sort_keys=False)
            f.write("---\n")
            if description:
                f.write(f"\n{description}\n")
        
        logger.debug(f"Saved company: {self.slug}")

        # 3. Sync with Email Index (if a campaign is active)
        if email_sync:
            from ..core.email_index_manager import EmailIndexManager
            campaign_name = get_campaign()
            if campaign_name:
                try:
                    index_manager = EmailIndexManager(campaign_name)
                    # Collect all unique emails
                    emails_to_sync = set()
                    if self.email:
                        emails_to_sync.add(self.email)
                    if self.all_emails:
                        for e in self.all_emails:
                            emails_to_sync.add(e)
                    
                    for email_str in emails_to_sync:
                        entry = EmailEntry(
                            email=email_str,
                            domain=self.domain or "unknown",
                            company_slug=self.slug,
                            source="company_save",
                            found_at=datetime.now(UTC),
                            tags=self.tags
                        )
                        index_manager.add_email(entry)
                except Exception as e:
                    logger.error(f"Error syncing emails to index for {self.slug}: {e}")
