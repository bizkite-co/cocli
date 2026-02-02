from pathlib import Path
from cocli.utils.usv_utils import USVDictReader

def audit_sample(sample_dir: Path):
    print(f"Auditing metadata for {sample_dir}")
    stats = {
        "total": 0,
        "missing_name": 0,
        "missing_city": 0,
        "missing_zip": 0,
        "missing_address": 0,
        "legacy_headers": 0,
        "snake_headers": 0
    }

    for usv_file in sample_dir.glob("*.usv"):
        stats["total"] += 1
        with open(usv_file, "r") as f:
            # Note: We use USVDictReader which handles \x1f and \x1e/\n
            reader = USVDictReader(f)
            try:
                records = list(reader)
                if not records:
                    continue
                
                row = records[0]
                # Detect header style
                if "Name" in row or "Full_Address" in row:
                    stats["legacy_headers"] += 1
                elif "name" in row or "full_address" in row:
                    stats["snake_headers"] += 1

                # Check for metadata
                name = row.get("name") or row.get("Name")
                city = row.get("city") or row.get("City")
                zip_code = row.get("zip") or row.get("Zip")
                address = row.get("full_address") or row.get("Full_Address")

                if not name or name.strip() == "":
                    stats["missing_name"] += 1
                
                # Heuristic: If city/zip are missing, check if they are in the address
                if (not city or city.strip() == "") and address:
                    # Very simple heuristic for "City, ST ZIP"
                    if "," in address:
                        parts = address.split(",")
                        if len(parts) > 1:
                            last_part = parts[-1].strip()
                            if len(last_part.split()) >= 2: # "CO 80501"
                                stats["missing_city"] += 0 # Potentially recoverable
                            else:
                                stats["missing_city"] += 1
                        else:
                            stats["missing_city"] += 1
                    else:
                        stats["missing_city"] += 1
                elif not city or city.strip() == "":
                    stats["missing_city"] += 1

                if not zip_code or zip_code.strip() == "":
                    stats["missing_zip"] += 1
                if not address or address.strip() == "":
                    stats["missing_address"] += 1

            except Exception as e:
                print(f"Error parsing {usv_file}: {e}")

    print("\n--- Sample Audit Report ---")
    for key, value in stats.items():
        print(f"{key.replace('_', ' ').title()}: {value}")

if __name__ == "__main__":
    audit_sample(Path("/tmp/roadmap_audit"))
