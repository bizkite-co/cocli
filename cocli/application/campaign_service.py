import csv
import logging
import toml
from typing import Optional, Dict, Any

from ..core.config import get_campaign_dir, load_campaign_config
from ..core.exclusions import ExclusionManager
from ..core.geocoding import get_coordinates_from_city_state, get_coordinates_from_address

logger = logging.getLogger(__name__)

class CampaignService:
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.campaign_dir = get_campaign_dir(campaign_name)
        if not self.campaign_dir:
            # Fallback for bootstrapping: check if the directory exists in data/campaigns
            from ..core.config import get_campaigns_dir
            self.campaign_dir = get_campaigns_dir() / campaign_name
            
        self.config_path = self.campaign_dir / "config.toml"
        self.exclusion_manager = ExclusionManager(campaign_name)

    def get_config(self) -> Dict[str, Any]:
        """Returns the raw configuration dictionary."""
        return load_campaign_config(self.campaign_name)

    def activate(self) -> None:
        """
        Sets this campaign as the active context and performs side effects 
        like updating .envrc with the campaign's AWS profile.
        """
        from ..core.config import set_campaign
        from pathlib import Path
        
        set_campaign(self.campaign_name)
        
        config = self.get_config()
        admin_profile = config.get("aws", {}).get("profile")
        
        if admin_profile:
            envrc_path = Path(".envrc")
            if envrc_path.exists():
                try:
                    lines = []
                    found = False
                    with open(envrc_path, "r") as ef:
                        for line in ef:
                            if line.strip().startswith("export AWS_PROFILE="):
                                lines.append(f'export AWS_PROFILE="{admin_profile}"\n')
                                found = True
                            else:
                                lines.append(line)
                    if not found:
                        lines.append(f'export AWS_PROFILE="{admin_profile}"\n')
                    with open(envrc_path, "w") as ef:
                        ef.writelines(lines)
                    logger.info(f"Updated .envrc with AWS_PROFILE={admin_profile}")
                except Exception as e:
                    logger.warning(f"Could not update .envrc: {e}")

    def add_exclude(self, identifier: str, reason: Optional[str] = None) -> bool:
        """Identifier can be a slug or a domain."""
        if "." in identifier:
            self.exclusion_manager.add_exclusion(domain=identifier, reason=reason)
        else:
            self.exclusion_manager.add_exclusion(slug=identifier, reason=reason)
        return True

    def remove_exclude(self, identifier: str) -> bool:
        if "." in identifier:
            self.exclusion_manager.remove_exclusion(domain=identifier)
        else:
            self.exclusion_manager.remove_exclusion(slug=identifier)
        return True

    def add_query(self, query: str) -> bool:
        config = load_campaign_config(self.campaign_name)
        queries = config.setdefault("prospecting", {}).get("queries", [])
        if query not in queries:
            queries.append(query)
            queries.sort()
            config["prospecting"]["queries"] = queries
            self._save_config(config)
            return True
        return False

    def remove_query(self, query: str) -> bool:
        config = load_campaign_config(self.campaign_name)
        queries = config.get("prospecting", {}).get("queries", [])
        if query in queries:
            queries.remove(query)
            config["prospecting"]["queries"] = queries
            self._save_config(config)
            return True
        return False

    def add_location(self, location: str) -> bool:
        config = load_campaign_config(self.campaign_name)
        target_csv = config.get("prospecting", {}).get("target-locations-csv")
        
        if target_csv:
            csv_path = self.campaign_dir / target_csv
            rows = []
            exists = False
            fieldnames = ["name", "beds", "lat", "lon", "city", "state", "csv_name", "saturation_score", "company_slug"]
            
            if csv_path.exists():
                with open(csv_path, "r", newline="") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames:
                        fieldnames = list(reader.fieldnames)
                    for row in reader:
                        if row.get("name") == location or row.get("city") == location:
                            exists = True
                        rows.append(row)
            
            if not exists:
                new_row = {fn: "" for fn in fieldnames}
                if "," in location:
                    city, state = [part.strip() for part in location.split(",", 1)]
                    new_row["city"] = city
                    new_row["state"] = state
                    new_row["name"] = location
                    coords = get_coordinates_from_city_state(location)
                else:
                    new_row["name"] = location
                    new_row["city"] = location
                    coords = get_coordinates_from_address(location)
                
                if coords:
                    new_row["lat"] = str(coords["latitude"])
                    new_row["lon"] = str(coords["longitude"])
                
                rows.append(new_row)
                rows.sort(key=lambda x: x.get("name") or x.get("city") or "")
                
                with open(csv_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                return True
        else:
            locations = config.setdefault("prospecting", {}).get("locations", [])
            if location not in locations:
                locations.append(location)
                locations.sort()
                config["prospecting"]["locations"] = locations
                self._save_config(config)
                return True
        return False

    def remove_location(self, location: str) -> bool:
        config = load_campaign_config(self.campaign_name)
        target_csv = config.get("prospecting", {}).get("target-locations-csv")
        removed = False
        
        if target_csv:
            csv_path = self.campaign_dir / target_csv
            if csv_path.exists():
                rows = []
                with open(csv_path, "r", newline="") as f:
                    reader = csv.DictReader(f)
                    fieldnames = list(reader.fieldnames) if reader.fieldnames else []
                    for row in reader:
                        if row.get("name") == location or row.get("city") == location:
                            removed = True
                            continue
                        rows.append(row)
                
                if removed:
                    with open(csv_path, "w", newline="") as f:
                        writer = csv.DictWriter(f, fieldnames=fieldnames)
                        writer.writeheader()
                        writer.writerows(rows)
                    return True
        
        if not removed:
            locations = config.get("prospecting", {}).get("locations", [])
            if location in locations:
                locations.remove(location)
                config["prospecting"]["locations"] = locations
                self._save_config(config)
                return True
        return False

    def add_node(self, hostname: str, label: Optional[str] = None) -> bool:
        """Adds a worker node to the cluster configuration."""
        config = self.get_config()
        cluster = config.setdefault("cluster", {})
        nodes = cluster.setdefault("nodes", [])
        
        # Check if already exists
        for node in nodes:
            if node.get("host") == hostname:
                return False
                
        nodes.append({"host": hostname, "label": label or hostname})
        self.save_config(config)
        return True

    def remove_node(self, hostname: str) -> bool:
        """Removes a worker node from the cluster configuration."""
        config = self.get_config()
        cluster = config.get("cluster", {})
        nodes = cluster.get("nodes", [])
        
        initial_len = len(nodes)
        cluster["nodes"] = [n for n in nodes if n.get("host") != hostname]
        
        if len(cluster["nodes"]) < initial_len:
            self.save_config(config)
            return True
        return False

    def set_scaling(self, host: str, worker_type: str, count: int) -> bool:
        """Sets the worker count for a specific host and task type."""
        config = self.get_config()
        scaling = config.setdefault("prospecting", {}).setdefault("scaling", {})
        host_scaling = scaling.setdefault(host, {})
        host_scaling[worker_type] = count
        self.save_config(config)
        return True

    def geocode_locations(self) -> int:
        """
        Scans the campaign's target locations CSV and fills in missing geocoordinates.
        Returns the number of updated locations.
        """
        config = self.get_config()
        target_csv = config.get("prospecting", {}).get("target-locations-csv")
        if not target_csv:
            return 0

        csv_path = self.campaign_dir / target_csv
        if not csv_path.exists():
            return 0

        rows = []
        updated_count = 0
        fieldnames = []
        
        with open(csv_path, "r", newline="") as f:
            reader = csv.DictReader(f)
            fieldnames = list(reader.fieldnames) if reader.fieldnames else []
            for row in reader:
                if not row.get("lat") or not row.get("lon"):
                    name = row.get("name") or row.get("city")
                    if name:
                        coords = None
                        if "," in name:
                            coords = get_coordinates_from_city_state(name)
                        else:
                            coords = get_coordinates_from_address(name)
                        
                        if coords:
                            row["lat"] = str(coords["latitude"])
                            row["lon"] = str(coords["longitude"])
                            updated_count += 1
                rows.append(row)

        if updated_count > 0:
            with open(csv_path, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
        
        return updated_count

    def save_config(self, config: Any) -> None:
        """
        Saves the campaign configuration.
        Accepts either a dictionary or a Campaign Pydantic model.
        """
        if hasattr(config, "model_dump"):
            # If it's a Pydantic model (like Campaign)
            data = config.model_dump(by_alias=True, exclude_none=True)
            
            # The Campaign model is flattened. We need to move campaign-specific 
            # fields back into a [campaign] section to match the established format.
            campaign_fields = ["name", "tag", "domain", "company-slug", "workflows", "queue_type", "timezone"]
            structured_data: Dict[str, Any] = {"campaign": {}}
            
            for k, v in data.items():
                if k in campaign_fields:
                    structured_data["campaign"][k] = v
                else:
                    structured_data[k] = v
            
            with open(self.config_path, "w") as f:
                toml.dump(structured_data, f)
        else:
            with open(self.config_path, "w") as f:
                toml.dump(config, f)
        logger.info(f"Saved configuration to {self.config_path}")

    def _save_config(self, config: Dict[str, Any]) -> None:
        self.save_config(config)

    def compile_lifecycle_index(self) -> Any:
        """
        Compiles the lifecycle index for this campaign.
        Yields progress updates.
        """
        from ..core.lifecycle_manager import LifecycleManager
        manager = LifecycleManager(self.campaign_name)
        yield from manager.compile()

    def restore_names_from_index(self, dry_run: bool = False) -> Any:
        """
        Reads from the Google Maps prospect index and restores names in _index.md.
        Also writes a file-per-object USV to enrichments/ for provenance.
        Yields status updates for progress bars.
        """
        from ..core.prospects_csv_manager import ProspectsIndexManager
        from ..models.companies.company import Company
        from ..core.config import get_companies_dir
        from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect

        manager = ProspectsIndexManager(self.campaign_name)
        companies_dir = get_companies_dir()
        
        stats = {"restored": 0, "receipts_written": 0, "errors": 0}
        
        # 1. Load prospects into a list to get a total count
        prospects = list(manager.read_all_prospects())
        total = len(prospects)
        
        for i, prospect in enumerate(prospects):
            if not prospect.company_slug or not prospect.name:
                continue
                
            slug = prospect.company_slug
            company_obj = Company.get(slug)
            
            # Yield progress
            yield {"current": i + 1, "total": total, "slug": slug}

            if not company_obj:
                continue

            try:
                # 1. Restore Name if corrupted or missing
                if company_obj.name != prospect.name:
                    logger.info(f"Restoring name for {slug}: {company_obj.name} -> {prospect.name}")
                    company_obj.name = prospect.name
                    if not dry_run:
                        company_obj.save(email_sync=False)
                    stats["restored"] += 1

                # 2. Write provenance receipt (google_maps.usv)
                if not dry_run:
                    enrich_dir = companies_dir / slug / "enrichments"
                    enrich_dir.mkdir(exist_ok=True)
                    receipt_path = enrich_dir / "google_maps.usv"
                    
                    from ..core.utils import UNIT_SEP
                    with open(receipt_path, "w", encoding="utf-8") as f:
                        header = UNIT_SEP.join(list(GoogleMapsProspect.model_fields.keys()))
                        f.write(f"{header}\n")
                        f.write(prospect.to_usv())
                    stats["receipts_written"] += 1
                    
            except Exception as e:
                logger.error(f"Failed to restore name for {slug}: {e}")
                stats["errors"] += 1
                
        yield stats
