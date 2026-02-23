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
    source_path: Optional[str] = None
    dest_path: Optional[str] = None
    process_details: Optional[str] = None

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
                "op_compact_index", "Compact Email Index", 
                "Merges email WAL files from S3 into the local checkpoint USV.", 
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/emails/inbox/",
                dest_path="data/campaigns/{campaign}/indexes/emails/shards/",
                process_details="Moves 'inbox/' USVs to a temporary shard before merging into 00-ff shards. deduplicates on 'email' field."
            ),
            "op_compile_lifecycle": OperationMetadata(
                "op_compile_lifecycle", "Compile Lifecycle", 
                "Builds the lifecycle index (scrape/detail dates) from local queues.", 
                "maintenance",
                source_path="data/campaigns/{campaign}/queues/gm-list/completed/",
                dest_path="data/campaigns/{campaign}/indexes/lifecycle.usv",
                process_details="Scans all completed task JSONs to extract 'scraped_at' and 'details_at' timestamps."
            ),
            "op_compact_prospects": OperationMetadata(
                "op_compact_prospects", "Compact Prospects Index", 
                "Merges completed GM results into the main checkpoint and cleans up queue files.", 
                "maintenance",
                source_path="data/campaigns/{campaign}/queues/gm-list/completed/results/",
                dest_path="data/campaigns/{campaign}/indexes/google_maps_prospects/prospects.checkpoint.usv",
                process_details="Consolidates high-precision results into 0.1-degree tiles, then appends to main checkpoint and deletes source USVs."
            ),
            "op_compile_top_prospects": OperationMetadata(
                "op_compile_top_prospects", "Compile Top Prospects", 
                "Identifies high-rating, highly-reviewed leads with contact info using DuckDB.", 
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/google_maps_prospects/",
                dest_path="data/companies/{slug}/",
                process_details="Filters DuckDB 'items' view for rating >= 4.5 and reviews >= 20. Tags matches with 'to-call'."
            ),
            "op_restore_names": OperationMetadata(
                "op_restore_names", "Restore Company Names", 
                "Restores company names from Google Maps index and writes provenance USVs.", 
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/google_maps_prospects/",
                dest_path="data/companies/{slug}/_index.md",
                process_details="Maps PlaceIDs to slugs, updates YAML 'name' field if current name is generic."
            ),
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
            elif op_id == "op_compact_prospects":
                def run_compaction() -> Dict[str, Any]:
                    from cocli.core.prospect_compactor import consolidate_campaign_results, compact_prospects_to_checkpoint
                    
                    # 1. Consolidate results into standard tiles
                    c_count = consolidate_campaign_results(self.campaign_name)
                    
                    # 2. Merge tiles into checkpoint
                    m_count = compact_prospects_to_checkpoint(self.campaign_name)
                    
                    return {"files_consolidated": c_count, "prospects_merged": m_count}
                result = await asyncio.to_thread(run_compaction)
            elif op_id == "op_compile_top_prospects":
                def run_compile() -> Dict[str, Any]:
                    from .search_service import get_fuzzy_search_results
                    filters = {"has_contact_info": True}
                    results = get_fuzzy_search_results(
                        "", 
                        item_type="company", 
                        campaign_name=self.campaign_name,
                        filters=filters,
                        sort_by="rating",
                        limit=500
                    )
                    top_prospects = [r for r in results if (r.average_rating or 0) >= 4.5 and (r.reviews_count or 0) >= 20]
                    tagged = 0
                    from cocli.models.companies.company import Company
                    for p in top_prospects:
                        if p.slug:
                            company = Company.get(p.slug)
                            if company and "to-call" not in company.tags:
                                company.tags.append("to-call")
                                company.save()
                                tagged += 1
                    return {"top_candidates_found": len(top_prospects), "newly_tagged": tagged}
                result = await asyncio.to_thread(run_compile)
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
