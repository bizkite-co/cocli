from cocli.core.transformers.gm_list_to_checkpoint import compact_gm_list_results
import logging

logging.basicConfig(level=logging.INFO)
print("Starting compaction...")
count = compact_gm_list_results("roadmap")
print(f"Compaction complete. Merged {count} records.")
