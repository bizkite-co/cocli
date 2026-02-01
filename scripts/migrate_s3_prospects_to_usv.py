import boto3
import csv
import io
import logging
import typer
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from cocli.utils.usv_utils import USVDictWriter
from cocli.models.google_maps_prospect import GoogleMapsProspect
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

# Set logging to WARNING to silence individual file logs
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = typer.Typer()

def migrate_prospect_csv_to_usv(s3_client: Any, bucket: str, key: str, delete_old: bool = False) -> None:
    usv_key = key.replace(".csv", ".usv")
    
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        csv_content = response['Body'].read().decode('utf-8')
        
        # Read CSV
        f_in = io.StringIO(csv_content)
        reader = csv.DictReader(f_in)
        rows = list(reader)
        
        if not rows:
            return

        # Write USV
        f_out = io.StringIO()
        fieldnames = list(GoogleMapsProspect.model_fields.keys())
        writer = USVDictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        
        for row in rows:
            # Map and validate
            model_data = {k: v for k, v in row.items() if k in GoogleMapsProspect.model_fields}
            try:
                # Basic type cleanup if needed (though Pydantic handles much of it)
                prospect = GoogleMapsProspect.model_validate(model_data)
                writer.writerow(prospect.model_dump(by_alias=False))
            except Exception as e:
                logger.error(f"Validation error in {key}: {e}")

        s3_client.put_object(
            Bucket=bucket, 
            Key=usv_key, 
            Body=f_out.getvalue().encode('utf-8'),
            ContentType="text/plain"
        )
        
        if delete_old and key != usv_key:
            s3_client.delete_object(Bucket=bucket, Key=key)
            
    except Exception as e:
        print(f"\n[ERROR] Failed to migrate {key}: {e}")

@app.command()
def main(
    bucket: str = typer.Argument(..., help="S3 Bucket name"),
    prefix: str = typer.Option("campaigns/turboship/indexes/google_maps_prospects/", "--prefix", "-p"),
    workers: int = typer.Option(50, "--workers", "-w"),
    delete_old: bool = typer.Option(False, "--delete-old")
) -> None:
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    
    csv_keys = []
    
    print(f"Scanning s3://{bucket}/{prefix}...")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                if key.endswith(".csv"):
                    csv_keys.append(key)
    
    if not csv_keys:
        print("No CSV files found to migrate.")
        return

    print(f"Migrating {len(csv_keys)} files using {workers} workers...")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        auto_refresh=True,
    ) as progress:
        task = progress.add_task("[cyan]Processing...", total=len(csv_keys))
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(migrate_prospect_csv_to_usv, s3, bucket, key, delete_old) for key in csv_keys]
            
            for _ in as_completed(futures):
                progress.advance(task)

    print("\n[bold green]Migration complete![/bold green]")

if __name__ == "__main__":
    app()
