import asyncio
import logging
from cocli.application.worker_service import WorkerService

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("local_discovery")

async def run_local_discovery() -> None:
    campaign = "roadmap"
    print("--- STARTING LOCAL DISCOVERY BATCH (5 TILES) ---")
    
    service = WorkerService(campaign, role="full")
    
    # Run discovery worker locally. 
    # headless=True for performance, debug=True for visibility
    # once=True to stop after the queue is empty
    await service.run_worker(headless=True, debug=True, once=True, workers=1, role="full")
    
    print("\n--- DISCOVERY BATCH COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(run_local_discovery())
