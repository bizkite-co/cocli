import re
from pathlib import Path
from typing import Optional, List, Any

import yaml
from pydantic import BaseModel, Field, BeforeValidator, ValidationError # Import ValidationError
from typing_extensions import Annotated

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


    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None

    @classmethod
    def from_directory(cls, company_dir: Path) -> Optional["Company"]:
        index_path = company_dir / "_index.md"
        tags_path = company_dir / "tags.lst"

        if not index_path.exists():

            return None

        content = index_path.read_text()
        frontmatter_data = {}
        markdown_content = ""

        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, markdown_content = content.split("---", 2)[1:]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError:
                pass # Ignore YAML errors for now, return what we have

        # Add name from directory if not in frontmatter
        if "name" not in frontmatter_data:
            frontmatter_data["name"] = company_dir.name.replace("-", " ").title()

        # Add tags
        tags = []
        if tags_path.exists():
            tags = tags_path.read_text().strip().splitlines()
        frontmatter_data["tags"] = tags

        try:
            return cls(**frontmatter_data)
        except ValidationError as e:
            print(f"Warning: Validation error loading company from {company_dir}: {e}")
            return None
        except Exception as e:
            print(f"Warning: Unexpected error loading company from {company_dir}: {e}")
            return None


class Person(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None # Added to link person to company

    @classmethod
    def from_directory(cls, person_file: Path) -> Optional["Person"]:
        if not person_file.exists() or not person_file.suffix == ".md":
            return None