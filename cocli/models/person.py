from pathlib import Path
from typing import Any, Optional, Iterator
import logging

import yaml
from pydantic import BaseModel, Field, ValidationError, EmailStr

from ..core.config import get_people_dir

logger = logging.getLogger(__name__)

class Person(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, pattern=r"^\+?(?:\d{1,3})?[\s.-]*(?:\(\d{1,4}\))?[\s.-]*\d{1,14}(?:[\s.-]*\d+)*(?:\s*(?:ext|x|Ext|X|\#)\.?\s*\d{1,5})?$")
    company_name: Optional[str] = None  # Added to link person to company
    role: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    slug: str # Changed from Optional[str] to str

    full_address: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None

    @classmethod
    def get_all(cls) -> Iterator["Person"]:
        """Iterates through all person directories and yields Person objects."""
        people_dir = get_people_dir()
        for person_dir in sorted(people_dir.iterdir()):
            if person_dir.is_dir():
                person = cls.from_directory(person_dir)
                if person:
                    yield person

    @classmethod
    def get(cls, slug: str) -> Optional["Person"]:
        """Retrieves a single person by their slug."""
        people_dir = get_people_dir()
        person_dir = people_dir / slug
        if person_dir.is_dir():
            return cls.from_directory(person_dir)
        return None

    @classmethod
    def from_directory(cls, person_dir: Path) -> Optional["Person"]:
        # This method needs to be updated to pass the slug to from_file
        for person_file in person_dir.glob("*.md"):
            return cls.from_file(person_file, person_dir.name) # Pass slug here
        return None

    @classmethod
    def from_file(cls, person_file: Path, slug: str) -> Optional["Person"]:
        if not person_file.exists():
            return None

        content = person_file.read_text()
        frontmatter_data: dict[str, Any] = {}

        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, _ = content.split("---", 2)[1:]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError:
                pass  # Ignore YAML errors for now, return what we have

        # Set the slug from the directory name
        frontmatter_data["slug"] = slug

        try:
            return cls(**frontmatter_data)
        except ValidationError as e:
            logger.warning(f"Validation error loading person from {person_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading person from {person_file}: {e}")
            return None
