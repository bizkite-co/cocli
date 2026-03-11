# POLICY: frictionless-data-policy-enforcement
from datetime import datetime
from typing import Optional, List, Any
from pydantic import Field
from pathlib import Path
import yaml
from ..base import BaseUsvModel

class Event(BaseUsvModel):
    """
    Standard model for Fullertonian community events.
    Stored as directories with README.md (YAML frontmatter + Markdown body).
    Allows for attaching images/assets in the same folder.
    """
    # Authoritative Sequence for USV
    start_time: datetime = Field(..., description="ISO datetime of the event")
    host_slug: str = Field(..., description="Slug of the hosting organization/venue")
    event_slug: str = Field(..., description="Slug of the event name")
    name: str = Field(..., description="Full human-readable event name")
    host_name: str = Field(..., description="Full human-readable host name")
    
    location: Optional[str] = None
    fee: Optional[str] = "Free"
    description: Optional[str] = None
    url: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    
    # Metadata
    campaign_name: str = "fullertonian"
    source_url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now())
    
    def get_event_dir_name(self) -> str:
        """
        Generates the standard directory name:
        ISO_DATETIME_host-slug_event-slug
        """
        ts = self.start_time.strftime("%Y%m%dT%H%M%S")
        return f"{ts}_{self.host_slug}_{self.event_slug}"

    def save_to_wal(self, wal_dir: Path) -> Path:
        """
        Saves the event as a directory with a README.md file.
        """
        event_dir = wal_dir / self.get_event_dir_name()
        event_dir.mkdir(parents=True, exist_ok=True)
        
        readme_path = event_dir / "README.md"
        
        # Prepare frontmatter
        data = self.model_dump(mode="json", exclude_none=True)
        description = data.pop("description", "")
        
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write("---\n")
            yaml.safe_dump(data, f, sort_keys=False)
            f.write("---\n")
            if description:
                f.write(f"\n{description}\n")
                
        return event_dir
