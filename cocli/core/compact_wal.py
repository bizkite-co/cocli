import shutil
import logging
from ..models.companies.company import Company

logger = logging.getLogger(__name__)

def compact_company_wal(company_slug: str) -> None:
    """
    Reads a company's WAL updates, applies them to the main index,
    saves the index, and clears the updates/ directory.
    """
    from ..core.config import get_companies_dir
    company_dir = get_companies_dir() / company_slug
    
    if not company_dir.exists():
        logger.warning(f"Cannot compact WAL for non-existent company: {company_slug}")
        return

    # Loading the company automatically applies WAL updates because of our change to from_directory
    company = Company.from_directory(company_dir)
    if not company:
        logger.error(f"Failed to load company {company_slug} for compaction.")
        return

    # Save company back to disk (this will overwrite _index.md with latest data)
    # We pass use_wal=False to avoid re-writing the same data back to WAL
    company.save(use_wal=False)
    
    # Now clear the updates/ directory
    updates_dir = company_dir / "updates"
    if updates_dir.exists():
        logger.info(f"Clearing WAL for {company_slug} after compaction.")
        shutil.rmtree(updates_dir)
        updates_dir.mkdir(parents=True, exist_ok=True)

def compact_all_companies() -> None:
    """
    Iterates through all companies and compacts their WALs.
    """
    from ..core.config import get_companies_dir
    companies_dir = get_companies_dir()
    for company_dir in companies_dir.iterdir():
        if company_dir.is_dir() and (company_dir / "updates").exists():
            compact_company_wal(company_dir.name)
