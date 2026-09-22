from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional


@dataclass
class CompanyActivity:
    """A unified activity item (call, email, note, or meeting) for a company."""

    timestamp: datetime
    activity_type: Literal["call", "email", "note", "meeting"]
    icon: str  # "📞", "✉", "📝", "📅"
    title: str
    preview: str
    content: str
    file_path: Optional[Path] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    is_scheduled: bool = False
