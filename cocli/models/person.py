from pathlib import Path
from typing import Any, Optional, Iterator
from datetime import datetime, UTC
import logging

import yaml
from pydantic import BaseModel, Field, ValidationError
from .email_address import EmailAddress
from .phone import OptionalPhone
from .email import EmailEntry
from ..core.config import get_people_dir, get_campaign
from ..core.email_index_manager import EmailIndexManager

logger = logging.getLogger(__name__)

class Person(BaseModel):
    name: str
    email: Optional[EmailAddress] = None
    phone: OptionalPhone = None
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
        """Loads a person from a directory by looking for the first .md file."""
        for person_file in person_dir.glob("*.md"):
            # Use the directory name as the slug
            return cls.from_file(person_file, person_dir.name)
        return None

    @classmethod
    def from_file(cls, person_file: Path, slug: str) -> Optional["Person"]:
        if not person_file.exists():
            return None

        content = person_file.read_text()
        frontmatter_data: dict[str, Any] = {}

        if content.startswith("---") and "---" in content[3:]:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_str = parts[1]
                try:
                    frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                except yaml.YAMLError:
                    pass

        # Set the slug from the directory name
        frontmatter_data["slug"] = slug

        try:
            person = cls(**frontmatter_data)
            return person
        except ValidationError as e:
            logger.warning(f"Validation error loading person from {person_file}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading person from {person_file}: {e}")
            return None

    def save(self, person_file: Optional[Path] = None, base_dir: Optional[Path] = None) -> None:
        """Saves the person data to a markdown file and syncs with email index."""
        if not person_file:
            people_dir = base_dir or get_people_dir()
            person_dir = people_dir / self.slug
            person_dir.mkdir(parents=True, exist_ok=True)
            from ..core.text_utils import slugify
            person_file = person_dir / f"{slugify(self.name)}.md"

        # We don't want to save the description/content in YAML if it's large
        data = self.model_dump(exclude_none=True)
        
        # Determine if we should preserve existing markdown content
        markdown_content = f"\n# {self.name}\n"
        if person_file.exists():
            content = person_file.read_text()
            if "---" in content:
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    markdown_content = parts[2]

        with open(person_file, 'w') as f:
            f.write("---\n")
            yaml.safe_dump(data, f, sort_keys=False)
            f.write("---\n")
            f.write(markdown_content)
        
        # Sync with Email Index
        campaign_name = get_campaign()
        if campaign_name and self.email:
            try:
                index_manager = EmailIndexManager(campaign_name)
                entry = EmailEntry(
                    email=self.email,
                    domain=self.email.split("@")[-1] if "@" in self.email else "unknown",
                    company_slug=None, 
                    source="person_save",
                    found_at=datetime.now(UTC),
                    tags=self.tags
                )
                index_manager.add_email(entry)
            except Exception as e:
                logger.error(f"Error syncing email for person {self.name} to index: {e}")