# POLICY: frictionless-data-policy-enforcement
import logging
import asyncio
import subprocess
from typing import List, Dict
from rich.console import Console

from ..core.config import load_campaign_config
from ..models.campaigns.worker_config import CampaignClusterConfig, PiNodeConfig

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
        
        cluster_data = self.config.get("cluster", {})
        self.cluster_config = CampaignClusterConfig(**cluster_data)
        
        # Resolve Registry Host (Default to cocli5x1.pi)
        self.registry_host = self.config.get("cluster", {}).get("registry_host", "cocli5x1.pi")
        self.registry_url = f"{self.registry_host}:5000"
        
        # Fallback to prospecting.scaling if cluster.nodes is empty
        if not self.cluster_config.nodes:
            scaling = self.config.get("prospecting", {}).get("scaling", {})
            for host_key in scaling.keys():
                if host_key == "fargate":
                    continue
                host = host_key if "." in host_key else f"{host_key}.pi"
                self.cluster_config.nodes.append(PiNodeConfig(hostname=host))

    def get_nodes(self) -> List[PiNodeConfig]:
        return self.cluster_config.nodes

    async def deploy_hotfix_safe(self, user: str = "mstouffer") -> Dict[str, bool]:
        """
        PERFORMS SAFE HOTFIX:
        1. Sync code to Registry Host.
        2. Build image on Registry Host.
        3. Push to local registry.
        4. All nodes pull and restart with 'cocli worker orchestrate'.
        """
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
        try:
            # Sync
            subprocess.run(["ssh", f"{user}@{host}", f"mkdir -p {BUILD_DIR}"], check=True)
            rsync_cmd = [
                "rsync", "-az", "--delete",
                "--exclude", ".venv", "--exclude", ".git", "--exclude", "data", "--exclude", ".logs",
                "./", f"{user}@{host}:{BUILD_DIR}/"
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
            # Optional: Add local build fallback here if desired
            return False

    async def _restart_node(self, host: str, image_name: str, user: str) -> None:
        """Restarts the node using the new ORCHESTRATED worker mode."""
        short_name = host.split(".")[0]
        # Standardize on 'cocli-supervisor' as the container name for now
        stop_cmd = "docker stop cocli-supervisor && docker rm cocli-supervisor"
        subprocess.run(["ssh", f"{user}@{host}", stop_cmd], capture_output=True)
        
        run_cmd = f"""docker run -d --restart always --name cocli-supervisor \
            --shm-size=2gb \
            -e TZ=America/Los_Angeles \
            -e CAMPAIGN_NAME='{self.campaign_name}' \
            -e COCLI_HOSTNAME={short_name} \
            -e COCLI_QUEUE_TYPE=filesystem \
            -v ~/repos/data:/app/data \
            -v ~/.aws:/root/.aws:ro \
            -v ~/.cocli:/root/.cocli:ro \
            {image_name} \
            cocli worker orchestrate --campaign {self.campaign_name}"""
        
        subprocess.run(["ssh", f"{user}@{host}", run_cmd], check=True)
        logger.info(f"  Node {host} restarted with orchestrated workers.")

    async def run_remote_command(self, node: PiNodeConfig, command: str, user: str = "mstouffer") -> str:
        res = subprocess.run(["ssh", f"{user}@{node.hostname}", command], capture_output=True, text=True)
        return res.stdout if res.returncode == 0 else res.stderr
