from pathlib import Path
from typing import Optional, Dict, List

from ..models.campaigns.indexes.domains import WebsiteDomainCsv
from .domain_index_manager import DomainIndexManager
from ..models.campaigns.campaign import Campaign

CURRENT_SCRAPER_VERSION = 6

class WebsiteDomainCsvManager:
    """
    Legacy wrapper for DomainIndexManager to maintain backward compatibility.
    Now uses the sharded USV architecture internally.
    """
    def __init__(self, indexes_dir: Optional[Path] = None):
        # We try to load the current campaign context
        from .config import get_campaign
        campaign_name = get_campaign() or "roadmap" # Fallback
        self.campaign = Campaign.load(campaign_name)
        self.manager = DomainIndexManager(self.campaign)
        
        # Force local mode if indexes_dir is provided or if not in cloud
        if indexes_dir:
            self.manager.is_cloud = False
            self.manager.root_dir = indexes_dir
            self.manager.protocol = ""

        self.data: Dict[str, WebsiteDomainCsv] = {}

    def get_by_domain(self, domain: str) -> Optional[WebsiteDomainCsv]:
        return self.manager.get_by_domain(domain)

    def add_or_update(self, item: WebsiteDomainCsv) -> None:
        self.manager.add_or_update(item)

    def flag_as_email_provider(self, domain: str) -> None:
        item = self.get_by_domain(domain)
        if not item:
            item = WebsiteDomainCsv(domain=domain)
        item.is_email_provider = True
        self.add_or_update(item)

    def rebuild_cache(self) -> None:
        """Compact the inbox into shards."""
        self.manager.compact_inbox()

    def save(self) -> None:
        self.rebuild_cache()

    @property
    def all_items(self) -> List[WebsiteDomainCsv]:
        """Legacy access to all items. WARNING: This can be slow for large indexes."""
        return self.manager.query()
