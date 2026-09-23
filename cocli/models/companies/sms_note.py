from __future__ import annotations
from pathlib import Path
from datetime import datetime, UTC
from typing import Any, Literal, Optional
import yaml
from pydantic import BaseModel, Field, ConfigDict
import logging

logger = logging.getLogger(__name__)


class SmsNote(BaseModel):
    """
    Structured Pydantic model for SMS notes saved to Markdown with YAML frontmatter.
    Conforms to SmsNoteProtocol.
    """

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    title: str
    type: Literal["sms"] = "sms"
    direction: Literal["inbound", "outbound"] = "inbound"
    from_phone: str = ""
    to_phone: str = ""
    content: str = ""
    message_sid: Optional[str] = None
    status: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    def to_file(self, notes_dir: Path) -> Path:
        """Write the SMS note as a markdown file with YAML frontmatter."""
        notes_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        sid_suffix = self.message_sid[:8] if self.message_sid else ""
        if not sid_suffix:
            slugified_title = self.title.lower().replace(" ", "-").replace("/", "-")
            slugified_title = "".join(
                c for c in slugified_title if c.isalnum() or c in ("-", "_")
            ).strip("-")
            sid_suffix = slugified_title[:20]

        filename = f"{timestamp_str}-sms-{self.direction}-{sid_suffix}.md"
        note_path = notes_dir / filename

        frontmatter_data: dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "title": self.title,
            "type": self.type,
            "direction": self.direction,
            "from": self.from_phone,
            "to": self.to_phone,
        }
        if self.message_sid:
            frontmatter_data["message_sid"] = self.message_sid
        if self.status:
            frontmatter_data["status"] = self.status

        frontmatter = yaml.dump(
            frontmatter_data, sort_keys=False, default_flow_style=False, allow_unicode=True
        )
        file_content = f"---\n{frontmatter}---\n{self.content.strip()}\n"
        note_path.write_text(file_content, encoding="utf-8")
        return note_path

    @classmethod
    def from_file(cls, note_path: Path) -> Optional[SmsNote]:
        """Loads an SmsNote from a markdown file with YAML frontmatter."""
        if not note_path.exists():
            return None
        try:
            content = note_path.read_text(encoding="utf-8")
            frontmatter_data: dict[str, Any] = {}
            markdown_content = ""
            if content.startswith("---") and "---" in content[3:]:
                parts = content.split("---", 2)
                frontmatter_str = parts[1]
                markdown_content = parts[2] if len(parts) > 2 else ""
                try:
                    frontmatter_data = yaml.safe_load(frontmatter_str) or {}
                except yaml.YAMLError as e:
                    logger.warning(f"Error parsing YAML frontmatter in {note_path}: {e}")
                    return None
            else:
                markdown_content = content

            title = frontmatter_data.get("title") or note_path.stem.replace("-", " ").title()
            timestamp_str = frontmatter_data.get("timestamp")
            if not timestamp_str:
                try:
                    timestamp_part = "-".join(note_path.stem.split("-")[:6])
                    timestamp = datetime.strptime(timestamp_part, "%Y-%m-%dT%H-%M-%SZ")
                except ValueError:
                    timestamp = datetime.fromtimestamp(note_path.stat().st_mtime, tz=UTC)
            else:
                try:
                    timestamp = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
                except ValueError:
                    timestamp = datetime.fromtimestamp(note_path.stat().st_mtime, tz=UTC)

            raw_dir = str(frontmatter_data.get("direction") or "inbound").lower()
            direction: Literal["inbound", "outbound"] = (
                "outbound" if "out" in raw_dir else "inbound"
            )

            from_phone = str(
                frontmatter_data.get("from")
                or frontmatter_data.get("from_phone")
                or ""
            )
            to_phone = str(
                frontmatter_data.get("to")
                or frontmatter_data.get("to_phone")
                or ""
            )
            message_sid = frontmatter_data.get("message_sid")
            status = frontmatter_data.get("status")

            return cls(
                timestamp=timestamp,
                title=title,
                type="sms",
                direction=direction,
                from_phone=from_phone,
                to_phone=to_phone,
                content=markdown_content.strip(),
                message_sid=str(message_sid) if message_sid else None,
                status=str(status) if status else None,
            )
        except Exception as e:
            logger.error(f"Error loading SmsNote from {note_path}: {e}")
            return None
