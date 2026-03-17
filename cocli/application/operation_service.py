# POLICY: frictionless-data-policy-enforcement
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
    category: str  # 'reporting', 'sync', 'scaling', 'maintenance'
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
        import socket
        import os

        self.campaign_name = campaign_name
        self.services = services or ServiceContainer(campaign_name=campaign_name)
        self.processed_by = (
            os.getenv("COCLI_HOSTNAME") or socket.gethostname().split(".")[0]
        )

        # Define the Registry
        self.operations: Dict[str, OperationMetadata] = {
            "op_report": OperationMetadata(
                "op_report",
                "Campaign Report",
                "Generates a full data funnel report, including prospect counts and queue depths.",
                "reporting",
            ),
            "op_analyze_emails": OperationMetadata(
                "op_analyze_emails",
                "Email Analysis",
                "Performs deep validation of found emails and domain patterns.",
                "reporting",
            ),
            "op_sync_all": OperationMetadata(
                "op_sync_all",
                "Full S3 Sync",
                "Synchronizes all campaign data from S3 to your local machine.",
                "sync",
            ),
            "op_sync_gm_list": OperationMetadata(
                "op_sync_gm_list",
                "Sync GM List Queue",
                "Synchronizes the Google Maps area search queue from S3.",
                "sync",
            ),
            "op_sync_gm_details": OperationMetadata(
                "op_sync_gm_details",
                "Sync GM Details Queue",
                "Synchronizes the Google Maps place detail queue from S3.",
                "sync",
            ),
            "op_sync_enrichment": OperationMetadata(
                "op_sync_enrichment",
                "Sync Enrichment Queue",
                "Synchronizes the website enrichment queue from S3.",
                "sync",
            ),
            "op_sync_indexes": OperationMetadata(
                "op_sync_indexes",
                "Sync Indexes",
                "Synchronizes checkpoint and witness indexes from S3.",
                "sync",
            ),
            "op_scale_0": OperationMetadata(
                "op_scale_0",
                "Stop Cloud Workers",
                "Sets Fargate service desired count to 0.",
                "scaling",
            ),
            "op_scale_1": OperationMetadata(
                "op_scale_1",
                "Scale to 1 Worker",
                "Sets Fargate service desired count to 1.",
                "scaling",
            ),
            "op_scale_5": OperationMetadata(
                "op_scale_5",
                "Scale to 5 Workers",
                "Sets Fargate service desired count to 5.",
                "scaling",
            ),
            "op_scale_10": OperationMetadata(
                "op_scale_10",
                "Scale to 10 Workers",
                "Sets Fargate service desired count to 10.",
                "scaling",
            ),
            "op_compact_index": OperationMetadata(
                "op_compact_index",
                "Compact Email Index",
                "Merges email WAL files from S3 into the local checkpoint USV.",
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/emails/inbox/",
                dest_path="data/campaigns/{campaign}/indexes/emails/shards/",
                process_details="Moves 'inbox/' USVs to a temporary shard before merging into 00-ff shards. deduplicates on 'email' field.",
                steps=[
                    OperationStep(
                        "s3_sync_down", "Pull latest email WAL files from S3."
                    ),
                    OperationStep(
                        "offline_inbox", "Move inbox files to processing directory."
                    ),
                    OperationStep(
                        "merge_shards", "Deduplicate and merge into 00-ff shards."
                    ),
                    OperationStep("s3_sync_up", "Push updated shards to S3."),
                    OperationStep("cleanup", "Remove processing directory."),
                ],
            ),
            "op_compile_lifecycle": OperationMetadata(
                "op_compile_lifecycle",
                "Compile Lifecycle",
                "Builds the lifecycle index (scrape/detail dates) from local queues.",
                "maintenance",
                source_path="data/campaigns/{campaign}/queues/gm-list/completed/",
                dest_path="data/campaigns/{campaign}/indexes/lifecycle.usv",
                process_details="Scans all completed task JSONs to extract 'scraped_at' and 'details_at' timestamps.",
            ),
            "op_compact_prospects": OperationMetadata(
                "op_compact_prospects",
                "Compact Prospects Index",
                "Merges completed GM results into the main checkpoint and cleans up queue files.",
                "maintenance",
                source_path="data/campaigns/{campaign}/queues/gm-list/completed/results/",
                dest_path="data/campaigns/{campaign}/indexes/google_maps_prospects/prospects.checkpoint.usv",
                process_details="Consolidates high-precision results into 0.1-degree tiles, then appends to main checkpoint and deletes source USVs.",
                steps=[
                    OperationStep("s3_sync_down", "Pull latest results from S3."),
                    OperationStep(
                        "consolidate_tiles", "Align results to 0.1-degree tiles."
                    ),
                    OperationStep(
                        "merge_checkpoint", "Append results to main checkpoint."
                    ),
                    OperationStep("s3_sync_up", "Push updated checkpoint to S3."),
                    OperationStep("cleanup", "Delete source USV result files."),
                ],
            ),
            "op_compile_to_call": OperationMetadata(
                "op_compile_to_call",
                "Compile To-Call List",
                "Full workflow: Compacts GM and Email indexes, then identifies top leads for calling.",
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/",
                dest_path="data/companies/{slug}/",
                process_details="1. Compacts GM results. 2. Compacts Email shards. 3. Filters rating >= 4.5, reviews >= 20, HAS email/phone. 4. Tags results as 'to-call'.",
                steps=[
                    OperationStep(
                        "compact_gm", "Run full Google Maps index compaction."
                    ),
                    OperationStep("compact_emails", "Run full Email index compaction."),
                    OperationStep(
                        "identify_leads",
                        "Filter DuckDB for high-rating/reviewed leads with contact info.",
                    ),
                    OperationStep(
                        "tag_leads", "Add 'to-call' tag to matching companies."
                    ),
                ],
            ),
            "op_compile_top_prospects": OperationMetadata(
                "op_compile_top_prospects",
                "Compile Top Prospects",
                "Identifies high-rating, highly-reviewed leads with contact info using DuckDB.",
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/google_maps_prospects/",
                dest_path="data/companies/{slug}/",
                process_details="Filters DuckDB 'items' view for rating >= 4.5 and reviews >= 20. Tags matches with 'to-call'.",
            ),
            "op_restore_names": OperationMetadata(
                "op_restore_names",
                "Restore Company Names",
                "Restores company names from Google Maps index and writes provenance USVs.",
                "maintenance",
                source_path="data/campaigns/{campaign}/indexes/google_maps_prospects/",
                dest_path="data/companies/{slug}/_index.md",
                process_details="Maps PlaceIDs to slugs, updates YAML 'name' field if current name is generic.",
            ),
            "op_scrape_details": OperationMetadata(
                "op_scrape_details",
                "Scrape Company Details",
                "Runs a local browser to scrape full Google Maps details for a specific Place ID.",
                "maintenance",
                process_details="Uses Playwright locally to fetch ratings, reviews, and social links for a given place_id.",
            ),
            "op_re_enrich": OperationMetadata(
                "op_re_enrich",
                "Re-enrich Company Website",
                "Runs a local browser to perform website-level enrichment (emails, socials) for a specific domain.",
                "maintenance",
                process_details="Uses Playwright locally to crawl the company's website and extract contact info.",
            ),
            "op_refresh_dev": OperationMetadata(
                "op_refresh_dev",
                "Refresh DEV from PROD",
                "Clones local PROD data into the DEV environment using rsync.",
                "maintenance",
                process_details="Safe, isolated refresh of local development data. Excludes transient logs and WAL files.",
            ),
            "op_sanitize_discovery": OperationMetadata(
                "op_sanitize_discovery",
                "Sanitize Discovery Results",
                "Full workflow: Pulls from S3, purges non-conforming/hollow USVs, pushes to S3, and propagates to PIs.",
                "maintenance",
                source_path="data/campaigns/{campaign}/queues/gm-list/completed/results/",
                steps=[
                    OperationStep(
                        "s3_sync_down",
                        "Pull latest results from S3 to ensure no data loss.",
                    ),
                    OperationStep(
                        "aggressive_cleanup",
                        "Purge non-conforming paths and hollow USVs locally.",
                    ),
                    OperationStep(
                        "s3_sync_up", "Push deletions to S3 (Standardizing the cloud)."
                    ),
                    OperationStep(
                        "cluster_propagate",
                        "Propagate the sanitized state to all cluster nodes.",
                    ),
                ],
            ),
            "op_rollout_discovery": OperationMetadata(
                "op_rollout_discovery",
                "Discovery Batch Rollout",
                "Full discovery rollout: 1. Create named batch. 2. Build mission index. 3. Propagate tasks to cluster.",
                "maintenance",
                steps=[
                    OperationStep(
                        "create_batch", "Extract fresh tasks from the frontier USV."
                    ),
                    OperationStep(
                        "build_index",
                        "Activate tasks into the discovery-gen completed pool.",
                    ),
                    OperationStep(
                        "cluster_push", "Propagate active tasks to all cluster PIs."
                    ),
                ],
            ),
            "op_purge_pending": OperationMetadata(
                "op_purge_pending",
                "Purge Pending Tasks",
                "Forcefully clears expired leases and vestigial tasks from the GM list queue.",
                "maintenance",
                steps=[
                    OperationStep("s3_sync_down", "Pull latest queue state from S3."),
                    OperationStep(
                        "aggressive_cleanup",
                        "Purge expired leases and non-conforming tasks.",
                    ),
                    OperationStep("s3_sync_up", "Push cleaned state to S3."),
                ],
            ),
        }

    def get_details(self, op_id: str) -> Optional[OperationMetadata]:
        return self.operations.get(op_id)

    async def execute(
        self,
        op_id: str,
        log_callback: Optional[Callable[[str], None]] = None,
        step_callback: Optional[Callable[[str, str], None]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Executes the specified operation asynchronously.
        This is the shared logic used by both the TUI and CLI.
        """
        params = params or {}
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
            "op_compile_to_call": "google_maps_prospects",  # Primary anchor
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
                    f.write(
                        UNIT_SEP.join(["timestamp", "step", "status", "details"]) + "\n"
                    )
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
                result = await asyncio.to_thread(
                    self.services.reporting_service.get_campaign_stats
                )
            elif op_id == "op_sync_all":
                result = await asyncio.to_thread(
                    self.services.data_sync_service.sync_all
                )
            elif op_id == "op_sync_gm_list":
                result = await asyncio.to_thread(
                    self.services.data_sync_service.sync_queues, "gm-list"
                )
            elif op_id == "op_sync_gm_details":
                result = await asyncio.to_thread(
                    self.services.data_sync_service.sync_queues, "gm-details"
                )
            elif op_id == "op_sync_enrichment":
                result = await asyncio.to_thread(
                    self.services.data_sync_service.sync_queues, "enrichment"
                )
            elif op_id == "op_sync_indexes":
                result = await asyncio.to_thread(
                    self.services.data_sync_service.sync_indexes
                )
            elif op_id == "op_compact_index":

                async def run_compaction() -> Dict[str, Any]:
                    log_step(
                        "s3_sync_down",
                        "pending",
                        "Pulling latest email WAL files from S3...",
                    )
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
                result = await asyncio.to_thread(
                    self.services.data_sync_service.push_queue
                )
            elif op_id == "op_audit_integrity":
                result = await asyncio.to_thread(
                    self.services.audit_service.audit_campaign_integrity
                )
            elif op_id == "op_audit_queue":
                result = await asyncio.to_thread(
                    self.services.audit_service.audit_queue_completion
                )
            elif op_id == "op_path_check":
                # Default paths for quick check
                paths_to_check = [
                    "wal/",
                    "indexes/scraped_areas/",
                    "indexes/scraped-tiles/",
                ]

                def run_check() -> Dict[str, Any]:
                    return {
                        "results": self.services.audit_service.audit_cluster_paths(
                            paths_to_check
                        )
                    }

                result = await asyncio.to_thread(run_check)
            elif op_id == "op_compact_prospects":

                async def run_compaction() -> Dict[str, Any]:
                    log_step(
                        "s3_sync_down",
                        "pending",
                        "Pulling latest GM results from S3...",
                    )
                    await asyncio.to_thread(
                        self.services.data_sync_service.sync_prospects
                    )
                    log_step("s3_sync_down", "success")

                    log_step("consolidate_tiles", "pending")
                    from cocli.core.prospect_compactor import (
                        consolidate_campaign_results,
                        compact_prospects_to_checkpoint,
                    )

                    await asyncio.to_thread(
                        consolidate_campaign_results, self.campaign_name
                    )
                    log_step("consolidate_tiles", "success")

                    log_step("merge_checkpoint", "pending")
                    m_count = await asyncio.to_thread(
                        compact_prospects_to_checkpoint, self.campaign_name
                    )
                    log_step("merge_checkpoint", "success", f"Merged {m_count} records")

                    log_step(
                        "s3_sync_up", "pending", "Pushing updated checkpoint to S3..."
                    )
                    await asyncio.to_thread(
                        self.services.data_sync_service.sync_prospects
                    )
                    log_step("s3_sync_up", "success")

                    log_step("cleanup", "success")
                    return {"prospects_merged": m_count}

                result = await run_compaction()
            elif op_id == "op_compile_to_call":

                async def run_workflow() -> Dict[str, Any]:
                    report: Dict[str, Any] = {"steps": []}

                    log_step("compact_gm", "pending", "Running GM index compaction...")
                    from cocli.core.prospect_compactor import (
                        consolidate_campaign_results,
                        compact_prospects_to_checkpoint,
                    )

                    await asyncio.to_thread(
                        consolidate_campaign_results, self.campaign_name
                    )
                    m_count = await asyncio.to_thread(
                        compact_prospects_to_checkpoint, self.campaign_name
                    )
                    log_step("compact_gm", "success", f"{m_count} records merged")

                    log_step(
                        "compact_emails", "pending", "Running Email index compaction..."
                    )
                    from ..core.email_index_manager import EmailIndexManager

                    email_manager = EmailIndexManager(self.campaign_name)
                    await asyncio.to_thread(email_manager.compact)
                    log_step("compact_emails", "success")

                    log_step(
                        "identify_leads",
                        "pending",
                        "Identifying top leads via DuckDB...",
                    )
                    from .search_service import get_fuzzy_search_results

                    filters = {"has_contact_info": True}
                    # Get candidates with contact info
                    results = await asyncio.to_thread(
                        get_fuzzy_search_results,
                        "",
                        item_type="company",
                        campaign_name=self.campaign_name,
                        filters=filters,
                        limit=2000,  # Larger pool to find the absolute best
                    )

                    # Sort by Rating * Reviews Count descending
                    top_prospects = [
                        p
                        for p in results
                        if p.average_rating is not None and p.reviews_count is not None
                    ]
                    top_prospects.sort(
                        key=lambda x: (x.average_rating or 0) * (x.reviews_count or 0),
                        reverse=True,
                    )

                    log_step(
                        "identify_leads",
                        "success",
                        f"Identified {len(top_prospects)} candidates (filtered)",
                    )

                    log_step("tag_leads", "pending")
                    tagged = 0
                    limit = params.get("limit")
                    from cocli.models.companies.company import Company

                    for p in top_prospects:
                        if limit and tagged >= limit:
                            break

                        if p.slug:
                            company = await asyncio.to_thread(Company.get, p.slug)
                            if company:
                                score = (p.average_rating or 0) * (p.reviews_count or 0)
                                logger.info(
                                    f"Processing Lead: {p.slug} | Score: {score:.1f} (R: {p.average_rating}, C: {p.reviews_count})"
                                )

                                # Hydrate metadata from index if missing or messy
                                if (
                                    p.average_rating is not None
                                    and not company.average_rating
                                ):
                                    company.average_rating = p.average_rating
                                if (
                                    p.reviews_count is not None
                                    and not company.reviews_count
                                ):
                                    company.reviews_count = p.reviews_count

                                # CLEAN NAME: Remove double quotes that often plague YAML frontmatter from messy USV imports
                                if p.name:
                                    clean_name = p.name.strip("\"'")
                                    if clean_name and clean_name != company.name:
                                        company.name = clean_name

                                if "to-call" not in company.tags:
                                    # toggle_to_call now handles both the tag and the filesystem queue USV
                                    await asyncio.to_thread(company.toggle_to_call)
                                    tagged += 1
                                    logger.info(f"Tagged {p.slug}")
                                else:
                                    # Already tagged, but might have updated metadata (rating/reviews/clean name)
                                    await asyncio.to_thread(company.save)
                                    logger.info(f"Already tagged {p.slug}")
                            else:
                                logger.warning(f"Could not load company {p.slug}")
                        else:
                            logger.warning(f"Prospect {p} has no slug")

                    log_step(
                        "tag_leads",
                        "success",
                        f"Processed {len(top_prospects)} leads, tagged {tagged} new",
                    )

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
                        limit=500,
                    )
                    top_prospects = [
                        r
                        for r in results
                        if (r.average_rating or 0) >= 4.5
                        and (r.reviews_count or 0) >= 20
                    ]
                    tagged = 0
                    from cocli.models.companies.company import Company

                    for p in top_prospects:
                        if p.slug:
                            company = Company.get(p.slug)
                            if company and "to-call" not in company.tags:
                                company.tags.append("to-call")
                                company.save()
                                tagged += 1
                    return {
                        "top_candidates_found": len(top_prospects),
                        "newly_tagged": tagged,
                    }

                result = await asyncio.to_thread(run_compile)
            elif op_id == "op_analyze_emails":
                result = await asyncio.to_thread(
                    self.services.reporting_service.get_email_analysis
                )
            elif op_id == "op_scrape_details":

                async def run_local_scrape() -> Dict[str, Any]:
                    place_id = params.get("place_id")
                    slug = params.get("company_slug")
                    if not place_id:
                        raise ValueError("No place_id provided for scrape")

                    from ..models.campaigns.queues.gm_details import GmItemTask
                    from .processors.google_maps import GoogleMapsDetailsProcessor
                    from playwright.async_api import async_playwright

                    task = GmItemTask(
                        place_id=place_id,
                        company_slug=slug or "",
                        campaign_name=self.campaign_name,
                        force_refresh=True,
                    )

                    log_step("browser_init", "pending")
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True)
                        context = await browser.new_context()
                        page = await context.new_page()
                        log_step("browser_init", "success")

                        log_step("scrape", "pending")
                        processor = GoogleMapsDetailsProcessor(processed_by="local-tui")
                        prospect = await processor.process(task, page, debug=True)

                        await browser.close()

                        if prospect:
                            log_step(
                                "scrape",
                                "success",
                                f"Captured Rating: {prospect.average_rating}",
                            )
                            return prospect.model_dump()
                        else:
                            log_step("scrape", "error", "No data captured")
                            return {"status": "error"}

                result = await run_local_scrape()
            elif op_id == "op_re_enrich":

                async def run_local_enrichment() -> Dict[str, Any]:
                    slug = params.get("company_slug")
                    domain = params.get("domain")
                    if not slug or not domain:
                        raise ValueError(
                            "company_slug and domain are required for re-enrichment"
                        )

                    from ..core.enrichment import enrich_company_website
                    from ..models.companies.company import Company
                    from ..models.campaigns.campaign import Campaign
                    from playwright.async_api import async_playwright

                    log_step("browser_init", "pending")
                    async with async_playwright() as p:
                        browser = await p.chromium.launch(headless=True)
                        context = await browser.new_context()
                        log_step("browser_init", "success")

                        try:
                            campaign_obj = Campaign.load(self.campaign_name)
                            company = Company.get(slug) or Company(
                                name=slug, domain=domain, slug=slug
                            )

                            log_step(
                                "enrich",
                                "pending",
                                f"Enriching website for {domain}...",
                            )
                            website_data = await enrich_company_website(
                                browser=context,
                                company=company,
                                campaign=campaign_obj,
                                force=True,
                                debug=True,
                                processed_by=self.processed_by,
                            )

                            if website_data:
                                website_data.save(slug)
                                log_step(
                                    "enrich",
                                    "success",
                                    f"Captured {len(website_data.all_emails)} emails",
                                )
                                return website_data.model_dump()
                            else:
                                log_step("enrich", "error", "No data captured")
                                return {"status": "error"}
                        finally:
                            await browser.close()

                result = await run_local_enrichment()
            elif op_id == "op_refresh_dev":

                async def run_refresh() -> Dict[str, Any]:
                    from ..core.environment import get_environment, Environment
                    import subprocess
                    import os
                    from pathlib import Path

                    env = get_environment()
                    if env == Environment.PROD:
                        raise ValueError("Cannot refresh-dev while in PROD mode.")

                    # 1. Resolve Roots
                    # We need the real PROD root
                    if "COCLI_DATA_HOME" in os.environ:
                        prod_root = (
                            Path(os.environ["COCLI_DATA_HOME"]).expanduser().resolve()
                        )
                    else:
                        # Fallback to standard prod path logic
                        import platform

                        if platform.system() == "Windows":
                            base = (
                                Path(
                                    os.environ.get(
                                        "LOCALAPPDATA",
                                        Path.home() / "AppData" / "Local",
                                    )
                                )
                                / "cocli"
                            )
                        elif platform.system() == "Darwin":
                            base = (
                                Path.home()
                                / "Library"
                                / "Application Support"
                                / "cocli"
                            )
                        else:
                            base = Path.home() / ".local" / "share" / "cocli"
                        prod_root = base / "data"

                    target_root = prod_root.parent / f"{prod_root.name}_{env.value}"

                    log_step(
                        "env_check",
                        "success",
                        f"Refreshing {env.value} from {prod_root}",
                    )

                    # 2. Execute rsync
                    log_step("rsync", "pending", "Syncing local files...")
                    excludes = ["wal", "logs", "recovery", "*.usv.wal", "temp"]
                    cmd = ["rsync", "-av", "--delete"]
                    for ex in excludes:
                        cmd.extend(["--exclude", ex])

                    cmd.append(str(prod_root) + "/")
                    cmd.append(str(target_root) + "/")

                    try:
                        res = subprocess.run(
                            cmd, capture_output=True, text=True, check=True
                        )
                        log_step("rsync", "success", "Local refresh complete")
                        return {"status": "success", "rsync_output": res.stdout}
                    except subprocess.CalledProcessError as e:
                        log_step("rsync", "error", f"rsync failed: {e.stderr}")
                        return {"status": "error", "message": e.stderr}

                result = await run_refresh()
            elif op_id == "op_sanitize_discovery":

                async def run_sanitization() -> Dict[str, Any]:
                    from ..services.cluster_service import ClusterService
                    from pathlib import Path
                    import importlib.util
                    import sys

                    project_root = Path(__file__).parent.parent.parent.resolve()
                    script_path = (
                        project_root / "scripts" / "cleanup_discovery_results.py"
                    )

                    spec = importlib.util.spec_from_file_location(
                        "cleanup_discovery_results", str(script_path)
                    )
                    if not spec or not spec.loader:
                        raise ImportError(f"Could not load script at {script_path}")

                    module = importlib.util.module_from_spec(spec)
                    sys.modules["cleanup_discovery_results"] = module
                    spec.loader.exec_module(module)

                    log_step("s3_sync_down", "pending")
                    await asyncio.to_thread(
                        self.services.data_sync_service.sync_prospects
                    )
                    log_step("s3_sync_down", "success")

                    log_step(
                        "aggressive_cleanup",
                        "pending",
                        "Purging non-conforming and hollow USVs...",
                    )
                    await asyncio.to_thread(
                        module.cleanup_discovery_results,
                        self.campaign_name,
                        execute=True,
                        push=False,
                        delete_hollow=True,
                    )

                    # Also cleanup the gm-list pending queue (leases/tasks)
                    log_step(
                        "aggressive_cleanup",
                        "pending",
                        "Purging vestigial worker tasks...",
                    )
                    import importlib.util

                    pending_script = (
                        project_root / "scripts" / "cleanup_gm_list_pending.py"
                    )
                    p_spec = importlib.util.spec_from_file_location(
                        "cleanup_gm_list_pending", str(pending_script)
                    )
                    if p_spec and p_spec.loader:
                        p_mod = importlib.util.module_from_spec(p_spec)
                        p_spec.loader.exec_module(p_mod)
                        await asyncio.to_thread(
                            p_mod.cleanup_pending_queue,
                            self.campaign_name,
                            dry_run=False,
                        )

                    log_step("aggressive_cleanup", "success")

                    log_step("s3_sync_up", "pending", "Pushing deletions to S3...")
                    await asyncio.to_thread(
                        module.cleanup_discovery_results,
                        self.campaign_name,
                        execute=False,
                        push=True,
                    )
                    log_step("s3_sync_up", "success")

                    log_step(
                        "cluster_propagate",
                        "pending",
                        "Syncing clean state to cluster nodes...",
                    )
                    cluster = ClusterService(self.campaign_name)
                    # ClusterService.push_data already uses -rtz and timeout
                    await cluster.push_data(delete=True)
                    log_step("cluster_propagate", "success")

                    return {"status": "success"}

                result = await run_sanitization()
            elif op_id == "op_purge_pending":

                async def run_purge() -> Dict[str, Any]:
                    from pathlib import Path
                    import importlib.util

                    project_root = Path(__file__).parent.parent.parent.resolve()
                    pending_script = (
                        project_root / "scripts" / "cleanup_gm_list_pending.py"
                    )

                    p_spec = importlib.util.spec_from_file_location(
                        "cleanup_gm_list_pending", str(pending_script)
                    )
                    if not p_spec or not p_spec.loader:
                        raise ImportError(f"Could not load script at {pending_script}")
                    p_mod = importlib.util.module_from_spec(p_spec)
                    p_spec.loader.exec_module(p_mod)

                    log_step(
                        "s3_sync_down", "pending", "Pulling latest queue from S3..."
                    )
                    await asyncio.to_thread(
                        self.services.data_sync_service.sync_queues, "gm-list"
                    )
                    log_step("s3_sync_down", "success")

                    log_step(
                        "aggressive_cleanup",
                        "pending",
                        "Purging expired leases and vestigial tasks...",
                    )
                    await asyncio.to_thread(
                        p_mod.cleanup_pending_queue, self.campaign_name, dry_run=False
                    )
                    log_step("aggressive_cleanup", "success")

                    log_step("s3_sync_up", "pending", "Pushing clean queue to S3...")
                    # Sync logic inside cleanup script is better than bulk sync for deletions
                    await asyncio.to_thread(self.services.data_sync_service.push_queue)
                    log_step("s3_sync_up", "success")

                    return {"status": "success"}

                result = await run_purge()
            elif op_id == "op_rollout_discovery":

                async def run_rollout() -> Dict[str, Any]:
                    batch_name = params.get("batch_name", f"rollout_{int(time.time())}")
                    limit = int(params.get("limit", 50))
                    ttl_days = int(params.get("ttl_days", 30))
                    purge = params.get("purge", False)

                    log_step(
                        "create_batch",
                        "pending",
                        f"Creating batch '{batch_name}' (Limit: {limit}, TTL: {ttl_days}d)...",
                    )

                    from ..models.campaigns.mission import MissionTask
                    from ..core.scrape_index import ScrapeIndex
                    from ..core.paths import paths
                    import toml
                    import shutil

                    campaign_dir = paths.campaign(self.campaign_name).path
                    dg = paths.campaign(self.campaign_name).queue(
                        "discovery-gen", ensure=True
                    )

                    if purge:
                        log_step(
                            "purge_active",
                            "pending",
                            "Purging existing active task pool...",
                        )
                        if dg.completed.exists():
                            shutil.rmtree(dg.completed)
                        dg.completed.mkdir(parents=True, exist_ok=True)
                        log_step("purge_active", "success")

                    frontier_path = dg.pending / "frontier.usv"
                    batch_path = dg.pending / "batches" / f"{batch_name}.usv"
                    state_path = campaign_dir / "mission_state.toml"

                    scrape_index = ScrapeIndex()
                    current_offset = 0
                    if state_path.exists():
                        state = toml.load(state_path)
                        current_offset = state.get("last_offset", 0)

                    tasks: List[MissionTask] = []
                    skipped_count = 0

                    if not frontier_path.exists():
                        log_step("create_batch", "error", "Frontier file not found.")
                        return {
                            "status": "error",
                            "message": "Frontier file not found. Run prepare-mission first.",
                        }

                    with open(frontier_path, "r", encoding="utf-8") as f:
                        for i, line in enumerate(f):
                            if i < current_offset:
                                continue
                            if len(tasks) >= limit:
                                break
                            if line.strip():
                                try:
                                    task = MissionTask.from_usv(line)
                                    if not scrape_index.is_tile_scraped(
                                        task.search_phrase,
                                        task.tile_id,
                                        ttl_days=ttl_days,
                                    ):
                                        tasks.append(task)
                                    else:
                                        skipped_count += 1
                                except Exception:
                                    continue

                    if not tasks:
                        log_step(
                            "create_batch", "error", "No new tasks found in frontier."
                        )
                        return {
                            "status": "error",
                            "message": "No new tasks found in frontier.",
                        }

                    MissionTask.save_usv_with_datapackage(tasks, batch_path, batch_name)
                    new_offset = current_offset + len(tasks) + skipped_count
                    with open(state_path, "w") as f:
                        toml.dump({"last_offset": new_offset}, f)

                    log_step(
                        "create_batch",
                        "success",
                        f"Created {len(tasks)} tasks (Offset: {new_offset})",
                    )

                    log_step(
                        "build_index",
                        "pending",
                        "Activating tasks into mission index...",
                    )
                    from ..core.sharding import get_geo_shard
                    from cocli.core.text_utils import slugify

                    activated_count = 0
                    for task in tasks:
                        tile_id = task.tile_id
                        phrase = task.search_phrase
                        lat_str, lon_str = tile_id.split("_")
                        lat_shard = get_geo_shard(float(task.latitude))

                        tile_dir = dg.completed / lat_shard / lat_str / lon_str
                        tile_dir.mkdir(parents=True, exist_ok=True)

                        target_path = tile_dir / f"{slugify(phrase)}.usv"
                        if not target_path.exists():
                            with open(target_path, "w") as f:
                                f.write(task.to_usv())
                            activated_count += 1

                    log_step(
                        "build_index",
                        "success",
                        f"Activated {activated_count} task files.",
                    )

                    log_step(
                        "cluster_push", "pending", "Pushing tasks to PI cluster..."
                    )
                    from ..services.cluster_service import ClusterService

                    cluster = ClusterService(self.campaign_name)
                    await cluster.push_data(delete=True)
                    log_step("cluster_push", "success")

                    return {
                        "status": "success",
                        "batch": batch_name,
                        "tasks": len(tasks),
                    }

                    return {
                        "status": "success",
                        "batch": batch_name,
                        "tasks": len(tasks),
                    }

                import time

                result = await run_rollout()
            elif "op_scale_" in op_id:
                count = int(op_id.replace("op_scale_", ""))
                result = await asyncio.to_thread(
                    self.services.deployment_service.scale_service, count
                )
            else:
                raise NotImplementedError(
                    f"Logic for {op_id} not implemented in OperationService"
                )

            return {"status": "success", "op_id": op_id, "result": result}
        except Exception as e:
            logger.error(f"Operation {op_id} failed: {e}", exc_info=True)
            return {"status": "error", "op_id": op_id, "message": str(e)}
