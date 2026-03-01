# POLICY: frictionless-data-policy-enforcement
import logging
from cocli.core.paths import paths
from cocli.utils.usv_utils import USVReader

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("recovery_batch_trace")

def create_trace_batch(campaign_name: str, limit: int = 50) -> None:
    results_dir = paths.campaign(campaign_name).path / "queues" / "gm-list" / "completed" / "results"
    output_path = paths.campaign(campaign_name).path / "recovery" / "recovery_batch_50_trace.txt"
    
    targets = []
    seen_pids = set()
    
    logger.info(f"Scanning discovery traces in: {results_dir}")
    
    for usv_file in results_dir.rglob("*.usv"):
        try:
            with open(usv_file, "r", encoding="utf-8") as f:
                reader = USVReader(f)
                for row in reader:
                    if len(row) >= 9:
                        pid = row[0]
                        slug = row[1]
                        name = row[2]
                        url = row[8]
                        
                        if pid not in seen_pids and url and len(url) > 100 and "place_id" not in url:
                            targets.append(f"{pid}|{slug}|{name}|{url}")
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
            
    logger.info(f"Successfully created trace recovery batch: {output_path}")
    logger.info(f"Found {len(targets)} hollow prospects with canonical URLs.")

if __name__ == "__main__":
    create_trace_batch("roadmap")
