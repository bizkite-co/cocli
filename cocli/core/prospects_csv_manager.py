# POLICY: frictionless-data-policy-enforcement (See docs/FRICTIONLESS_DATA_POLICY_ENFORCEMENT.md)
import csv
import logging
from pathlib import Path
from typing import Iterator, Optional

from ..models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from .sharding import get_place_id_shard
from .config import get_campaign_dir, get_campaign_scraped_data_dir  # noqa: F401

logger = logging.getLogger(__name__)

class ProspectsIndexManager:
    """
    Manages Google Maps prospects stored as individual files in a sharded index.
    Supports both legacy CSV (.csv) and modern USV (.usv) formats.
    Directory: data/campaigns/{campaign}/indexes/google_maps_prospects/
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        from cocli.core.paths import paths
        self.index_dir = paths.campaign_prospect_index(campaign_name)
        
        # FDPE: Ensure the schema authority exists
        try:
            GoogleMapsProspect.save_datapackage(self.index_dir)
        except Exception as e:
            logger.error(f"FDPE: Failed to save datapackage for prospect index: {e}")
            
    def _get_checkpoint_path(self) -> Path:
        """Internal helper for maintenance scripts."""
        return self.index_dir / "prospects.checkpoint.usv"

    def get_file_path(self, place_id: str, for_write: bool = False) -> Path:
        """
        Returns the path to a prospect file.
        If for_write=True, ALWAYS returns the new sharded path in the WAL.
        If for_write=False (default), checks for existing files in both modern and legacy locations.
        """
        from cocli.core.paths import paths
        shard = get_place_id_shard(place_id)
        # Use paths authority for standard WAL location
        sharded_path = paths.campaign(self.campaign_name).index("google_maps_prospects").wal / shard / f"{place_id}.usv"
        
        if for_write:
            return sharded_path

        # 1. Check for standard sharded path (.usv) in the WAL
        if sharded_path.exists():
            return sharded_path
            
        # 2. Check for legacy paths (root-level shards, inbox, or flat root)
        legacy_paths = [
            self.index_dir / shard / f"{place_id}.usv",
            self.index_dir / f"{place_id}.usv",
            self.index_dir / f"{place_id}.csv",
            self.index_dir / "inbox" / f"{place_id}.usv",
            self.index_dir / "inbox" / f"{place_id}.csv"
        ]
        
        for p in legacy_paths:
            if p.exists():
                return p
                
        return sharded_path

    def has_prospect(self, place_id: str) -> bool:
        """Checks if a prospect exists in the index (WAL or Checkpoint)."""
        # 1. Check WAL / Legacy paths (fast individual file check)
        if self.get_file_path(place_id).exists():
            return True
            
        # 2. Check Checkpoint (slower file scan, but necessary for completeness)
        checkpoint_path = self._get_checkpoint_path()
        if checkpoint_path.exists():
            try:
                # Fast string check for existence in USV
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    return place_id in content
            except Exception:
                pass
        return False

    def has_place_id(self, place_id: str) -> bool:
        """Legacy alias for has_prospect."""
        return self.has_prospect(place_id)

    def append_prospect(self, prospect: GoogleMapsProspect) -> bool:
        """Saves a prospect to the index. Returns True if successful."""
        try:
            file_path = self.get_file_path(prospect.place_id, for_write=True)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(prospect.to_usv())
            return True
        except Exception as e:
            logger.error(f"Failed to append prospect {prospect.place_id}: {e}")
            return False

    def read_all_prospects(self) -> Iterator[GoogleMapsProspect]:
        """Iterates through all prospects in the index."""
        all_files = []

        # 1. Read Checkpoint (Cold Layer) FIRST
        checkpoint_path = self._get_checkpoint_path()
        if checkpoint_path.exists():
            all_files.append(checkpoint_path)

        # 2. Read WAL (Hot Layer) LAST
        from cocli.core.paths import paths
        wal_dir = paths.campaign(self.campaign_name).index("google_maps_prospects").wal
        search_dirs = [wal_dir]
        
        for s_dir in search_dirs:
            if s_dir.exists():
                all_files.extend(list(s_dir.rglob("*.usv")))
                all_files.extend(list(s_dir.rglob("*.csv")))

        for file_path in all_files:
            if not file_path.is_file():
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.suffix == ".usv":
                        # Detect Header
                        first_line = f.readline()
                        if not first_line:
                            continue
                        
                        # Skip header if present
                        if "created_at" in first_line:
                            # It's a header, read the next line
                            pass
                        else:
                            # It's data, parse it
                            try:
                                yield GoogleMapsProspect.from_usv(first_line)
                            except Exception:
                                pass
                        
                        # Parse remaining lines
                        for line in f:
                            if line.strip():
                                try:
                                    yield GoogleMapsProspect.from_usv(line)
                                except Exception:
                                    pass
                    else:
                        # Legacy CSV
                        reader = csv.DictReader(f)
                        for row in reader:
                            try:
                                yield GoogleMapsProspect.model_validate(row)
                            except Exception:
                                pass
            except Exception as e:
                logger.error(f"Error reading prospect file {file_path}: {e}")

    def get_prospect(self, place_id: str) -> Optional[GoogleMapsProspect]:
        """Retrieves a single prospect by place_id."""
        file_path = self.get_file_path(place_id)
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.suffix == ".usv":
                        # Skip header if present
                        for line in f:
                            if line.strip():
                                if "created_at" in line:
                                    continue
                                return GoogleMapsProspect.from_usv(line)
                    else:
                        reader = csv.DictReader(f)
                        data = next(reader, None)
                        if data:
                            return GoogleMapsProspect.model_validate(data)
            except Exception as e:
                logger.error(f"Error reading prospect {place_id} from {file_path}: {e}")

        # 2. Check Checkpoint if individual file not found
        checkpoint_path = self._get_checkpoint_path()
        if checkpoint_path.exists():
            try:
                # Fast check before parsing
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    # Checkpoint might be large, but we need to find the specific line
                    for line in f:
                        if place_id in line:
                            try:
                                prospect = GoogleMapsProspect.from_usv(line)
                                if prospect.place_id == place_id:
                                    return prospect
                            except Exception:
                                continue
            except Exception as e:
                logger.error(f"Error searching checkpoint for {place_id}: {e}")
                
        return None
