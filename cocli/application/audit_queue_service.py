"""Audit Queue Service

Provides audit operations focusing on queues and data quality.
"""

from typing import Any, List, Optional
from pathlib import Path
from .audit_service import AuditService

class AuditQueueService(AuditService):
    """Service exposing only queue‑related audit methods."""

    def run_queue_gm_list(self, campaign_name: str) -> str:
        return super().run_queue_gm_list(campaign_name)

    def audit_enrichment(self, campaign_name: str) -> dict[str, Any]:
        return super().audit_enrichment(campaign_name)

    def get_enrichment_interactive_targets(self, campaign_name: str) -> List[tuple[Optional[str], str, str, bool, bool]]:
        return super().get_enrichment_interactive_targets(campaign_name)

    def run_gm_list_html_audit(self, campaign: str, limit: int, output: str) -> Path:
        return super().run_gm_list_html_audit(campaign, limit, output)

    def prepare_validate(
        self,
        campaign: str,
        tile: Optional[str] = None,
        phrase: Optional[str] = None,
        usv_path: Optional[Path] = None,
        headed: bool = False,
        limit: int = 0,
    ) -> dict[str, Any]:
        return super().prepare_validate(
            campaign=campaign,
            tile=tile,
            phrase=phrase,
            usv_path=usv_path,
            headed=headed,
            limit=limit,
        )

    def save_reviewed_item(self, reviewed_path: Path, place_id: str, field_name: str, expected: str) -> None:
        super().save_reviewed_item(reviewed_path, place_id, field_name, expected)

    def replay_audit_corrections(
        self,
        campaign: str,
        usv_path: Path,
        output: Optional[Path] = None,
        corrections_path: Optional[Path] = None,
        reviewed_path_opt: Optional[Path] = None,
    ) -> dict[str, Any]:
        return super().replay_audit_corrections(
            campaign=campaign,
            usv_path=usv_path,
            output=output,
            corrections_path=corrections_path,
            reviewed_path_opt=reviewed_path_opt,
        )

    def export_cases(self, campaign: str, tile: Optional[str] = None, phrase: Optional[str] = None) -> dict[str, Any]:
        return super().export_cases(campaign=campaign, tile=tile, phrase=phrase)

    def get_tile_status(self, campaign_name: str) -> dict[str, Any]:
        return super().get_tile_status(campaign_name)

    def purge_leases(
        self,
        campaign_name: str,
        queue_name: str,
        force: bool = False,
        dry_run: bool = False,
        max_age_minutes: int = 30,
    ) -> dict[str, Any]:
        return super().purge_leases(
            campaign_name=campaign_name,
            queue_name=queue_name,
            force=force,
            dry_run=dry_run,
            max_age_minutes=max_age_minutes,
        )
