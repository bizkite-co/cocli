import logging
from pathlib import Path

from .base import QueueMessage
from ....core.paths import paths
from ....core.ordinant import QueueName
from ....core.sharding import get_domain_shard

logger = logging.getLogger(__name__)


class EnrichmentTask(QueueMessage):
    """
    Gold Standard Enrichment Task.
    Shard: sha256(domain)[:2] (same as FSQ ENRICHMENT StationDecl / get_domain_shard)
    Task ID: The raw domain (deduplication anchor)
    """

    @property
    def collection(self) -> QueueName:
        from ....core.ordinant import QueueIdentity
        return QueueIdentity.ENRICHMENT

    @property
    def task_id(self) -> str:
        """The domain is the unique anchor for enrichment."""
        return self.domain

    @property
    def shard(self) -> str:
        """Deterministic shard (00-ff) based on domain hash."""
        return self.get_shard_id()

    def get_shard_id(self) -> str:
        # Path authority: same function as QueueLayout / FilesystemEnrichmentQueue
        return get_domain_shard(self.domain)

    def get_local_path(self) -> Path:
        """Local pending dir: queues/.../enrichment/pending/{shard}/{domain}"""
        return (
            paths.campaign(self.campaign_name).queue("enrichment").pending
            / self.get_shard_id()
            / self.task_id
        )

    def get_remote_key(self) -> str:
        return self.get_s3_task_key()

    def get_s3_task_key(self) -> str:
        # Must match FilesystemQueue._get_s3_task_key for queue_name=enrichment
        return (
            f"campaigns/{self.campaign_name}/queues/enrichment/pending/"
            f"{self.get_shard_id()}/{self.task_id}/task.json"
        )

    def get_s3_lease_key(self) -> str:
        return (
            f"campaigns/{self.campaign_name}/queues/enrichment/pending/"
            f"{self.get_shard_id()}/{self.task_id}/lease.json"
        )

    def get_local_dir(self) -> Path:
        """Legacy helper for existing code."""
        return self.get_local_path()
