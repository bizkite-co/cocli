from pydantic import BaseModel, Field, model_validator, computed_field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import yaml
import logging
from .domain import Domain

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
    phone: Optional[str] = None
    email: Optional[str] = None
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
    tags: List[str] = []
    scraper_version: Optional[int] = 1
    associated_company_folder: Optional[str] = None
    is_email_provider: bool = False
    all_emails: List[str] = []
    email_contexts: Dict[str, str] = {}
    tech_stack: List[str] = []

    def save(self, company_slug: str) -> None:
        """Saves the website enrichment data to the local company directory."""
        from ..core.config import get_companies_dir
        
        company_dir = get_companies_dir() / company_slug
        enrichment_dir = company_dir / "enrichments"
        enrichment_dir.mkdir(parents=True, exist_ok=True)
        
        website_md_path = enrichment_dir / "website.md"
        
        # Ensure updated_at is refreshed on save
        self.updated_at = datetime.now(timezone.utc)

        with open(website_md_path, "w") as f:
            f.write("---")
            yaml.dump(
                self.model_dump(exclude_none=True),
                f,
                sort_keys=False,
                default_flow_style=False,
                allow_unicode=True,
            )
            f.write("---")
        
        logger.debug(f"Saved website enrichment locally for {company_slug}")