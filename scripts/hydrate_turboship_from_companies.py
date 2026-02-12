import yaml
from pathlib import Path
from cocli.core.utils import UNIT_SEP
from cocli.models.google_maps_prospect import GoogleMapsProspect

def hydrate():
    checkpoint_path = Path("data/campaigns/turboship/recovery/indexes/google_maps_prospects/prospects.checkpoint.usv")
    companies_dir = Path("data/companies")
    
    output_lines = []
    hydrated_count = 0
    
    if not checkpoint_path.exists():
        print("Checkpoint not found.")
        return

    with open(checkpoint_path, "r") as f:
        lines = f.readlines()

    for line in lines:
        parts = line.strip("\n").split(UNIT_SEP)
        if len(parts) < 15:
            output_lines.append(line)
            continue
            
        place_id = parts[0]
        slug = parts[1]
        name = parts[2]
        current_hash = parts[8]
        
        # Only attempt hydration if hash or address is missing
        if not current_hash or not parts[11]:
            try:
                company_md = companies_dir / slug / "_index.md"
                if len(str(company_md)) < 4096 and company_md.exists():
                    with open(company_md, "r") as cf:
                        content = cf.read()
                        if "---" in content:
                            sections = content.split("---")
                            if len(sections) >= 2:
                                yaml_text = sections[1]
                                data = yaml.safe_load(yaml_text)
                                
                                new_place_id = data.get("place_id") or place_id
                                full_address = data.get("full_address")
                                
                                if full_address and len(str(full_address)) > 5:
                                    temp_data = {
                                        "place_id": new_place_id,
                                        "company_slug": slug,
                                        "name": name,
                                        "full_address": full_address
                                    }
                                    p = GoogleMapsProspect(**temp_data)
                                    
                                    parts[0] = p.place_id
                                    parts[8] = p.company_hash or ""
                                    parts[10] = p.full_address or ""
                                    parts[11] = p.street_address or ""
                                    parts[12] = p.city or ""
                                    parts[13] = p.zip or ""
                                    
                                    hydrated_count += 1
            except (OSError, Exception):
                pass
        
        output_lines.append(UNIT_SEP.join(parts) + "\n")

    with open(checkpoint_path, "w") as f:
        f.writelines(output_lines)
        
    print(f"Hydration complete. Recovered {hydrated_count} records.")

if __name__ == "__main__":
    hydrate()
