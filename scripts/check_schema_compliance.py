# POLICY: frictionless-data-policy-enforcement
import json
import logging
from cocli.core.paths import paths
from cocli.core.constants import UNIT_SEP

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("check_compliance")

def check_schema_compliance(campaign_name: str) -> None:
    logger.info(f"--- Checking Schema Compliance for campaign: {campaign_name} ---")
    
    # 1. Target Index and Datapackage
    prospect_idx = paths.campaign(campaign_name).index("google_maps_prospects")
    checkpoint_path = prospect_idx.checkpoint
    prospect_dp = prospect_idx.path / "datapackage.json"

    if not prospect_dp.exists():
        logger.error(f"Datapackage not found: {prospect_dp}")
        return

    with open(prospect_dp, "r") as f:
        dp_data = json.load(f)
        expected_cols = len(dp_data["resources"][0]["schema"]["fields"])
        logger.info(f"Expected Columns: {expected_cols}")

    if not checkpoint_path.exists():
        logger.error(f"Checkpoint not found: {checkpoint_path}")
        return

    total_rows = 0
    non_conforming = 0
    
    # Check Checkpoint
    logger.info(f"Scanning {checkpoint_path.name}...")
    with open(checkpoint_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            total_rows += 1
            # Strip record separator and newline
            clean_line = line.strip("\x1e\n")
            if not clean_line:
                continue
                
            parts = clean_line.split(UNIT_SEP)
            if len(parts) != expected_cols:
                non_conforming += 1
                if non_conforming <= 10:
                    logger.warning(f"Row {i}: Found {len(parts)} columns (Expected {expected_cols}) | PID: {parts[0] if parts else 'N/A'}")
                elif non_conforming == 11:
                    logger.warning("... more non-conforming rows found ...")

    # Check WAL
    wal_dir = prospect_idx.wal
    if wal_dir.exists():
        logger.info(f"Scanning WAL shards in {wal_dir}...")
        for file_path in wal_dir.rglob("*.usv"):
            with open(file_path, "r", encoding="utf-8") as f:
                for line_num, line in enumerate(f, 1):
                    clean_line = line.strip("\x1e\n")
                    if not clean_line:
                        continue
                    parts = clean_line.split(UNIT_SEP)
                    if len(parts) != expected_cols:
                        non_conforming += 1
                        logger.warning(f"File {file_path.name}, Line {line_num}: Found {len(parts)} columns (Expected {expected_cols})")

    logger.info("\n--- Compliance Report ---")
    logger.info(f"Total Rows Scanned: {total_rows}")
    logger.info(f"Non-Conforming Rows: {non_conforming}")
    
    if total_rows > 0:
        compliance_pct = ((total_rows - non_conforming) / total_rows) * 100
        logger.info(f"Compliance Rating: {compliance_pct:.2f}%")

if __name__ == "__main__":
    import sys
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    check_schema_compliance(campaign)
