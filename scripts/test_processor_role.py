import asyncio
import logging
from cocli.application.worker_service import WorkerService

async def test_processor_role() -> None:
    # Setup logging to console
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    service = WorkerService("roadmap", role="processor")
    print("Starting Processor Role Worker (Once)...")
    # headless=True, debug=True, once=True
    await service.run_details_worker(headless=True, debug=True, once=True, workers=1, role="processor")

if __name__ == "__main__":
    asyncio.run(test_processor_role())
