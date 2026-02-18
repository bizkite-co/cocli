from typing import Optional, List, Any, cast, Dict
from pydantic import BaseModel, Field

from cocli.application.search_service import get_fuzzy_search_results, get_template_counts
from cocli.application.campaign_service import CampaignService
from cocli.application.worker_service import WorkerService
from cocli.application.reporting_service import ReportingService
from cocli.application.audit_service import AuditService
from cocli.application.data_sync_service import DataSyncService
from cocli.application.deployment_service import DeploymentService
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

    campaign_name: str = Field(default_factory=lambda: get_campaign() or "default")
    
    search_service: Any = Field(default_factory=lambda: get_fuzzy_search_results)
    company_service: Any = Field(default_factory=lambda: get_company_details_for_view)
    
    # Lazy properties for services that need campaign_name
    _campaign_service: Optional[CampaignService] = None
    _worker_service: Optional[WorkerService] = None
    _reporting_service: Optional[ReportingService] = None
    _audit_service: Optional[AuditService] = None
    _data_sync_service: Optional[DataSyncService] = None
    _deployment_service: Optional[DeploymentService] = None
    _operation_service: Optional[Any] = None

    @property
    def campaign_service(self) -> CampaignService:
        if not self._campaign_service:
            self._campaign_service = CampaignService(campaign_name=self.campaign_name)
        return self._campaign_service

    @property
    def worker_service(self) -> WorkerService:
        if not self._worker_service:
            self._worker_service = WorkerService(campaign_name=self.campaign_name)
        return self._worker_service

    @property
    def reporting_service(self) -> ReportingService:
        if not self._reporting_service:
            self._reporting_service = ReportingService(campaign_name=self.campaign_name)
        return self._reporting_service

    @property
    def audit_service(self) -> AuditService:
        if not self._audit_service:
            self._audit_service = AuditService(campaign_name=self.campaign_name)
        return self._audit_service

    @property
    def data_sync_service(self) -> DataSyncService:
        if not self._data_sync_service:
            self._data_sync_service = DataSyncService(campaign_name=self.campaign_name)
        return self._data_sync_service

    @property
    def deployment_service(self) -> DeploymentService:
        if not self._deployment_service:
            self._deployment_service = DeploymentService(campaign_name=self.campaign_name)
        return self._deployment_service

    @property
    def operation_service(self) -> Any:
        if not self._operation_service:
            from .operation_service import OperationService
            self._operation_service = OperationService(campaign_name=self.campaign_name, services=self)
        return self._operation_service

    # If True, the TUI will perform searches synchronously (useful for tests)
    sync_search: bool = False

    def fuzzy_search(
        self,
        search_query: str = "",
        item_type: Optional[str] = None,
        campaign_name: Optional[str] = None,
        force_rebuild_cache: bool = False,
        filters: Optional[Dict[str, Any]] = None,
        sort_by: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[SearchResult]:
        # Wrap the function call to match the expected signature
        results = self.search_service(
            search_query=search_query,
            item_type=item_type,
            campaign_name=campaign_name,
            force_rebuild_cache=force_rebuild_cache,
            filters=filters,
            sort_by=sort_by,
            limit=limit,
            offset=offset
        )
        return cast(List[SearchResult], results)

    def get_template_counts(self, campaign_name: Optional[str] = None) -> Dict[str, int]:
        return get_template_counts(campaign_name)

    def get_company_details(self, company_slug: str) -> Optional[Dict[str, Any]]:
        return self.company_service(company_slug) # type: ignore
