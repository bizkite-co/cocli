import csv
import logging
import argparse
from pathlib import Path
from typing import List, Optional

from cocli.core.config import load_campaign_config
from cocli.core.prospects_csv_manager import ProspectsIndexManager
from cocli.models.companies.company import Company

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def audit_campaign(campaign_name: str, fix: bool = False, output_csv: Optional[str] = None) -> None:
    config = load_campaign_config(campaign_name)
    authorized_queries = set(config.get("prospecting", {}).get("queries", []))
    # Add slugified versions of authorized queries
    from cocli.core.text_utils import slugify
    authorized_slugs = {slugify(q) for q in authorized_queries}
    
    logger.info(f"Authorized queries for {campaign_name}: {authorized_queries}")

    if output_csv is None:
        from cocli.core.config import get_campaign_dir
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            logger.error(f"Could not find campaign directory for {campaign_name}")
            return
        export_dir = campaign_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        output_csv = str(export_dir / f"{campaign_name}_contamination_report.csv")

    manager = ProspectsIndexManager(campaign_name)
    
    report_data = []
    prospects_to_remove: List[Path] = []
    companies_to_untag: List[Company] = []

    # Patterns that indicate cross-contamination from OTHER campaigns
    # If we are in turboship (flooring), wealth management terms are contamination.
    # If we are in roadmap (wealth), flooring terms are contamination.
    
    flooring_patterns = ["floor", "tile", "carpet", "epoxy", "vinyl", "hardwood", "laminate", "linoleum"]
    wealth_patterns = ["advisor", "wealth", "planner", "financial", "investment", "retirement", "tax analyzer"]

    if campaign_name == "turboship":
        contamination_patterns = wealth_patterns
        # Also authorized keywords are strictly flooring, so we check if it's NOT flooring
        required_patterns = flooring_patterns
    else:
        contamination_patterns = flooring_patterns
        required_patterns = wealth_patterns

    # 1. Audit Prospects
    logger.info("Auditing prospects...")
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
                
                # Check for explicit contamination patterns
                for p in contamination_patterns:
                    if p in keyword.lower() or p in name.lower() or p in category:
                        reason = f"Explicit Contamination Pattern: {p}"
                        break
                
                # If it's turboship, and doesn't look like flooring at all, flag it
                if not reason and campaign_name == "turboship":
                    looks_like_flooring = any(p in name.lower() or p in category or p in keyword.lower() for p in required_patterns)
                    if not looks_like_flooring and keyword and slugify(keyword) not in authorized_slugs:
                        reason = f"Does not match campaign niche and unauthorized keyword: {keyword}"

                if reason:
                    report_data.append({
                        "Type": "Prospect",
                        "Name": name,
                        "Domain": domain,
                        "Slug": row.get("company_slug", ""),
                        "Reason": reason,
                        "Source": str(file_path.name)
                    })
                    prospects_to_remove.append(file_path)

        except Exception as e:
            logger.error(f"Error auditing prospect {file_path}: {e}")

    # 2. Audit Companies
    logger.info("Auditing companies...")
    for company in Company.get_all():
        if campaign_name in company.tags:
            reason = None
            
            # Check for explicit contamination
            for p in contamination_patterns:
                if any(p in kw.lower() for kw in company.keywords) or \
                   any(p in cat.lower() for cat in company.categories) or \
                   p in company.name.lower():
                    reason = f"Explicit Contamination Pattern: {p}"
                    break
            
            if reason:
                report_data.append({
                    "Type": "Company",
                    "Name": company.name,
                    "Domain": company.domain,
                    "Slug": company.slug,
                    "Reason": reason,
                    "Source": "_index.md"
                })
                companies_to_untag.append(company)

    # 3. Write Report
    with open(output_csv, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Type", "Name", "Domain", "Slug", "Reason", "Source"])
        writer.writeheader()
        writer.writerows(report_data)
    
    logger.info(f"Audit Complete. Report written to: {output_csv}")
    logger.info(f"Total contaminated items found: {len(report_data)}")

    # 4. Fix if requested
    if fix:
        logger.info("Fix mode enabled. Cleaning up...")
        for prospect_file in prospects_to_remove:
            prospect_file.unlink()
        logger.info(f"Deleted {len(prospects_to_remove)} prospect files.")
        
        for company in companies_to_untag:
            company.tags = [t for t in company.tags if t != campaign_name]
            company.save()
        logger.info(f"Removed '{campaign_name}' tag from {len(companies_to_untag)} companies.")
    else:
        logger.info("Run with --fix to apply changes.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit campaign for cross-contamination.")
    parser.add_argument("campaign", help="Campaign name (e.g. roadmap)")
    parser.add_argument("--fix", action="store_true", help="Apply cleanup fixes")
    parser.add_argument("--output", default=None, help="Output report CSV path (defaults to campaign exports)")
    
    args = parser.parse_args()
    audit_campaign(args.campaign, args.fix, args.output)
