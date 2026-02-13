from typing import Optional, List, Any, cast, Dict
from pydantic import BaseModel, Field

from cocli.application.search_service import get_fuzzy_search_results
from cocli.application.campaign_service import CampaignService
from cocli.application.worker_service import WorkerService
from cocli.application.company_service import get_company_details_for_view
from cocli.models.search import SearchResult
from cocli.core.config import get_campaign

class ServiceContainer(BaseModel):
    """
    A container for application services, enabling dependency injection
    and easier mocking in tests.
    """
    class Config:
        arbitrary_types_allowed = True

    search_service: Any = Field(default_factory=lambda: get_fuzzy_search_results)
    company_service: Any = Field(default_factory=lambda: get_company_details_for_view)
    
    # We use a factory that resolves the current campaign for the default service instances
    campaign_service: Any = Field(default_factory=lambda: CampaignService(campaign_name=get_campaign() or "default"))
    worker_service: Any = Field(default_factory=lambda: WorkerService(campaign_name=get_campaign() or "default"))

    # If True, the TUI will perform searches synchronously (useful for tests)
    sync_search: bool = False

    def fuzzy_search(
        self,
        search_query: str = "",
        item_type: Optional[str] = None,
        campaign_name: Optional[str] = None,
        force_rebuild_cache: bool = False
    ) -> List[SearchResult]:
        # Wrap the function call to match the expected signature
        results = self.search_service(
            search_query=search_query,
            item_type=item_type,
            campaign_name=campaign_name,
            force_rebuild_cache=force_rebuild_cache
        )
        return cast(List[SearchResult], results)

    def get_company_details(self, company_slug: str) -> Optional[Dict[str, Any]]:
        return self.company_service(company_slug) # type: ignore
