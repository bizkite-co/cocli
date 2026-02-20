import typer
from rich.progress import track
from cocli.core.config import get_companies_dir, get_campaigns_dir
from cocli.models.companies.company import Company
from cocli.models.campaigns.indexes.google_maps_prospect import GoogleMapsProspect
from cocli.utils.usv_utils import USVDictReader, USVDictWriter
import io

app = typer.Typer()

@app.command()
def backfill(campaign: str = "turboship") -> None:
    companies_dir = get_companies_dir()
    campaign_dir = get_campaigns_dir() / campaign
    prospects_dir = campaign_dir / "indexes" / "google_maps_prospects"

    print(f"Backfilling company_hash for companies in {companies_dir}...")
    for company_path in track(list(companies_dir.iterdir()), description="Companies"):
        if company_path.is_dir() and (company_path / "_index.md").exists():
            try:
                company = Company.from_directory(company_path)
                # Validation logic in Company model automatically generates hash
                if company:
                    company.save()
            except Exception as e:
                print(f"Error processing company {company_path.name}: {e}")

    if prospects_dir.exists():
        print(f"Backfilling company_hash for prospects in {prospects_dir}...")
        usv_files = list(prospects_dir.glob("*.usv"))
        for usv_path in track(usv_files, description="Prospects"):
            try:
                content = usv_path.read_text()
                f_in = io.StringIO(content)
                reader = USVDictReader(f_in)
                rows = list(reader)
                
                if not rows:
                    continue

                f_out = io.StringIO()
                writer = USVDictWriter(f_out, fieldnames=list(GoogleMapsProspect.model_fields.keys()))
                writer.writeheader()

                updated = False
                for row in rows:
                    # Model validation will populate company_hash and company_slug
                    prospect = GoogleMapsProspect.model_validate(row)
                    writer.writerow(prospect.model_dump(by_alias=False))
                    updated = True

                if updated:
                    usv_path.write_text(f_out.getvalue())
            except Exception as e:
                print(f"Error processing prospect {usv_path.name}: {e}")

    print("Backfill complete.")

if __name__ == "__main__":
    app()
