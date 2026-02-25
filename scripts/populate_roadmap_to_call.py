# POLICY: frictionless-data-policy-enforcement
import asyncio
import logging
import sys
from typing import Any, Dict
from cocli.application.operation_service import OperationService
from cocli.core.config import set_campaign

# Setup basic logging to see the operation progress
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("populate_roadmap_to_call")

async def main() -> None:
    campaign_name = "roadmap"
    print(f"--- Populating To-Call List for Campaign: {campaign_name} ---")
    
    # Ensure global config reflects the target campaign
    set_campaign(campaign_name)
    
    # Initialize the OperationService for the roadmap campaign
    op_service = OperationService(campaign_name=campaign_name)
    
    def log_callback(msg: str) -> None:
        sys.stdout.write(msg)
        sys.stdout.flush()

    def step_callback(step_name: str, status: str) -> None:
        logger.info(f"Step: {step_name} | Status: {status}")

    # Execute the 'op_compile_to_call' operation
    # This operation:
    # 1. Compacts GM results
    # 2. Compacts Email shards
    # 3. Filters via DuckDB for rating >= 4.5, reviews >= 20, HAS email/phone
    # 4. Tags results as 'to-call' and adds to the filesystem queue
    
    print("Starting 'op_compile_to_call' operation...")
    result = await op_service.execute(
        "op_compile_to_call", 
        log_callback=log_callback,
        step_callback=step_callback
    )
    
    if result.get("status") == "success":
        data: Dict[str, Any] = result.get("result", {})
        print("\n--- Operation Successful ---")
        print(f"Top leads found: {data.get('top_leads_found', 0)}")
        print(f"Newly tagged leads: {data.get('newly_tagged', 0)}")
    else:
        print("\n--- Operation Failed ---")
        print(f"Error: {result.get('message')}")

if __name__ == "__main__":
    asyncio.run(main())
