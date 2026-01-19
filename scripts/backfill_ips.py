import socket
import asyncio
import logging
from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def resolve_ip(domain):
    try:
        return socket.gethostbyname(domain)
    except Exception:
        return None

async def backfill_ips(max_workers=20):
    manager = WebsiteDomainCsvManager()
    domains_to_check = [item for item in manager.data.values() if not item.ip_address]
    
    print(f"Total domains in index: {len(manager.data)}")
    print(f"Domains needing IP backfill: {len(domains_to_check)}")
    
    if not domains_to_check:
        return

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
                updated_count += 1
        
        print(f"Successfully resolved {updated_count} IPs.")
        manager.save()
        print("Index saved.")

if __name__ == "__main__":
    asyncio.run(backfill_ips())
