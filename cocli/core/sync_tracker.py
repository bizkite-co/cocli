"""
SyncTracker: Manages PI sync timestamps for campaigns.
"""

from datetime import datetime, UTC
from typing import Optional

from cocli.core.config import get_campaigns_dir


class SyncTracker:
    """
    Manages the last-sync timestamp for PI results.

    The timestamp file is stored at:
        data/campaigns/{campaign}/.last_pi_sync

    Usage:
        tracker = SyncTracker("roadmap")
        if tracker.needs_sync():
            # run sync
            tracker.update_last_sync()
    """

    TIMESTAMP_FILENAME = ".last_pi_sync"

    def __init__(self, campaign_name: str) -> None:
        self.campaign = campaign_name
        self.timestamp_file = (
            get_campaigns_dir() / campaign_name / self.TIMESTAMP_FILENAME
        )

    def get_last_sync(self) -> Optional[datetime]:
        """
        Returns the last sync time as a datetime, or None if never synced.
        """
        if not self.timestamp_file.exists():
            return None

        try:
            content = self.timestamp_file.read_text().strip()
            return datetime.fromisoformat(content)
        except (ValueError, OSError):
            return None

    def needs_sync(self, threshold_hours: float = 1.0) -> bool:
        """
        Check if sync is needed based on threshold.

        Args:
            threshold_hours: Minimum age of last sync before a new sync is needed.

        Returns:
            True if sync is needed, False if recent enough.
        """
        last_sync = self.get_last_sync()
        if last_sync is None:
            return True

        now = datetime.now(UTC)
        age_hours = (now - last_sync).total_seconds() / 3600
        return age_hours >= threshold_hours

    def update_last_sync(self) -> None:
        """
        Update the timestamp file with the current time.
        """
        self.timestamp_file.parent.mkdir(parents=True, exist_ok=True)
        self.timestamp_file.write_text(datetime.now(UTC).isoformat())
