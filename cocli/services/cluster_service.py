# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
import subprocess
from pathlib import Path
from typing import List, Dict
from rich.console import Console

from ..core.config import load_campaign_config
from ..models.campaigns.worker_config import CampaignClusterConfig, PiNodeConfig, WorkerDefinition

logger = logging.getLogger(__name__)
console = Console()

BUILD_DIR = "~/repos/cocli_build"

class ClusterService:
    """
    Central service for managing the Raspberry Pi cluster.
    Implements the 'Safe Hotfix' (Registry-Propagation) deployment strategy.
    """
    
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        self.config = load_campaign_config(campaign_name)
        
        # 1. Load Global Config (The Authority for Node List)
        from ..core.config import load_global_config
        global_config = load_global_config()
        cluster_data = global_config.get("cluster", {})
        self.cluster_config = CampaignClusterConfig(**cluster_data)
        
        # 2. Resolve Registry Host and IP
        self.registry_host = cluster_data.get("registry_host", "cocli5x1.pi")
        
        # Use IP for registry URL to avoid DNS issues on spokes
        registry_node = next((n for n in self.cluster_config.nodes if n.hostname == self.registry_host), None)
        self.registry_ip = registry_node.ip_address if registry_node else self.registry_host
        self.registry_url = f"{self.registry_ip}:5000"
        
        # 3. Fallback to prospecting.scaling ONLY if global node list is empty
        if not self.cluster_config.nodes:
            logger.info("Global node list empty, falling back to campaign scaling config.")
            scaling = self.config.get("prospecting", {}).get("scaling", {})
            for host_key, workers_data in scaling.items():
                if host_key == "fargate":
                    continue
                host = host_key if "." in host_key else f"{host_key}.pi"
                
                # Create WorkerDefinitions from scaling data
                node_workers = []
                for content_type, count in workers_data.items():
                    if count > 0:
                        node_workers.append(WorkerDefinition(
                            name=f"{host_key}-{content_type}",
                            role="full",
                            content_type=content_type,
                            workers=count,
                            iot_profile=None
                        ))
                
                if node_workers:
                    self.cluster_config.nodes.append(PiNodeConfig(host=host, ip=None, workers=node_workers))

    def get_nodes(self) -> List[PiNodeConfig]:
        return self.cluster_config.nodes

    def _verify_local_build(self) -> bool:
        """Verifies that the local context is complete for a Docker build."""
        project_root = Path(__file__).parent.parent.parent.resolve()
        docker_file = project_root / "docker" / "rpi-worker" / "Dockerfile"
        if not docker_file.exists():
            logger.error(f"Missing Dockerfile at {docker_file}")
            return False
        return True

    async def deploy_hotfix_safe(self, user: str = "mstouffer") -> Dict[str, bool]:
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

        results = {}
        image_name = "cocli-worker-rpi:latest"
        registry_image = f"{self.registry_url}/{image_name}"

        # 1. Prepare Registry Host (The Hub)
        logger.info(f"--- Preparing Registry Hub: {self.registry_host} ---")
        if not await self._sync_and_build(self.registry_host, image_name, registry_image, user):
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
            for i, node in enumerate([n for n in self.get_nodes() if n.hostname != self.registry_host]):
                results[node.hostname] = spoke_results[i]

        return results

    async def _sync_and_build(self, host: str, image_name: str, registry_image: str, user: str) -> bool:
        # Ensure we sync from the absolute project root
        project_root = Path(__file__).parent.parent.parent.resolve()
        
        try:
            # Sync
            subprocess.run(["ssh", f"{user}@{host}", f"mkdir -p {BUILD_DIR}"], check=True)
            rsync_cmd = [
                "rsync", "-az", "--delete",
                "--exclude", ".venv", "--exclude", ".git", "--exclude", "data", "--exclude", ".logs",
                str(project_root) + "/", f"{user}@{host}:{BUILD_DIR}/"
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

    async def _deploy_to_spoke(self, node: PiNodeConfig, image_name: str, registry_image: str, user: str) -> bool:
        host = node.hostname
        logger.info(f"Deploying to Spoke: {host}...")
        try:
            # Pull
            pull_cmd = f"docker pull {registry_image} && docker tag {registry_image} {image_name}"
            subprocess.run(["ssh", f"{user}@{host}", pull_cmd], check=True)
            
            # Restart
            await self._restart_node(host, image_name, user)
            return True
        except Exception as e:
            logger.info(f"Pull failed on {host}, falling back to local build: {e}")
            return False

    async def _restart_node(self, host: str, image_name: str, user: str) -> None:
        """Restarts the node using the new ORCHESTRATED worker mode."""
        short_name = host.split(".")[0]
        # Standardize on 'cocli-supervisor' as the container name for now
        stop_cmd = "docker stop cocli-supervisor && docker rm cocli-supervisor"
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
            cocli worker orchestrate --campaign {self.campaign_name}"""
        
        subprocess.run(["ssh", f"{user}@{host}", run_cmd], check=True)
        logger.info(f"  Node {host} restarted with orchestrated workers.")

    async def sync_and_audit(self, user: str = "mstouffer") -> None:
        """
        Pulls data from all cluster nodes and runs a quality audit.
        Surgically targets queues/ and raw/ witness data for speed.
        """
        project_root = Path(__file__).parent.parent.parent.resolve()
        local_campaign_dir = project_root / "data" / "campaigns" / self.campaign_name

        logger.info(f"[bold cyan]Surgical Pull: cluster results for {self.campaign_name}...[/bold cyan]")

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
                    "rsync", "-rtWz",
                    f"{user}@{host}:{remote_path}", str(local_path) + "/"
                ]

                try:
                    subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=120)
                except subprocess.TimeoutExpired:
                    logger.warning(f"  Pull from {host}:{folder} timed out.")
                except Exception as e:
                    logger.warning(f"  Could not pull from {host}:{folder}: {e}")

        # Now run the auditor logic via dynamic import to avoid mypy package collisions
        import importlib.util
        import sys
        
        script_path = project_root / "scripts" / "audit_prospect_quality.py"
        spec = importlib.util.spec_from_file_location("audit_prospect_quality", str(script_path))
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
        
        logger.info(f"[bold cyan]Surgical Push: discovery-gen tasks, batches and config for {self.campaign_name}...[/bold cyan]")
        
        for node in self.get_nodes():
            host = node.hostname
            logger.info(f"  Pushing to {host}...")
            
            remote_campaign_root = f"~/repos/data/campaigns/{self.campaign_name}/"
            remote_dg_completed = f"{remote_campaign_root}queues/discovery-gen/completed/"
            remote_dg_batches = f"{remote_campaign_root}queues/discovery-gen/pending/batches/"
            remote_config = f"{remote_campaign_root}config.toml"
            
            try:
                # Ensure remote directories exist
                subprocess.run(["ssh", f"{user}@{host}", f"mkdir -p {remote_dg_completed} {remote_dg_batches}"], check=True, capture_output=True, timeout=15)
                
                # Sync Active Task Pool
                rsync_cmd_tasks = ["rsync", "-rtWz"]
                if delete:
                    rsync_cmd_tasks.append("--delete")
                rsync_cmd_tasks.extend([str(local_dg_completed) + "/", f"{user}@{host}:{remote_dg_completed}"])
                subprocess.run(rsync_cmd_tasks, check=True, capture_output=True, text=True, timeout=120)

                # Sync Batches (Always sync, small files)
                rsync_cmd_batches = ["rsync", "-rtWz", str(local_dg_batches) + "/", f"{user}@{host}:{remote_dg_batches}"]
                subprocess.run(rsync_cmd_batches, check=True, capture_output=True, text=True, timeout=60)

                # Sync Config (Crucial for hot-reloading)
                if local_config.exists():
                    rsync_cmd_config = ["rsync", "-rtWz", str(local_config), f"{user}@{host}:{remote_config}"]
                    subprocess.run(rsync_cmd_config, check=True, capture_output=True, text=True, timeout=30)
                
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

        logger.info(f"[bold cyan]Direct Pull: high-speed witness data from cluster...[/bold cyan]")

        for node in self.get_nodes():
            host = node.hostname
            logger.info(f"  Pulling tiles from {host}...")
            # Witness files are stored in global indexes/scraped-tiles on the host
            remote_path = "~/repos/data/indexes/scraped-tiles/"

            # Use -rtWz for fastest performance
            rsync_cmd = [
                "rsync", "-rtWz",
                f"{user}@{host}:{remote_path}", str(local_tiles_dir) + "/"
            ]

            try:
                subprocess.run(rsync_cmd, capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired:
                logger.warning(f"  Pull from {host} timed out.")
            except Exception as e:
                logger.warning(f"  Could not pull from {host}: {e}")

    async def run_remote_command(self, node: PiNodeConfig, command: str, user: str = "mstouffer") -> str:
        res = subprocess.run(["ssh", f"{user}@{node.hostname}", command], capture_output=True, text=True)
        return res.stdout if res.returncode == 0 else res.stderr
