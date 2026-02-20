import logging
import json
import shutil
import csv
from pathlib import Path
from typing import Any, Dict, List

from ..core.config import get_campaign_dir, load_campaign_config
from ..models.campaigns.queues.gm_details import GmItemTask
from ..models.companies.company import Company
from ..core.prospects_csv_manager import ProspectsIndexManager
from ..core.text_utils import slugify

logger = logging.getLogger(__name__)

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
            if self.campaign_name in company.tags:
                reason = None
                for p in contamination_patterns:
                    if any(p in kw.lower() for kw in company.keywords) or any(p in cat.lower() for cat in company.categories) or p in company.name.lower():
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
