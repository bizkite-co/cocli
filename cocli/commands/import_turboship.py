import typer
import pandas as pd
from pathlib import Path
import re
import yaml
import logging

from ..core.config import get_companies_dir, get_people_dir
from ..core.utils import slugify, create_company_files, create_person_files
from ..models.person import Person
from ..models.company import Company
from ..models.shopify import ShopifyData

logger = logging.getLogger(__name__)

app = typer.Typer()

COMMON_DOMAINS = ["gmail.com", "yahoo.com", "hotmail.com", "aol.com", "msn.com", "icloud.com", "comcast.net", "sbcglobal.net", "cox.net", "att.net", "verizon.net"]

def clean_phone_number(phone: str) -> str:
    if pd.isna(phone):
        return None
    return re.sub(r'[\s\-().]', '', str(phone))

@app.command()
def import_turboship(
    customers_csv_path: Path = typer.Argument(..., help="Path to the customers.csv file"),
    addresses_csv_path: Path = typer.Argument(..., help="Path to the customer_addresses.csv file"),
) -> None:
    """
    Import customers from a Turboship CSV file.
    """
    if not customers_csv_path.exists():
        logger.error(f"Error: File not found at {customers_csv_path}")
        raise typer.Exit(1)
    if not addresses_csv_path.exists():
        logger.error(f"Error: File not found at {addresses_csv_path}")
        raise typer.Exit(1)

    customers_df = pd.read_csv(customers_csv_path, header=None)
    customers_df.columns = ['id', 'first_name', 'last_name', 'email', 'phone', 'tags']

    addresses_df = pd.read_csv(addresses_csv_path, header=None)
    addresses_df.columns = ['id', 'company_name', 'address', 'city', 'state', 'zip', 'country', 'address_phone']

    # Clean phone numbers before merging
    customers_df['phone'] = customers_df['phone'].apply(clean_phone_number)
    addresses_df['address_phone'] = addresses_df['address_phone'].apply(clean_phone_number)

    # Merge dataframes
    df = pd.merge(customers_df, addresses_df, on='id', how='left')

    # Coalesce phone numbers
    df['phone'] = df['phone'].fillna(df['address_phone'])

    # Drop duplicates, keeping the first entry for each customer
    df = df.drop_duplicates(subset=['id'], keep='first')

    for _, row in df.iterrows():
        email = row['email']
        if pd.isna(email):
            continue

        first_name = row['first_name'] if not pd.isna(row['first_name']) else ""
        last_name = row['last_name'] if not pd.isna(row['last_name']) else ""
        name = f"{first_name} {last_name}".strip()

        if not name:
            name = email.split('@')[0]

        person = Person(
            name=name,
            email=email,
            phone=row['phone'] if not pd.isna(row['phone']) else None,
            tags=["turboship", "customer"],
            full_address=row['address'] if not pd.isna(row['address']) else None,
            city=row['city'] if not pd.isna(row['city']) else None,
            state=row['state'] if not pd.isna(row['state']) else None,
            zip_code=row['zip'] if not pd.isna(row['zip']) else None,
            country=row['country'] if not pd.isna(row['country']) else None,
        )

        company_name_from_address = row['company_name'] if not pd.isna(row['company_name']) else None
        domain = email.split('@')[1]
        company_name = ""
        website = ""

        if domain not in COMMON_DOMAINS:
            website = domain

        if company_name_from_address:
            company_name = company_name_from_address
        elif domain not in COMMON_DOMAINS:
            company_name = domain.split('.')[0]

        if company_name:
            company = Company(
                name=company_name.replace("-", " ").title(),
                domain=website,
                tags=["turboship", "customer"],
                phone_1=row['phone'] if not pd.isna(row['phone']) else None,
            )
            company_dir = get_companies_dir() / slugify(company.name)
            create_company_files(company, company_dir)
            person.company_name = company.name

        people_dir = get_people_dir()
        person_dir = people_dir / slugify(person.name)
        create_person_files(person, person_dir)

        # Create ShopifyData object and save to enrichments
        shopify_data = ShopifyData(
            id=str(row['id']),
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=row['phone'] if not pd.isna(row['phone']) else None,
            tags=person.tags, # Use the merged tags from the person object
            company_name=company_name,
            address=row['address'] if not pd.isna(row['address']) else None,
            city=row['city'] if not pd.isna(row['city']) else None,
            state=row['state'] if not pd.isna(row['state']) else None,
            zip=row['zip'] if not pd.isna(row['zip']) else None,
            country=row['country'] if not pd.isna(row['country']) else None,
            address_phone=row['address_phone'] if not pd.isna(row['address_phone']) else None,
        )

        person_enrichment_dir = person_dir / "enrichments"
        person_enrichment_dir.mkdir(exist_ok=True)
        shopify_md_path = person_enrichment_dir / "shopify.md"
        with open(shopify_md_path, "w") as f_md:
            f_md.write("---")
            yaml.dump(shopify_data.model_dump(exclude_none=True), f_md, sort_keys=False, default_flow_style=False, allow_unicode=True)
            f_md.write("---")

        logger.info(f"Imported {person.name}")
