# POLICY: frictionless-data-policy-enforcement
import logging
import sys
from cocli.core.paths import paths
from cocli.utils.usv_utils import USVDictReader, USVWriter
from cocli.models.campaigns.indexes.google_maps_raw import GoogleMapsRawResult
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.core.prospects_csv_manager import ProspectsIndexManager

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("rescue_op")

def rescue_and_audit(campaign_name: str) -> None:
    logger.info(f"--- Rescuing and Auditing Raw Inbox Data for: {campaign_name} ---")
    
    source_dir = paths.root / "campaigns" / campaign_name / "recovery" / "raw_inbox"
    recovery_dir = paths.root / "campaigns" / campaign_name / "recovery"
    quarantine_path = recovery_dir / "quarantined_raw.usv"
    
    if not source_dir.exists():
        logger.error(f"Source directory not found: {source_dir}")
        return

    manager = ProspectsIndexManager(campaign_name)
    success_count = 0
    quarantine_count = 0
    total_files = 0

    files = list(source_dir.glob("*.usv"))
    logger.info(f"Found {len(files)} files to process.")

    with open(quarantine_path, "w", encoding="utf-8") as qf:
        q_writer = USVWriter(qf)
        # Header for the quarantine file
        q_writer.writerow(["source_file", "error_type", "error_message", "raw_data_summary"])

        for file_path in files:
            total_files += 1
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = USVDictReader(f)
                    for row in reader:
                        # 1. Raw Model Validation
                        try:
                            raw_item = GoogleMapsRawResult.model_validate(row)
                        except Exception as ve:
                            quarantine_count += 1
                            q_writer.writerow([file_path.name, "RAW_SCHEMA_ERROR", str(ve), str(row)[:200]])
                            continue
                        
                        # 2. Strict Identity Check (discard name-less items)
                        if not raw_item.Name or not str(raw_item.Name).strip():
                            quarantine_count += 1
                            q_writer.writerow([file_path.name, "MISSING_NAME", "Business name is null or empty", f"PID: {raw_item.Place_ID}"])
                            continue

                        # 3. Gold Model Transformation
                        try:
                            prospect = GoogleMapsProspect.from_raw(raw_item)
                            # 4. Save to WAL
                            if manager.append_prospect(prospect):
                                success_count += 1
                            else:
                                quarantine_count += 1
                                q_writer.writerow([file_path.name, "SAVE_ERROR", "Failed to append to WAL", f"PID: {raw_item.Place_ID}"])
                        except Exception as pe:
                            quarantine_count += 1
                            q_writer.writerow([file_path.name, "GOLD_PROSPECT_ERROR", str(pe), f"PID: {raw_item.Place_ID}"])
                            
            except Exception as e:
                logger.error(f"Critical error in {file_path.name}: {e}")
                quarantine_count += 1
                q_writer.writerow([file_path.name, "CRITICAL_SYSTEM_ERROR", str(e), ""])

    logger.info("\n--- Operation Complete ---")
    logger.info(f"Successfully Migrated to WAL: {success_count}")
    logger.info(f"Quarantined for Audit: {quarantine_count}")
    logger.info(f"Audit list saved to: {quarantine_path.relative_to(paths.root)}")

if __name__ == "__main__":
    campaign = sys.argv[1] if len(sys.argv) > 1 else "roadmap"
    rescue_and_audit(campaign)
