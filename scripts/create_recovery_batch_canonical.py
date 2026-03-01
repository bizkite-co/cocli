# POLICY: frictionless-data-policy-enforcement
import logging
from cocli.core.paths import paths
from cocli.utils.usv_utils import USVReader

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("recovery_batch_canonical")

def create_canonical_batch(campaign_name: str, limit: int = 50) -> None:
    results_dir = paths.campaign(campaign_name).path / "queues" / "gm-list" / "completed" / "results"
    output_path = paths.campaign(campaign_name).path / "recovery" / "recovery_batch_50_canonical.txt"
    
    targets = []
    seen_pids = set()
    
    logger.info("Scanning discovery traces for high-fidelity canonical URLs...")
    
    # Discovery Trace Schema:
    # 0: place_id, 1: slug, 2: name, 3: phone, 4: domain, 5: reviews, 6: rating, 7: address, 8: gmb_url
    for usv_file in results_dir.rglob("*.usv"):
        try:
            with open(usv_file, "r", encoding="utf-8") as f:
                reader = USVReader(f)
                for row in reader:
                    if len(row) >= 9:
                        pid = row[0]
                        url = row[8]
                        
                        # We want LONG canonical URLs
                        if pid not in seen_pids and url and len(url) > 100 and "place_id" not in url:
                            targets.append(f"{pid}|{row[1]}|{row[2]}|{url}")
                            seen_pids.add(pid)
                            if len(targets) >= limit:
                                break
        except Exception:
            pass
            
        if len(targets) >= limit:
            break

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for t in targets:
            f.write(f"{t}\n")
            
    logger.info(f"Successfully created canonical recovery batch: {output_path}")
    logger.info(f"Found {len(targets)} targets with canonical URLs.")

if __name__ == "__main__":
    create_canonical_batch("roadmap")
