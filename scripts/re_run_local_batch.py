# POLICY: frictionless-data-policy-enforcement
import asyncio
import logging
import os
import sys
from pathlib import Path
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from cocli.application.worker_service import WorkerService
from cocli.core.paths import paths

# 1. Setup Logging to File
LOG_FILE = Path(".logs/recovery_batch.log")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler(LOG_FILE, mode='a')]
)
logger = logging.getLogger("local_batch")

def get_pending_count(pending_dir: Path) -> int:
    """Counts task.json files in sharded pending directory."""
    if not pending_dir.exists():
        return 0
    count = 0
    for root, dirs, files in os.walk(pending_dir):
        for f in files:
            if f == "task.json":
                count += 1
    return count

async def run_local_batch():
    campaign = "roadmap"
    
    # 2. Determine initial state
    queue_base = paths.queue(campaign, "gm-details")
    pending_dir = queue_base / "pending"
    initial_pending = get_pending_count(pending_dir)
    total_batch = 200 # Our target size
    
    print(f"--- RECOVERY BATCH START ---")
    print(f"Log: {LOG_FILE}")
    print(f"Pending tasks found: {initial_pending}")

    if initial_pending == 0:
        print("No tasks found in queue. Did you run re_enqueue_batch.py?")
        return

    service = WorkerService(campaign, role="full")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("({task.completed}/{task.total})"),
        refresh_per_second=1
    ) as progress:
        
        batch_task = progress.add_task("[cyan]Recovering Ratings...", total=total_batch)
        
        # Start Worker in background
        # We use once=False so it keeps the browser open across tasks
        worker_coro = service.run_details_worker(headless=True, debug=True, once=False, workers=1, role="full")
        worker_task = asyncio.create_task(worker_coro)
        
        # Update current progress based on what's already done
        progress.update(batch_task, completed=total_batch - initial_pending)
        
        # Monitor Loop
        try:
            while True:
                pending = get_pending_count(pending_dir)
                completed = total_batch - pending
                progress.update(batch_task, completed=completed)
                
                if pending == 0:
                    logger.info("Queue empty. Batch complete.")
                    break
                
                if worker_task.done():
                    # If worker crashed or exited early
                    exc = worker_task.exception()
                    if exc:
                        logger.error(f"Worker crashed: {exc}")
                    break
                    
                await asyncio.sleep(5)
        finally:
            # Stop the worker
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

    print("\n--- BATCH COMPLETE ---")
    print(f"Processed results are in the WAL.")
    print("Next: Run 'python3 scripts/compact_shards.py roadmap' to finalize.")

if __name__ == "__main__":
    try:
        asyncio.run(run_local_batch())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
