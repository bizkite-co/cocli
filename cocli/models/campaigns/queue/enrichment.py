import logging
from pathlib import Path

from ...queue import QueueMessage
from ....core.paths import paths
from ....core.sharding import get_domain_shard

logger = logging.getLogger(__name__)

class EnrichmentTask(QueueMessage):
    """
    Gold Standard Enrichment Task.
    Shard: sha256(domain)[:2]
    Task ID: The raw domain (deduplication anchor)
    """
    
    @property
    def task_id(self) -> str:
        """The domain is the unique anchor for enrichment."""
        return self.domain

    @property
    def shard(self) -> str:
        """Deterministic shard (00-ff) based on domain hash."""
        return get_domain_shard(self.domain)

    def get_local_dir(self) -> Path:
        """Returns the local pending directory: queues/{campaign}/enrichment/pending/{shard}/{domain}"""
        base = paths.queue(self.campaign_name, "enrichment")
        return base / "pending" / self.shard / self.task_id

    def get_s3_task_key(self) -> str:
        return paths.s3_queue_pending(
            self.campaign_name, 
            "enrichment", 
            self.shard, 
            self.task_id
        ) + "task.json"

    def get_s3_lease_key(self) -> str:
        return paths.s3_queue_pending(
            self.campaign_name, 
            "enrichment", 
            self.shard, 
            self.task_id
        ) + "lease.json"
