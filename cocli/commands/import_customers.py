import typer
import csv
from pathlib import Path
from typing import List, Dict, Optional
import logging

from ..core.config import get_companies_dir, get_people_dir
from cocli.core.text_utils import slugify
from cocli.core.utils import create_company_files, create_person_files
from ..models.person import Person
from ..models.company import Company
from ..models.website_domain_csv import WebsiteDomainCsv
from ..core.website_domain_csv_manager import WebsiteDomainCsvManager
from ..core.email_index_manager import EmailIndexManager
from ..models.email import EmailEntry
from ..models.email_address import EmailAddress
from ..core.config import get_campaign

logger = logging.getLogger(__name__)

def import_customers(
    customers_csv_path: Path = typer.Argument(..., help="Path to the customers.csv file", exists=True, file_okay=True, dir_okay=False, readable=True),
    addresses_csv_path: Path = typer.Argument(..., help="Path to the customer_addresses.csv file", exists=True, file_okay=True, dir_okay=False, readable=True),
    tags: List[str] = typer.Option(..., "--tag", help="Tags to add to the companies and people."),
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name for indexing found emails."),
) -> None:
    """
    Imports customers and their addresses from CSV files, creating companies and people.
    """
    website_csv_manager = WebsiteDomainCsvManager()
    
    eff_campaign = campaign_name or get_campaign()
    email_index = EmailIndexManager(eff_campaign) if eff_campaign else None

    # Load addresses into a dictionary for easy lookup
    addresses: Dict[str, Dict[str, str | None]] = {}
    with open(addresses_csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if row:
                addresses[row[0]] = {
                    "company_name": row[1],
                    "address": row[2],
                    "city": row[3],
                    "state": row[4],
                    "zip": row[5],
                    "country": row[6],
                    "address_phone": row[7],
                }

    # Process customers
    with open(customers_csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row or not row[3]: # Skip if no email
                continue

            customer_id, first_name, last_name, email, phone, _ = row
            name = f"{first_name} {last_name}".strip()
            if not name:
                name = email.split('@')[0]

            address_data = addresses.get(customer_id, {})

            try:
                email_addr = EmailAddress(email)
            except Exception:
                email_addr = None

            person = Person(
                name=name,
                email=email_addr,
                phone=phone or address_data.get("address_phone"),
                tags=tags,
                full_address=address_data.get("address"),
                city=address_data.get("city"),
                state=address_data.get("state"),
                zip_code=address_data.get("zip"),
                country=address_data.get("country"),
                slug=slugify(name),
            )
            
            # Index found email
            if email_index:
                domain = email.split('@')[-1]
                try:
                    email_addr = EmailAddress(email)
                    email_index.add_email(EmailEntry(
                        email=email_addr,
                        domain=domain,
                        source="shopify_customer_import",
                        tags=tags
                    ))
                except Exception:
                    pass

            company_name_from_address = address_data.get('company_name')
            domain = email.split('@')[1]
            company_name = ""
            website_url = ""

            cached_website = website_csv_manager.get_by_domain(domain)
            is_email_provider = cached_website and cached_website.is_email_provider

            if not is_email_provider:
                website_url = domain

            if company_name_from_address:
                company_name = company_name_from_address
            elif not is_email_provider:
                if cached_website and cached_website.company_name:
                    company_name = cached_website.company_name
                else:
                    company_name = domain.split('.')[0]

            if company_name:
                company = Company(
                    name=company_name.replace("-", " ").title(),
                    domain=website_url,
                    tags=tags,
                    phone_1=phone or address_data.get("address_phone"),
                    slug=slugify(company_name.replace("-", " ").title()),
                )
                company_dir = get_companies_dir() / slugify(company.name)
                create_company_files(company, company_dir)
                person.company_name = company.name

                if company.domain:
                    website = website_csv_manager.get_by_domain(company.domain)
                    if not website:
                        website = WebsiteDomainCsv(domain=company.domain)
                    for tag in tags:
                        if tag not in website.tags:
                            website.tags.append(tag)
                    website_csv_manager.add_or_update(website)

            people_dir = get_people_dir()
            person_dir = people_dir / slugify(person.name)
            create_person_files(person, person_dir)

            logger.info(f"Imported customer: {person.name}")