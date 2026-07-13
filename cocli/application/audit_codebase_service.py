"""Audit Codebase Service

Provides audit operations focusing on static codebase and filesystem.
"""

from typing import Any
from .audit_service import AuditService

class AuditCodebaseService(AuditService):
    """Service exposing only code‑base‑related audit methods."""

    def get_cli_tree(self) -> str:
        return super().get_cli_tree()

    def audit_filesystem(self, campaign_name: str | None = None, skip_companies: bool = True, gen_cleanup: bool = False) -> dict[str, Any]:
        return super().audit_filesystem(campaign_name=campaign_name, skip_companies=skip_companies, gen_cleanup=gen_cleanup)

    def audit_schemas(self, campaign: str | None = None, fix: bool = False, dry_run: bool = False) -> dict[str, Any]:
        return super().audit_schemas(campaign=campaign, fix=fix, dry_run=dry_run)

    def audit_campaign_integrity(self, fix: bool = False) -> dict[str, Any]:
        return super().audit_campaign_integrity(fix=fix)
