"""Compile the customer enriched-emails yield from worker output.

The five steps are one yield. Skipping the email pull or the prospect
compact counts the previous checkpoint. Publishing the CSV is separate:
``cocli web export-emails`` calls this and then uploads.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from typing import Optional

from cocli.application.lead_export_service import LeadExportResult


def compile_customer_yield(
    campaign_name: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> LeadExportResult:
    """Pull worker results, fold them, and write the local CSV/USV.

    Does not upload. Raises ``RuntimeError`` when queue sync, the email
    pull, email compaction, or prospect compaction fails, before writing
    a count from a partial fold.
    """
    from cocli.application.data_sync_service import DataSyncService
    from cocli.application.index_service import IndexService
    from cocli.application.lead_export_service import export_enriched_emails
    from cocli.application.pi_sync_service import PiSyncService, describe_sync_results

    def log(msg: str) -> None:
        if log_callback:
            log_callback(msg)

    log(
        "Syncing gm-list/gm-details/enrichment results from workers "
        f"for {campaign_name}..."
    )
    try:
        subprocess.run(
            [
                "uv",
                "run",
                "cocli",
                "sync",
                "pi-results",
                "--campaign",
                campaign_name,
                "--force",
            ],
            check=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        log(f"Pi results sync failed: {exc}")
        raise RuntimeError(f"Pi results sync failed: {exc}") from exc

    log(f"Syncing email indexes from workers for {campaign_name}...")
    email_ok, email_detail = describe_sync_results(
        PiSyncService(campaign_name).sync_email_indexes()
    )
    if not email_ok:
        log(f"Email index sync failed: {email_detail}")
        raise RuntimeError(f"Email index sync failed: {email_detail}")
    log(f"Email index sync complete ({email_detail})")

    log(f"Compacting email index for {campaign_name}...")
    email_compact = DataSyncService(campaign_name).compact_index()
    if email_compact.get("status") != "success":
        detail = str(email_compact.get("message") or "email compact failed")
        log(f"Email compaction failed: {detail}")
        raise RuntimeError(f"Email compaction failed: {detail}")
    log(str(email_compact.get("message") or "Email index compacted"))

    log(f"Compacting google_maps_prospects index for {campaign_name}...")
    try:
        compact_result = IndexService(campaign_name).compact(
            index_name="google_maps_prospects",
            log_callback=log,
        )
    except Exception as exc:
        log(f"Prospect compaction failed: {exc}")
        raise RuntimeError(f"Prospect compaction failed: {exc}") from exc
    if not compact_result.success:
        log(f"Prospect compaction failed: {compact_result.message}")
        raise RuntimeError(f"Prospect compaction failed: {compact_result.message}")

    log("Regenerating export CSV...")
    export_result = export_enriched_emails(campaign_name)
    log(f"Exported {export_result.exported_count} companies")
    return export_result
