from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import yaml
import logging
from .domain import Domain
from .email_address import EmailAddress
from .phone import PhoneNumber

logger = logging.getLogger(__name__)

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

    company_name: Optional[str] = None
    phone: Optional[PhoneNumber] = None
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
    associated_company_folder: Optional[str] = None
    is_email_provider: bool = False
    all_emails: List[EmailAddress] = []
    email_contexts: Dict[str, str] = {}
    tech_stack: List[str] = []

    def save(self, company_slug: str) -> None:
        """Saves the website enrichment data to the local company directory."""
        from ..core.config import get_companies_dir, get_campaign
        from ..core.email_index_manager import EmailIndexManager
        from .email import EmailEntry
        from datetime import UTC

        company_dir = get_companies_dir() / company_slug
        enrichment_dir = company_dir / "enrichments"
        enrichment_dir.mkdir(parents=True, exist_ok=True)
        
        website_md_path = enrichment_dir / "website.md"
        
        # Ensure updated_at is refreshed on save
        self.updated_at = datetime.now(timezone.utc)

        with open(website_md_path, "w") as f:
            f.write("---\n")
            yaml.safe_dump(
                self.model_dump(exclude_none=True),
                f,
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )
            f.write("---\n")
        
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