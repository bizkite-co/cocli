import logging
import yaml
from pathlib import Path
from typing import List
from ..models.campaigns.events import Event
from ..core.paths import paths

logger = logging.getLogger(__name__)

class EventService:
    """
    Manages the lifecycle of community events, including curation (approval/rejection).
    """
    def __init__(self, campaign_name: str = "fullertonian"):
        self.campaign_name = campaign_name

    def get_pending_events(self) -> List[Event]:
        """
        Scans the events WAL for pending (non-curated) events.
        """
        events = []
        wal_dir = paths.campaign(self.campaign_name).queue("events").wal
        
        if not wal_dir.exists():
            return []

        # WAL is sharded by YYYYMM
        for shard_dir in sorted(wal_dir.iterdir()):
            if not shard_dir.is_dir():
                continue
            
            for event_dir in sorted(shard_dir.iterdir()):
                if not event_dir.is_dir():
                    continue
                
                readme_path = event_dir / "README.md"
                if not readme_path.exists():
                    continue

                try:
                    event = self._load_event_from_dir(event_dir)
                    # Only include events that haven't been curated yet 
                    # (in a real system we might check a curated/ directory or metadata)
                    if not self._is_curated(event):
                        events.append(event)
                except Exception as e:
                    logger.error(f"Failed to load event from {event_dir}: {e}")
        
        return events

    def _load_event_from_dir(self, event_dir: Path) -> Event:
        readme_path = event_dir / "README.md"
        content = readme_path.read_text(encoding="utf-8")
        
        parts = content.split("---")
        if len(parts) < 3:
            raise ValueError(f"Invalid README.md format in {event_dir}")
        
        frontmatter = yaml.safe_load(parts[1])
        description = parts[2].strip()
        
        # Merge description back into data
        frontmatter["description"] = description
        return Event(**frontmatter)

    def _is_curated(self, event: Event) -> bool:
        """Checks if the event has already been moved to approved/ or rejected/."""
        # For now, we'll assume events in the WAL are pending until moved.
        # But we also check curation flags in the model.
        if event.is_excluded:
            return True
        
        # Check if it exists in the approved directory
        approved_path = self.get_approved_dir() / event.get_shard_id() / event.get_event_dir_name()
        if approved_path.exists():
            return True
            
        return False

    def get_approved_dir(self) -> Path:
        p = paths.campaign(self.campaign_name).path / "queues" / "events" / "approved"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def get_rejected_dir(self) -> Path:
        p = paths.campaign(self.campaign_name).path / "queues" / "events" / "rejected"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def approve_event(self, event: Event) -> bool:
        """Moves an event from WAL to the approved directory."""
        try:
            source_dir = event.get_local_path()
            target_dir = self.get_approved_dir() / event.get_shard_id() / event.get_event_dir_name()
            
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            
            # Simple rename/move
            if source_dir.exists():
                import shutil
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.move(str(source_dir), str(target_dir))
                logger.info(f"Approved event: {event.event_slug}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to approve event {event.event_slug}: {e}")
            return False

    def reject_event(self, event: Event, reason: str = "") -> bool:
        """Moves an event from WAL to the rejected directory."""
        try:
            source_dir = event.get_local_path()
            target_dir = self.get_rejected_dir() / event.get_shard_id() / event.get_event_dir_name()
            
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            
            if source_dir.exists():
                import shutil
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.move(str(source_dir), str(target_dir))
                
                # Optional: write rejection reason to a file
                if reason:
                    (target_dir / "rejection_reason.txt").write_text(reason)
                    
                logger.info(f"Rejected event: {event.event_slug}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to reject event {event.event_slug}: {e}")
            return False

    def update_event(self, event: Event) -> bool:
        """Saves modifications to an event still in the WAL."""
        try:
            event.save()
            return True
        except Exception as e:
            logger.error(f"Failed to update event {event.event_slug}: {e}")
            return False
