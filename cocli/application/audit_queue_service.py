"""Audit Queue Service

Provides audit operations focusing on queues and data quality.
"""
from __future__ import annotations

from typing import Any, Optional
from pathlib import Path
from .audit_service import AuditService
from cocli.models import TileStatusResult, MissionReconciliationResult

class AuditQueueService:
    """Service exposing only queue‑related audit methods."""

    def __init__(self, campaign_name: str):
        self._service = AuditService(campaign_name)
        self.campaign_name = campaign_name

    def run_queue_gm_list(self, campaign_name: str) -> str:
        return self._service.run_queue_gm_list(campaign_name)

    def audit_enrichment(self, campaign_name: str) -> dict[str, Any]:
        return self._service.audit_enrichment(campaign_name)

    def get_enrichment_interactive_targets(self, campaign_name: str) -> list[tuple[Optional[str], str, str, bool, bool]]:
        return self._service.get_enrichment_interactive_targets(campaign_name)

    def run_gm_list_html_audit(self, campaign: str, limit: int, output: str) -> Path:
        return self._service.run_gm_list_html_audit(campaign, limit, output)

    def prepare_validate(
        self,
        campaign: str,
        tile: Optional[str] = None,
        phrase: Optional[str] = None,
        usv_path: Optional[Path] = None,
        headed: bool = False,
        limit: int = 0,
    ) -> dict[str, Any]:
        return self._service.prepare_validate(
            campaign=campaign,
            tile=tile,
            phrase=phrase,
            usv_path=usv_path,
            headed=headed,
            limit=limit,
        )

    def save_reviewed_item(self, reviewed_path: Path, place_id: str, field_name: str, expected: str) -> None:
        self._service.save_reviewed_item(reviewed_path, place_id, field_name, expected)

    def replay_audit_corrections(
        self,
        campaign: str,
        usv_path: Path,
        output: Optional[Path] = None,
        corrections_path: Optional[Path] = None,
        reviewed_path_opt: Optional[Path] = None,
    ) -> dict[str, Any]:
        return self._service.replay_audit_corrections(
            campaign=campaign,
            usv_path=usv_path,
            output=output,
            corrections_path=corrections_path,
            reviewed_path_opt=reviewed_path_opt,
        )

    def export_cases(self, campaign: str, tile: Optional[str] = None, phrase: Optional[str] = None) -> dict[str, Any]:
        return self._service.export_cases(campaign=campaign, tile=tile, phrase=phrase)

    def get_tile_status(self, campaign_name: str) -> TileStatusResult:
        return self._service.get_tile_status(campaign_name)

    def audit_mission_reconciliation(self, campaign_name: str) -> MissionReconciliationResult:
        return self._service.audit_mission_reconciliation(campaign_name)

    def purge_leases(
        self,
        campaign_name: str,
        queue_name: str,
        force: bool = False,
        dry_run: bool = False,
        max_age_minutes: int = 30,
    ) -> dict[str, Any]:
        return self._service.purge_leases(
            campaign_name=campaign_name,
            queue_name=queue_name,
            force=force,
            dry_run=dry_run,
            max_age_minutes=max_age_minutes,
        )
