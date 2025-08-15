import os
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

# --- Configuration ---
# Adhere to the XDG Base Directory Specification.
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME", "~/.local/share")).expanduser()
COCLI_DIR = DATA_HOME / "cocli"
COMPANIES_DIR = COCLI_DIR / "companies"
PEOPLE_DIR = COCLI_DIR / "people"

# --- Data Models ---

class Company(BaseModel):
    name: str
    domain: Optional[str] = None
    type: str = "N/A"
    tags: list[str] = Field(default_factory=list)

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
    Creates the directory and files for a new company.
    Writes YAML frontmatter to the _index.md file.
    Returns the path to the new company directory.
    """
    company_slug = slugify(company.name)
    company_dir = COMPANIES_DIR / company_slug

    if not company_dir.exists():
        print(f"Creating new company: {company.name}")
        (company_dir / "contacts").mkdir(parents=True, exist_ok=True)
        (company_dir / "meetings").mkdir(parents=True, exist_ok=True)

        index_path = company_dir / "_index.md"
        
        # Create YAML frontmatter
        frontmatter = yaml.dump(company.dict(exclude_none=True), sort_keys=False)
        
        # Write the file with frontmatter and a title
        index_path.write_text(f"---\n{frontmatter}---\n\n# {company.name}\n")

        # Create the tags file
        if company.tags:
            tags_path = company_dir / "tags.lst"
            tags_path.write_text("\n".join(company.tags) + "\n")
    else:
        print(f"Company '{company.name}' already exists.")
        
    return company_dir

# Ensure base directories exist when this module is loaded
COMPANIES_DIR.mkdir(parents=True, exist_ok=True)
PEOPLE_DIR.mkdir(parents=True, exist_ok=True)
