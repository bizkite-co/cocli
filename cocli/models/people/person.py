from __future__ import annotations
from pathlib import Path
from typing import Any, Optional, Iterator
from datetime import datetime, UTC
import logging

import yaml
from pydantic import BaseModel, Field, ValidationError
from ..email_address import EmailAddress
from ..phone import OptionalPhone
from ..company_name import OptionalCompanyName
from ..company_address import OptionalCompanyAddress
from ..campaigns.indexes.email import EmailEntry
from ...core.paths import paths
from ...core.ordinant import CollectionName
from ...core.config import get_campaign
from ...core.email_index_manager import EmailIndexManager

logger = logging.getLogger(__name__)


def _read_person_frontmatter(person_file: Path) -> Optional[dict[str, Any]]:
    """Return the current markdown mapping, or None when there is no file.

    A YAML error also returns None so a save still writes the file and does
    not journal a bogus full diff.
    """
    if not person_file.exists():
        return None
    try:
        content = person_file.read_text(encoding="utf-8")
    except OSError:
        return None
    if not (content.startswith("---") and "---" in content[3:]):
        return {}
    try:
        loaded = yaml.safe_load(content.split("---", 2)[1])
    except yaml.YAMLError:
        return None
    return loaded if isinstance(loaded, dict) else {}


class Person(BaseModel):
    name: OptionalCompanyName = None
    email: Optional[EmailAddress] = None
    phone: OptionalPhone = None
    company_name: OptionalCompanyName = None  # Added to link person to company
    role: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    slug: str # Changed from Optional[str] to str

    full_address: OptionalCompanyAddress = None
    street_address: OptionalCompanyAddress = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    country: Optional[str] = None

    # A bio/team-page URL for this person at their employer's site (e.g.
    # https://www.higginbotham.com/team/mitchell-gaylord/) - distinct from
    # the company's own website_url, matching Company's "*_url" field
    # naming convention.
    profile_url: Optional[str] = None

    # Same social URL fields as Company, so a person profile can hold the
    # links that today only exist on the company record.
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None

    # --- Ordinant Protocol Implementation ---
    @property
    def collection(self) -> CollectionName:
        from ...core.ordinant import CollectionIdentity
        return CollectionIdentity.PEOPLE


    def get_local_path(self) -> Path:
        """Returns the path to the person directory: data/people/{slug}/"""
        return paths.people.entry(self.slug).path

    def get_file_path(self) -> Optional[Path]:
        """Returns this person's actual .md file (the same one
        from_directory() would read), or None if it doesn't exist yet.
        Callers that re-save an edited Person must pass this as save()'s
        person_file - otherwise save() derives a filename from the
        (possibly just-edited) name and a rename silently leaves two .md
        files behind, with from_directory() reading whichever one its
        glob happens to return first."""
        for person_file in self.get_local_path().glob("*.md"):
            return person_file
        return None

    def get_remote_key(self) -> str:
        """Returns the S3 prefix: people/{slug}/"""
        return f"people/{self.slug}/"

    def get_shard_id(self) -> str:
        """People are currently flat within the global collection."""
        return ""
    # ----------------------------------------

    @classmethod
    def get_all(cls) -> Iterator["Person"]:
        """Iterates through all person directories and yields Person objects."""
        people_dir = paths.people.path
        if not people_dir.exists():
            return
        for person_dir in sorted(people_dir.iterdir()):
            if person_dir.is_dir():
                person = cls.from_directory(person_dir)
                if person:
                    yield person

    @classmethod
    def get(cls, slug: str) -> Optional["Person"]:
        """Retrieves a single person by their slug."""
        entry = paths.people.entry(slug)
        if entry.is_dir():
            return cls.from_directory(entry.path)
        return None

    @classmethod
    def from_directory(cls, person_dir: Path) -> Optional["Person"]:
        """Loads a person from a directory by looking for the first .md file."""
        entry = paths.people.entry(person_dir)
        for person_file in entry.path.glob("*.md"):
            # Use the directory name as the slug
            return cls.from_file(person_file, entry.path.name)
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

        # Peer field datagrams overlay the file the same way company load does.
        # The slug stays the directory name even if a row names another.
        from cocli.core.entity_field_log import apply_field_updates_to_mapping
        from cocli.core.wal import read_updates

        wal_records = read_updates(person_file.parent)
        if wal_records:
            frontmatter_data = apply_field_updates_to_mapping(
                frontmatter_data, wal_records
            )
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

    def save(
        self,
        person_file: Optional[Path] = None,
        base_dir: Optional[Path] = None,
        use_wal: bool = True,
    ) -> None:
        """Saves the person data to a markdown file and syncs with email index.

        ``use_wal`` appends one datagram per changed frontmatter field so
        another machine can overlay it on load. The local file is still
        written. The first save has no previous file, so it does not emit
        a full snapshot. ``use_wal=False`` keeps bulk writers quiet.
        """
        if not person_file:
            if base_dir:
                person_dir = base_dir / self.slug
            else:
                person_dir = paths.people.entry(self.slug).path

            person_dir.mkdir(parents=True, exist_ok=True)
            from ...core.text_utils import slugify
            person_file = person_dir / f"{slugify(str(self.name) if self.name else 'unnamed')}.md"
        else:
            person_dir = person_file.parent

        previous = _read_person_frontmatter(person_file)

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

        if use_wal and previous is not None:
            try:
                from ...core.wal import journal_field_changes

                journal_field_changes(person_dir, previous, data)
            except Exception as exc:
                logger.error("person save journal failed for %s: %s", self.slug, exc)
        
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