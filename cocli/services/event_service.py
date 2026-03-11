import logging
from typing import List
import yaml
from ..models.campaigns.events import Event
from ..core.paths import paths
from ..core.ordinant import QueueIdentity

logger = logging.getLogger(__name__)

class EventService:
    def __init__(self, campaign_name: str = "fullertonian"):
        self.campaign_name = campaign_name
        self.events_wal = paths.campaign(campaign_name).queue(QueueIdentity.EVENTS).wal

    def get_upcoming_events(self) -> List[Event]:
        """
        Retrieves all events from the WAL, sorted by start_time ascending.
        """
        events: List[Event] = []
        if not self.events_wal.exists():
            return events

        # Walk the shard directories (YYYYMM)
        for shard_dir in sorted(self.events_wal.iterdir()):
            if not shard_dir.is_dir():
                continue
            
            # Walk event directories
            for event_dir in shard_dir.iterdir():
                if not event_dir.is_dir():
                    continue
                
                readme = event_dir / "README.md"
                if readme.exists():
                    try:
                        # Parse YAML frontmatter
                        content = readme.read_text()
                        if content.startswith("---"):
                            _, frontmatter, _ = content.split("---", 2)
                            data = yaml.safe_load(frontmatter)
                            # Add description back if needed (not strictly required for the list)
                            event = Event.model_validate(data)
                            events.append(event)
                    except Exception as e:
                        logger.error(f"Error loading event from {event_dir}: {e}")

        # Sort by start_time ascending
        events.sort(key=lambda x: x.start_time)
        return events

    def toggle_exclude(self, event: Event) -> Event:
        """Toggles the exclusion flag and saves the event."""
        event.is_excluded = not event.is_excluded
        event.save()
        return event

    def toggle_highlight(self, event: Event) -> Event:
        """Toggles the highlight flag and saves the event."""
        event.is_highlighted = not event.is_highlighted
        event.save()
        return event
