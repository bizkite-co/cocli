import os
import re
from pathlib import Path
from typing import Optional, List, Any
import platform

import yaml
from pydantic import BaseModel, Field, BeforeValidator
from typing_extensions import Annotated

# --- Configuration ---

def get_cocli_base_dir() -> Path:
    """
    Determines the root data directory for cocli, respecting environment variables.
    Order of precedence: COCLI_DATA_HOME > XDG_DATA_HOME > default.
    """
    if "COCLI_DATA_HOME" in os.environ:
        return Path(os.environ["COCLI_DATA_HOME"]).expanduser()
    elif "XDG_DATA_HOME" in os.environ:
        return Path(os.environ["XDG_DATA_HOME"]).expanduser() / "cocli"
    else:
        # Default location based on OS
        if platform.system() == "Windows":
            return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "cocli"
        elif platform.system() == "Darwin": # macOS
            return Path.home() / "Library" / "Application Support" / "cocli"
        else: # Linux and other Unix-like
            return Path.home() / ".local" / "share" / "cocli"

def get_config_dir() -> Path:
    """
    Determines the configuration directory for cocli.
    """
    if "COCLI_CONFIG_HOME" in os.environ:
        return Path(os.environ["COCLI_CONFIG_HOME"]).expanduser()
    elif "XDG_CONFIG_HOME" in os.environ:
        return Path(os.environ["XDG_CONFIG_HOME"]).expanduser() / "cocli"
    else:
        # Default location based on OS
        if platform.system() == "Windows":
            return Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "cocli"
        elif platform.system() == "Darwin": # macOS
            return Path.home() / "Library" / "Preferences" / "cocli"
        else: # Linux and other Unix-like
            return Path.home() / ".config" / "cocli"

def get_companies_dir() -> Path:
    return get_cocli_base_dir() / "companies"

def get_people_dir() -> Path:
    return get_cocli_base_dir() / "people"

class ScraperSettings(BaseModel):
    google_maps_delay_seconds: int = Field(20, description="Delay in seconds between page scrolls/requests for Google Maps scraper.")
    google_maps_max_pages: int = Field(3, description="Maximum number of pages/scrolls to fetch for Google Maps scraper.")

def load_scraper_settings() -> ScraperSettings:
    """
    Loads scraper settings from cocli_config.yml.
    """
    config_dir = get_config_dir()
    config_file = config_dir / "cocli_config.yml"

    if not config_file.exists():
        print(f"Warning: Config file not found at {config_file}. Using default scraper settings.")
        return ScraperSettings()

    try:
        with config_file.open('r', encoding='utf-8') as f:
            config_data = yaml.safe_load(f)
            if config_data and "scraper" in config_data:
                return ScraperSettings(**config_data["scraper"])
            else:
                print(f"Warning: 'scraper' section not found in {config_file}. Using default scraper settings.")
                return ScraperSettings()
    except Exception as e:
        print(f"Error loading config file {config_file}: {e}. Using default scraper settings.")
        return ScraperSettings()

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
    # Use the getter function to ensure dynamic path resolution
    current_companies_dir = get_companies_dir()
    company_slug = slugify(company.name)
    company_dir = current_companies_dir / company_slug
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
    # Use the getter function to ensure dynamic path resolution
    current_people_dir = get_people_dir()
    person_slug = slugify(person.name)
    person_file = current_people_dir / f"{person_slug}.md"

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
