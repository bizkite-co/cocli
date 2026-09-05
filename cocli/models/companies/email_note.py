from __future__ import annotations
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional, Any, Literal
import yaml
from pydantic import BaseModel, Field, ConfigDict
import logging

logger = logging.getLogger(__name__)


class EmailNote(BaseModel):
    """
    Structured Pydantic model for email notes saved to Markdown with YAML frontmatter.
    Conforms to EmailNoteProtocol.
    """

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    title: str
    type: Literal["email"] = "email"
    direction: Literal["sent", "received"]
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)
    date: Optional[datetime] = None
    message_id: Optional[str] = None
    content: str

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    def to_file(self, notes_dir: Path) -> Path:
        """Write the email note as a markdown file with YAML frontmatter."""
        notes_dir.mkdir(parents=True, exist_ok=True)

        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        # Clean title for filename slug
        slugified_title = self.title.lower().replace(" ", "-").replace("/", "-")
        slugified_title = "".join(
            c for c in slugified_title if c.isalnum() or c in ("-", "_")
        ).strip("-")
        filename = f"{timestamp_str}-email-{self.direction}-{slugified_title[:40]}.md"
        note_path = notes_dir / filename

        frontmatter_data: dict[str, Any] = {
            "timestamp": self.timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "title": self.title,
            "type": self.type,
            "direction": self.direction,
            "from": self.from_address,
            "to": self.to_addresses,
        }
        if self.date:
            dt_iso = self.date.isoformat(timespec="seconds").replace("+00:00", "Z")
            frontmatter_data["date"] = dt_iso
        if self.message_id:
            frontmatter_data["message_id"] = self.message_id

        frontmatter = yaml.dump(
            frontmatter_data, sort_keys=False, default_flow_style=False, allow_unicode=True
        )
        file_content = f"---\n{frontmatter}---\n{self.content.strip()}\n"
        note_path.write_text(file_content, encoding="utf-8")
        return note_path
