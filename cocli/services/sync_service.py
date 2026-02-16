import subprocess
import logging
from pathlib import Path
from typing import Optional, List, Literal, Dict, Any
from ..core.config import load_campaign_config
from ..core.paths import paths

logger = logging.getLogger(__name__)

SyncDirection = Literal["up", "down"]

class SyncService:
    """
    Core Service for S3 Synchronization.
    Encapsulates bucket resolution, path mapping, and command execution.
    """

    def __init__(self, campaign_name: str, aws_config: Optional[Dict[str, Any]] = None):
        self.campaign_name = campaign_name
        self.config = load_campaign_config(campaign_name)
        
        self.aws_config = aws_config or self.config.get("aws", {})
        self.bucket = self.aws_config.get("data_bucket_name") or f"cocli-data-{campaign_name}"
        self.profile = self.aws_config.get("profile") or self.aws_config.get("aws_profile")
        self.region = self.aws_config.get("region_name") or self.aws_config.get("region")

    def _get_aws_bin(self) -> str:
        """Returns the absolute path to the aws binary if not in PATH."""
        import shutil
        aws_bin = shutil.which("aws")
        if aws_bin:
            return aws_bin
        
        # Fallbacks for common container/RPi paths
        for p in ["/usr/local/bin/aws", "/usr/bin/aws"]:
            if Path(p).exists():
                return p
        return "aws"

    def sync_queue(
        self, 
        queue_name: str, 
        direction: SyncDirection = "up", 
        delete: bool = False, 
        dry_run: bool = False,
        limit: Optional[int] = None
    ) -> subprocess.CompletedProcess[str]:
        """
        Syncs a campaign queue (pending folder) with S3.
        """
        local_path = paths.queue(self.campaign_name, queue_name) / "pending"
        s3_key = paths.s3_queue_pending(self.campaign_name, queue_name)
        s3_path = f"s3://{self.bucket}/{s3_key}"

        if direction == "up" and not local_path.exists():
            raise FileNotFoundError(f"Local queue path does not exist: {local_path}")

        source = str(local_path) if direction == "up" else s3_path
        dest = s3_path if direction == "up" else str(local_path)

        if limit:
            # Simple simulation: exclude everything, then include specific shards
            # We'll just take the first 'limit' shards if they are dirs
            import os
            try:
                # Get first N shards from local for 'up', or we'd need S3 list for 'down'
                shards = sorted([d for d in os.listdir(local_path) if len(d) <= 2])[:limit]
                # AWS CLI 'include' works after 'exclude'
                # But it's easier to just pass them as extra args to _run_sync
                # For now, let's just use a simple list of includes
                include_patterns = [f"{s}/*" for s in shards]
                # We'll modify _run_sync to handle this
                return self._run_sync(source, dest, delete=delete, dry_run=dry_run, exclude=["*"], include=include_patterns)
            except Exception:
                pass

        return self._run_sync(source, dest, delete=delete, dry_run=dry_run)

    def sync_indexes(self, dry_run: bool = False) -> List[subprocess.CompletedProcess[str]]:
        """
        Performs bidirectional sync of both Shared Areas and Campaign indexes.
        """
        results = []
        results.extend(self.sync_shared_areas(dry_run=dry_run))
        results.extend(self.sync_campaign_indexes(dry_run=dry_run))
        return results

    def sync_shared_areas(self, dry_run: bool = False) -> List[subprocess.CompletedProcess[str]]:
        """Syncs the shared scraped_areas index."""
        local_areas = paths.indexes / "scraped_areas"
        s3_path = f"s3://{self.bucket}/indexes/scraped_areas/"
        
        results = []
        results.append(self._run_sync(s3_path, str(local_areas), dry_run=dry_run))
        results.append(self._run_sync(str(local_areas), s3_path, dry_run=dry_run))
        return results

    def sync_campaign_indexes(self, dry_run: bool = False) -> List[subprocess.CompletedProcess[str]]:
        """Syncs campaign-specific indexes."""
        local_idx = paths.campaign_indexes(self.campaign_name)
        s3_key = f"campaigns/{self.campaign_name}/indexes/"
        s3_path = f"s3://{self.bucket}/{s3_key}"

        results = []
        # 1. Down (Merge updates from cloud)
        results.append(self._run_sync(s3_path, str(local_idx), dry_run=dry_run))
        # 2. Up (Push local updates to cloud)
        results.append(self._run_sync(str(local_idx), s3_path, dry_run=dry_run))
        
        return results

    def sync_config(self, direction: SyncDirection = "up", dry_run: bool = False) -> subprocess.CompletedProcess[str]:
        """Syncs the campaign config.toml file specifically."""
        local_path = paths.campaign(self.campaign_name) / "config.toml"
        s3_path = f"s3://{self.bucket}/campaigns/{self.campaign_name}/config.toml"

        if direction == "up" and not local_path.exists():
            raise FileNotFoundError(f"Local config file not found: {local_path}")

        source = str(local_path) if direction == "up" else s3_path
        dest = s3_path if direction == "up" else str(local_path)

        # Use 'cp' instead of 'sync' for a single file to be explicit
        cmd = [self._get_aws_bin(), "s3", "cp", source, dest]
        if dry_run:
            cmd.append("--dryrun")
        if self.profile:
            cmd.extend(["--profile", self.profile])
        if self.region:
            cmd.extend(["--region", self.region])

        logger.info(f"Executing config sync: {' '.join(cmd)}")
        return subprocess.run(cmd, check=True, capture_output=True, text=True)

    def _run_sync(
        self, 
        source: str, 
        dest: str, 
        delete: bool = False, 
        dry_run: bool = False,
        exclude: Optional[List[str]] = None,
        include: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> subprocess.CompletedProcess[str]:
        """Helper to execute the AWS CLI command with logging."""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = Path(".logs") / f"{timestamp}_s3_sync.log"
        log_file.parent.mkdir(exist_ok=True)

        cmd = [self._get_aws_bin(), "s3", "sync", source, dest]
        
        if delete:
            cmd.append("--delete")
        if dry_run:
            cmd.append("--dryrun")
        if self.profile:
            cmd.extend(["--profile", self.profile])
        if self.region:
            cmd.extend(["--region", self.region])
        
        if exclude:
            for pattern in exclude:
                cmd.extend(["--exclude", pattern])
        if include:
            for pattern in include:
                cmd.extend(["--include", pattern])

        logger.info(f"Executing: {' '.join(cmd)}")
        
        with open(log_file, "w") as f:
            f.write(f"Command: {' '.join(cmd)}\n\n")
            return subprocess.run(cmd, check=True, stdout=f, stderr=f, text=True)
