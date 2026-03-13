import logging
from typing import List
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta  # type: ignore

from ..models.campaigns.events import EventSource, EventScrapeTask
from ..core.paths import paths
from ..core.ordinant import QueueIdentity

logger = logging.getLogger(__name__)

class EventGeneratorService:
    """
    Hydrates EventSource templates into time-specific EventScrapeTasks.
    """
    def __init__(self, campaign_name: str = "fullertonian"):
        self.campaign_name = campaign_name
        self.sources_dir = paths.campaign(campaign_name).queue(QueueIdentity.EVENTS).path / "sources"
        self.pending_dir = paths.campaign(campaign_name).queue(QueueIdentity.EVENTS).path / "pending"
        self.completed_dir = paths.campaign(campaign_name).queue(QueueIdentity.EVENTS).path / "completed"

    def load_sources(self) -> List[EventSource]:
        """Loads all active event sources from the filesystem."""
        sources: List[EventSource] = []
        if not self.sources_dir.exists():
            return sources
            
        for p in self.sources_dir.glob("*.json"):
            try:
                with open(p, "r") as f:
                    source = EventSource.model_validate_json(f.read())
                    if source.is_active:
                        sources.append(source)
            except Exception as e:
                logger.error(f"Failed to load event source {p}: {e}")
        return sources

    def generate_tasks(self, windows_ahead: int = 1) -> List[EventScrapeTask]:
        """
        Generates tasks for the specified number of windows ahead.
        """
        sources = self.load_sources()
        generated_tasks = []
        
        # Calculate windows
        now = datetime.now()
        
        for source in sources:
            windows = self._calculate_windows(source, now, windows_ahead)
            for window_date, window_id in windows:
                if self._task_exists(source.host_slug, window_id):
                    continue
                    
                task = self._create_task(source, window_date, window_id)
                task.save_task()
                generated_tasks.append(task)
                logger.info(f"Generated task: {source.host_slug} for {window_id}")
                
        return generated_tasks

    def _calculate_windows(self, source: EventSource, start_date: datetime, count: int) -> List[tuple[datetime, str]]:
        """
        Returns a list of (date, window_id) tuples based on frequency.
        """
        windows = []
        for i in range(count):
            if source.frequency == "monthly":
                target_date = start_date + relativedelta(months=i)
                window_id = target_date.strftime("%Y%m")
            elif source.frequency == "weekly":
                target_date = start_date + timedelta(weeks=i)
                # ISO Week: 2026-W11
                window_id = target_date.strftime("%Y-W%V")
            else:
                continue
            windows.append((target_date, window_id))
        return windows

    def _task_exists(self, source_id: str, window_id: str) -> bool:
        """Checks if a task already exists in pending or completed."""
        # 1. Check pending
        if (self.pending_dir / window_id / f"{source_id}.json").exists():
            return True
        # 2. Check completed
        if (self.completed_dir / window_id / f"{source_id}.json").exists():
            return True
        return False

    def _create_task(self, source: EventSource, window_date: datetime, window_id: str) -> EventScrapeTask:
        """Hydrates templates into a task instance."""
        
        # Mapping for common placeholders
        replacements = {
            "{month}": window_date.strftime("%B"),
            "{year}": window_date.strftime("%Y"),
            "{YYYY}": window_date.strftime("%Y"),
            "{MM}": window_date.strftime("%m"),
            "{YYYY-MM}": window_date.strftime("%Y-%m"),
        }
        
        url = source.url_template
        phrase = source.search_phrase_template
        
        for k, v in replacements.items():
            url = url.replace(k, v)
            phrase = phrase.replace(k, v)
            
        return EventScrapeTask(
            source_id=source.host_slug,
            target_window=window_id,
            hydrated_url=url,
            hydrated_phrase=phrase,
            scraper_type=source.scraper_type,
            campaign_name=self.campaign_name
        )
