import typer
from typing_extensions import Annotated
import pandas as pd
from pathlib import Path
import yaml

from cocli.core.utils import generate_company_hash
from cocli.core.config import get_companies_dir

app = typer.Typer()

@app.command()
def deduplicate(
    dry_run: Annotated[bool, typer.Option(help="Print what would be changed without actually changing anything.")] = True,
):
    """
    Deduplicates company data by generating a stable hash for each company and removing duplicates.
    """
    companies_dir = get_companies_dir()
    if not companies_dir.exists():
        print("Companies directory does not exist.")
        raise typer.Exit()

    all_companies = []
    for company_file in companies_dir.glob("**/_index.md"):
        with open(company_file, 'r') as f:
            try:
                # Split the file into frontmatter and content
                parts = f.read().split('---')
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    if frontmatter:
                        frontmatter['file_path'] = str(company_file)
                        all_companies.append(frontmatter)
            except yaml.YAMLError as e:
                print(f"Error parsing YAML in {company_file}: {e}")

    if not all_companies:
        print("No companies found to deduplicate.")
        raise typer.Exit()

    df = pd.DataFrame(all_companies)
    
    df['hash_id'] = df.apply(generate_company_hash, axis=1)
    
    # Identify duplicates
    duplicates = df[df.duplicated('hash_id', keep=False)]
    
    if duplicates.empty:
        print("No duplicates found.")
        raise typer.Exit()

    print(f"Found {len(duplicates)} duplicate records.")

    if dry_run:
        print("Dry run enabled. The following duplicates were found:")
        print(duplicates.sort_values('hash_id'))
    else:
        print("Writing changes is not yet implemented.")

if __name__ == "__main__":
    app()