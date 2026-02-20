import csv
import yaml
from pathlib import Path
from typing import Any, cast
from rich.console import Console
from .base import BaseCompiler
from ..models.companies.company import Company
from ..core.config import get_cocli_base_dir

console = Console()

class GoogleMapsCompiler(BaseCompiler):
    def compile(self, company_dir: Path) -> None:
        company = Company.from_directory(company_dir)
        if not company:
            return
        place_id = company.place_id
        
        gm_data = None
        
        # 1. Try by place_id if we have it
        if place_id:
            gm_data = self._get_gm_data_by_id(place_id, company_dir)
            
        # 2. If no data yet, try to find it in the turboship campaign index by slug
        if not gm_data:
            campaign_gm_index = get_cocli_base_dir() / "campaigns" / "turboship" / "indexes" / "google_maps_prospects"
            if campaign_gm_index.exists():
                for csv_file in campaign_gm_index.glob("*.csv"):
                    try:
                        with open(csv_file, 'r') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                row_slug = row.get("slug") or row.get("Slug")
                                row_domain = row.get("domain") or row.get("Domain")
                                if row_slug == company.slug or (company.domain and row_domain == company.domain):
                                    gm_data = row
                                    break
                    except Exception:
                        continue
                    if gm_data:
                        break

        if not gm_data:
            return

        updated = False
        
        # Name: Prioritize Google Maps name if current name is a slug/domain/junk/generic
        gm_name = gm_data.get("Name") or gm_data.get("name")
        if gm_name and company.name != gm_name:
            current_name = company.name
            is_slug_based = current_name == company.slug or (company.domain and current_name == company.domain)
            is_generic = current_name in ["N/A", "Home", "Flooring Contractor", "Flooring", "Contractor", "Gmail", "Currently.com", "403 Forbidden", "404 Not Found", "Facebook", "Instagram", "dot.cards"]
            is_domain_like = "." in current_name and " " not in current_name
            is_junk = "servicing" in current_name.lower() or "reliability by design" in current_name.lower()

            if is_slug_based or is_generic or is_domain_like or is_junk or len(current_name) < 4:
                if len(gm_name) > 2:
                    company.name = gm_name
                    updated = True

        # Address recovery
        if not company.full_address:
            val = gm_data.get("Full Address") or gm_data.get("full_address") or gm_data.get("address") or gm_data.get("Full_Address")
            if val:
                company.full_address = val
                updated = True
            
        # Place ID recovery
        if not company.place_id:
            val = gm_data.get("Place ID") or gm_data.get("place_id") or gm_data.get("Place_ID")
            if val:
                company.place_id = val
                updated = True

        if updated:
            company.save()
            console.print(f"Updated (GM Index) -> {company.name} ({company.slug})")

    def _get_gm_data_by_id(self, place_id: str, company_dir: Path) -> dict[str, Any] | None:
        gm_enrich_path = company_dir / "enrichments" / "google-maps.md"
        if gm_enrich_path.exists():
            try:
                with open(gm_enrich_path, "r") as f:
                    content = f.read()
                    from ..core.text_utils import parse_frontmatter
                    frontmatter_str = parse_frontmatter(content)
                    if frontmatter_str:
                        data = yaml.safe_load(frontmatter_str)
                        return cast(dict[str, Any], data)
            except Exception:
                pass
        
        # Also check global cache
        gm_cache_path = get_cocli_base_dir() / "campaigns" / "turboship" / "indexes" / "google_maps_prospects" / f"{place_id}.csv"
        if gm_cache_path.exists():
            try:
                with open(gm_cache_path, "r") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        return cast(dict[str, Any], row)
            except Exception:
                pass
        return None