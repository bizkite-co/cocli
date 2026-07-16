"""Deployment and campaign rollout orchestration (application layer).

No Rich/console presentation — callers format diagnostics for CLI/TUI.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from pydantic import BaseModel, Field

from ..core.config import get_campaign, load_campaign_config
from ..core.paths import paths

logger = logging.getLogger(__name__)

LogCallback = Callable[[str], None]


def _emit(log_callback: Optional[LogCallback], message: str) -> None:
    logger.info(message)
    if log_callback is not None:
        log_callback(message)


class RolloutBatchStatus(BaseModel):
    """Discovery-gen batches deployed for a campaign."""

    campaign_name: str
    batches: Dict[str, int] = Field(default_factory=dict)

    @property
    def total_tasks(self) -> int:
        return sum(self.batches.values())


class PiNodeStats(BaseModel):
    """Per-PI scrape index counters (SSH diagnostics)."""

    wal_companies: int = 0
    active_companies: int = 0
    reachable: bool = False


class RolloutDiagnostics(BaseModel):
    """Intermediate artifact: hub-side rollout status / progress / report data."""

    campaign_name: str
    batches: Dict[str, int] = Field(default_factory=dict)
    hub_companies: int = 0
    total_tasks: int = 0
    avg_per_task: float = 0.0
    coverage_estimate_pct: float = 0.0

    @classmethod
    def from_counts(
        cls,
        campaign_name: str,
        batches: Dict[str, int],
        hub_companies: int,
    ) -> "RolloutDiagnostics":
        total = sum(batches.values())
        avg = hub_companies / total if total > 0 else 0.0
        # Same heuristic as the original report command.
        coverage = (hub_companies / (total * 10)) * 100 if total > 0 else 0.0
        return cls(
            campaign_name=campaign_name,
            batches=batches,
            hub_companies=hub_companies,
            total_tasks=total,
            avg_per_task=avg,
            coverage_estimate_pct=coverage,
        )


class ConfigSyncResult(BaseModel):
    """Result of pushing/pulling campaign config.toml via S3."""

    campaign_name: str
    success: bool = True
    message: str = ""
    bucket_name: str = ""
    s3_key: str = ""
    local_path: Optional[Path] = None
    warning: bool = False


class BroadcastConfigResult(BaseModel):
    """Result of gossip-broadcasting scaling config to cluster nodes."""

    campaign_name: str
    success: bool = True
    message: str = ""
    scaling: Dict[str, Any] = Field(default_factory=dict)


class RolloutSyncResult(BaseModel):
    """Result of S3 pull + place_id dedup for rollout results."""

    campaign_name: str
    success: bool = True
    message: str = ""
    total_tasks_deployed: int = 0
    unique_companies: int = 0
    duplicates: int = 0
    avg_companies_per_task: float = 0.0


class DeploymentService:
    def __init__(self, campaign_name: Optional[str] = None):
        self.campaign_name = campaign_name or get_campaign() or "default"

    # ------------------------------------------------------------------
    # Existing infra methods
    # ------------------------------------------------------------------

    def deploy_infra(self) -> Dict[str, Any]:
        """Deploys AWS Infrastructure using CDK."""
        try:
            cmd = f"cocli infrastructure deploy-infra --campaign {self.campaign_name}"
            subprocess.run(cmd, shell=True, check=True)
            return {"status": "success", "message": "Infra deployment triggered."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def scale_service(self, count: int) -> Dict[str, Any]:
        """
        Scales the enrichment service in Fargate.
        Corresponds to 'make scale'.
        """
        config = load_campaign_config(self.campaign_name)
        aws_config = config.get("aws", {})
        profile = aws_config.get("profile")
        region = aws_config.get("region", "us-east-1")

        try:
            cmd = [
                "aws",
                "ecs",
                "update-service",
                "--cluster",
                "ScraperCluster",
                "--service",
                "EnrichmentService",
                "--desired-count",
                str(count),
                "--region",
                region,
            ]
            if profile:
                cmd.extend(["--profile", profile])

            subprocess.run(cmd, check=True)
            return {"status": "success", "count": count}
        except Exception as e:
            logger.error(f"Failed to scale service: {e}")
            return {"status": "error", "message": str(e)}

    def get_service_status(self) -> Dict[str, Any]:
        """Returns status of Fargate service."""
        from ..core.reporting import get_active_fargate_tasks, get_boto3_session

        config = load_campaign_config(self.campaign_name)
        session = get_boto3_session(config)

        count = get_active_fargate_tasks(session)
        return {"status": "active", "running_tasks": count}

    # ------------------------------------------------------------------
    # Rollout helpers (from commands/campaign/rollout.py)
    # ------------------------------------------------------------------

    @staticmethod
    def get_pi_hostnames() -> Dict[str, str]:
        """PI hostnames (Tailscale MagicDNS names)."""
        return {
            "cocli5x0": "cocli5x0.tail87cf32.ts.net",
            "cocli5x1": "cocli5x1.tail87cf32.ts.net",
        }

    @staticmethod
    def ssh_run(hostname: str, command: str) -> Tuple[int, str]:
        """Run command on remote host via SSH. Returns (exit_code, output)."""
        try:
            result = subprocess.run(
                ["ssh", f"mstouffer@{hostname}", command],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode, result.stdout.strip()
        except subprocess.TimeoutExpired:
            return 1, ""
        except Exception as e:
            return 1, str(e)

    @staticmethod
    def count_lines_in_dir(path: Path, pattern: str = "*.usv") -> int:
        """Count total lines in all matching files in a directory."""
        count = 0
        if path.exists():
            for file in path.glob(pattern):
                try:
                    with open(file, "r") as f:
                        count += sum(1 for _ in f)
                except Exception:
                    pass
        return count

    def get_batch_status(
        self, campaign_name: Optional[str] = None
    ) -> RolloutBatchStatus:
        """Status of discovery-gen batches under pending/batches/."""
        name = campaign_name or self.campaign_name
        dg_queue = paths.campaign(name).queue("discovery-gen")
        batches_dir = dg_queue.pending / "batches"

        batches: Dict[str, int] = {}
        if batches_dir.exists():
            for batch_file in batches_dir.glob("*.usv"):
                with open(batch_file, "r") as f:
                    count = sum(1 for _ in f)
                batches[batch_file.stem] = count

        return RolloutBatchStatus(campaign_name=name, batches=batches)

    def get_pi_stats(
        self, campaign_name: Optional[str] = None
    ) -> Dict[str, PiNodeStats]:
        """Scraping stats from each PI via SSH (rollout diagnostics)."""
        name = campaign_name or self.campaign_name
        stats: Dict[str, PiNodeStats] = {}

        for pi_name, hostname in self.get_pi_hostnames().items():
            wal_command = (
                f"find ~/repos/data/campaigns/{name}/indexes/google_maps_prospects/wal "
                "-name '*.usv' 2>/dev/null | xargs wc -l 2>/dev/null | "
                "tail -1 | awk '{print $1}'"
            )
            active_command = (
                f"find ~/repos/data/campaigns/{name}/indexes/google_maps_prospects/active "
                "-name '*.usv' 2>/dev/null | xargs wc -l 2>/dev/null | "
                "tail -1 | awk '{print $1}'"
            )

            rc1, wal_out = self.ssh_run(hostname, wal_command)
            rc2, active_out = self.ssh_run(hostname, active_command)

            stats[pi_name] = PiNodeStats(
                wal_companies=int(wal_out) if wal_out and wal_out.isdigit() else 0,
                active_companies=int(active_out)
                if active_out and active_out.isdigit()
                else 0,
                reachable=rc1 == 0 and rc2 == 0,
            )

        return stats

    def get_rollout_diagnostics(
        self, campaign_name: Optional[str] = None
    ) -> RolloutDiagnostics:
        """Hub-side batch + active-index snapshot for status/progress/report."""
        name = campaign_name or self.campaign_name
        batches = self.get_batch_status(name).batches
        hub_index_path = (
            paths.campaign(name).index("google_maps_prospects").path / "active"
        )
        hub_companies = self.count_lines_in_dir(hub_index_path)
        return RolloutDiagnostics.from_counts(name, batches, hub_companies)

    # ------------------------------------------------------------------
    # Config broadcast / S3 config sync
    # ------------------------------------------------------------------

    def broadcast_scaling_config(
        self,
        campaign_name: Optional[str] = None,
        log_callback: Optional[LogCallback] = None,
    ) -> BroadcastConfigResult:
        """
        Broadcast current scaling config to cluster nodes via Gossip.

        Intermediate artifact: ConfigDatagram on the gossip bus (not persisted).
        """
        import toml

        from cocli.core.environment import get_environment
        from cocli.core.gossip_bridge import bridge
        from cocli.models.wal.record import ConfigDatagram

        name = campaign_name or self.campaign_name
        config_path = paths.campaign(name).path / "config.toml"
        if not config_path.exists():
            raise ValueError(f"Config not found at {config_path}")

        with open(config_path, "r") as f:
            config = toml.load(f)

        scaling = config.get("prospecting", {}).get("scaling", {})
        if not scaling:
            return BroadcastConfigResult(
                campaign_name=name,
                success=True,
                message="No scaling configuration found in config.toml",
                scaling={},
            )

        datagram = ConfigDatagram(
            campaign_name=name,
            node_id="*",
            config_json=json.dumps(scaling),
            timestamp=str(int(time.time())),
            environment=get_environment().value,
        )

        _emit(log_callback, f"Broadcasting scaling update for {name}...")
        bridge.start()
        time.sleep(2)
        bridge.broadcast_msg(datagram.to_usv())
        time.sleep(1)
        bridge.stop()

        return BroadcastConfigResult(
            campaign_name=name,
            success=True,
            message="Broadcast complete.",
            scaling=dict(scaling) if isinstance(scaling, dict) else {"raw": scaling},
        )

    def push_config_to_s3(
        self, campaign_name: Optional[str] = None
    ) -> ConfigSyncResult:
        """Upload local campaign config.toml to S3 (Fargate source of truth)."""
        from cocli.core.reporting import (
            get_boto3_session,
            get_data_bucket_name,
            get_s3_client,
        )

        name = campaign_name or self.campaign_name
        config_path = paths.campaign(name).path / "config.toml"
        if not config_path.exists():
            raise ValueError(f"Config not found at {config_path}")

        config = load_campaign_config(name)
        bucket_name = get_data_bucket_name(config, name)
        session = get_boto3_session(config)
        s3 = get_s3_client(session=session)

        s3_key = paths.s3.campaign(name).config()
        s3.upload_file(str(config_path), bucket_name, s3_key)

        return ConfigSyncResult(
            campaign_name=name,
            success=True,
            message=f"Pushed {config_path} -> s3://{bucket_name}/{s3_key}",
            bucket_name=bucket_name,
            s3_key=s3_key,
            local_path=config_path,
        )

    def pull_config_from_s3(
        self, campaign_name: Optional[str] = None
    ) -> ConfigSyncResult:
        """
        Download campaign config.toml from S3 to local disk.

        On Fargate uses task role (no profile) when COCLI_RUNNING_IN_FARGATE is set.
        Missing remote config is a warning, not a hard failure (matches original CLI).
        """
        from cocli.core.reporting import (
            get_boto3_session,
            get_data_bucket_name,
            get_s3_client,
        )

        name = campaign_name or self.campaign_name
        config = load_campaign_config(name)
        bucket_name = os.environ.get("COCLI_S3_BUCKET_NAME") or get_data_bucket_name(
            config, name
        )

        if os.getenv("COCLI_RUNNING_IN_FARGATE"):
            session = get_boto3_session({})
        else:
            session = get_boto3_session(config)
        s3 = get_s3_client(session=session)

        s3_key = paths.s3.campaign(name).config()
        config_path = paths.campaign(name).path / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            s3.download_file(bucket_name, s3_key, str(config_path))
            return ConfigSyncResult(
                campaign_name=name,
                success=True,
                message=f"Pulled s3://{bucket_name}/{s3_key} -> {config_path}",
                bucket_name=bucket_name,
                s3_key=s3_key,
                local_path=config_path,
            )
        except Exception as e:
            msg = (
                f"Warning: Could not pull config from S3 ({e}). "
                "Continuing with whatever is on local disk."
            )
            logger.warning(msg)
            return ConfigSyncResult(
                campaign_name=name,
                success=True,
                message=msg,
                bucket_name=str(bucket_name),
                s3_key=s3_key,
                local_path=config_path,
                warning=True,
            )

    # ------------------------------------------------------------------
    # Rollout sync (S3 + dedup diagnostics)
    # ------------------------------------------------------------------

    def sync_rollout_results(
        self,
        campaign_name: Optional[str] = None,
        workers: int = 20,
        full: bool = False,
        force: bool = False,
        log_callback: Optional[LogCallback] = None,
    ) -> RolloutSyncResult:
        """
        Sync scraping results from PIs via S3 and compute place_id dedup stats.

        Intermediate artifact: local active USV index under
        ``indexes/google_maps_prospects/`` (smart_sync). Diagnostics report
        unique place_ids and cross-PI duplicates.
        """
        from cocli.core.reporting import get_data_bucket_name
        from cocli.core.smart_sync import run_smart_sync

        name = campaign_name or self.campaign_name
        _emit(log_callback, f"Syncing results for {name}...")

        config = load_campaign_config(name)
        aws_config = config.get("aws", {})
        bucket_name = get_data_bucket_name(config, name)

        _emit(log_callback, "Step 1/3: Pulling prospects index from S3...")
        prefix = f"campaigns/{name}/indexes/google_maps_prospects/"
        local_base = paths.campaign(name).index("google_maps_prospects").path
        run_smart_sync(
            "prospects",
            bucket_name,
            prefix,
            local_base,
            name,
            aws_config,
            workers=workers,
            full=full,
            force=force,
        )

        active_path = local_base / "active"
        seen_place_ids: set[str] = set()
        duplicates = 0

        _emit(log_callback, "Step 2/3: Deduplicating by place_id...")
        if active_path.exists():
            for usv_file in active_path.glob("*.usv"):
                try:
                    with open(usv_file, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip():
                                parts = line.strip().split("\x1f")
                                if len(parts) >= 1:
                                    place_id = parts[0]
                                    if place_id in seen_place_ids:
                                        duplicates += 1
                                    else:
                                        seen_place_ids.add(place_id)
                except Exception as e:
                    logger.error(f"Error reading {usv_file}: {e}")

        batches = self.get_batch_status(name).batches
        total_tasks_deployed = sum(batches.values())
        unique_companies = len(seen_place_ids)
        avg = (
            unique_companies / total_tasks_deployed if total_tasks_deployed > 0 else 0.0
        )

        _emit(log_callback, "Step 3/3: Reporting results...")

        return RolloutSyncResult(
            campaign_name=name,
            success=True,
            message=f"Sync Complete for {name}",
            total_tasks_deployed=total_tasks_deployed,
            unique_companies=unique_companies,
            duplicates=duplicates,
            avg_companies_per_task=avg,
        )

    async def push_discovery_data(self, delete: bool = False) -> None:
        """Propagate local discovery tasks/batches to the cluster."""
        from cocli.services.cluster_service import ClusterService

        service = ClusterService(self.campaign_name)
        await service.push_data(delete=delete)

    async def sync_and_audit_cluster(self) -> None:
        """Pull results from cluster nodes and run quality audit."""
        from cocli.services.cluster_service import ClusterService

        service = ClusterService(self.campaign_name)
        await service.sync_and_audit()
