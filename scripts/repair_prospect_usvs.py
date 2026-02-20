import typer
import io
from rich.progress import track
from cocli.core.config import get_campaigns_dir
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader, USVDictWriter

app = typer.Typer()

@app.command()
def repair(campaign: str = "turboship") -> None:
    campaign_dir = get_campaigns_dir() / campaign
    prospects_dir = campaign_dir / "indexes" / "google_maps_prospects"

    if not prospects_dir.exists():
        print(f"Directory not found: {prospects_dir}")
        return

    usv_files = list(prospects_dir.glob("*.usv"))
    print(f"Repairing {len(usv_files)} USV files in {prospects_dir}...")

    fieldnames = list(GoogleMapsProspect.model_fields.keys())

    for usv_path in track(usv_files, description="Repairing"):
        try:
            content = usv_path.read_text()
            f_in = io.StringIO(content)
            reader = USVDictReader(f_in)
            
            # Use raw rows to avoid early validation errors
            rows = []
            for row in reader:
                # Basic cleanup: ensure numeric fields are at least empty strings not whitespace
                for k, v in row.items():
                    if v is None:
                        row[k] = ""
                    else:
                        row[k] = str(v).strip()
                rows.append(row)

            if not rows:
                continue

            f_out = io.StringIO()
            writer = USVDictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()

            for row in rows:
                try:
                    # Validate and clean via model
                    prospect = GoogleMapsProspect.model_validate(row)
                    writer.writerow(prospect.model_dump(by_alias=False))
                except Exception:
                    # If it still fails, write the original row but ensure it has all fields
                    clean_row = {fn: row.get(fn, "") for fn in fieldnames}
                    writer.writerow(clean_row)

            usv_path.write_text(f_out.getvalue())
        except Exception as e:
            print(f"Failed to repair {usv_path.name}: {e}")

    # Write datapackage.json
    dp_path = prospects_dir / "datapackage.json"
    import json
    dp = {
        "profile": "tabular-data-package",
        "resources": [
            {
                "name": "google_maps_prospects",
                "path": "*.usv",
                "profile": "tabular-data-resource",
                "schema": {
                    "fields": list([
                        {"name": fn, "type": "string"} for fn in fieldnames
                    ])
                },
                "dialect": {
                    "delimiter": "\u001f",
                    "recordDelimiter": "\u001e"
                }
            }
        ]
    }
    # Set correct types for numeric fields in datapackage
    from typing import List, Dict
    fields: List[Dict[str, str]] = dp["resources"][0]["schema"]["fields"] # type: ignore
    for field in fields:
        if field["name"] in ["latitude", "longitude", "average_rating"]:
            field["type"] = "number"
        elif field["name"] in ["reviews_count", "version"]:
            field["type"] = "integer"

    dp_path.write_text(json.dumps(dp, indent=2))
    print(f"Created {dp_path}")

if __name__ == "__main__":
    app()
