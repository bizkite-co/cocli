from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging
import os
from playwright.async_api import async_playwright
import toml 
from typing import Optional, Dict, Any, cast
from contextlib import asynccontextmanager

# Adjust imports to be absolute from the project root
from cocli.core.enrichment import enrich_company_website
from cocli.models.companies.website import Website
from cocli.models.companies.company import Company
from cocli.models.company_name import CompanyName
from cocli.models.campaigns.campaign import Campaign 
from cocli.core.config import get_campaign_dir
from cocli.core.exceptions import EnrichmentError, NavigationError
from cocli.core.text_utils import slugify
from cocli.utils.headers import ANTI_BOT_HEADERS, USER_AGENT
import socket
import httpx

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    version = os.getenv("COCLI_VERSION", "unknown")
    logger.info(f"Starting Enrichment Service v{version}")
    yield

app = FastAPI(lifespan=lifespan)

class EnrichmentRequest(BaseModel):
    domain: str
    force: bool = False
    ttl_days: int = 30
    debug: bool = False
    campaign_name: Optional[str] = None
    aws_profile_name: Optional[str] = None
    company_slug: Optional[str] = None
    navigation_timeout_ms: Optional[int] = None # New field

@app.get("/debug/network")
async def debug_network() -> Dict[str, Any]:
    results = {}
    
    # 1. DNS Check
    try:
        ip = socket.gethostbyname("google.com")
        results["dns_google"] = f"OK: {ip}"
    except Exception as e:
        results["dns_google"] = f"FAIL: {e}"

    # 2. HTTP Check (to google)
    try:
        async with httpx.AsyncClient(headers={**ANTI_BOT_HEADERS, "User-Agent": USER_AGENT}) as client:
            resp = await client.get("https://www.google.com", timeout=5.0)
            results["http_google"] = f"OK: {resp.status_code}"
    except Exception as e:
        results["http_google"] = f"FAIL: {e}"

    # 3. HTTP Check (to a target that failed, e.g. softroc.com)
    try:
        async with httpx.AsyncClient(verify=False, headers={**ANTI_BOT_HEADERS, "User-Agent": USER_AGENT}) as client: # verify=False to mimic scraper
             resp = await client.get("https://softroc.com", timeout=5.0)
             results["http_softroc"] = f"OK: {resp.status_code}"
    except Exception as e:
         results["http_softroc"] = f"FAIL: {e}"

    return results

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
        if campaign_dir and (campaign_dir / "config.toml").exists():
            # Try loading from file first
            with open(campaign_dir / "config.toml", "r") as f:
                config_data = toml.load(f)
            flat_config = config_data.pop('campaign')
            flat_config.update(config_data)
            campaign = Campaign.model_validate(flat_config)
        elif request.campaign_name:
            # Fallback to constructing ephemeral campaign from request params
            # This handles the Fargate case where config.toml is missing and we use IAM roles (no profile)
            logger.info("Campaign config not found locally. Using provided parameters for stateless operation.")
            
            # Use provided company_slug or default to campaign_name (as a reasonable fallback for the folder name)
            company_slug = request.company_slug or slugify(request.campaign_name)
            
            # Minimal campaign object for S3 access
            campaign_data = {
                "campaign": {
                    "name": request.campaign_name,
                    "tag": "placeholder",
                    "domain": "placeholder.com",
                    "company-slug": company_slug,  # Use alias for dictionary
                    "workflows": [],
                },
                "aws": {
                    "profile": request.aws_profile_name or "default" # Dummy profile if missing, S3CompanyManager handles the rest
                },
                "import": {  # Use alias for dictionary
                    "format": "csv"
                },
                "google_maps": {  # Use field name if no alias
                    "email": "placeholder",
                    "one_password_path": "placeholder"
                },
                "prospecting": {  # Use field name if no alias
                    "locations": [],
                    "tools": [],
                    "queries": []
                }
            }
            
            # Extract the 'campaign' section and merge other sections into it
            flat_config = cast(Dict[str, Any], campaign_data.pop("campaign"))
            # Now flat_config is a dict. Merge the rest of campaign_data into it.
            # Use ** for dictionary unpacking to ensure mypy knows it's a dict
            final_config_dict = {**flat_config, **campaign_data}
            
            try:
                campaign = Campaign.model_validate(final_config_dict)
            except Exception as e:
                logger.error(f"Failed to create ephemeral campaign object: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to initialize campaign context: {e}")
        else:
            logger.error(f"Campaign '{request.campaign_name}' config not found and insufficient parameters provided.")
            raise HTTPException(status_code=404, detail=f"Campaign '{request.campaign_name}' configuration not found and params missing.")

    async with async_playwright() as p:
        # Using --no-sandbox is often necessary in Docker environments
        browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
        try:
            # We create a dummy company object to pass to the enrichment function.
            # Prefer the caller's real (business-name-derived) slug - falling
            # back to a domain-derived one only when the caller genuinely
            # doesn't have one yet - or every call creates a second, orphaned
            # company folder keyed by the raw domain (e.g. "hurleymat-com")
            # alongside the real discovery-pipeline company
            # ("b-f-hurley-mat-co") for the same business. See task-agent
            # ticket investigate-duplicate-company-records-domain-slug-orphans-vs-business-name-slug-discovery-records.
            slug = request.company_slug or slugify(request.domain)
            dummy_company = Company(name=CompanyName(request.domain), domain=request.domain, slug=slug)
            
            website_data = await enrich_company_website(
                browser=browser,
                company=dummy_company,
                campaign=campaign, # Pass the campaign object
                force=request.force,
                ttl_days=request.ttl_days,
                debug=request.debug,
                navigation_timeout_ms=request.navigation_timeout_ms # Pass new param
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
            logger.error(f"An unexpected error occurred during enrichment for {request.domain}: {e}", exc_info=True) # Added exc_info
            raise HTTPException(status_code=500, detail=f"An internal error occurred: {e}")
        finally:
            await browser.close()

@app.get("/health")
async def health_check() -> dict[str, Any]:
    if os.getenv("COCLI_RUNNING_IN_FARGATE") == "true":
        import time
        import json
        hb_path = "/tmp/cocli_heartbeat.json"
        if not os.path.exists(hb_path):
            raise HTTPException(status_code=503, detail="Worker orchestrator has not started yet.")
            
        try:
            mtime = os.path.getmtime(hb_path)
            if time.time() - mtime > 120:
                raise HTTPException(status_code=503, detail="Worker orchestrator heartbeat is stale.")
                
            with open(hb_path, "r") as f:
                stats = json.load(f)
            return {"status": "ok", "orchestrator": stats}
        except HTTPException as he:
            raise he
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to read orchestrator heartbeat: {e}")
            
    return {"status": "ok"}