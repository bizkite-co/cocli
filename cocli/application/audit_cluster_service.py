"""Audit Cluster Service

Provides audit operations focusing on cluster nodes, infrastructure, and paths.
"""

from typing import Any, List, Optional
from .audit_service import AuditService

class AuditClusterService:
    """Service exposing only cluster‑related audit methods."""

    def __init__(self, campaign_name: str):
        self._service = AuditService(campaign_name)
        self.campaign_name = campaign_name

    def audit_queue_completion(self, execute: bool = False) -> dict[str, Any]:
        return self._service.audit_queue_completion(execute)

    def audit_cluster_paths(self, target_paths: List[str], campaigns: Optional[List[str]] = None) -> List[dict[str, Any]]:
        return self._service.audit_cluster_paths(target_paths, campaigns)
