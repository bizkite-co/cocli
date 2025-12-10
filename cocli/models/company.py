import re
from pathlib import Path
from typing import Optional, List, Any, Iterator
import logging
from datetime import datetime

import yaml
from pydantic import BaseModel, Field, BeforeValidator, ValidationError, model_validator
from typing_extensions import Annotated

from ..core.config import get_companies_dir

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
    slug: str # Changed from Optional[str] to str
    description: Optional[str] = None
    visits_per_day: Optional[int] = None

    # New fields for enrichment
    # id: Optional[str] = None # Removed as per feedback
    keyword: Optional[str] = None
    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None

    phone_1: Optional[str] = None
    phone_number: Optional[str] = None
    phone_from_website: Optional[str] = None
    email: Optional[str] = None
    website_url: Optional[str] = None

    categories: Annotated[List[str], BeforeValidator(split_categories)] = Field(default_factory=list)

    reviews_count: Optional[int] = None
    average_rating: Optional[float] = None
    business_status: Optional[str] = None
    hours: Optional[str] = None

    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    about_us_url: Optional[str] = None
    contact_url: Optional[str] = None


    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    place_id: Optional[str] = None
    last_enriched: Optional[datetime] = None
    enrichment_ttl_days: int = 30

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
        logger.debug(f"Starting from_directory for {company_dir}")
        try:
            index_path = company_dir / "_index.md"
            tags_path = company_dir / "tags.lst"

            if not index_path.exists():
                logger.warning(f"Skipping {company_dir.name}: _index.md not found.") # More explicit message
                return None

            logger.info(f"Start reading indexes: {index_path}")
            content = index_path.read_text()
            logger.info(f"Finished reading indexes: {index_path}")
            frontmatter_data: dict[str, Any] = {}
            markdown_content = ""

            if content.startswith("---") and "---" in content[3:]:
                frontmatter_str, markdown_content = content.split("---", 2)[1:]
                try:
                    frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                except yaml.YAMLError as e: # Catch YAML errors specifically
                    logger.warning(f"Skipping {company_dir.name}: YAML error in _index.md: {e}")
                    return None

            # Load tags from tags.lst
            tags = []
            if tags_path.exists():
                tags = tags_path.read_text().strip().split('\n')

            # Prepare data for model instantiation
            model_data = frontmatter_data
            model_data["tags"] = tags
            model_data["slug"] = company_dir.name
            if "description" not in model_data or model_data["description"] is None:
                 model_data["description"] = markdown_content.strip()

            # Ensure name is present
            if "name" not in model_data:
                model_data["name"] = company_dir.name

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
