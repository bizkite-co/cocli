import os
import re
from pathlib import Path
from typing import Optional, List, Any

import yaml
from pydantic import BaseModel, Field, BeforeValidator
from typing_extensions import Annotated

# --- Configuration ---
# Adhere to the XDG Base Directory Specification.
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser()
COCLI_DIR = DATA_HOME / "cocli"
COMPANIES_DIR = COCLI_DIR / "companies"
PEOPLE_DIR = COCLI_DIR / "people"

# --- Data Models ---

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
    keyword: Optional[str] = Field(None, alias="Keyword")
    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = Field(None, alias="Zip") # Use alias for CSV column name
    state: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None

    phone_1: Optional[str] = Field(None, alias="Phone_1")
    phone_number: Optional[str] = Field(None, alias="Phone_Standard_format")
    phone_from_website: Optional[str] = Field(None, alias="Phone_From_WEBSITE")
    email: Optional[str] = Field(None, alias="Email_From_WEBSITE")
    website_url: Optional[str] = Field(None, alias="Website")

    categories: Annotated[List[str], BeforeValidator(split_categories)] = Field(default_factory=list)

    reviews_count: Optional[int] = None
    average_rating: Optional[float] = None
    business_status: Optional[str] = Field(None, alias="Business_Status")
    hours: Optional[str] = None

    facebook_url: Optional[str] = Field(None, alias="Facebook_URL")
    linkedin_url: Optional[str] = Field(None, alias="Linkedin_URL")
    instagram_url: Optional[str] = Field(None, alias="Instagram_URL")

    meta_description: Optional[str] = Field(None, alias="Meta_Description")
    meta_keywords: Optional[str] = Field(None, alias="Meta_Keywords")


class Person(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None

# --- Core Logic (Shared Component) ---

def slugify(text: str) -> str:
    """Converts text to a filesystem-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W]+', '-', text)
    return text.strip('-')

def create_company_files(company: Company) -> Path:
    """
    Creates the directory and files for a new company, or updates an existing one.
    Writes YAML frontmatter to the _index.md file.
    Returns the path to the new company directory.
    """
    company_slug = slugify(company.name)
    company_dir = COMPANIES_DIR / company_slug
    index_path = company_dir / "_index.md"
    tags_path = company_dir / "tags.lst"

    existing_data = {}
    existing_tags = set()

    if company_dir.exists():
        print(f"Company '{company.name}' already exists. Updating data...")
        if index_path.exists():
            content = index_path.read_text()
            # Extract YAML frontmatter
            if content.startswith("---") and "---" in content[3:]:
                _, frontmatter_str, _ = content.split("---", 2)
                existing_data = yaml.safe_load(frontmatter_str) or {}

        if tags_path.exists():
            existing_tags.update(tags_path.read_text().splitlines())
    else:
        print(f"Creating new company: {company.name}")
        (company_dir / "contacts").mkdir(parents=True, exist_ok=True)
        (company_dir / "meetings").mkdir(parents=True, exist_ok=True)

    # Merge new company data with existing data
    # Prioritize new data, but keep existing if new is None
    merged_data = company.model_dump(exclude_none=True)
    for key, value in existing_data.items():
        if key not in merged_data or merged_data[key] is None:
            merged_data[key] = value

    # Handle tags separately: add new tags to existing set
    new_tags = set(merged_data.pop("tags", [])) # Remove tags from merged_data for _index.md
    all_tags = sorted(list(existing_tags.union(new_tags)))

    # Create YAML frontmatter from merged data (excluding tags)
    frontmatter = yaml.dump(merged_data, sort_keys=False)

    # Write the _index.md file with frontmatter and a title
    index_path.write_text(f"---\n{frontmatter}---\n\n# {company.name}\n")

    # Write the tags file (only if there are tags)
    if all_tags:
        tags_path.write_text("\n".join(all_tags) + "\n")
    elif tags_path.exists():
        tags_path.unlink() # Remove tags.lst if no tags

    return company_dir

def create_person_files(person: Person) -> Path:
    """
    Creates the markdown file for a new person.
    Returns the path to the new person file.
    """
    person_slug = slugify(person.name)
    person_file = PEOPLE_DIR / f"{person_slug}.md"

    if not person_file.exists():
        print(f"Creating new person: {person.name}")
        content = f"# {person.name}\n\n"
        if person.email:
            content += f"- **Email:** {person.email}\n"
        if person.phone:
            content += f"- **Phone:** {person.phone}\n"
        person_file.write_text(content)
    else:
        print(f"Person '{person.name}' already exists.")

    return person_file

# Ensure base directories exist when this module is loaded
COMPANIES_DIR.mkdir(parents=True, exist_ok=True)
PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
