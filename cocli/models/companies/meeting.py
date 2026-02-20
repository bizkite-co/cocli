from pathlib import Path
from datetime import datetime, UTC
from typing import Optional, Any
import yaml
from pydantic import BaseModel, Field, ValidationError
import logging

logger = logging.getLogger(__name__)

class Meeting(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    title: str
    type: str = "meeting" # meeting, phone-call, email, etc.
    content: str = ""

    @classmethod
    def from_file(cls, meeting_path: Path) -> Optional["Meeting"]:
        if not meeting_path.exists():
            return None

        content = meeting_path.read_text()
        frontmatter_data: dict[str, Any] = {}
        markdown_content = ""

        if content.startswith("---") and "---" in content[3:]:
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_str = parts[1]
                markdown_content = parts[2]
                try:
                    frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                except yaml.YAMLError as e:
                    logger.warning(f"Error parsing YAML frontmatter in {meeting_path}: {e}")
                    return None
        else:
            markdown_content = content

        # Extract timestamp from frontmatter or filename
        timestamp_str = frontmatter_data.get("timestamp")
        if not timestamp_str:
            try:
                # Expected filename: YYYY-MM-DDTHHMMZ-title.md
                timestamp_part = meeting_path.stem.split('-')[0]
                if 'T' in timestamp_part and timestamp_part.endswith('Z'):
                    timestamp = datetime.strptime(timestamp_part, "%Y-%m-%dT%H%MZ").replace(tzinfo=UTC)
                else:
                    timestamp = datetime.strptime(timestamp_part, "%Y-%m-%d").replace(tzinfo=UTC)
            except (ValueError, IndexError):
                timestamp = datetime.fromtimestamp(meeting_path.stat().st_mtime, tz=UTC)
        else:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                timestamp = datetime.fromtimestamp(meeting_path.stat().st_mtime, tz=UTC)

        title = frontmatter_data.get("title")
        if not title:
            # Extract title from filename: YYYY-MM-DDTHHMMZ-title.md
            # filename stem might look like 2026-02-20T1030Z-my-meeting
            # split by first hyphen that isn't part of the date? No, date has hyphens.
            # YYYY-MM-DD is 10 chars. T is 11. HHMMZ is 16. 
            # If it starts with a ISO-ish date, we skip that.
            if len(meeting_path.stem) > 17 and meeting_path.stem[10] == 'T':
                title = meeting_path.stem[17:].replace('-', ' ').title()
            else:
                title = meeting_path.stem.replace('-', ' ').title()

        try:
            return cls(
                timestamp=timestamp,
                title=title or "Untitled Meeting",
                type=frontmatter_data.get("type", "meeting"),
                content=markdown_content.strip()
            )
        except ValidationError as e:
            logger.error(f"Validation error loading meeting from {meeting_path}: {e}")
            return None

    def to_file(self, meetings_dir: Path) -> Path:
        """Saves the meeting to a file and returns the path."""
        meetings_dir.mkdir(parents=True, exist_ok=True)

        # Filename: YYYY-MM-DDTHHMMZ-title.md
        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H%MZ")
        slugified_title = self.title.lower().replace(' ', '-').replace('/', '-')
        filename = f"{timestamp_str}-{slugified_title}.md"
        meeting_path = meetings_dir / filename

        # Prepare frontmatter
        frontmatter_data = {
            "timestamp": self.timestamp.isoformat(timespec='seconds').replace('+00:00', 'Z'),
            "title": self.title,
            "type": self.type,
        }
        frontmatter = yaml.dump(frontmatter_data, sort_keys=False, default_flow_style=False, allow_unicode=True)

        # Construct file content
        file_content = f"---\n{frontmatter}---\n\n{self.content.strip()}\n"

        meeting_path.write_text(file_content)
        return meeting_path
