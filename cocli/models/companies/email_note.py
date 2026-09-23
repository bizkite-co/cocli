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

    @classmethod
    def from_file(cls, note_path: Path) -> Optional[EmailNote]:
        """Loads an EmailNote from a markdown file with YAML frontmatter."""
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

            title = str(frontmatter_data.get("title") or note_path.stem.replace("-", " ").title())
            timestamp_str = frontmatter_data.get("timestamp") or frontmatter_data.get("date")
            if not timestamp_str:
                try:
                    timestamp_part = "-".join(note_path.stem.split("-")[:6])
                    timestamp = datetime.strptime(timestamp_part, "%Y-%m-%dT%H-%M-%SZ").replace(tzinfo=UTC)
                except ValueError:
                    timestamp = datetime.fromtimestamp(note_path.stat().st_mtime, tz=UTC)
            else:
                try:
                    timestamp = datetime.fromisoformat(str(timestamp_str).replace("Z", "+00:00"))
                except ValueError:
                    timestamp = datetime.fromtimestamp(note_path.stat().st_mtime, tz=UTC)

            raw_dir = str(frontmatter_data.get("direction") or "sent").lower()
            direction: Literal["sent", "received"] = (
                "received" if ("rec" in raw_dir or "in" in raw_dir) else "sent"
            )

            from_addr = str(
                frontmatter_data.get("from")
                or frontmatter_data.get("from_address")
                or ""
            )
            to_raw = frontmatter_data.get("to") or frontmatter_data.get("to_addresses") or []
            if isinstance(to_raw, str):
                to_addrs = [to_raw]
            elif isinstance(to_raw, list):
                to_addrs = [str(a) for a in to_raw]
            else:
                to_addrs = [str(to_raw)]

            message_id = frontmatter_data.get("message_id")

            return cls(
                timestamp=timestamp,
                title=title,
                type="email",
                direction=direction,
                from_address=from_addr,
                to_addresses=to_addrs,
                date=timestamp,
                message_id=str(message_id) if message_id else None,
                content=markdown_content.strip(),
            )
        except Exception as e:
            logger.error(f"Error loading EmailNote from {note_path}: {e}")
            return None


class CompanyEmail(BaseModel):
    """A unified email item (inbound or outbound) for recent email views."""

    datetime_utc: datetime
    datetime_local: datetime
    company_name: str
    company_slug: str
    title: str
    direction: Literal["sent", "received"]
    from_address: str = ""
    to_addresses: list[str] = Field(default_factory=list)
    content: str = ""
    file_path: Optional[Path] = None
    message_id: Optional[str] = None
    status: str = "sent"
    batch_id: Optional[str] = None
    template_id: Optional[str] = None
    error: Optional[str] = None
    initiative: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )

    @property
    def subject(self) -> str:
        return self.title

    @property
    def recipient(self) -> str:
        return self.to_addresses[0] if self.to_addresses else ""

    @property
    def sent_at(self) -> datetime:
        return self.datetime_local


