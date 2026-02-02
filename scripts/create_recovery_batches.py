import csv
import os
import argparse

def create_batches(input_csv: str, output_dir: str, batch_size: int = 20) -> None:
    if not os.path.exists(input_csv):
        print(f"Error: {input_csv} not found.")
        return

    os.makedirs(output_dir, exist_ok=True)
    
    with open(input_csv, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        place_ids = [row["place_id"] for row in reader if row.get("place_id")]

    print(f"Total Place IDs to batch: {len(place_ids)}")
    
    batch_num = 1
    for i in range(0, len(place_ids), batch_size):
        batch = place_ids[i:i + batch_size]
        batch_file = os.path.join(output_dir, f"batch_{batch_num:03d}.csv")
        
        with open(batch_file, "w", encoding="utf-8", newline="") as bf:
            writer = csv.writer(bf)
            writer.writerow(["place_id"])
            for pid in batch:
                writer.writerow([pid])
        
        batch_num += 1
        if batch_num > 100: # Safety cap for now
            print("Reached 100 batches (2000 records). Stopping batch creation for now.")
            break

    print(f"Created {batch_num - 1} batches in {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create recovery batches from hollow Place IDs.")
    parser.add_argument("--input", default="/home/mstouffer/.local/share/cocli_data/campaigns/roadmap/recovery/hollow_place_ids.csv")
    parser.add_argument("--output-dir", default="/home/mstouffer/.local/share/cocli_data/campaigns/roadmap/recovery/batches")
    parser.add_argument("--size", type=int, default=20)
    args = parser.parse_args()

    create_batches(args.input, args.output_dir, args.size)
