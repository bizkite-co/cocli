
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
        
    csv_files = list(prospects_dir.glob("*.csv"))
    if not csv_files:
        print("No CSV files found to deduplicate.")
        raise typer.Exit(code=1)
        
    df_list = []
    for file in csv_files:
        if file.name != "index.csv":
            df_list.append(pd.read_csv(file))
            
    if not df_list:
        print("No data found in CSV files.")
        raise typer.Exit(code=1)
        
    combined_df = pd.concat(df_list, ignore_index=True)
    deduplicated_df = combined_df.drop_duplicates(subset=["Place_ID"])
    
    index_file = prospects_dir / "index.csv"
    deduplicated_df.to_csv(index_file, index=False)
    
    print(f"Deduplicated {len(combined_df)} records into {len(deduplicated_df)} records.")
    print(f"Index file created at: {index_file}")
