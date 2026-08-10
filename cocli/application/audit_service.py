import logging
import json
import shutil
import csv
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import get_campaign_dir, load_campaign_config, load_global_config
from ..models.campaigns.queues.gm_details import GmItemTask
from ..models.companies.company import Company
from ..models import TileStatusResult, MissionReconciliationResult
from ..core.prospects_csv_manager import ProspectsIndexManager
from ..core.text_utils import slugify
from ..core.paths import paths

logger = logging.getLogger(__name__)

def dump_cli_tree(command: Any, out: Any, indent: int = 0) -> None:
    name = command.name or "cocli"
    help_text = f" - {command.help.splitlines()[0]}" if command.help else ""
    out.write(" " * indent + f"{name}{help_text}\n")

    for param in command.params:
        if getattr(param, "hidden", False):
            continue
        if param.name in ["install_completion", "show_completion"]:
            continue

        param_name = "/".join(param.opts) if param.opts else param.name
        param_type = f" ({param.type.name})" if hasattr(param.type, "name") else ""
        required = " [required]" if param.required else ""
        out.write(" " * (indent + 4) + f"{param_name}{param_type}{required}\n")

    if hasattr(command, "commands"):
        for sub_name, sub_command in sorted(command.commands.items()):
            dump_cli_tree(sub_command, out, indent + 4)

class AuditService:
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name

    def audit_campaign_integrity(self, fix: bool = False) -> Dict[str, Any]:
        """
        Audits campaign for cross-contamination.
        Corresponds to 'make audit-campaign' / 'scripts/audit_campaign_integrity.py'.
        """
        config = load_campaign_config(self.campaign_name)
        authorized_queries = set(config.get("prospecting", {}).get("queries", []))
        authorized_slugs = {slugify(q) for q in authorized_queries}
        
        manager = ProspectsIndexManager(self.campaign_name)
        report_data = []
        prospects_to_remove: List[Path] = []
        companies_to_untag: List[Company] = []

        flooring_patterns = ["floor", "tile", "carpet", "epoxy", "vinyl", "hardwood", "laminate", "linoleum"]
        wealth_patterns = ["advisor", "wealth", "planner", "financial", "investment", "retirement", "tax analyzer"]

        if self.campaign_name == "turboship":
            contamination_patterns = wealth_patterns
            required_patterns = flooring_patterns
        else:
            contamination_patterns = flooring_patterns
            required_patterns = wealth_patterns

        # Audit Prospects
        for file_path in list(manager.index_dir.rglob("*.csv")):
            if not file_path.is_file():
                continue
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    row = next(reader, None)
                    if not row:
                        continue
                    keyword = row.get("Keyword", "").strip()
                    name = row.get("Name", "") or ""
                    domain = row.get("Domain", "") or ""
                    category = (row.get("First_category", "") or "").lower()
                    reason = None
                    for p in contamination_patterns:
                        if p in keyword.lower() or p in name.lower() or p in category:
                            reason = f"Explicit Contamination Pattern: {p}"
                            break
                    if not reason and self.campaign_name == "turboship":
                        looks_like_flooring = any(p in name.lower() or p in category or p in keyword.lower() for p in required_patterns)
                        if not looks_like_flooring and keyword and slugify(keyword) not in authorized_slugs:
                            reason = f"Does not match campaign niche and unauthorized keyword: {keyword}"
                    if reason:
                        report_data.append({"Type": "Prospect", "Name": name, "Domain": domain, "Reason": reason})
                        prospects_to_remove.append(file_path)
            except Exception:
                continue

        # Audit Companies
        for company in Company.get_all():
            if company is None:
                continue
            if self.campaign_name in company.tags:
                reason = None
                for p in contamination_patterns:
                    company_name_lower = str(company.name).lower() if company.name else ""
                    if any(p in kw.lower() for kw in company.keywords) or any(p in cat.lower() for cat in company.categories) or p in company_name_lower:
                        reason = f"Explicit Contamination Pattern: {p}"
                        break
                if reason:
                    report_data.append({"Type": "Company", "Name": company.name, "Domain": company.domain, "Reason": reason})
                    companies_to_untag.append(company)

        if fix:
            for prospect_file in prospects_to_remove:
                prospect_file.unlink()
            for company in companies_to_untag:
                company.tags = [t for t in company.tags if t != self.campaign_name]
                company.save()

        return {
            "campaign_name": self.campaign_name,
            "items_found": len(report_data),
            "items_fixed": len(prospects_to_remove) + len(companies_to_untag) if fix else 0,
            "report": report_data
        }

    def audit_queue_completion(self, execute: bool = False) -> Dict[str, Any]:
        """
        Audits completion markers against models and index.
        Corresponds to 'make audit-queue' / 'scripts/audit_queue_completion.py'.
        """
        campaign_dir = get_campaign_dir(self.campaign_name)
        if not campaign_dir:
            return {"error": f"Campaign {self.campaign_name} not found."}

        completed_dir = campaign_dir / "queues" / "gm-details" / "completed"
        recovery_dir = campaign_dir / "recovery" / "gm-details" / "completed"
        
        existing_pids = set()
        for f_idx in campaign_dir.rglob("google_maps_prospects/**/*.usv"):
            existing_pids.add(f_idx.stem)
        for f_idx in campaign_dir.rglob("google_maps_prospects/**/*.csv"):
            existing_pids.add(f_idx.stem)
        
        stats = {"total": 0, "valid": 0, "invalid_model": 0, "missing_index": 0, "moved": 0}
        all_files = list(completed_dir.glob("*.json")) if completed_dir.exists() else []
        stats["total"] = len(all_files)
        
        for f_path in all_files:
            try:
                with open(f_path, 'r') as f:
                    data = json.load(f)
                try:
                    task = GmItemTask.model_validate(data)
                    if task.place_id not in existing_pids:
                        stats["missing_index"] += 1
                        is_valid = False
                    else:
                        is_valid = True
                        stats["valid"] += 1
                except Exception:
                    stats["invalid_model"] += 1
                    is_valid = False

                if not is_valid and execute:
                    recovery_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f_path), str(recovery_dir / f_path.name))
                    stats["moved"] += 1
            except Exception:
                continue

        return stats

    def audit_cluster_paths(self, target_paths: List[str], campaigns: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Audits specific paths across the cluster and S3.
        target_paths: List of path templates (can use {campaign} placeholder).
        campaigns: Optional list of campaigns to check (defaults to active campaign).
        """
        active_campaigns = campaigns or [self.campaign_name]
        global_config = load_global_config()
        nodes = global_config.get("cluster", {}).get("nodes", [])
        
        results = []

        for campaign in active_campaigns:
            try:
                config = load_campaign_config(campaign)
                aws_config = config.get("aws", {})
                bucket = aws_config.get("data_bucket_name") or aws_config.get("cocli_data_bucket_name")
                profile = aws_config.get("profile") or aws_config.get("aws_profile", "default")
                
                # Local Root is always 'data/' symlink in this repo context
                local_root = Path("data")

                for template in target_paths:
                    actual_path = template.replace("{campaign}", campaign)
                    
                    # 1. Local
                    local_target = local_root / actual_path.lstrip("/")
                    results.append({
                        "campaign": campaign,
                        "template": template,
                        "location": "Local",
                        "status": "FOUND" if local_target.exists() else "MISSING"
                    })

                    # 2. PIs
                    for node in nodes:
                        host = node['host']
                        pi_path = f"~/.local/share/cocli_data/{actual_path.lstrip('/')}"
                        exists = self._check_remote_pi(host, pi_path)
                        results.append({
                            "campaign": campaign,
                            "template": template,
                            "location": f"Pi: {host}",
                            "status": "FOUND" if exists else "MISSING"
                        })

                    # 3. Check S3
                    if bucket:
                        exists = self._check_s3(bucket, profile, actual_path)
                        results.append({
                            "campaign": campaign,
                            "template": template,
                            "location": f"S3: {bucket}",
                            "status": "FOUND" if exists else "MISSING"
                        })
                    else:
                        results.append({
                            "campaign": campaign,
                            "template": template,
                            "location": "S3",
                            "status": "NO BUCKET"
                        })

            except Exception as e:
                logger.error(f"Error auditing paths for campaign {campaign}: {e}")
        
        return results

    def _check_remote_pi(self, host: str, path: str) -> bool:
        try:
            cmd = f"ls -d {path} >/dev/null 2>&1 && echo 'EXISTS' || echo 'MISSING'"
            res = subprocess.run(["ssh", "-o", "ConnectTimeout=2", f"mstouffer@{host}", cmd], capture_output=True, text=True, timeout=5)
            return "EXISTS" in res.stdout
        except Exception:
            return False

    def _check_s3(self, bucket: str, profile: str, path: str) -> bool:
        try:
            s3_path = path.lstrip("/")
            cmd = ["aws", "s3", "ls", f"s3://{bucket}/{s3_path}", "--profile", profile]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return res.returncode == 0 and len(res.stdout.strip()) > 0
        except Exception:
            return False

    def get_cli_tree(self, click_command: Any) -> str:
        """Dumps the CLI command hierarchy as a string."""
        from io import StringIO

        out = StringIO()
        dump_cli_tree(click_command, out)
        return out.getvalue()

    def audit_filesystem(
        self,
        campaign_name: Optional[str] = None,
        skip_companies: bool = True,
        gen_cleanup: bool = False,
    ) -> Dict[str, Any]:
        """Audits the filesystem for OMAP compliance and Screaming Architecture."""
        from ..core.audit.fs_auditor import FsAuditor
        from datetime import datetime

        auditor = FsAuditor()
        root_node = auditor.audit_full(
            campaign_name=campaign_name, skip_companies=skip_companies
        )

        orphans = []
        cleanup_report_path = None
        if gen_cleanup:
            orphans = auditor.get_orphans(root_node)
            if orphans:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                cleanup_report_path = paths.root / ".logs" / f"orphan_cleanup_{ts}.txt"
                cleanup_report_path.parent.mkdir(parents=True, exist_ok=True)
                auditor.generate_removal_report(orphans, cleanup_report_path)

        return {
            "root_node": root_node,
            "orphans": orphans,
            "cleanup_report_path": cleanup_report_path,
        }

    def audit_schemas(
        self,
        campaign: Optional[str] = None,
        fix: bool = False,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Audit datapackage.json files for schema compliance."""
        from cocli.models.campaigns.indexes.google_maps_list_item import GoogleMapsListItem
        from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
        from cocli.models.campaigns.queues.to_call import ToCallTask

        schema_models = [
            GoogleMapsListItem,
            GoogleMapsProspect,
            ToCallTask,
        ]

        root = paths.root
        issues_found = []
        files_checked = 0
        fixed_count = 0

        for dp_file in root.rglob("datapackage.json"):
            if campaign:
                campaign_dir = paths.campaign(campaign).path
                try:
                    dp_file.relative_to(campaign_dir)
                except ValueError:
                    continue

            files_checked += 1

            try:
                with open(dp_file, "r") as f:
                    dp = json.load(f)

                resource_name = dp.get("name", dp_file.parent.name)
                existing_hash = dp.get("cocli:schema_hash")

                if existing_hash is None:
                    issues_found.append(
                        {
                            "file": str(dp_file.relative_to(root)),
                            "issue": "MISSING_SCHEMA_HASH",
                            "details": "Old datapackage.json without schema_hash",
                        }
                    )
                    continue

                ledger_path = root / "schema_ledger.json"
                if ledger_path.exists():
                    with open(ledger_path, "r") as f:
                        ledger = json.load(f)

                    if resource_name in ledger:
                        ledger_hash = ledger[resource_name].get("current_hash", "")
                        if ledger_hash and ledger_hash != existing_hash:
                            issues_found.append(
                                {
                                    "file": str(dp_file.relative_to(root)),
                                    "issue": "HASH_MISMATCH",
                                    "details": f"File: {existing_hash[:8]}, Ledger: {ledger_hash[:8]}",
                                }
                            )
            except Exception as e:
                issues_found.append(
                    {
                        "file": str(dp_file.relative_to(root)),
                        "issue": "READ_ERROR",
                        "details": str(e),
                    }
                )

        if fix and issues_found and not dry_run:
            for issue in issues_found:
                if issue["issue"] in ["MISSING_SCHEMA_HASH", "HASH_MISMATCH"]:
                    dp_file = root / issue["file"]
                    for model in schema_models:
                        try:
                            model.save_datapackage(  # type: ignore[attr-defined]
                                dp_file.parent,
                                dp_file.parent.name,
                                "*.usv",
                                force=True,
                            )
                            fixed_count += 1
                            break
                        except Exception:
                            continue

        return {
            "files_checked": files_checked,
            "issues_found": issues_found,
            "fixed_count": fixed_count,
        }

    def run_queue_gm_list(self, campaign_name: str) -> str:
        """Runs end-to-end audit for the gm-list queue."""
        from ..core.auditors.audit_workflow import DataAuditWorkflow
        workflow = DataAuditWorkflow(campaign=campaign_name, queue="gm-list")
        workflow.start()
        return workflow.state

    def audit_enrichment(self, campaign_name: str) -> Dict[str, Any]:
        """Audit website enrichment metrics for a campaign."""
        import yaml
        from ..core.text_utils import parse_frontmatter

        companies_dir = paths.companies.ensure()
        if not companies_dir.exists():
            raise FileNotFoundError(f"Companies directory not found at {companies_dir}")

        total_companies = 0
        total_enriched = 0
        has_contact_name = 0
        has_phone = 0
        has_email = 0
        has_social = 0
        tier_1 = 0
        tier_2 = 0
        tier_3 = 0

        for path in companies_dir.iterdir():
            if not path.is_dir():
                continue

            tags_path = path / "tags.lst"
            if not tags_path.exists():
                continue

            try:
                with open(tags_path, "r", encoding="utf-8") as f:
                    tags = [line.strip() for line in f if line.strip()]
                if campaign_name not in tags:
                    continue
            except Exception:
                continue

            total_companies += 1

            website_md_path = path / "enrichments" / "website.md"
            if not website_md_path.exists():
                continue

            try:
                content = website_md_path.read_text(encoding="utf-8")
                fm_str = parse_frontmatter(content)
                if not fm_str:
                    continue
                data = yaml.safe_load(fm_str)
                if not data:
                    continue

                total_enriched += 1

                has_name_val = False
                personnel = data.get("personnel", [])
                if isinstance(personnel, list) and len(personnel) > 0:
                    if any(
                        p.get("name") or p.get("first_name") or p.get("last_name")
                        for p in personnel
                        if isinstance(p, dict)
                    ):
                        has_name_val = True

                has_phone_val = bool(data.get("phone"))
                has_email_val = bool(data.get("email") or data.get("all_emails"))
                has_social_val = any(
                    bool(data.get(f"{platform}_url"))
                    for platform in [
                        "facebook",
                        "linkedin",
                        "instagram",
                        "twitter",
                        "youtube",
                    ]
                )

                if has_name_val:
                    has_contact_name += 1
                if has_phone_val:
                    has_phone += 1
                if has_email_val:
                    has_email += 1
                if has_social_val:
                    has_social += 1

                if has_name_val and (
                    has_email_val or has_phone_val or has_social_val
                ):
                    tier_1 += 1
                elif has_email_val or has_phone_val or has_social_val:
                    tier_2 += 1
                else:
                    tier_3 += 1

            except Exception:
                continue

        return {
            "total_companies": total_companies,
            "total_enriched": total_enriched,
            "has_contact_name": has_contact_name,
            "has_phone": has_phone,
            "has_email": has_email,
            "has_social": has_social,
            "tier_1": tier_1,
            "tier_2": tier_2,
            "tier_3": tier_3,
        }

    def get_enrichment_interactive_targets(
        self, campaign_name: str
    ) -> List[tuple[Optional[str], str, str, bool, bool]]:
        """Retrieves targets that do not have a contact name for interactive audit."""
        import yaml
        from ..core.text_utils import parse_frontmatter

        companies_dir = paths.companies.ensure()
        if not companies_dir.exists():
            raise FileNotFoundError(f"Companies directory not found at {companies_dir}")

        targets = []
        for path in sorted(companies_dir.iterdir(), key=lambda p: p.name):
            if not path.is_dir():
                continue

            tags_path = path / "tags.lst"
            if not tags_path.exists():
                continue

            try:
                with open(tags_path, "r", encoding="utf-8") as f:
                    tags = [line.strip() for line in f if line.strip()]
                if campaign_name not in tags:
                    continue
            except Exception:
                continue

            website_md_path = path / "enrichments" / "website.md"
            if not website_md_path.exists():
                domain = None
                name = path.name
                index_md = path / "_index.md"
                if index_md.exists():
                    try:
                        fm = parse_frontmatter(
                            index_md.read_text(encoding="utf-8")
                        )
                        if fm:
                            idx_data = yaml.safe_load(fm)
                            if idx_data:
                                domain = idx_data.get("domain")
                                name = idx_data.get("name") or path.name
                    except Exception:
                        pass
                if domain:
                    targets.append((domain, name, path.name, False, False))
                continue

            try:
                content = website_md_path.read_text(encoding="utf-8")
                fm_str = parse_frontmatter(content)
                if not fm_str:
                    continue
                data = yaml.safe_load(fm_str)
                if not data:
                    continue

                has_name_val = False
                personnel = data.get("personnel", [])
                if isinstance(personnel, list) and len(personnel) > 0:
                    if any(
                        p.get("name") or p.get("first_name") or p.get("last_name")
                        for p in personnel
                        if isinstance(p, dict)
                    ):
                        has_name_val = True

                if not has_name_val:
                    domain = data.get("url") or data.get("domain") or path.name
                    name = (
                        data.get("company_name") or data.get("title") or path.name
                    )
                    has_email = bool(data.get("email") or data.get("all_emails"))
                    has_phone = bool(data.get("phone"))
                    targets.append((domain, name, path.name, has_email, has_phone))
            except Exception:
                continue

        return targets

    def run_gm_list_html_audit(self, campaign: str, limit: int, output: str) -> Path:
        """Runs the HTML reviews/ratings auditor."""
        from cocli.core.auditors.gm_list_auditor import run_html_audit

        return run_html_audit(campaign, limit=limit, output_name=output)

    def prepare_validate(
        self,
        campaign: str,
        tile: Optional[str] = None,
        phrase: Optional[str] = None,
        usv_path: Optional[Path] = None,
        headed: bool = False,
        limit: int = 0,
    ) -> Dict[str, Any]:
        """Prepares human-in-the-loop validation of scraped list items."""
        import csv
        from datetime import datetime, UTC
        from ..core.text_utils import slugify
        from ..models.campaigns.indexes.google_maps_list_item import (
            GoogleMapsListItem,
        )
        from ..models.campaigns.indexes.gm_list_audit_log_item import (
            GmListAuditLogItem,
        )
        from ..models.campaigns.indexes.gm_list_reviewed_item import (
            GmListReviewedItem,
        )
        from ..application.processors.gm_list import GmListProcessor

        if usv_path:
            mode = "offline"
            if not usv_path.exists():
                raise FileNotFoundError(f"USV file not found: {usv_path}")
        elif tile and phrase:
            mode = "online"
            parts = tile.split(",")
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            phrase_slug = slugify(phrase)
        else:
            raise ValueError("Provide tile + phrase (online) or usv_path (offline)")

        # Online mode scrape execution
        items = []
        if mode == "online":
            from ..models.campaigns.queues.gm_list import ScrapeTask
            from ..core.sharding import get_geo_shard, get_grid_tile_id

            lat_shard = get_geo_shard(lat)
            grid_id = get_grid_tile_id(lat, lon)
            lat_tile_v, lon_tile_v = grid_id.split("_")

            def _target_scrape() -> list[Any]:
                from playwright.async_api import async_playwright
                from ..scrapers.google.gm_scraper.coordinator import (
                    ScrapeCoordinator,
                )
                import asyncio

                async def run_scrape() -> list[Any]:
                    async with async_playwright() as pw:
                        browser = await pw.chromium.launch(headless=not headed)
                        try:
                            coordinator = ScrapeCoordinator(
                                browser, campaign_name=campaign, debug=False
                            )
                            scraped = []
                            scrape_limit = limit if limit > 0 else 20
                            async for item in coordinator.run(
                                start_lat=lat,
                                start_lon=lon,
                                search_phrases=[phrase or ""],
                                force_refresh=True,
                            ):
                                scraped.append(item)
                                if len(scraped) >= scrape_limit:
                                    break
                            return scraped
                        finally:
                            await browser.close()

                return asyncio.run(run_scrape())

            # Run scraping
            import threading

            class ScrapeThread(threading.Thread):

                def __init__(self) -> None:
                    super().__init__(daemon=True)
                    self.result: list[Any] = []

                def run(self) -> None:
                    self.result = _target_scrape()

            t = ScrapeThread()
            t.start()
            t.join()
            items = t.result

            if items:
                task = ScrapeTask(
                    latitude=lat,  # type: ignore[arg-type]
                    longitude=lon,  # type: ignore[arg-type]
                    zoom=15,
                    search_phrase=phrase or "",
                    campaign_name=campaign,
                    force_refresh=True,
                    ack_token=f"validate-{phrase_slug}-{datetime.now(UTC).timestamp()}",
                )
                processor = GmListProcessor(processed_by="audit-validate")
                import asyncio

                asyncio.run(processor.process_results(task, items))

                usv_path = (
                    paths.queue(campaign, "gm-list").completed
                    / "results"
                    / lat_shard
                    / lat_tile_v
                    / lon_tile_v
                    / f"{phrase_slug}.usv"
                )

        if not usv_path or not usv_path.exists():
            raise FileNotFoundError("No USV file available for review.")

        # Read records
        field_names = list(GoogleMapsListItem.model_fields.keys())
        excluded = {
            n for n, f in GoogleMapsListItem.model_fields.items() if f.exclude
        }
        review_skip = {"place_id", "company_slug"}
        display_fields = [
            n
            for n in field_names
            if n not in excluded and n not in review_skip
        ]

        records = []
        with open(usv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\x1f")
            for row in reader:
                if row:
                    while len(row) < len(field_names):
                        row.append("")
                    records.append(row[: len(field_names)])

        # Record audit log
        audit_dir = paths.queue(campaign, "gm-list").pending / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)

        try:
            records_file = str(
                usv_path.relative_to(paths.queue(campaign, "gm-list").completed)
            )
        except ValueError:
            records_file = str(usv_path.name)

        log_item = GmListAuditLogItem.create(
            tile=str(usv_path.parent),
            search_phrase=phrase or usv_path.stem,
            total_companies=len(items) if mode == "online" else len(records),
            records_file=records_file,
            usv_count=len(records),
            scraper_version="audit-validate",
        )
        audit_log = audit_dir / "gm_list_audit_log.usv"
        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(log_item.to_usv())

        GmListAuditLogItem.append_resource_to_datapackage(
            audit_dir, "gm_list_audit_log", "gm_list_audit_log.usv"
        )

        # Load existing reviewed place IDs
        reviewed_path = audit_dir / "gm_list_reviewed.usv"
        already_reviewed = set()
        if reviewed_path.exists():
            with open(reviewed_path, "r", encoding="utf-8") as f:
                for line in f:
                    p = line.strip().split("\x1f")
                    if len(p) >= 1 and p[0]:
                        already_reviewed.add(p[0])

        for model_cls, name, path_fn in [
            (GmListReviewedItem, "gm_list_reviewed", "gm_list_reviewed.usv"),
            (GmListAuditLogItem, "gm_list_audit_log", "gm_list_audit_log.usv"),
        ]:
            model_cls.append_resource_to_datapackage(audit_dir, name, path_fn)  # type: ignore[attr-defined]

        return {
            "records": records,
            "already_reviewed": already_reviewed,
            "audit_log": audit_log,
            "reviewed_path": reviewed_path,
            "display_fields": display_fields,
            "field_names": field_names,
            "mode": mode,
            "phrase": phrase or usv_path.stem,
            "usv_path": usv_path,
            "items_scraped_count": len(items),
        }

    def save_reviewed_item(
        self, reviewed_path: Path, place_id: str, field_name: str, expected: str
    ) -> None:
        """Saves a single human validation field correction."""
        from ..models.campaigns.indexes.gm_list_reviewed_item import (
            GmListReviewedItem,
        )

        item = GmListReviewedItem(
            place_id=place_id, field_name=field_name, expected=expected
        )
        header_needed = (
            not reviewed_path.exists() or reviewed_path.stat().st_size == 0
        )
        with open(reviewed_path, "a", encoding="utf-8") as f:
            if header_needed and GmListReviewedItem.HEADER:
                f.write(GmListReviewedItem.get_header())
            f.write(item.to_usv())

    def replay_audit_corrections(
        self,
        campaign: str,
        usv_path: Path,
        output: Optional[Path] = None,
        corrections_path: Optional[Path] = None,
        reviewed_path_opt: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Replay audit corrections onto a USV results file."""
        from collections import defaultdict
        from ..models.campaigns.indexes.google_maps_list_item import (
            GoogleMapsListItem,
        )
        import csv

        audit_dir = paths.queue(campaign, "gm-list").pending / "audit"

        if not corrections_path:
            corrections_path = audit_dir / "gm_list_corrections.usv"
        if not reviewed_path_opt:
            reviewed_path_opt = audit_dir / "gm_list_reviewed.usv"

        field_corrections: dict[str, dict[str, str]] = defaultdict(dict)
        if corrections_path.exists():
            with open(corrections_path, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\x1f")
                    if len(parts) >= 4:
                        field_corrections[parts[0]][parts[1]] = parts[3]

        reviewed_overrides: dict[str, dict[str, str]] = defaultdict(dict)
        if reviewed_path_opt.exists():
            with open(reviewed_path_opt, "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.strip().split("\x1f")
                    if len(parts) >= 3:
                        place_id = parts[0]
                        field_name = parts[1]
                        expected_val = parts[2]
                        if field_name and expected_val:
                            reviewed_overrides[place_id][field_name] = expected_val

        field_names = list(GoogleMapsListItem.model_fields.keys())
        excluded = {
            n for n, f in GoogleMapsListItem.model_fields.items() if f.exclude
        }
        display_names = [n for n in field_names if n not in excluded]

        records = []
        with open(usv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\x1f")
            for row in reader:
                if row:
                    while len(row) < len(field_names):
                        row.append("")
                    records.append(row[: len(field_names)])

        applied_count = 0
        reviewed_applied = 0
        for row in records:
            place_id = row[0] if len(row) > 0 else ""
            if not place_id:
                continue

            all_overrides = field_corrections.get(place_id, {}).copy()
            if place_id in reviewed_overrides:
                all_overrides.update(reviewed_overrides[place_id])

            if all_overrides:
                for fi, fn in enumerate(display_names):
                    if fn in all_overrides:
                        row[fi] = all_overrides[fn]
                        if fn in field_corrections.get(place_id, {}):
                            applied_count += 1
                        else:
                            reviewed_applied += 1

        output_path = output or usv_path.with_suffix(".corrected.usv")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for row in records:
                f.write("\x1f".join(row) + "\x1e\n")

        return {
            "records_count": len(records),
            "applied_count": applied_count,
            "reviewed_applied": reviewed_applied,
            "output_path": output_path,
        }

    def export_cases(
        self,
        campaign: str,
        tile: Optional[str] = None,
        phrase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Export corrections as parametrized test cases."""
        import csv

        reviewed_path = (
            paths.queue(campaign, "gm-list").pending
            / "audit"
            / "gm_list_reviewed.usv"
        )
        if not reviewed_path.exists():
            raise FileNotFoundError(
                "No gm_list_reviewed.usv found. Run audit validate first."
            )

        corrections = []
        with open(reviewed_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter="\x1f")
            for row in reader:
                if len(row) >= 3 and row[0].startswith("ChIJ"):
                    corrections.append((row[0], row[1], row[2]))

        if not corrections:
            return {"cases_count": 0, "test_cases_path": None, "missing_html": 0}

        raw_base = paths.campaign(campaign).path / "raw" / "gm-list"
        if not raw_base.exists():
            raise FileNotFoundError(f"Raw HTML directory not found: {raw_base}")

        cases = []
        missing_html = 0
        for place_id, field, expected in corrections:
            html_path = None
            for html_file in raw_base.rglob(f"{place_id}.html"):
                html_path = html_file
                break
            if html_path is None:
                missing_html += 1
                continue
            cases.append((place_id, field, expected, html_path))

        if not cases:
            return {
                "cases_count": 0,
                "test_cases_path": None,
                "missing_html": missing_html,
            }

        test_data_dir = paths.root / "tests" / "data" / "maps.google.com"
        html_dir = test_data_dir / "html"
        html_dir.mkdir(parents=True, exist_ok=True)

        for place_id, field, expected, src_html in cases:
            dst = html_dir / f"{place_id}.html"
            if not dst.exists():
                dst.write_bytes(src_html.read_bytes())

        test_cases_path = test_data_dir / "field_extraction_cases.usv"
        HEADER_LINE = "\x1f".join(["place_id", "field", "expected", "html_path"])
        with open(test_cases_path, "w", encoding="utf-8") as f:
            f.write(HEADER_LINE + "\n")
            for place_id, field, expected, _ in cases:
                html_rel = f"html/{place_id}.html"
                f.write(
                    "\x1f".join([place_id, field, expected, html_rel]) + "\n"
                )

        from ..models.campaigns.indexes.gm_list_reviewed_item import (
            GmListReviewedItem,
        )

        GmListReviewedItem.append_resource_to_datapackage(
            test_data_dir,
            "field_extraction_cases",
            "field_extraction_cases.usv",
        )

        return {
            "cases_count": len(cases),
            "test_cases_path": test_cases_path,
            "missing_html": missing_html,
        }

    def get_tile_status(self, campaign_name: str) -> TileStatusResult:
        """Audit tile-queue status.

        map-tile has no processing phase (removed 2026-08-09 - it's a pure
        tile registry, no staging/throttling job of its own). pending_dir/
        completed_dir hold sharded files ({shard}/{lat}/{lon}/{tile_id}.usv),
        so counts use a recursive walk, not a flat glob (a flat glob against
        the real sharded shape always returned 0 - fixed here).
        """
        from ..core.queue.factory import get_queue_manager

        campaign_val = campaign_name or "default"
        tile_queue = get_queue_manager(
            "map-tile", queue_type="tile", campaign_name=campaign_val
        )

        def _count_usv(root: Path) -> int:
            if not root.exists():
                return 0
            return sum(1 for _ in root.rglob("*.usv"))

        pending_count = _count_usv(tile_queue.pending_dir)
        completed_count = _count_usv(tile_queue.completed_dir)

        return TileStatusResult(
            pending_count=pending_count,
            completed_count=completed_count,
        )

    def audit_mission_reconciliation(self, campaign_name: str) -> MissionReconciliationResult:
        """Reconcile gm-list's mission (discovery-gen/completed), pending
        (gm-list/pending), and receipts (gm-list/completed/results) by
        normalized identity, so "how much work remains" doesn't depend on
        which of pending/ or discovery-gen/completed the live pipeline
        happens to be reading from."""
        from typing import cast
        from ..core.queue.factory import get_queue_manager
        from ..core.queue.filesystem import FilesystemGmListQueue
        from ..core.queue.reconcile import reconcile_identities

        campaign_val = campaign_name or "default"
        # queue_type="gm-list" always resolves to FilesystemGmListQueue for the
        # filesystem provider; CampaignQueueProtocol is intentionally generic
        # and doesn't declare gm-list's extra pending_dir/completed_dir/
        # target_tiles_dir attributes.
        gm_list_queue = cast(
            FilesystemGmListQueue,
            get_queue_manager("gm-list", queue_type="gm-list", campaign_name=campaign_val),
        )
        receipts_dir = gm_list_queue.completed_dir / "results"

        mission_vs_receipts = reconcile_identities(
            gm_list_queue.target_tiles_dir, receipts_dir
        )
        pending_vs_receipts = reconcile_identities(
            gm_list_queue.pending_dir, receipts_dir
        )

        return MissionReconciliationResult(
            campaign_name=campaign_val,
            mission_total=mission_vs_receipts.left_total,
            receipt_total=mission_vs_receipts.right_total,
            unscraped_count=len(mission_vs_receipts.left_only),
            unscraped_ids=sorted(mission_vs_receipts.left_only),
            orphaned_receipt_count=len(mission_vs_receipts.right_only),
            orphaned_receipt_ids=sorted(mission_vs_receipts.right_only),
            pending_total=pending_vs_receipts.left_total,
            stale_pending_count=pending_vs_receipts.matched,
            stale_pending_ids=sorted(pending_vs_receipts.intersection),
            truly_pending_count=len(pending_vs_receipts.left_only),
            truly_pending_ids=sorted(pending_vs_receipts.left_only),
        )

    def purge_leases(
        self,
        campaign_name: str,
        queue_name: str,
        force: bool = False,
        dry_run: bool = False,
        max_age_minutes: int = 30,
    ) -> Dict[str, Any]:
        """Purge stale or expired leases from a queue directory."""
        from cocli.services.lease_cleanup import (
            purge_expired_leases,
            force_purge_all_leases,
        )

        campaign_val = campaign_name or "default"
        queue_dir = paths.campaign(campaign_val).queue(queue_name).pending

        if force:
            metrics = force_purge_all_leases(queue_dir, dry_run=dry_run)
        else:
            metrics = purge_expired_leases(
                queue_dir,
                max_heartbeat_age_minutes=max_age_minutes,
                dry_run=dry_run,
            )

        return {
            "metrics": metrics,
            "queue_dir": queue_dir,
        }
