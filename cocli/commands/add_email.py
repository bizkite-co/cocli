import typer
import logging
from typing import Optional

from ..core.config import get_companies_dir, get_campaign
from ..models.companies.company import Company
from ..core.utils import create_company_files
from ..models.email_address import EmailAddress

logger = logging.getLogger(__name__)
app = typer.Typer()

@app.command()
def add_email(
    company_name: str = typer.Argument(..., help="The slug or name of the company to add the email to."),
    email: str = typer.Argument(..., help="The email address to add."),
    campaign_name: Optional[str] = typer.Option(None, "--campaign", "-c", help="Campaign name for indexing."),
) -> None:
    """
    Adds an email address to a company and records it in the campaign index.
    """
    companies_dir = get_companies_dir()
    company_dir = companies_dir / company_name
    if not company_dir.exists():
        # Try slugified version if exact match fails
        from cocli.core.text_utils import slugify
        company_dir = companies_dir / slugify(company_name)
        
    if not company_dir.exists():
        logger.error(f"Company folder '{company_name}' not found at {company_dir}")
        raise typer.Exit(code=1)

    company = Company.from_directory(company_dir)
    if not company:
        logger.error(f"Could not load company data for {company_name}")
        raise typer.Exit(code=1)

    try:
        email_addr = EmailAddress(email)
    except Exception as e:
        logger.error(f"Invalid email: {e}")
        raise typer.Exit(code=1)

    # Index the email if campaign is known
    eff_campaign = campaign_name or get_campaign()
    if eff_campaign:
        from ..core.config import set_campaign
        set_campaign(eff_campaign)

    company.email = email_addr
    create_company_files(company, company_dir)
    logger.info(f"Added email {email_addr} to {company.name}")
