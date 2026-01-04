import json
import logging
from pathlib import Path
from typing import List, Iterator
from datetime import datetime, UTC

from ..models.email import EmailEntry
from .config import get_campaign_dir
from .text_utils import slugify, slugdotify

logger = logging.getLogger(__name__)

class EmailIndexManager:
    """
    Manages a campaign-specific index of emails.
    Stored in cocli_data/campaigns/{campaign}/indexes/emails/ as individual JSON files.
    Structure: cocli_data/campaigns/{campaign}/indexes/emails/{domain_part}/{user_part}.json
    """
    def __init__(self, campaign_name: str):
        self.campaign_name = campaign_name
        campaign_dir = get_campaign_dir(campaign_name)
        if not campaign_dir:
            # Fallback if campaign dir doesn't exist (e.g. during early initialization)
            from .config import get_campaigns_dir
            campaign_dir = get_campaigns_dir() / campaign_name
            
        self.base_dir = campaign_dir / "indexes" / "emails"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_email_path(self, email: str) -> Path:
        """
        Returns the file path for a given email, derived strictly from the email address itself.
        Structure: indexes/emails/{domain_slug}/{user_slug}.json
        """
        if "@" in email:
            user_part, domain_part = email.rsplit("@", 1)
        else:
            user_part, domain_part = email, "unknown"
            
        # Use slugdotify to preserve dots in domain (e.g. example.com) and user (john.doe)
        domain_slug = slugdotify(domain_part)
        email_slug = slugdotify(user_part)
        
        domain_dir = self.base_dir / domain_slug
        domain_dir.mkdir(parents=True, exist_ok=True)
        return domain_dir / f"{email_slug}.json"

    def add_email(self, email_entry: EmailEntry) -> bool:
        """
        Adds or updates an email entry in the index.
        Thread-safe 'latest write wins' approach for distributed workers.
        """
        path = self._get_email_path(email_entry.email)
        
        now = datetime.now(UTC)
        
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
                existing_entry = EmailEntry.model_validate(existing_data)
                
                # Update existing entry fields
                email_entry.first_seen = existing_entry.first_seen
                email_entry.last_seen = now
                
                # Preserve company_slug if already present
                if not email_entry.company_slug and existing_entry.company_slug:
                    email_entry.company_slug = existing_entry.company_slug
                
                # Preserve verification status if existing is better
                if email_entry.verification_status == "unknown" and existing_entry.verification_status != "unknown":
                    email_entry.verification_status = existing_entry.verification_status
                    
                # Merge tags
                if existing_entry.tags:
                    new_tags = set(email_entry.tags) | set(existing_entry.tags)
                    email_entry.tags = sorted(list(new_tags))
                    
            except Exception as e:
                logger.error(f"Error reading existing email entry {path}: {e}")

        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(email_entry.model_dump_json(indent=2))
            return True
        except Exception as e:
            logger.error(f"Error writing email entry {path}: {e}")
            return False

    def get_emails_for_domain(self, domain: str) -> List[EmailEntry]:
        """Returns all indexed emails for a given domain."""
        domain_slug = slugify(domain)
        domain_dir = self.base_dir / domain_slug
        emails: List[EmailEntry] = []
        
        if not domain_dir.exists():
            return emails
            
        for file_path in domain_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                emails.append(EmailEntry.model_validate(data))
            except Exception as e:
                logger.error(f"Error loading email entry {file_path}: {e}")
        return emails

    def read_all_emails(self) -> Iterator[EmailEntry]:
        """Yields all emails in the campaign index."""
        if not self.base_dir.exists():
            return

        for domain_dir in self.base_dir.iterdir():
            if domain_dir.is_dir():
                for file_path in domain_dir.glob("*.json"):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        yield EmailEntry.model_validate(data)
                    except Exception as e:
                        logger.error(f"Error loading email entry {file_path}: {e}")