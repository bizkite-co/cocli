
import typer
import pandas as pd
from pathlib import Path

app = typer.Typer()

@app.command()
def prospects(
    campaign_name: str = typer.Argument(..., help="Name of the campaign to deduplicate prospects for.")
):
    """
    Deduplicate scraped prospects for a campaign.
    """
    
    prospects_dir = Path(f"cocli_data/scraped_data/{campaign_name}/prospects")
    if not prospects_dir.exists():
        print(f"Prospects directory not found for campaign '{campaign_name}'.")
        raise typer.Exit(code=1)
        
    prospects_file = prospects_dir / "prospects.csv"
    if not prospects_file.exists():
        print(f"Prospects file not found for campaign '{campaign_name}'.")
        raise typer.Exit(code=1)
        
    df = pd.read_csv(prospects_file)
    deduplicated_df = df.drop_duplicates(subset=["Place_ID"])
    
    deduplicated_df.to_csv(prospects_file, index=False)
    
    print(f"Deduplicated {len(df)} records into {len(deduplicated_df)} records.")
    print(f"Prospects file updated at: {prospects_file}")
