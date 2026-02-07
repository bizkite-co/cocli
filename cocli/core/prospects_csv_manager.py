import csv
import logging
from pathlib import Path
from typing import Iterator

from ..models.google_maps_prospect import GoogleMapsProspect
from ..core.config import get_campaign_scraped_data_dir, get_campaign_dir
from ..core.sharding import get_place_id_shard
from ..core.utils import UNIT_SEP
from ..utils.usv_utils import USVDictReader

logger = logging.getLogger(__name__)

class ProspectsIndexManager:
    """
    Manages Google Maps prospects stored as individual files in a sharded index.
    Supports both legacy CSV (.csv) and modern USV (.usv) formats.
    Directory: data/campaigns/{campaign}/indexes/google_maps_prospects/
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        campaign_dir = get_campaign_dir(campaign_name)
        if campaign_dir:
            self.index_dir = campaign_dir / "indexes" / "google_maps_prospects"
        else:
            # Fallback to legacy path if campaign not found
            self.index_dir = get_campaign_scraped_data_dir(campaign_name)
            
    def get_file_path(self, place_id: str) -> Path:
        """
        Returns the path to a prospect file, prioritizing sharded .usv
        but falling back to legacy locations for reads.
        """
        # 1. Check for new sharded path (.usv)
        shard = get_place_id_shard(place_id)
        sharded_path = self.index_dir / shard / f"{place_id}.usv"
        if sharded_path.exists():
            return sharded_path
            
        # 2. Check for legacy paths
        # Recursive check would be slow for get_file_path, so we check common spots
        legacy_paths = [
            self.index_dir / f"{place_id}.usv",
            self.index_dir / f"{place_id}.csv",
            self.index_dir / "inbox" / f"{place_id}.usv",
            self.index_dir / "inbox" / f"{place_id}.csv"
        ]
        for p in legacy_paths:
            if p.exists():
                return p
                
        # 3. Default for new files: ALWAYS SHARDED
        return sharded_path

    def _get_checkpoint_path(self) -> Path:
        return self.index_dir / "prospects.checkpoint.usv"

    def read_all_prospects(self) -> Iterator[GoogleMapsProspect]:
        """
        Yields prospects from the index, merging the checkpoint and WAL.
        """
        if not self.index_dir.exists():
            return

        seen_pids = set()
        checkpoint_path = self._get_checkpoint_path().resolve()
        
        # 1. Read WAL (Hot Layer) - Files in shards, root, or inbox
        all_files = list(self.index_dir.rglob("*.usv")) + list(self.index_dir.rglob("*.csv"))
        
        # Sort: .usv before .csv, and sharded (more parts) before flat
        sorted_files = sorted(all_files, key=lambda p: (p.stem, p.suffix == ".csv", -len(p.parts)))
        
        for file_path in sorted_files:
            if file_path.resolve() == checkpoint_path:
                continue
            if not file_path.is_file():
                continue
                
            place_id_stem = file_path.stem
            if place_id_stem in seen_pids:
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    if file_path.suffix == ".usv":
                        # Headerless USV: Provide explicit field order
                        ordered_fields = ["place_id", "company_slug", "name", "phone_1"]
                        all_fields = list(GoogleMapsProspect.model_fields.keys())
                        remaining = [f for f in all_fields if f not in ordered_fields]
                        fieldnames = ordered_fields + remaining
                        reader = USVDictReader(f, fieldnames=fieldnames)
                    else:
                        reader = csv.DictReader(f) # type: ignore
                        
                    for row in reader:
                        try:
                            model_data = {k: v for k, v in row.items() if k in GoogleMapsProspect.model_fields}
                            p = GoogleMapsProspect.model_validate(model_data)
                            if p.place_id:
                                seen_pids.add(p.place_id)
                                yield p
                        except Exception as e:
                            logger.error(f"Error validating prospect in {file_path.name}: {e}")
            except Exception as e:
                logger.error(f"Error reading file {file_path}: {e}")

        # 2. Read Checkpoint (Cold Layer)
        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    ordered_fields = ["place_id", "company_slug", "name", "phone_1"]
                    all_fields = list(GoogleMapsProspect.model_fields.keys())
                    remaining = [f for f in all_fields if f not in ordered_fields]
                    fieldnames = ordered_fields + remaining
                    
                    reader = USVDictReader(f, fieldnames=fieldnames)
                    for row in reader:
                        try:
                            p = GoogleMapsProspect.model_validate(row)
                            if p.place_id and p.place_id not in seen_pids:
                                seen_pids.add(p.place_id)
                                yield p
                        except Exception:
                            continue
            except Exception as e:
                logger.error(f"Error reading checkpoint {checkpoint_path}: {e}")

    def append_prospect(self, prospect_data: GoogleMapsProspect) -> bool:
        """
        Writes a single GoogleMapsProspect object to its sharded file in the index.
        Always writes in headerless USV format.
        """
        if not prospect_data.place_id:
            logger.warning(f"Prospect data missing place_id, cannot save to index. Skipping: {prospect_data.name or prospect_data.domain}")
            return False
        
        file_path = self.get_file_path(prospect_data.place_id)
        if file_path.suffix == ".csv":
            old_path = file_path
            file_path = file_path.with_suffix(".usv")
        else:
            old_path = None
        
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'w', encoding='utf-8') as f:
                logger.info(f"WRITING PROSPECT: {prospect_data.place_id} | processed_by: {prospect_data.processed_by}")
                f.write(prospect_data.to_usv())
            
            if old_path and old_path.exists():
                old_path.unlink()
            return True
        except Exception as e:
            logger.error(f"Error writing prospect to index (place_id: {prospect_data.place_id}): {e}")
            return False

    def has_place_id(self, place_id: str) -> bool:
        """Checks if a given Place_ID already exists in the index, using checkpoint baselines."""
        if not place_id:
            return False
        
        shard = get_place_id_shard(place_id)
        if (self.index_dir / shard / f"{place_id}.usv").exists():
            return True
            
        checkpoint = self._get_checkpoint_path()
        if checkpoint.exists():
            try:
                with open(checkpoint, 'r') as f:
                    for line in f:
                        if line.startswith(f"{place_id}{UNIT_SEP}"):
                            return True
            except Exception:
                pass
        
        safe_filename = place_id.replace("/", "_").replace("\\", "_")
        for ext in [".usv", ".csv"]:
            if list(self.index_dir.rglob(f"{safe_filename}{ext}")):
                return True
        return False