import logging
import asyncio
from typing import Any, Dict, Optional, Callable, List
from dataclasses import dataclass, field as dataclass_field

from .services import ServiceContainer

logger = logging.getLogger(__name__)

@dataclass
class OperationStep:
    name: str
    description: str

@dataclass
class OperationMetadata:
    id: str
    title: str
    description: str
    category: str # 'reporting', 'sync', 'scaling', 'maintenance'
    source_path: Optional[str] = None
    dest_path: Optional[str] = None
    process_details: Optional[str] = None
    steps: List[OperationStep] = dataclass_field(default_factory=list)

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
                process_details="Moves 'inbox/' USVs to a temporary shard before merging into 00-ff shards. deduplicates on 'email' field.",
                steps=[
                    OperationStep("s3_sync_down", "Pull latest email WAL files from S3."),
                    OperationStep("offline_inbox", "Move inbox files to processing directory."),
                    OperationStep("merge_shards", "Deduplicate and merge into 00-ff shards."),
                    OperationStep("s3_sync_up", "Push updated shards to S3."),
                    OperationStep("cleanup", "Remove processing directory.")
                ]
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
                process_details="Consolidates high-precision results into 0.1-degree tiles, then appends to main checkpoint and deletes source USVs.",
                steps=[
                    OperationStep("s3_sync_down", "Pull latest results from S3."),
                    OperationStep("consolidate_tiles", "Align results to 0.1-degree tiles."),
                    OperationStep("merge_checkpoint", "Append results to main checkpoint."),
                    OperationStep("s3_sync_up", "Push updated checkpoint to S3."),
                    OperationStep("cleanup", "Delete source USV result files.")
                ]
            ),
            "op_compile_to_call": OperationMetadata(
                "op_compile_to_call", "Compile To-Call List", 
                "Full workflow: Compacts GM and Email indexes, then identifies top leads for calling.", 
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/",
                dest_path="data/companies/{slug}/",
                process_details="1. Compacts GM results. 2. Compacts Email shards. 3. Filters rating >= 4.5, reviews >= 20, HAS email/phone. 4. Tags results as 'to-call'.",
                steps=[
                    OperationStep("compact_gm", "Run full Google Maps index compaction."),
                    OperationStep("compact_emails", "Run full Email index compaction."),
                    OperationStep("identify_leads", "Filter DuckDB for high-rating/reviewed leads with contact info."),
                    OperationStep("tag_leads", "Add 'to-call' tag to matching companies.")
                ]
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

    async def execute(
        self, 
        op_id: str, 
        log_callback: Optional[Callable[[str], None]] = None,
        step_callback: Optional[Callable[[str, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes the specified operation asynchronously.
        This is the shared logic used by both the TUI and CLI.
        """
        from datetime import datetime, UTC
        from pathlib import Path
        op = self.get_details(op_id)
        if not op:
            raise ValueError(f"Unknown operation: {op_id}")

        logger.info(f"Executing operation: {op.title} ({op_id})")
        
        # 1. Initialize Durable Run Log
        run_ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        run_file: Optional[Path] = None
        
        # Determine index context for run log
        index_map = {
            "op_compact_index": "emails",
            "op_compact_prospects": "google_maps_prospects",
            "op_compile_to_call": "google_maps_prospects" # Primary anchor
        }
        
        from ..core.paths import paths
        if op_id in index_map:
            idx_name = index_map[op_id]
            run_dir = paths.campaign(self.campaign_name).index(idx_name).runs
            run_dir.mkdir(parents=True, exist_ok=True)
            run_file = run_dir / f"{run_ts}_{op_id}.usv"
            logger.info(f"Durable Run Log: {run_file}")
            
            # Write Header
            from cocli.core.constants import UNIT_SEP
            try:
                with open(run_file, "w") as f:
                    f.write(UNIT_SEP.join(["timestamp", "step", "status", "details"]) + "\n")
            except Exception as e:
                logger.error(f"Failed to create run log file: {e}")
                run_file = None

        def log_step(step_name: str, status: str, details: str = "") -> None:
            if run_file:
                ts = datetime.now(UTC).isoformat()
                from cocli.core.constants import UNIT_SEP
                try:
                    with open(run_file, "a") as f:
                        f.write(UNIT_SEP.join([ts, step_name, status, details]) + "\n")
                except Exception as e:
                    logger.error(f"Failed to write to run log: {e}")
            
            msg = f"[{status.upper()}] {step_name}: {details}"
            logger.info(msg)
            if log_callback:
                log_callback(msg + "\n")
            if step_callback:
                step_callback(step_name, status)

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
                async def run_compaction() -> Dict[str, Any]:
                    log_step("s3_sync_down", "pending", "Pulling latest email WAL files from S3...")
                    await asyncio.to_thread(self.services.data_sync_service.sync_emails)
                    log_step("s3_sync_down", "success")

                    log_step("offline_inbox", "pending")
                    # Offline logic is integrated in Manager.compact()
                    log_step("offline_inbox", "success")

                    log_step("merge_shards", "pending")
                    from ..core.email_index_manager import EmailIndexManager
                    email_manager = EmailIndexManager(self.campaign_name)
                    await asyncio.to_thread(email_manager.compact)
                    log_step("merge_shards", "success")

                    log_step("s3_sync_up", "pending", "Pushing updated shards to S3...")
                    await asyncio.to_thread(self.services.data_sync_service.sync_emails)
                    log_step("s3_sync_up", "success")
                    
                    log_step("cleanup", "success")
                    return {"status": "success"}
                result = await run_compaction()
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
                async def run_compaction() -> Dict[str, Any]:
                    log_step("s3_sync_down", "pending", "Pulling latest GM results from S3...")
                    await asyncio.to_thread(self.services.data_sync_service.sync_prospects)
                    log_step("s3_sync_down", "success")

                    log_step("consolidate_tiles", "pending")
                    from cocli.core.prospect_compactor import consolidate_campaign_results, compact_prospects_to_checkpoint
                    await asyncio.to_thread(consolidate_campaign_results, self.campaign_name)
                    log_step("consolidate_tiles", "success")
                    
                    log_step("merge_checkpoint", "pending")
                    m_count = await asyncio.to_thread(compact_prospects_to_checkpoint, self.campaign_name)
                    log_step("merge_checkpoint", "success", f"Merged {m_count} records")
                    
                    log_step("s3_sync_up", "pending", "Pushing updated checkpoint to S3...")
                    await asyncio.to_thread(self.services.data_sync_service.sync_prospects)
                    log_step("s3_sync_up", "success")
                    
                    log_step("cleanup", "success")
                    return {"prospects_merged": m_count}
                result = await run_compaction()
            elif op_id == "op_compile_to_call":
                async def run_workflow() -> Dict[str, Any]:
                    report: Dict[str, Any] = {"steps": []}
                    
                    log_step("compact_gm", "pending", "Running GM index compaction...")
                    from cocli.core.prospect_compactor import consolidate_campaign_results, compact_prospects_to_checkpoint
                    await asyncio.to_thread(consolidate_campaign_results, self.campaign_name)
                    m_count = await asyncio.to_thread(compact_prospects_to_checkpoint, self.campaign_name)
                    log_step("compact_gm", "success", f"{m_count} records merged")

                    log_step("compact_emails", "pending", "Running Email index compaction...")
                    from ..core.email_index_manager import EmailIndexManager
                    email_manager = EmailIndexManager(self.campaign_name)
                    await asyncio.to_thread(email_manager.compact)
                    log_step("compact_emails", "success")

                    log_step("identify_leads", "pending", "Identifying top leads via DuckDB...")
                    from .search_service import get_fuzzy_search_results
                    filters = {"has_contact_info": True}
                    results = await asyncio.to_thread(
                        get_fuzzy_search_results, 
                        "", 
                        item_type="company", 
                        campaign_name=self.campaign_name,
                        filters=filters,
                        sort_by="rating",
                        limit=1000
                    )
                    top_prospects = [r for r in results if (r.average_rating or 0) >= 4.5 and (r.reviews_count or 0) >= 20]
                    log_step("identify_leads", "success", f"Found {len(top_prospects)} leads")
                    
                    log_step("tag_leads", "pending")
                    tagged = 0
                    from cocli.models.companies.company import Company
                    for p in top_prospects:
                        if p.slug:
                            company = await asyncio.to_thread(Company.get, p.slug)
                            if company and "to-call" not in company.tags:
                                # toggle_to_call now handles both the tag and the filesystem queue USV
                                await asyncio.to_thread(company.toggle_to_call)
                                tagged += 1
                    log_step("tag_leads", "success", f"Tagged {tagged} new leads")
                    
                    report["top_leads_found"] = len(top_prospects)
                    report["newly_tagged"] = tagged
                    return report
                result = await run_workflow()
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
