# POLICY: frictionless-data-policy-enforcement
from __future__ import annotations
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import Any, Optional, Callable

from ..core.config import load_campaign_config
from ..models.campaigns.worker_config import (
    CampaignClusterConfig,
    PiNodeConfig,
    WorkerDefinition,
)

from rich.console import Console

logger = logging.getLogger(__name__)
console = Console()


BUILD_DIR = "~/repos/cocli_build"


def find_node_ownership_conflicts() -> dict[str, list[str]]:
    """Cross-campaign check: which hostnames are declared in more than one
    campaign's own [cluster.nodes]?

    No separate ownership registry - a dedicated "which campaign owns this
    node" file is exactly the kind of thing that goes stale on its own
    (confirmed 2026-08-07: roadmap's config.toml still declared cocli5x0
    after it was reassigned to turboship-only, discovered only by manually
    diffing `cluster status --campaign X` across campaigns). Deriving the
    conflict set from each campaign's already-authoritative [cluster.nodes]
    means there's nothing extra to keep in sync - a campaign's own config
    change is the only thing that can ever resolve a conflict.

    Returns {hostname: [campaign names that declare it]} for every hostname
    declared by 2+ campaigns. Empty dict means no conflicts.
    """
    from ..core.config import get_all_campaign_dirs
    from ..core.paths import paths

    declared_by: dict[str, list[str]] = {}
    for campaign_dir in get_all_campaign_dirs():
        campaign_name = str(campaign_dir.relative_to(paths.campaigns))
        try:
            service = ClusterService(campaign_name)
        except Exception:
            continue
        for node in service.get_nodes():
            declared_by.setdefault(node.hostname, []).append(campaign_name)

    return {
        hostname: campaigns
        for hostname, campaigns in declared_by.items()
        if len(campaigns) > 1
    }


class ClusterService:
    """
    Central service for managing the Raspberry Pi cluster.
    Implements the 'Safe Hotfix' (Registry-Propagation) deployment strategy.
    """

    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.config = load_campaign_config(campaign_name)

        # 1. Prefer this campaign's OWN [cluster] config over the global one.
        # The global file is a single block with no campaign scoping at all -
        # if it's ever populated (e.g. hand-edited for one campaign's hub),
        # it silently overrides every other campaign's topology too, since
        # ClusterService("other-campaign") reads the exact same block.
        # Confirmed live: setting turboship's registry_host there redirected
        # a `deploy-hotfix --campaign roadmap` run onto turboship's hub and
        # node list instead of roadmap's own.
        cluster_data = self.config.get("cluster", {})
        if not cluster_data.get("nodes"):
            from ..core.config import load_global_config

            global_config = load_global_config()
            cluster_data = global_config.get("cluster", {})

        self.cluster_config = CampaignClusterConfig(**cluster_data)

        # 2. Resolve Registry Host - no cross-campaign hardcoded default here;
        # if nothing specifies one, fall through to the first node the
        # scaling-based fallback below produces.
        self.registry_host: str = cluster_data.get("registry_host") or ""

        # 3. Fallback to prospecting.scaling ONLY if the node list is still empty
        if not self.cluster_config.nodes:
            logger.info(
                "No cluster nodes configured for this campaign, falling back to campaign scaling config."
            )
            scaling = self.config.get("prospecting", {}).get("scaling", {})
            for host_key, workers_data in scaling.items():
                # Nodes are reached over Tailscale by their bare machine name
                # (e.g. "cocli5x1") - confirmed live, "cocli5x1.pi"/"cocli5x0.pi"
                # don't resolve at all, while the bare names do. The old
                # ".pi" suffix looks like a holdover from a pre-Tailscale mDNS
                # setup; keep host_key as-is unless it's already a dotted
                # hostname/IP.
                host = host_key

                # Create WorkerDefinitions from scaling data
                node_workers = []
                for content_type, count in workers_data.items():
                    if count > 0:
                        node_workers.append(
                            WorkerDefinition(
                                name=f"{host_key}-{content_type}",
                                role="full",
                                content_type=content_type,
                                workers=count,
                                iot_profile=None,
                            )
                        )

                if node_workers:
                    self.cluster_config.nodes.append(
                        PiNodeConfig(host=host, ip=None, workers=node_workers, arch="arm64")
                    )

        if not self.registry_host and self.cluster_config.nodes:
            self.registry_host = self.cluster_config.nodes[0].hostname

        # Use IP for registry URL to avoid DNS issues on spokes
        # We need to resolve the hostname to IP using Tailscale if possible
        registry_node = next(
            (n for n in self.cluster_config.nodes if n.hostname == self.registry_host),
            None,
        )
        self.registry_ip = (
            registry_node.ip_address
            if registry_node and registry_node.ip_address
            else self.registry_host
        )
        self.registry_url = f"{self.registry_ip}:5000"

    def get_nodes(self) -> list[PiNodeConfig]:
        return self.cluster_config.nodes

    def _verify_local_build(self) -> bool:
        """Verifies that the local context is complete for a Docker build."""
        project_root = Path(__file__).parent.parent.parent.resolve()
        docker_file = project_root / "docker" / "rpi-worker" / "Dockerfile"
        if not docker_file.exists():
            logger.error(f"Missing Dockerfile at {docker_file}")
            return False
        return True

    async def deploy_hotfix_safe(self, user: str = "mstouffer", force: bool = False) -> dict[str, bool]:
        """
        PERFORMS SAFE HOTFIX:
        1. Verify local build context.
        2. Sync code to Registry Host.
        3. Build image on Registry Host.
        4. Push to local registry.
        5. All nodes pull and restart with 'cocli worker orchestrate'.
        """
        if not self._verify_local_build():
            logger.error("Local build context verification failed. Aborting.")
            return {"local": False}

        # A node declared in more than one campaign's [cluster.nodes] is a
        # live incident waiting to happen: this exact deploy would restart it
        # under THIS campaign's worker mix, and if that node is currently
        # serving a different campaign, that campaign silently loses it
        # (confirmed 2026-08-07 - see find_node_ownership_conflicts()).
        if not force:
            conflicts = find_node_ownership_conflicts()
            contested = {
                node.hostname: [c for c in conflicts[node.hostname] if c != self.campaign_name]
                for node in self.get_nodes()
                if node.hostname in conflicts
            }
            if contested:
                for hostname, other_campaigns in contested.items():
                    logger.error(
                        f"Node '{hostname}' is also declared in [cluster.nodes] for: "
                        f"{', '.join(other_campaigns)}. Deploying '{self.campaign_name}' would "
                        f"restart it under this campaign's worker mix, potentially stealing it "
                        f"from whichever campaign it's actually serving. Remove it from the "
                        f"other campaign's config.toml first, or pass force=True to override."
                    )
                logger.error("Aborting deployment due to node ownership conflict(s).")
                return {hostname: False for hostname in contested}

        results = {}
        image_name = "cocli-worker-rpi:latest"
        registry_image = f"{self.registry_url}/{image_name}"

        # 1. Prepare Registry Host (The Hub)
        logger.info(f"--- Preparing Registry Hub: {self.registry_host} ---")
        if not await self._sync_and_build(
            self.registry_host, image_name, registry_image, user
        ):
            logger.error("Registry Hub build failed. Aborting cluster deployment.")
            return {self.registry_host: False}

        results[self.registry_host] = True

        # 2. Deploy to Spokes
        tasks = []
        for node in self.get_nodes():
            if node.hostname == self.registry_host:
                continue
            tasks.append(self._deploy_to_spoke(node, image_name, registry_image, user))

        if tasks:
            spoke_results = await asyncio.gather(*tasks)
            for i, node in enumerate(
                [n for n in self.get_nodes() if n.hostname != self.registry_host]
            ):
                results[node.hostname] = spoke_results[i]

        return results

    async def _sync_and_build(
        self, host: str, image_name: str, registry_image: str, user: str
    ) -> bool:
        # Ensure we sync from the absolute project root
        project_root = Path(__file__).parent.parent.parent.resolve()

        try:
            # Sync
            subprocess.run(
                ["ssh", f"{user}@{host}", f"mkdir -p {BUILD_DIR}"], check=True
            )
            rsync_cmd = [
                "rsync",
                "-az",
                "--delete",
                "--exclude",
                ".venv",
                "--exclude",
                ".git",
                "--exclude",
                "data",
                "--exclude",
                ".logs",
                str(project_root) + "/",
                f"{user}@{host}:{BUILD_DIR}/",
            ]
            subprocess.run(rsync_cmd, check=True)

            # Build and Push
            build_cmd = f"cd {BUILD_DIR} && docker build -t {image_name} -f docker/rpi-worker/Dockerfile . && docker tag {image_name} {registry_image} && docker push {registry_image}"
            subprocess.run(["ssh", f"{user}@{host}", build_cmd], check=True)

            # Restart Hub
            await self._restart_node(host, image_name, user)
            return True
        except Exception as e:
            logger.error(f"Hub build/push failed on {host}: {e}")
            return False

    async def _deploy_to_spoke(
        self, node: PiNodeConfig, image_name: str, registry_image: str, user: str
    ) -> bool:
        host = node.hostname
        logger.info(f"Deploying to Spoke: {host} (arch: {node.arch})...")

        registry_node = next(
            (n for n in self.cluster_config.nodes if n.hostname == self.registry_host),
            None,
        )
        registry_arch = registry_node.arch if registry_node else "arm64"

        # If architecture matches hub, try fast pull from hub registry
        if node.arch == registry_arch:
            try:
                pull_cmd = f"docker pull {registry_image} && docker tag {registry_image} {image_name}"
                subprocess.run(["ssh", f"{user}@{host}", pull_cmd], check=True)
                await self._restart_node(host, image_name, user)
                return True
            except Exception as e:
                logger.info(f"Pull failed on {host}, falling back to local build: {e}")

        # Mismatched architecture or pull failure: perform native local build on spoke
        logger.info(f"Performing native local build on {host} ({node.arch})...")
        try:
            project_root = Path(__file__).parent.parent.parent.resolve()
            subprocess.run(
                ["ssh", f"{user}@{host}", f"mkdir -p {BUILD_DIR}"], check=True
            )
            rsync_cmd = [
                "rsync",
                "-az",
                "--delete",
                "--exclude",
                ".venv",
                "--exclude",
                ".git",
                "--exclude",
                "data",
                "--exclude",
                ".logs",
                str(project_root) + "/",
                f"{user}@{host}:{BUILD_DIR}/",
            ]
            subprocess.run(rsync_cmd, check=True)
            build_cmd = f"cd {BUILD_DIR} && docker build -t {image_name} -f docker/rpi-worker/Dockerfile ."
            subprocess.run(["ssh", f"{user}@{host}", build_cmd], check=True)
            await self._restart_node(host, image_name, user)
            return True
        except Exception as build_err:
            logger.error(f"Local build failed on {host}: {build_err}")
            return False

    async def _restart_node(self, host: str, image_name: str, user: str) -> None:
        """Restarts the node using the new ORCHESTRATED worker mode."""
        short_name = host.split(".")[0]

        # Ensure target host has latest campaign config in ~/repos/data for container mount
        project_root = Path(__file__).parent.parent.parent.resolve()
        local_cfg = project_root / "data" / "campaigns" / self.campaign_name / "config.toml"
        if local_cfg.exists():
            remote_dir = f"~/repos/data/campaigns/{self.campaign_name}"
            subprocess.run(["ssh", f"{user}@{host}", f"mkdir -p {remote_dir}"], capture_output=True)
            subprocess.run(
                ["rsync", "-az", str(local_cfg), f"{user}@{host}:{remote_dir}/config.toml"],
                capture_output=True,
            )

        # Standardize on 'cocli-supervisor' as the container name for now
        stop_cmd = "docker stop -t 5 cocli-supervisor 2>/dev/null || true; docker rm -f cocli-supervisor 2>/dev/null || true"
        subprocess.run(["ssh", f"{user}@{host}", stop_cmd], capture_output=True)

        # We map .cocli to both /root/ and the host user's home path
        # This ensures that 'credential_process' paths in ~/.aws/config (which use host absolute paths)
        # work correctly inside the container.
        run_cmd = f"""docker run -d --restart always --name cocli-supervisor \
            --network host \
            --shm-size=2gb \
            -e TZ=America/Los_Angeles \
            -e CAMPAIGN_NAME='{self.campaign_name}' \
            -e COCLI_HOSTNAME={short_name} \
            -e COCLI_QUEUE_TYPE=filesystem \
            -v ~/repos/data:/app/data \
            -v ~/.aws:/root/.aws:ro \
            -v ~/.cocli:/root/.cocli:ro \
            -v ~/.cocli:/home/{user}/.cocli:ro \
            {image_name} \
            cocli-worker worker orchestrate --campaign {self.campaign_name}"""

        subprocess.run(["ssh", f"{user}@{host}", run_cmd], check=True)
        logger.info(f"  Node {host} restarted with orchestrated workers.")

        # Both Pis already carry a pre-existing, undocumented hourly
        # `docker restart cocli-supervisor` cron job (predates this
        # codebase - discovered while verifying ticket
        # investigate-orphaned-playwright-future-targetclosederror-from-idle-timeout-cancellation).
        # It already bounds the leaked-Playwright-callback-Future
        # accumulation described there tighter than any interval we'd add
        # here, so deploy-hotfix intentionally does not install a second,
        # redundant cron job on top of it.

    async def sync_and_audit(self, user: str = "mstouffer") -> None:
        """
        Pulls data from all cluster nodes and runs a quality audit.
        Surgically targets queues/ and raw/ witness data for speed.
        """
        project_root = Path(__file__).parent.parent.parent.resolve()
        local_campaign_dir = project_root / "data" / "campaigns" / self.campaign_name

        console.print(
            f"[bold cyan]Surgical Pull: cluster results for {self.campaign_name}...[/bold cyan]"
        )



        for node in self.get_nodes():
            host = node.hostname
            logger.info(f"  Pulling from {host}...")
            # We only pull the dynamic worker output: queues and raw witness captures
            remote_base = f"~/repos/data/campaigns/{self.campaign_name}/"

            for folder in ["queues", "raw"]:
                remote_path = f"{remote_base}{folder}/"
                local_path = local_campaign_dir / folder
                local_path.mkdir(parents=True, exist_ok=True)

                # Use -rtWz for fastest SD card performance
                rsync_cmd = [
                    "rsync",
                    "-rtWz",
                    "-e",
                    "ssh -o ConnectTimeout=5 -o BatchMode=yes",
                    f"{user}@{host}:{remote_path}",
                    str(local_path) + "/",
                ]


                try:
                    subprocess.run(
                        rsync_cmd, capture_output=True, text=True, timeout=120
                    )
                except subprocess.TimeoutExpired:
                    logger.warning(f"  Pull from {host}:{folder} timed out.")
                except Exception as e:
                    logger.warning(f"  Could not pull from {host}:{folder}: {e}")

        # Now run the auditor logic via dynamic import to avoid mypy package collisions
        import importlib.util
        import sys

        script_path = project_root / "scripts" / "audit_prospect_quality.py"
        spec = importlib.util.spec_from_file_location(
            "audit_prospect_quality", str(script_path)
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            sys.modules["audit_prospect_quality"] = module
            spec.loader.exec_module(module)
            module.audit_quality(self.campaign_name)

    async def push_data(self, user: str = "mstouffer", delete: bool = False) -> None:
        """
        Propagates local campaign data to all cluster nodes.
        Surgically targets discovery-gen/completed, pending/batches, and config.toml
        to ensure fast and reliable task activation, monitoring, and hot-reloading.
        """
        from ..core.paths import paths

        campaign_dir = paths.campaign(self.campaign_name).path
        dg_queue = paths.campaign(self.campaign_name).queue("discovery-gen")

        # 1. Discovery Gen Completed (The Active Task Pool)
        local_dg_completed = dg_queue.completed

        # 2. Pending Batches (Required for monitor-batch)
        local_dg_batches = dg_queue.pending / "batches"

        # 3. Campaign Config (Required for hot-reloading scaling)
        local_config = campaign_dir / "config.toml"

        console.print(
            f"[bold cyan]Surgical Push: discovery-gen tasks, batches and config for {self.campaign_name}...[/bold cyan]"
        )



        for node in self.get_nodes():
            host = node.hostname
            logger.info(f"  Pushing to {host}...")

            remote_campaign_root = f"~/repos/data/campaigns/{self.campaign_name}/"
            remote_dg_completed = (
                f"{remote_campaign_root}queues/discovery-gen/completed/"
            )
            remote_dg_batches = (
                f"{remote_campaign_root}queues/discovery-gen/pending/batches/"
            )
            remote_config = f"{remote_campaign_root}config.toml"

            try:
                # Sync Active Queues (discovery-gen, enrichment, gm-details)
                local_enrichment_pending = campaign_dir / "queues" / "enrichment" / "pending"
                local_gmdetails_pending = campaign_dir / "queues" / "gm-details" / "pending"
                remote_enrichment_pending = f"{remote_campaign_root}queues/enrichment/pending/"
                remote_gmdetails_pending = f"{remote_campaign_root}queues/gm-details/pending/"

                remote_dirs: list[str] = []
                if local_enrichment_pending.exists():
                    remote_dirs.append(remote_enrichment_pending)
                if local_gmdetails_pending.exists():
                    remote_dirs.append(remote_gmdetails_pending)

                if remote_dirs:
                    subprocess.run(
                        [
                            "ssh",
                            f"{user}@{host}",
                            f"mkdir -p {' '.join(remote_dirs)}",
                        ],
                        check=True,
                        capture_output=True,
                        timeout=15,
                    )

                # Sync Active Task Pool
                if local_dg_completed.exists():
                    rsync_cmd_tasks = ["rsync", "-rtWz"]
                    if delete:
                        rsync_cmd_tasks.append("--delete")
                    rsync_cmd_tasks.extend(
                        [
                            str(local_dg_completed) + "/",
                            f"{user}@{host}:{remote_dg_completed}",
                        ]
                    )
                    subprocess.run(
                        rsync_cmd_tasks,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                # Sync Pending Enrichment tasks to spoke nodes
                if local_enrichment_pending.exists():
                    subprocess.run(
                        ["rsync", "-rtWz", str(local_enrichment_pending) + "/", f"{user}@{host}:{remote_enrichment_pending}"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                # Sync Pending GM-Details tasks to spoke nodes
                if local_gmdetails_pending.exists():
                    subprocess.run(
                        ["rsync", "-rtWz", str(local_gmdetails_pending) + "/", f"{user}@{host}:{remote_gmdetails_pending}"],
                        check=False,
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                # Sync Batches (Always sync, small files)
                if local_dg_batches.exists():
                    rsync_cmd_batches = [
                        "rsync",
                        "-rtWz",
                        str(local_dg_batches) + "/",
                        f"{user}@{host}:{remote_dg_batches}",
                    ]
                    subprocess.run(
                        rsync_cmd_batches,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                # Sync Config (Crucial for hot-reloading)
                if local_config.exists():
                    rsync_cmd_config = [
                        "rsync",
                        "-rtWz",
                        str(local_config),
                        f"{user}@{host}:{remote_config}",
                    ]
                    subprocess.run(
                        rsync_cmd_config,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    subprocess.run(
                        rsync_cmd_config,
                        check=True,
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

            except subprocess.TimeoutExpired:
                logger.warning(f"Push to {host} timed out.")
            except Exception as e:
                logger.warning(f"Could not push to {host}: {e}")

    async def pull_scraped_tiles(self, user: str = "mstouffer") -> None:
        """
        Directly pulls high-speed witness files from cluster nodes.
        Bypasses S3 for rapid local diagnostic updates.
        """
        from ..core.paths import paths

        local_tiles_dir = paths.indexes / "scraped-tiles"
        local_tiles_dir.mkdir(parents=True, exist_ok=True)

        console.print(
            "[bold cyan]Direct Pull: high-speed witness data from cluster...[/bold cyan]"
        )



        for node in self.get_nodes():
            host = node.hostname
            logger.info(f"  Pulling tiles from {host}...")
            # Witness files are stored in global indexes/scraped-tiles on the host
            remote_path = "~/repos/data/indexes/scraped-tiles/"

            # Use -rtWz for fastest performance
            rsync_cmd = [
                "rsync",
                "-rtWz",
                "-e",
                "ssh -o ConnectTimeout=5 -o BatchMode=yes",
                f"{user}@{host}:{remote_path}",
                str(local_tiles_dir) + "/",
            ]


            try:
                subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                logger.warning(f"  Pull from {host} timed out.")
            except Exception as e:
                logger.warning(f"  Could not pull from {host}: {e}")

    async def run_remote_command(
        self, node: PiNodeConfig, command: str, user: str = "mstouffer"
    ) -> str:
        # asyncio subprocess, not subprocess.run - callers gather() multiple
        # nodes concurrently, and a blocking subprocess.run inside an async
        # def would stall the whole event loop for each SSH round-trip in
        # turn, silently serializing what looked like concurrent calls.
        proc = await asyncio.create_subprocess_exec(
            "ssh", f"{user}@{node.hostname}", command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode()
        return stderr.decode()

    async def get_top_stats(self) -> list[dict[str, Any]]:
        """Collects load, temp, mem, and pids of all nodes."""
        results = []
        for node in self.get_nodes():
            cmd = "uptime && vcgencmd measure_temp && docker stats cocli-supervisor --no-stream --format '{{.MemUsage}} | {{.PIDs}}'"
            res = await self.run_remote_command(node, cmd)
            lines = res.strip().split("\n")
            if len(lines) >= 3:
                load = lines[0].split("average:")[1].strip() if "average:" in lines[0] else "N/A"
                temp = lines[1].replace("temp=", "")
                mem_pids = lines[2].split("|")
                mem = mem_pids[0].strip() if len(mem_pids) > 0 else "N/A"
                pids = mem_pids[1].strip() if len(mem_pids) > 1 else "N/A"
                results.append({
                    "node": node.hostname,
                    "load": load,
                    "temp": temp,
                    "mem": mem,
                    "pids": pids,
                    "status": "OK"
                })
            else:
                results.append({
                    "node": node.hostname,
                    "status": "OFFLINE"
                })
        return results

    async def sync_clocks(
        self,
        authoritative_node: str,
        auth_time: str,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        """Syncs node clocks with the authoritative node's time."""
        for node in self.get_nodes():
            if node.hostname == authoritative_node:
                continue
            if log_callback:
                log_callback(f"Syncing {node.hostname}...")
            cmd = f"sudo date -s '{auth_time}'"
            await self.run_remote_command(node, cmd)


    async def stop_workers(
        self, log_callback: Optional[Callable[[str], None]] = None
    ) -> None:
        """Stops and removes cocli worker containers on all nodes."""
        for node in self.get_nodes():
            if log_callback:
                log_callback(f"Stopping workers on {node.hostname}...")
            cmd = "docker stop $(docker ps -q --filter name=cocli-) 2>/dev/null || true"
            await self.run_remote_command(node, cmd)
            cmd_rm = "docker rm $(docker ps -a -q --filter name=cocli-) 2>/dev/null || true"
            await self.run_remote_command(node, cmd_rm)

    async def get_nodes_status(self) -> list[dict[str, Any]]:
        """Uptime/status checks on all cluster nodes.

        Also reports the CAMPAIGN_NAME actually baked into each node's
        running cocli-supervisor container - the ground truth of which
        campaign it's serving right now, independent of which campaign's
        config.toml lists it under (that only reflects the last deploy's
        intent, not live reality - see reference_cluster_config_propagation
        memory for a confirmed drift incident). Empty/"none" means no
        cocli-supervisor container is running on that node at all.
        """
        results = []
        campaign_marker = "---CAMPAIGN---"
        for node in self.get_nodes():
            cmd = (
                "uptime; "
                f"echo '{campaign_marker}'; "
                "docker inspect cocli-supervisor "
                "--format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null "
                "| grep '^CAMPAIGN_NAME=' | cut -d= -f2"
            )
            res = await self.run_remote_command(node, cmd)
            parts = res.split(campaign_marker, 1)
            uptime_part = parts[0]
            live_campaign = parts[1].strip() if len(parts) > 1 else ""
            if "load average" in uptime_part:
                uptime_str = uptime_part.split("up")[1].split(",")[0].strip()
                results.append({
                    "node": node.hostname,
                    "online": True,
                    "uptime": uptime_str,
                    "campaign": live_campaign or "none running",
                    "details": "Ready"
                })
            else:
                results.append({
                    "node": node.hostname,
                    "online": False,
                    "uptime": "N/A",
                    "campaign": "-",
                    "details": uptime_part.strip()[:30]
                })
        return results

    async def prune_nodes(
        self,
        validated_nodes: list[PiNodeConfig],
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> list[dict[str, Any]]:
        """Prunes docker objects on nodes and returns space reclaimed."""
        results = []
        for node in validated_nodes:
            if log_callback:
                log_callback(f"Pruning {node.hostname}...")
            cmd = "docker system prune -af"
            res = await self.run_remote_command(node, cmd)
            reclaimed_str = "0 B"
            if "Total reclaimed space:" in res:
                line = [row for row in res.split("\n") if "Total reclaimed space:" in row]
                if line:
                    reclaimed_str = line[0].replace("Total reclaimed space:", "").strip()
            success = "Total reclaimed space:" in res
            results.append({
                "node": node.hostname,
                "success": success,
                "reclaimed": reclaimed_str
            })
        return results
