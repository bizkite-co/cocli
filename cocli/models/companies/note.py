from __future__ import annotations
from pathlib import Path
from datetime import datetime, UTC
from typing import Optional, Any, Union, Literal
import yaml
from pydantic import BaseModel, Field, ValidationError
import logging
from .email_note import EmailNote

logger = logging.getLogger(__name__)


class Note(BaseModel):
    """
    Standard Pydantic model for general notes saved to Markdown with YAML frontmatter.
    Conforms to NoteProtocol.
    """

    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    title: str
    content: str

    @classmethod
    def from_file(cls, note_path: Path) -> Optional[Union["Note", EmailNote]]:
        """
        Loads a Note or EmailNote from a Markdown file with YAML frontmatter.
        Supports both modern frontmatter email notes and legacy notes.
        """
        if not note_path.exists():
            return None

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

        title = frontmatter_data.get("title")
        if not title:
            name_parts = note_path.stem.split("-", 6)
            if len(name_parts) > 6:
                title = "-".join(name_parts[6:])
            else:
                title = note_path.stem
            title = title.replace("-", " ").title()

        timestamp_str = frontmatter_data.get("timestamp")
        if not timestamp_str:
            try:
                timestamp_part = "-".join(note_path.stem.split("-")[:6])
                timestamp = datetime.strptime(timestamp_part, "%Y-%m-%dT%H-%M-%SZ")
            except ValueError:
                timestamp = datetime.fromtimestamp(note_path.stat().st_mtime, tz=UTC)
        else:
            try:
                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            except ValueError:
                timestamp = datetime.fromtimestamp(note_path.stat().st_mtime, tz=UTC)

        # Check if note is an Email Note (modern or legacy)
        is_email = (
            frontmatter_data.get("type") == "email"
            or "direction" in frontmatter_data
            or title.lower().startswith(("email sent:", "email received:"))
            or ("- Direction:" in markdown_content or "- From:" in markdown_content)
        )

        if is_email:
            return cls._parse_email_note(
                note_path=note_path,
                timestamp=timestamp,
                raw_title=title,
                frontmatter=frontmatter_data,
                markdown_content=markdown_content,
            )

        try:
            return cls(
                timestamp=timestamp,
                title=title,
                content=markdown_content.strip(),
            )
        except ValidationError as e:
            logger.error(f"Validation error loading note from {note_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error loading note from {note_path}: {e}")
            return None

    @classmethod
    def _parse_email_note(
        cls,
        note_path: Path,
        timestamp: datetime,
        raw_title: str,
        frontmatter: dict[str, Any],
        markdown_content: str,
    ) -> Optional[EmailNote]:
        clean_title = raw_title
        for prefix in ("email sent:", "email received:"):
            if clean_title.lower().startswith(prefix):
                clean_title = clean_title[len(prefix) :].strip()
                break

        direction = frontmatter.get("direction")
        from_addr = frontmatter.get("from") or frontmatter.get("from_address") or ""
        to_addrs = frontmatter.get("to") or frontmatter.get("to_addresses") or []
        if isinstance(to_addrs, str):
            to_addrs = [to_addrs]
        date_val = frontmatter.get("date")
        msg_id = frontmatter.get("message_id")

        body_lines = markdown_content.strip().splitlines()
        clean_body_lines: list[str] = []
        parsing_legacy_headers = True

        for line in body_lines:
            if parsing_legacy_headers:
                line_strip = line.strip()
                lower = line_strip.lower()
                if lower.startswith("- direction:"):
                    if not direction:
                        direction = line_strip.split(":", 1)[1].strip().lower()
                    continue
                elif lower.startswith("- from:"):
                    if not from_addr:
                        from_addr = line_strip.split(":", 1)[1].strip()
                    continue
                elif lower.startswith("- to:"):
                    if not to_addrs:
                        raw_to = line_strip.split(":", 1)[1].strip()
                        to_addrs = [a.strip() for a in raw_to.split(",") if a.strip()]
                    continue
                elif lower.startswith("- date:"):
                    if not date_val:
                        date_str = line_strip.split(":", 1)[1].strip()
                        try:
                            date_val = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    continue
                elif lower.startswith("- message-id:"):
                    if not msg_id:
                        msg_id = line_strip.split(":", 1)[1].strip()
                    continue
                elif line_strip == "":
                    continue
                else:
                    parsing_legacy_headers = False

            clean_body_lines.append(line)

        clean_content = "\n".join(clean_body_lines).strip()

        direction_literal: Literal["sent", "received"] = "received" if direction == "received" else "sent"

        parsed_date: Optional[datetime] = None
        if isinstance(date_val, datetime):
            parsed_date = date_val
        elif isinstance(date_val, str):
            try:
                parsed_date = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
            except ValueError:
                pass

        try:
            return EmailNote(
                timestamp=timestamp,
                title=clean_title or "(no subject)",
                direction=direction_literal,
                from_address=from_addr,
                to_addresses=to_addrs,
                date=parsed_date,
                message_id=msg_id,
                content=clean_content,
            )
        except Exception as e:
            logger.error(f"Error parsing EmailNote from {note_path}: {e}")
            return None

    def to_file(self, notes_dir: Path) -> Path:
        notes_dir.mkdir(parents=True, exist_ok=True)
        timestamp_str = self.timestamp.strftime("%Y-%m-%dT%H-%M-%SZ")
        slugified_title = self.title.lower().replace(" ", "-").replace("/", "-")
        slugified_title = "".join(
            c for c in slugified_title if c.isalnum() or c in ("-", "_")
        ).strip("-")
        filename = f"{timestamp_str}-{slugified_title[:50]}.md"
        note_path = notes_dir / filename

        frontmatter_data = {
            "timestamp": self.timestamp.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "title": self.title,
        }
        frontmatter = yaml.dump(
            frontmatter_data, sort_keys=False, default_flow_style=False, allow_unicode=True
        )
        file_content = f"---\n{frontmatter}---\n{self.content.strip()}\n"
        note_path.write_text(file_content, encoding="utf-8")
        return note_path
