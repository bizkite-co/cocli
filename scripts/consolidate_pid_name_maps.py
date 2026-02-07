#!/usr/bin/env python3
import os
import sys
import logging
from typing import Dict

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cocli.core.config import get_campaign, get_campaign_dir

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Unit separator is \x1f
US = "\x1f"

def consolidate(campaign_name: str) -> None:
    campaign_dir = get_campaign_dir(campaign_name)
    if not campaign_dir:
        logger.error(f"Campaign {campaign_name} not found.")
        return

    recovery_dir = campaign_dir / "recovery"
    output_file = recovery_dir / "consolidated_pid_name_map.usv"
    
    pid_name_map: Dict[str, str] = {}
    
    # Files to check specifically for PID/Name mappings
    source_files = list(recovery_dir.glob("pid_name_map_*.usv"))
    logger.info(f"Consolidating {len(source_files)} map files...")

    for f_path in source_files:
        try:
            with open(f_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.strip().split(US)
                    if len(parts) >= 2:
                        pid, name = parts[0], parts[1]
                        if pid.startswith("ChIJ") and len(name) > 2:
                            pid_name_map[pid] = name
        except Exception as e:
            logger.error(f"Error reading {f_path.name}: {e}")

    # Save consolidated map
    recovery_dir.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f_out:
        for pid, name in sorted(pid_name_map.items()):
            f_out.write(f"{pid}{US}{name}\n")

    logger.info(f"Consolidation complete. Total unique mappings: {len(pid_name_map)}")
    logger.info(f"Saved to: {output_file}")

if __name__ == "__main__":
    from cocli.core.config import get_campaign
    consolidate(get_campaign() or "roadmap")
