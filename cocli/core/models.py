import re
from pathlib import Path
from typing import Optional, List, Any

import yaml
from pydantic import BaseModel, Field, BeforeValidator
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
    keyword: Optional[str] = Field(None)
    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = Field(None) # Use alias for CSV column name
    state: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None

    phone_1: Optional[str] = Field(None)
    phone_number: Optional[str] = Field(None)
    phone_from_website: Optional[str] = Field(None)
    email: Optional[str] = Field(None)
    website_url: Optional[str] = Field(None)

    categories: Annotated[List[str], BeforeValidator(split_categories)] = Field(default_factory=list)

    reviews_count: Optional[int] = None
    average_rating: Optional[float] = None
    business_status: Optional[str] = Field(None)
    hours: Optional[str] = None

    facebook_url: Optional[str] = Field(None)
    linkedin_url: Optional[str] = Field(None)
    instagram_url: Optional[str] = Field(None)


    meta_description: Optional[str] = Field(None)
    meta_keywords: Optional[str] = Field(None)

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
        except Exception:
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

        content = person_file.read_text()
        name_match = re.search(r"^#\s*(.+)", content, re.MULTILINE)
        email_match = re.search(r"- \*\*Email:\*\* (.+)", content)
        phone_match = re.search(r"- \*\*Phone:\*\* (.+)", content)
        company_match = re.search(r"- \*\*Company:\*\* (.+)", content) # Assuming this format

        name = name_match.group(1).strip() if name_match else person_file.stem.replace("-", " ").title()
        email = email_match.group(1).strip() if email_match else None
        phone = phone_match.group(1).strip() if phone_match else None
        company_name = company_match.group(1).strip() if company_match else None

        return cls(name=name, email=email, phone=phone, company_name=company_name)