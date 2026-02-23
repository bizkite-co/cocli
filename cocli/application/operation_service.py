import logging
import asyncio
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass

from .services import ServiceContainer

logger = logging.getLogger(__name__)

@dataclass
class OperationMetadata:
    id: str
    title: str
    description: str
    category: str # 'reporting', 'sync', 'scaling', 'maintenance'

class OperationService:
    """
    Centralized registry and execution engine for all Cocli background tasks.
    Enables sharing operation logic between the TUI and CLI.
    """
    def __init__(self, campaign_name: str, services: Optional[ServiceContainer] = None):
        self.campaign_name = campaign_name
        self.services = services or ServiceContainer(campaign_name=campaign_name)
        
        # Define the Registry
        self.operations: Dict[str, OperationMetadata] = {
            "op_report": OperationMetadata(
                "op_report", "Campaign Report", 
                "Generates a full data funnel report, including prospect counts and queue depths.", 
                "reporting"
            ),
            "op_analyze_emails": OperationMetadata(
                "op_analyze_emails", "Email Analysis", 
                "Performs deep validation of found emails and domain patterns.", 
                "reporting"
            ),
            "op_sync_all": OperationMetadata(
                "op_sync_all", "Full S3 Sync", 
                "Synchronizes all campaign data from S3 to your local machine.", 
                "sync"
            ),
            "op_sync_gm_list": OperationMetadata(
                "op_sync_gm_list", "Sync GM List Queue", 
                "Synchronizes the Google Maps area search queue from S3.", 
                "sync"
            ),
            "op_sync_gm_details": OperationMetadata(
                "op_sync_gm_details", "Sync GM Details Queue", 
                "Synchronizes the Google Maps place detail queue from S3.", 
                "sync"
            ),
            "op_sync_enrichment": OperationMetadata(
                "op_sync_enrichment", "Sync Enrichment Queue", 
                "Synchronizes the website enrichment queue from S3.", 
                "sync"
            ),
            "op_sync_indexes": OperationMetadata(
                "op_sync_indexes", "Sync Indexes", 
                "Synchronizes checkpoint and witness indexes from S3.", 
                "sync"
            ),
            "op_scale_0": OperationMetadata("op_scale_0", "Stop Cloud Workers", "Sets Fargate service desired count to 0.", "scaling"),
            "op_scale_1": OperationMetadata("op_scale_1", "Scale to 1 Worker", "Sets Fargate service desired count to 1.", "scaling"),
            "op_scale_5": OperationMetadata("op_scale_5", "Scale to 5 Workers", "Sets Fargate service desired count to 5.", "scaling"),
            "op_scale_10": OperationMetadata("op_scale_10", "Scale to 10 Workers", "Sets Fargate service desired count to 10.", "scaling"),
            "op_compact_index": OperationMetadata(
                "op_compact_index", "Compact Index", 
                "Merges WAL files from S3 into the local checkpoint USV.", 
                "maintenance"
            ),
            "op_compile_lifecycle": OperationMetadata(
                "op_compile_lifecycle", "Compile Lifecycle", 
                "Builds the lifecycle index (scrape/detail dates) from local queues.", 
                "maintenance"
            ),
            "op_restore_names": OperationMetadata(
                "op_restore_names", "Restore Company Names", 
                "Restores company names from Google Maps index and writes provenance USVs.", 
                "maintenance"
            ),
            "op_push_queue": OperationMetadata(
                "op_push_queue", "Push Local Queue", 
                "Uploads locally generated enrichment tasks to S3.", 
                "maintenance"
            ),
            "op_audit_integrity": OperationMetadata(
                "op_audit_integrity", "Audit Campaign Integrity", 
                "Scans for cross-contamination between campaigns.", 
                "maintenance"
            ),
            "op_audit_queue": OperationMetadata(
                "op_audit_queue", "Audit Queue Completion", 
                "Verifies completed markers against the prospect index.", 
                "maintenance"
            ),
            "op_path_check": OperationMetadata(
                "op_path_check", "Cluster Path Check", 
                "Audits core data paths across local, PI cluster, and S3.", 
                "maintenance"
            )
        }

    def get_details(self, op_id: str) -> Optional[OperationMetadata]:
        return self.operations.get(op_id)

    async def execute(self, op_id: str, log_callback: Optional[Callable[[str], None]] = None) -> Dict[str, Any]:
        """
        Executes the specified operation asynchronously.
        This is the shared logic used by both the TUI and CLI.
        """
        op = self.get_details(op_id)
        if not op:
            raise ValueError(f"Unknown operation: {op_id}")

        logger.info(f"Executing operation: {op.title} ({op_id})")
        
        try:
            if op_id == "op_report":
                result = await asyncio.to_thread(self.services.reporting_service.get_campaign_stats)
            elif op_id == "op_sync_all":
                result = await asyncio.to_thread(self.services.data_sync_service.sync_all)
            elif op_id == "op_sync_gm_list":
                result = await asyncio.to_thread(self.services.data_sync_service.sync_queues, "gm-list")
            elif op_id == "op_sync_gm_details":
                result = await asyncio.to_thread(self.services.data_sync_service.sync_queues, "gm-details")
            elif op_id == "op_sync_enrichment":
                result = await asyncio.to_thread(self.services.data_sync_service.sync_queues, "enrichment")
            elif op_id == "op_sync_indexes":
                result = await asyncio.to_thread(self.services.data_sync_service.sync_indexes)
            elif op_id == "op_compact_index":
                result = await asyncio.to_thread(self.services.data_sync_service.compact_index)
            elif op_id == "op_compile_lifecycle":
                def run_compile() -> Dict[str, Any]:
                    gen = self.services.campaign_service.compile_lifecycle_index()
                    count = 0
                    for update in gen:
                        if not isinstance(update, dict):
                            count = update
                    return {"records_indexed": count}
                result = await asyncio.to_thread(run_compile)
            elif op_id == "op_restore_names":
                def run_restore() -> Dict[str, Any]:
                    gen = self.services.campaign_service.restore_names_from_index()
                    final: Dict[str, Any] = {}
                    for update in gen:
                        final = update
                    return final
                result = await asyncio.to_thread(run_restore)
            elif op_id == "op_push_queue":
                result = await asyncio.to_thread(self.services.data_sync_service.push_queue)
            elif op_id == "op_audit_integrity":
                result = await asyncio.to_thread(self.services.audit_service.audit_campaign_integrity)
            elif op_id == "op_audit_queue":
                result = await asyncio.to_thread(self.services.audit_service.audit_queue_completion)
            elif op_id == "op_path_check":
                # Default paths for quick check
                paths_to_check = ["wal/", "indexes/scraped_areas/", "indexes/scraped-tiles/"]
                def run_check() -> Dict[str, Any]:
                    return {"results": self.services.audit_service.audit_cluster_paths(paths_to_check)}
                result = await asyncio.to_thread(run_check)
            elif op_id == "op_analyze_emails":
                result = await asyncio.to_thread(self.services.reporting_service.get_email_analysis)
            elif "op_scale_" in op_id:
                count = int(op_id.replace("op_scale_", ""))
                result = await asyncio.to_thread(self.services.deployment_service.scale_service, count)
            else:
                raise NotImplementedError(f"Logic for {op_id} not implemented in OperationService")

            return {"status": "success", "op_id": op_id, "result": result}
        except Exception as e:
            logger.error(f"Operation {op_id} failed: {e}", exc_info=True)
            return {"status": "error", "op_id": op_id, "message": str(e)}
