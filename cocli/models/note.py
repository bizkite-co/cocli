from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import yaml
from pydantic import BaseModel, Field, ValidationError
import logging

logger = logging.getLogger(__name__)

class Note(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    title: str
    content: str

    @classmethod
    def from_file(cls, note_path: Path) -> Optional["Note"]:
        if not note_path.exists():
            return None

        content = note_path.read_text()
        frontmatter_data: dict[str, Any] = {}
        markdown_content = ""

        if content.startswith("---") and "---" in content[3:]:
            frontmatter_str, markdown_content = content.split("---", 2)[1:]
            try:
                frontmatter_data = yaml.safe_load(frontmatter_str) or {}
            except yaml.YAMLError as e:
                logger.warning(f"Error parsing YAML frontmatter in {note_path}: {e}")
                return None
        else:
            markdown_content = content

        # Extract title from filename if not in frontmatter
        title = frontmatter_data.get("title")
        if not title:
            # Attempt to extract title from filename (e.g., 2025-10-19T17:07:03Z-my-note.md)
            name_parts = note_path.stem.split('-', 6) # Split by up to 6 hyphens for timestamp
            if len(name_parts) > 6: # If it has a timestamp prefix
                title = "-".join(name_parts[6:])
            else:
                title = note_path.stem # Fallback to full stem
            title = title.replace('-', ' ').title()

        # Extract timestamp from filename if not in frontmatter
        timestamp_str = frontmatter_data.get("timestamp")
        if not timestamp_str:
            try:
                # Filename format: YYYY-MM-DDTHH-MM-SSZ-title.md
                timestamp_part = "-".join(note_path.stem.split('-')[:6])
                timestamp = datetime.strptime(timestamp_part, "%Y-%m-%dT%H-%M-%SZ")
            except ValueError:
                timestamp = datetime.utcfromtimestamp(note_path.stat().st_mtime) # Fallback to file modification time
        else:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                timestamp = datetime.utcfromtimestamp(note_path.stat().st_mtime)

        try:
            return cls(
                timestamp=timestamp,
                title=title,
                content=markdown_content.strip()
            )
        except ValidationError as e:
            logger.error(f"Validation error loading note from {note_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading note from {note_path}: {e}")
            return None

    def to_file(self, notes_dir: Path):
        # Ensure notes_dir exists
        notes_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename: YYYY-MM-DDTHH-MM-SSZ-slugified-title.md
        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        slugified_title = self.title.lower().replace(' ', '-').replace('/', '-')
        filename = f"{timestamp_str}-{slugified_title}.md"
        note_path = notes_dir / filename

        # Prepare frontmatter
        frontmatter_data = {
            "timestamp": self.timestamp.isoformat(timespec='seconds') + 'Z',
            "title": self.title,
        }
        frontmatter = yaml.dump(frontmatter_data, sort_keys=False, default_flow_style=False, allow_unicode=True)

        # Construct file content
        file_content = f"---\n{frontmatter}---\n{self.content.strip()}\n"

        note_path.write_text(file_content)
        return note_path
