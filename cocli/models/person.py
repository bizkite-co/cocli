from pathlib import Path
from typing import Optional

from pydantic import BaseModel


import yaml
from pydantic import BaseModel, Field, ValidationError

class Person(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    company_name: Optional[str] = None # Added to link person to company
    tags: list[str] = Field(default_factory=list)

    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None

    @classmethod
    def from_file(cls, person_file: Path) -> Optional["Person"]:
        if not person_file.exists():
            return None

        content = person_file.read_text()
        frontmatter_data = {}

        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, _ = content.split("---", 2)[1:]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError:
                pass # Ignore YAML errors for now, return what we have

        try:
            return cls(**frontmatter_data)
        except ValidationError as e:
            print(f"Warning: Validation error loading person from {person_file}: {e}")
            return None
        except Exception as e:
            print(f"Warning: Unexpected error loading person from {person_file}: {e}")
            return None
