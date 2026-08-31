"""Audit Codebase Service

Provides audit operations focusing on static codebase and filesystem.
"""

from typing import Any, List
from .audit_service import AuditService
from ..models.cli_help import CliCommandMatch

class AuditCodebaseService:
    """Service exposing only code‑base‑related audit methods."""

    def __init__(self, campaign_name: str):
        self._service = AuditService(campaign_name)
        self.campaign_name = campaign_name

    def get_cli_tree(self, click_command: Any) -> str:
        return self._service.get_cli_tree(click_command)

    def search_cli_tree(
        self, click_command: Any, query: str, limit: int = 25
    ) -> List[CliCommandMatch]:
        return self._service.search_cli_tree(click_command, query, limit=limit)

    def get_tui_actions(self, classes: List[type]) -> str:
        return self._service.get_tui_actions(classes)

    def get_tui_operations(self) -> str:
        return self._service.get_tui_operations()

    def audit_filesystem(self, campaign_name: str | None = None, skip_companies: bool = True, gen_cleanup: bool = False) -> dict[str, Any]:
        return self._service.audit_filesystem(campaign_name=campaign_name, skip_companies=skip_companies, gen_cleanup=gen_cleanup)

    def audit_schemas(self, campaign: str | None = None, fix: bool = False, dry_run: bool = False) -> dict[str, Any]:
        return self._service.audit_schemas(campaign=campaign, fix=fix, dry_run=dry_run)

    def audit_campaign_integrity(self, fix: bool = False) -> dict[str, Any]:
        return self._service.audit_campaign_integrity(fix=fix)
