
import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
from playwright.async_api import async_playwright

# Adjust imports to be absolute from the project root
from cocli.core.enrichment import enrich_company_website
from cocli.models.website import Website
from cocli.models.company import Company

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

class EnrichmentRequest(BaseModel):
    domain: str
    force: bool = False
    ttl_days: int = 30
    debug: bool = False

@app.post("/enrich", response_model=Website)
async def enrich_domain(request: EnrichmentRequest):
    """
    Accepts a domain and enrichment options, then scrapes the website
    to return structured data.
    """
    logger.info(f"Received enrichment request for domain: {request.domain}")
    
    async with async_playwright() as p:
        # Using --no-sandbox is often necessary in Docker environments
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            # We create a dummy company object to pass to the enrichment function
            dummy_company = Company(name=request.domain, domain=request.domain, slug=request.domain)
            
            website_data = await enrich_company_website(
                browser=browser,
                company=dummy_company,
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
            logger.error(f"An unexpected error occurred during enrichment for {request.domain}: {e}")
            raise HTTPException(status_code=500, detail="An internal error occurred during enrichment.")
        finally:
            await browser.close()

@app.get("/health")
async def health_check():
    return {"status": "ok"}

