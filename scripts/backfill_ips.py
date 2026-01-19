import logging
import asyncio
import socket
from typing import Optional
from concurrent.futures import ThreadPoolExecutor
from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def resolve_ip(domain: str) -> Optional[str]:
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None

async def backfill_ips() -> None:
    manager = WebsiteDomainCsvManager()
    domains_to_check = [item for item in manager.data.values() if not item.ip_address]
    
    if not domains_to_check:
        logger.info("No domains missing IP addresses.")
        return

    logger.info(f"Backfilling IPs for {len(domains_to_check)} domains...")
    
    max_workers = 20
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        tasks = []
        for item in domains_to_check:
            tasks.append(loop.run_in_executor(executor, resolve_ip, str(item.domain)))
        
        results = await asyncio.gather(*tasks)
        
        updated_count = 0
        for item, ip in zip(domains_to_check, results):
            if ip:
                item.ip_address = ip
                manager.add_or_update(item)
                updated_count += 1
        
        logger.info(f"Updated {updated_count} domains with IP addresses.")

if __name__ == "__main__":
    asyncio.run(backfill_ips())
