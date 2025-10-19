import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from cocli.core.website_cache import WebsiteCache
from cocli.core.website_domain_csv_manager import WebsiteDomainCsvManager
from cocli.models.website_domain_csv import WebsiteDomainCsv

def migrate():
    """
    Migrates the old website cache to the new website domain CSV index.
    """
    print("Starting website cache migration...")

    try:
        old_cache = WebsiteCache()
        new_manager = WebsiteDomainCsvManager()

        if not old_cache.data:
            print("Old cache is empty. Nothing to migrate.")
            return

        print(f"Found {len(old_cache.data)} items in the old cache.")

        for url, website in old_cache.data.items():
            website_domain_data = {
                "domain": url,
                "company_name": website.company_name,
                "phone": website.phone,
                "email": website.email,
                "facebook_url": website.facebook_url,
                "linkedin_url": website.linkedin_url,
                "instagram_url": website.instagram_url,
                "twitter_url": website.twitter_url,
                "youtube_url": website.youtube_url,
                "address": website.address,
                "personnel": website.personnel,
                "description": website.description,
                "about_us_url": website.about_us_url,
                "contact_url": website.contact_url,
                "services_url": website.services_url,
                "products_url": website.products_url,
                "tags": website.tags,
                "scraper_version": website.scraper_version,
                "associated_company_folder": website.associated_company_folder,
                "is_email_provider": website.is_email_provider,
                "created_at": website.created_at,
                "updated_at": website.updated_at,
            }
            
            filtered_data = {k: v for k, v in website_domain_data.items() if v is not None}

            new_item = WebsiteDomainCsv(**filtered_data)
            # Use the manager's internal data directly to avoid repeated saves
            new_manager.data[new_item.domain] = new_item

        # Save once at the end
        new_manager.save()

        print(f"Successfully migrated {len(new_manager.data)} items to the new index.")
        print(f"New index file created at: {new_manager.csv_file}")

    except Exception as e:
        print(f"An error occurred during migration: {e}")

if __name__ == "__main__":
    migrate()
