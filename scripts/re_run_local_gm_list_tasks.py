# POLICY: frictionless-data-policy-enforcement
import asyncio
import logging
from cocli.application.worker_service import WorkerService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("local_gm_list_runner")

async def run_local_gm_list_batch() -> None:
    campaign = "roadmap"
    print("\n--- STARTING LOCAL GM-LIST BATCH (5 TILES) ---")
    
    # Discovery uses 'full' role to include SidebarScraper
    # We use Workers=1 to avoid race conditions during the test
    service = WorkerService(campaign, role="full")
    
    # GM List tasks are handled by 'run_worker' in the WorkerService
    # once=True will stop when it finds no more tasks in the Mission Index (target-tiles)
    await service.run_worker(headless=False, debug=True, once=True, workers=1, role="full")
    
    print("\n--- GM-LIST BATCH COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(run_local_gm_list_batch())
