import boto3
import csv
import io
import logging
import typer
from typing import Any
from concurrent.futures import ThreadPoolExecutor
from cocli.utils.usv_utils import USVWriter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = typer.Typer()

def convert_csv_to_usv_bytes(csv_bytes: bytes) -> bytes:
    f_in = io.StringIO(csv_bytes.decode('utf-8'))
    reader = csv.reader(f_in)
    
    f_out = io.StringIO()
    writer = USVWriter(f_out)
    for row in reader:
        writer.writerow(row)
    
    return f_out.getvalue().encode('utf-8')

def migrate_object(s3_client: Any, bucket: str, key: str, delete_old: bool = False) -> None:
    if not key.endswith(".csv"):
        return

    usv_key = key[:-4] + ".usv"
    
    try:
        logger.info(f"Migrating s3://{bucket}/{key}")
        response = s3_client.get_object(Bucket=bucket, Key=key)
        csv_bytes = response['Body'].read()
        
        usv_bytes = convert_csv_to_usv_bytes(csv_bytes)
        
        s3_client.put_object(Bucket=bucket, Key=usv_key, Body=usv_bytes)
        logger.info(f"Created s3://{bucket}/{usv_key}")
        
        if delete_old:
            s3_client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"Deleted s3://{bucket}/{key}")
            
    except Exception as e:
        logger.error(f"Failed to migrate {key}: {e}")

@app.command()
def main(
    bucket: str = typer.Argument(..., help="S3 Bucket name"),
    prefix: str = typer.Argument("", help="S3 Prefix"),
    workers: int = typer.Option(10, "--workers", "-w"),
    delete_old: bool = typer.Option(False, "--delete-old", help="Delete the original CSV files after conversion.")
) -> None:
    s3 = boto3.client('s3')
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    
    with ThreadPoolExecutor(max_workers=workers) as executor:
        for page in pages:
            if 'Contents' in page:
                for obj in page['Contents']:
                    key = obj['Key']
                    if key.endswith(".csv"):
                        executor.submit(migrate_object, s3, bucket, key, delete_old)

if __name__ == "__main__":
    app()
