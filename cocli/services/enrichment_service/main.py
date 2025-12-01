
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from playwright.async_api import async_playwright
import toml # New import
from pathlib import Path # New import
from typing import Optional # New import

# Adjust imports to be absolute from the project root
from cocli.core.enrichment import enrich_company_website
from cocli.models.website import Website
from cocli.models.company import Company
from cocli.models.campaign import Campaign # New import
from cocli.core.config import get_campaign_dir # New import

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class EnrichmentRequest(BaseModel):
    domain: str
    force: bool = False
    ttl_days: int = 30
    debug: bool = False
    campaign_name: Optional[str] = None # New field

@app.post("/enrich", response_model=Website)
async def enrich_domain(request: EnrichmentRequest) -> Website:
    """
    Accepts a domain and enrichment options, then scrapes the website
    to return structured data.
    """
    logger.info(f"Received enrichment request for domain: {request.domain}")
    
    campaign: Optional[Campaign] = None
    if request.campaign_name:
        campaign_dir = get_campaign_dir(request.campaign_name)
        if not campaign_dir:
            logger.error(f"Campaign '{request.campaign_name}' not found for enrichment request.")
            raise HTTPException(status_code=404, detail=f"Campaign '{request.campaign_name}' not found.")
        
        config_path = campaign_dir / "config.toml"
        if not config_path.exists():
            logger.error(f"Configuration file not found for campaign '{request.campaign_name}'.")
            raise HTTPException(status_code=404, detail=f"Configuration file not found for campaign '{request.campaign_name}'.")
        
        with open(config_path, "r") as f:
            config_data = toml.load(f)
        
        flat_config = config_data.pop('campaign')
        flat_config.update(config_data)
        campaign = Campaign.model_validate(flat_config)

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
            
            if not website_data:
                logger.warning(f"Could not enrich domain: {request.domain}")
                raise HTTPException(status_code=404, detail=f"Could not enrich domain: {request.domain}")
            
            logger.info(f"Successfully enriched domain: {request.domain}")
            return website_data
        except HTTPException as e:
            raise e
        except Exception as e:
            logger.error(f"An unexpected error occurred during enrichment for {request.domain}: {e}", exc_info=True) # Added exc_info
            raise HTTPException(status_code=500, detail="An internal error occurred during enrichment.")
        finally:
            await browser.close()

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}

