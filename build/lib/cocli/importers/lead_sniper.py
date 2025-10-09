import csv
from pathlib import Path
from typing import Dict, Any, Optional

from ..core.models import Company
from ..core.utils import create_company_files, slugify
from ..core.config import get_companies_dir

def _safe_int(value: str) -> Optional[int]:
    try:
        return int(value) if value else None
    except ValueError:
        return None

def _safe_float(value: str) -> Optional[float]:
    try:
        return float(value) if value else None
    except ValueError:
        return None

def lead_sniper(filepath: Path, debug: bool = False): # Added debug parameter
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

                categories = []
                if row.get("First_category"):
                    categories.append(row["First_category"].strip())
                if row.get("Second_category"):
                    categories.append(row["Second_category"].strip())

                company_data: Dict[str, Any] = {
                    "name": row.get("Name"),
                    "domain": row.get("Domain"),
                    "type": "Lead",  # Set the type for this import
                    "tags": ["lead-sniper-import", row.get("Keyword")] if row.get("Keyword") else ["lead-sniper-import"],

                    "id": row.get("id"), # Added
                    "keyword": row.get("Keyword"), # Added
                    "full_address": row.get("Full_Address"),
                    "street_address": row.get("Street_Address"),
                    "city": row.get("City"),
                    "zip_code": row.get("Zip"), # Mapped via alias in model
                    "state": row.get("State"),
                    "country": row.get("Country"),
                    "timezone": row.get("Timezone"), # Added

                    "phone_1": row.get("Phone_1"), # Added
                    "phone_number": row.get("Phone_Standard_format"), # Mapped via alias
                    "phone_from_website": row.get("Phone_From_WEBSITE"), # Added
                    "email": row.get("Email_From_WEBSITE"), # Mapped via alias
                    "website_url": row.get("Website"), # Mapped via alias

                    "categories": categories, # Handled by BeforeValidator in model

                    "reviews_count": _safe_int(row.get("Reviews_count", "")),
                    "average_rating": _safe_float(row.get("Average_rating", "")),
                    "business_status": row.get("Business_Status"), # Mapped via alias
                    "hours": row.get("Hours"),

                    "facebook_url": row.get("Facebook_URL"), # Mapped via alias
                    "linkedin_url": row.get("Linkedin_URL"), # Mapped via alias
                    "instagram_url": row.get("Instagram_URL"), # Mapped via alias


                    "meta_description": row.get("Meta_Description"), # Mapped via alias
                    "meta_keywords": row.get("Meta_Keywords"), # Mapped via alias
                }

                # --- Validation and Creation ---
                try:
                    # Pydantic automatically validates the data.
                    company = Company(**company_data, by_alias=False)

                    # Construct company_dir
                    companies_base_dir = get_companies_dir()
                    company_slug = slugify(company.name)
                    company_dir = companies_base_dir / company_slug

                    # Pass the validated object to our core function
                    create_company_files(company, company_dir) # Pass company object directly

                except Exception as e:
                    print(f"Skipping row due to validation error: {e} -> {row}")

    except FileNotFoundError:
        print(f"Error: File not found at '{filepath}'")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return

    print("\nImport complete.")
