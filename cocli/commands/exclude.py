import typer
from typing import Optional
import logging

from ..core.config import get_companies_dir
from ..models.company import Company
from ..core.exclusions import ExclusionManager

logger = logging.getLogger(__name__)

app = typer.Typer()

@app.command()
def exclude(
    company_name: str = typer.Argument(..., help="The name of the company to exclude."),
    campaign: str = typer.Option(..., "--campaign", "-c", help="The campaign to exclude the company from."),
    reason: Optional[str] = typer.Option(None, "--reason", "-r", help="The reason for excluding the company."),
) -> None:
    """
    Excludes a company from a campaign.
    """
    companies_dir = get_companies_dir()
    company = Company.from_directory(companies_dir / company_name)
    if not company or not company.domain:
        logger.error(f"Could not find company or domain for {company_name}")
        raise typer.Exit(code=1)

    exclusion_manager = ExclusionManager(campaign=campaign)
    exclusion_manager.add_exclusion(domain=company.domain, reason=reason)
    logger.info(f"Excluded {company.name} ({company.domain}) from campaign '{campaign}'.")
