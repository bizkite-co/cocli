from pathlib import Path
from cocli.utils.usv_utils import USVReader, USVWriter

results_dir = Path(
    "/home/mstouffer/.local/share/cocli_data_dev/campaigns/roadmap/queues/gm-list/completed/results"
)
output_path = results_dir.parent / "results.usv"

count = 0
print(f"Compacting {results_dir} to {output_path}...")
with open(output_path, "w", encoding="utf-8") as f_out:
    writer = USVWriter(f_out)
    for usv_file in results_dir.rglob("*.usv"):
        if usv_file.name == "corrupted-records.usv" or usv_file.name == "results.usv":
            continue

        with open(usv_file, "rb") as f_in:
            reader = USVReader(f_in)
            for row in reader:
                writer.writerow(row)
                count += 1
print(f"Compacted {count} records to {output_path}")
