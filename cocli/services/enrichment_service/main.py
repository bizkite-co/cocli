
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
import os
from playwright.async_api import async_playwright
import toml # New import
from typing import Optional, Dict, Any, cast # New imports

# Adjust imports to be absolute from the project root
from cocli.core.enrichment import enrich_company_website
from cocli.models.website import Website
from cocli.models.company import Company
from cocli.models.campaign import Campaign # New imports
from cocli.core.config import get_campaign_dir # New import
from cocli.core.exceptions import EnrichmentError, NavigationError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
# ... (rest of file) ...
@app.post("/enrich", response_model=Website)
async def enrich_domain(request: EnrichmentRequest) -> Website:
    """
    Accepts a domain and enrichment options, then scrapes the website
    to return structured data.
    """
    logger.info(f"Received enrichment request for domain: {request.domain}")
    
    # ... (campaign loading logic) ...
    campaign: Optional[Campaign] = None
    if request.campaign_name:
        # ... (same logic) ...
        campaign_dir = get_campaign_dir(request.campaign_name)
        if campaign_dir and (campaign_dir / "config.toml").exists():
             # ...
             with open(campaign_dir / "config.toml", "r") as f:
                config_data = toml.load(f)
             flat_config = config_data.pop('campaign')
             flat_config.update(config_data)
             campaign = Campaign.model_validate(flat_config)
        elif request.aws_profile_name and request.company_slug:
             # ... (same logic) ...
             logger.info("Campaign config not found locally. Using provided parameters for stateless operation.")
             campaign_data = {
                "campaign": {
                    "name": request.campaign_name,
                    "tag": "placeholder",
                    "domain": "placeholder.com",
                    "company-slug": request.company_slug,
                    "workflows": [],
                },
                "aws": {
                    "profile": request.aws_profile_name
                },
                "import": {
                    "format": "csv"
                },
                "google_maps": {
                    "email": "placeholder",
                    "one_password_path": "placeholder"
                },
                "prospecting": {
                    "locations": [],
                    "tools": [],
                    "queries": []
                }
            }
             flat_config = cast(Dict[str, Any], campaign_data.pop("campaign"))
             final_config_dict = {**flat_config, **campaign_data}
             campaign = Campaign.model_validate(final_config_dict)
        else:
            logger.error(f"Campaign '{request.campaign_name}' config not found and insufficient parameters provided.")
            raise HTTPException(status_code=404, detail=f"Campaign '{request.campaign_name}' configuration not found and params missing.")

    async with async_playwright() as p:
        # Using --no-sandbox is often necessary in Docker environments
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            # We create a dummy company object to pass to the enrichment function
            dummy_company = Company(name=request.domain, domain=request.domain, slug=request.domain)
            
            website_data = await enrich_company_website(
                browser=browser,
                company=dummy_company,
                campaign=campaign, # Pass the campaign object
                force=request.force,
                ttl_days=request.ttl_days,
                debug=request.debug
            )
            
            # If we get here, website_data is valid (or None if no domain, but we checked request.domain)
            if not website_data:
                 # This might happen if company.domain is somehow empty despite request.domain
                 raise HTTPException(status_code=400, detail="Domain provided was empty or invalid.")

            logger.info(f"Successfully enriched domain: {request.domain}")
            return website_data

        except NavigationError as e:
            logger.warning(f"Navigation failed for {request.domain}: {e}")
            raise HTTPException(status_code=404, detail=str(e))
        except EnrichmentError as e:
            logger.error(f"Enrichment error for {request.domain}: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"An unexpected error occurred during enrichment for {request.domain}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
        finally:
            await browser.close()

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

