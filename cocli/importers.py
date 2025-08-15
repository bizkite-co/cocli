import csv
from pathlib import Path
from typing import Dict

from .core import Company, create_company_files

def lead_sniper(filepath: Path):
    """
    Importer for Lead Sniper CSV files.

    Parses the CSV, creates Company objects, and uses the core logic
    to create the company files and directories.
    """
    print(f"Starting Lead Sniper import from '{filepath}'...")

    try:
        with filepath.open(mode='r', encoding='utf-8') as f:
            # Use DictReader to easily access columns by their header name
            reader = csv.DictReader(f)
            for row in reader:
                # --- Data Mapping ---
                # Map CSV columns to our Pydantic Company model.
                # This is where you can handle different column names or clean data.
                company_data: Dict[str, any] = {
                    "name": row.get("Name"),
                    "domain": row.get("Domain"),
                    "type": "Lead",  # Set the type for this import
                    "tags": ["lead-sniper-import", "photography-studio"]
                }

                # --- Validation and Creation ---
                try:
                    # Pydantic automatically validates the data.
                    # If 'name' is missing, it will raise an error.
                    company = Company(**company_data)
                    
                    # Pass the validated object to our core function
                    create_company_files(company)

                except Exception as e:
                    print(f"Skipping row due to validation error: {e} -> {row}")

    except FileNotFoundError:
        print(f"Error: File not found at '{filepath}'")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return

    print("\nImport complete.")
