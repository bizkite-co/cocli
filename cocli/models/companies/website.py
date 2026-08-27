from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from pathlib import Path
import yaml
import logging
from ..domain import Domain
from ..email_address import EmailAddress
from ..phone import OptionalPhone
from ...core.error_classification import ErrorCategory

logger = logging.getLogger(__name__)


def _is_hollow(value: Any) -> bool:
    """A value a fresh scrape produces when it found nothing for a field -
    None, an empty/whitespace string, or an empty list/dict. Deliberately
    NOT hollow: False, 0, or any other falsy-but-meaningful value - those
    are real findings, not "we didn't look."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, dict)):
        return len(value) == 0
    return False


# Fields where a fresh, empty result must NOT fall back to whatever is
# already on disk - each describes the latest attempt's own outcome (or is
# handled separately), not accumulated knowledge about the company, so a
# fresh empty/absent value is meaningful in its own right rather than a
# sign the scrape just didn't find anything.
_WEBSITE_NEVER_MERGE_FROM_EXISTING = {"url", "sitemap_xml", "navbar_html", "error", "error_category"}


class Website(BaseModel):
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    url: Domain # Called `domain` in the website CSV model

    @model_validator(mode='before')
    @classmethod
    def _populate_url_from_domain(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if 'domain' in values and 'url' not in values:
            values['url'] = values['domain']
        return values

    @computed_field
    def domain(self) -> Domain:
        return self.url

    title: Optional[str] = None
    head_html: Optional[str] = None
    company_name: Optional[str] = None
    phone: OptionalPhone = None
    email: Optional[EmailAddress] = None
    facebook_url: Optional[str] = None
    linkedin_url: Optional[str] = None
    instagram_url: Optional[str] = None
    twitter_url: Optional[str] = None
    youtube_url: Optional[str] = None
    address: Optional[str] = None
    personnel: List[Dict[str, Any]] = []
    description: Optional[str] = None
    about_us_url: Optional[str] = None
    contact_url: Optional[str] = None
    services_url: Optional[str] = None
    products_url: Optional[str] = None
    services: List[str] = []
    products: List[str] = []
    categories: List[str] = []
    tags: List[str] = []
    scraper_version: Optional[int] = 1
    processed_by: Optional[str] = None
    associated_company_folder: Optional[str] = None
    is_email_provider: bool = False
    all_emails: List[EmailAddress] = []
    email_contexts: Dict[str, str] = {}
    ip_address: Optional[str] = None
    tech_stack: List[str] = []
    found_keywords: List[str] = []
    sitemap_xml: Optional[str] = None
    navbar_html: Optional[str] = None
    error: Optional[str] = None
    error_category: Optional[ErrorCategory] = None

    def compute_merged_save_data(self, existing_data: Dict[str, Any]) -> Dict[str, Any]:
        """Pure merge: fresh scrape values win unless hollow and the existing
        value isn't. Single source of truth for what "merge-safe save" means -
        every persistence target (local website.md, the S3 mirror) must call
        this instead of re-deriving its own merge logic, or they will drift
        into different merge behavior for the same data. See task-agent
        ticket
        website.save-blindly-overwrites-website.md-on-every-enrichment-write-no-merge-safety-against-sparse-force-refresh-scrapes.
        """
        save_data = self.model_dump(mode="json", exclude_none=True)
        save_data.pop("sitemap_xml", None)
        save_data.pop("navbar_html", None)

        for field_name in type(self).model_fields:
            if field_name in _WEBSITE_NEVER_MERGE_FROM_EXISTING:
                continue
            if _is_hollow(save_data.get(field_name)) and not _is_hollow(
                existing_data.get(field_name)
            ):
                save_data[field_name] = existing_data[field_name]

        return save_data

    @staticmethod
    def read_existing_frontmatter(website_md_path: Path) -> Dict[str, Any]:
        """Reads and parses an existing website.md's YAML frontmatter, if any.
        Returns {} on missing file or any parse failure (caller proceeds with
        fresh data only - never blocks a save on a corrupt existing file)."""
        from ...core.text_utils import parse_frontmatter

        if not website_md_path.exists():
            return {}
        try:
            frontmatter_str = parse_frontmatter(website_md_path.read_text(encoding="utf-8"))
            if frontmatter_str:
                loaded = yaml.safe_load(frontmatter_str)
                if isinstance(loaded, dict):
                    return loaded
        except Exception as merge_read_err:
            logger.warning(
                f"Could not read existing website.md at {website_md_path} to merge "
                f"against - proceeding with fresh data only: {merge_read_err}"
            )
        return {}

    def save(self, company_slug: str) -> None:
        """Saves the website enrichment data to the local company directory.

        Merges with any existing website.md first: a field only overwrites
        the existing value when the fresh scrape actually found something
        for it. A sparse or failed re-scrape (e.g. a force_refresh hitting a
        blocked/dead site) must not silently blank out previously-good data
        - force_refresh means "try again," not "erase what we had." See
        task-agent ticket
        website.save-blindly-overwrites-website.md-on-every-enrichment-write-no-merge-safety-against-sparse-force-refresh-scrapes.
        """
        from ...core.config import get_companies_dir, get_campaign
        from ...core.email_index_manager import EmailIndexManager
        from ..campaigns.indexes.email import EmailEntry
        from datetime import UTC

        company_dir = get_companies_dir() / company_slug
        enrichment_dir = company_dir / "enrichments"
        enrichment_dir.mkdir(parents=True, exist_ok=True)

        website_md_path = enrichment_dir / "website.md"

        # Ensure updated_at is refreshed on save
        self.updated_at = datetime.now(timezone.utc)

        existing_data = self.read_existing_frontmatter(website_md_path)
        save_data = self.compute_merged_save_data(existing_data)

        with open(website_md_path, "w") as f:
            f.write("---\n")
            yaml.safe_dump(
                save_data,
                f,
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )
            f.write("---\n")
        
        # Save raw auxiliary files with size limits (1MB)
        MAX_SIZE = 1 * 1024 * 1024
        if self.sitemap_xml:
            content = self.sitemap_xml
            if len(content.encode('utf-8')) > MAX_SIZE:
                logger.warning(f"Sitemap too large ({len(content.encode('utf-8'))} bytes), truncating.")
                content = content[:MAX_SIZE//2] + "\n... [TRUNCATED DUE TO SIZE] ...\n"
            (enrichment_dir / "sitemap.xml").write_text(content)
        if self.navbar_html:
            content = self.navbar_html
            if len(content.encode('utf-8')) > MAX_SIZE:
                logger.warning(f"Navbar HTML too large ({len(content.encode('utf-8'))} bytes), truncating.")
                content = content[:MAX_SIZE//2] + "\n... [TRUNCATED DUE TO SIZE] ...\n"
            (enrichment_dir / "navbar.html").write_text(content)

        logger.debug(f"Saved website enrichment locally for {company_slug}")

        # Sync with Email Index
        campaign_name = get_campaign()
        if campaign_name:
            try:
                index_manager = EmailIndexManager(campaign_name)
                emails_to_sync = set()
                if self.email:
                    emails_to_sync.add(self.email)
                for e in self.all_emails:
                    emails_to_sync.add(e)
                for p in self.personnel:
                    if p.get("email"):
                        emails_to_sync.add(p["email"])
                
                for email_str in emails_to_sync:
                    try:
                        email_addr = EmailAddress(email_str)
                        entry = EmailEntry(
                            email=email_addr,
                            domain=str(self.domain),
                            company_slug=company_slug,
                            source="website_enrichment_save",
                            found_at=datetime.now(UTC),
                            tags=self.tags
                        )
                        index_manager.add_email(entry)
                    except Exception:
                        continue
            except Exception as e:
                logger.error(f"Error syncing emails from website enrichment to index: {e}")