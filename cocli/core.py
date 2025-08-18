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
        cocli_base_dir = Path(os.environ["COCLI_DATA_HOME"]).expanduser()
    elif "XDG_DATA_HOME" in os.environ:
        cocli_base_dir = Path(os.environ["XDG_DATA_HOME"]).expanduser() / "cocli"
    else:
        # Default location based on OS
        if platform.system() == "Windows":
            cocli_base_dir = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "cocli"
        elif platform.system() == "Darwin": # macOS
            cocli_base_dir = Path.home() / "Library" / "Application Support" / "cocli"
        else: # Linux and other Unix-like
            cocli_base_dir = Path.home() / ".local" / "share" / "cocli"

    cocli_base_dir.mkdir(parents=True, exist_ok=True)
    return cocli_base_dir

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
    companies_dir = get_cocli_base_dir() / "companies"
    companies_dir.mkdir(parents=True, exist_ok=True)
    return companies_dir

def get_people_dir() -> Path:
    people_dir = get_cocli_base_dir() / "people"
    people_dir.mkdir(parents=True, exist_ok=True)
    return people_dir

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


# --- Core Logic (Shared Component) ---

def slugify(text: str) -> str:
    """Converts text to a filesystem-friendly slug."""
    text = text.lower()
    text = re.sub(r'[\s\W]+', '-', text)
    return text.strip('-')

def create_company_files(company_name: str, company_dir: Path) -> Path:
    """
    Creates the directory and files for a new company.
    """
    company_dir.mkdir(parents=True, exist_ok=True)
    (company_dir / "contacts").mkdir(exist_ok=True)
    (company_dir / "meetings").mkdir(exist_ok=True)

    index_path = company_dir / "_index.md"
    if not index_path.exists():
        index_path.write_text(f"---\nname: {company_name}\n---\n\n# {company_name}\n")
    return company_dir

def create_person_files(person_name: str, person_dir: Path, company_name: str) -> Path:
    """
    Creates the markdown file for a new person.
    """
    person_dir.mkdir(parents=True, exist_ok=True)
    person_file = person_dir / f"{slugify(person_name)}.md"
    if not person_file.exists():
        content = f"# {person_name}\n\n- **Company:** {company_name}\n"
        person_file.write_text(content)
    return person_file
