from typing import Optional, List, Any, cast, Dict
from pydantic import BaseModel, Field, ConfigDict, PrivateAttr
import logging

from cocli.application.search_service import (
    get_fuzzy_search_results,
    get_template_counts,
)
from cocli.application.campaign_service import CampaignService
from cocli.application.worker_service import WorkerService
from cocli.application.reporting_service import ReportingService
from cocli.application.audit_service import AuditService
from cocli.application.data_sync_service import DataSyncService
from cocli.application.deployment_service import DeploymentService
from cocli.application.company_service import get_company_details_for_view
from cocli.application.event_service import EventService
from cocli.core.secrets import get_secret_provider
from cocli.models.search import SearchResult
from cocli.core.config import get_campaign

from .protocols import (
    SearchProvider,
    CompanyServiceProvider,
    TemplateCountsProvider,
    CampaignServiceProvider,
    WorkerServiceProvider,
    ReportingServiceProvider,
    AuditServiceProvider,
    DataSyncServiceProvider,
    DeploymentServiceProvider,
    OperationServiceProvider,
    EventServiceProvider,
    SecretServiceProvider,
)

logger = logging.getLogger(__name__)


class ServiceContainer(BaseModel):
    """
    A container for application services, enabling dependency injection
    and easier mocking in tests.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    campaign_name: str = Field(default_factory=lambda: get_campaign() or "")

    def set_campaign(self, name: str) -> None:
        """Updates the campaign name and invalidates cached lazy services."""
        logger.warning(f"set_campaign called: {self.campaign_name} -> {name}")
        if self.campaign_name != name:
            self.campaign_name = name
            self._campaign_service = None
            self._worker_service = None
            self._reporting_service = None
            self._audit_service = None
            self._data_sync_service = None
            self._deployment_service = None
            self._operation_service = None
            self._event_service = None
            self._secret_service = None
            logger.warning(f"Services invalidated for campaign: {name}")

    # Provider overrides (can be injected via constructor or setters)
    injected_search_service: Optional[Any] = Field(default=None, alias="search_service")
    injected_company_service: Optional[Any] = Field(
        default=None, alias="company_service"
    )
    injected_template_counts_service: Optional[Any] = Field(
        default=None, alias="template_counts_service"
    )

    # Lazy attributes (PrivateAttr)
    _campaign_service: Optional[Any] = PrivateAttr(default=None)
    _worker_service: Optional[Any] = PrivateAttr(default=None)
    _reporting_service: Optional[Any] = PrivateAttr(default=None)
    _audit_service: Optional[Any] = PrivateAttr(default=None)
    _data_sync_service: Optional[Any] = PrivateAttr(default=None)
    _deployment_service: Optional[Any] = PrivateAttr(default=None)
    _operation_service: Optional[Any] = PrivateAttr(default=None)
    _event_service: Optional[Any] = PrivateAttr(default=None)
    _secret_service: Optional[Any] = PrivateAttr(default=None)

    @property
    def search_service(self) -> SearchProvider:
        return cast(
            SearchProvider, self.injected_search_service or get_fuzzy_search_results
        )

    @search_service.setter
    def search_service(self, value: SearchProvider) -> None:
        self.injected_search_service = value

    @property
    def company_service(self) -> CompanyServiceProvider:
        return cast(
            CompanyServiceProvider,
            self.injected_company_service or get_company_details_for_view,
        )

    @company_service.setter
    def company_service(self, value: CompanyServiceProvider) -> None:
        self.injected_company_service = value

    @property
    def template_counts_service(self) -> TemplateCountsProvider:
        return cast(
            TemplateCountsProvider,
            self.injected_template_counts_service or get_template_counts,
        )

    @template_counts_service.setter
    def template_counts_service(self, value: TemplateCountsProvider) -> None:
        self.injected_template_counts_service = value

    @property
    def campaign_service(self) -> CampaignServiceProvider:
        if not self._campaign_service:
            self._campaign_service = CampaignService(campaign_name=self.campaign_name)
        return cast(CampaignServiceProvider, self._campaign_service)

    @campaign_service.setter
    def campaign_service(self, value: CampaignServiceProvider) -> None:
        self._campaign_service = value

    @property
    def worker_service(self) -> WorkerServiceProvider:
        if not self._worker_service:
            self._worker_service = WorkerService(campaign_name=self.campaign_name)
        return cast(WorkerServiceProvider, self._worker_service)

    @worker_service.setter
    def worker_service(self, value: WorkerServiceProvider) -> None:
        self._worker_service = value

    @property
    def reporting_service(self) -> ReportingServiceProvider:
        if not self._reporting_service:
            self._reporting_service = ReportingService(campaign_name=self.campaign_name)
        return cast(ReportingServiceProvider, self._reporting_service)

    @reporting_service.setter
    def reporting_service(self, value: ReportingServiceProvider) -> None:
        self._reporting_service = value

    @property
    def audit_service(self) -> AuditServiceProvider:
        if not self._audit_service:
            self._audit_service = AuditService(campaign_name=self.campaign_name)
        return cast(AuditServiceProvider, self._audit_service)

    @audit_service.setter
    def audit_service(self, value: AuditServiceProvider) -> None:
        self._audit_service = value

    @property
    def data_sync_service(self) -> DataSyncServiceProvider:
        if not self._data_sync_service:
            self._data_sync_service = DataSyncService(campaign_name=self.campaign_name)
        return cast(DataSyncServiceProvider, self._data_sync_service)

    @data_sync_service.setter
    def data_sync_service(self, value: DataSyncServiceProvider) -> None:
        self._data_sync_service = value

    @property
    def deployment_service(self) -> DeploymentServiceProvider:
        if not self._deployment_service:
            self._deployment_service = DeploymentService(
                campaign_name=self.campaign_name
            )
        return cast(DeploymentServiceProvider, self._deployment_service)

    @deployment_service.setter
    def deployment_service(self, value: DeploymentServiceProvider) -> None:
        self._deployment_service = value

    @property
    def operation_service(self) -> OperationServiceProvider:
        if not self._operation_service:
            from .operation_service import OperationService

            self._operation_service = OperationService(
                campaign_name=self.campaign_name, services=self
            )
        return cast(OperationServiceProvider, self._operation_service)

    @operation_service.setter
    def operation_service(self, value: OperationServiceProvider) -> None:
        self._operation_service = value

    @property
    def event_service(self) -> EventServiceProvider:
        if not self._event_service:
            self._event_service = EventService(campaign_name=self.campaign_name)
        return cast(EventServiceProvider, self._event_service)

    @event_service.setter
    def event_service(self, value: EventServiceProvider) -> None:
        self._event_service = value

    @property
    def secret_service(self) -> SecretServiceProvider:
        if not self._secret_service:
            self._secret_service = get_secret_provider()
        return cast(SecretServiceProvider, self._secret_service)

    @secret_service.setter
    def secret_service(self, value: SecretServiceProvider) -> None:
        self._secret_service = value

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
        offset: int = 0,
    ) -> List[SearchResult]:
        return self.search_service(
            search_query=search_query,
            item_type=item_type,
            campaign_name=campaign_name,
            force_rebuild_cache=force_rebuild_cache,
            filters=filters,
            sort_by=sort_by,
            limit=limit,
            offset=offset,
        )

    def get_template_counts(
        self, campaign_name: Optional[str] = None
    ) -> Dict[str, int]:
        return self.template_counts_service(campaign_name)

    def get_company_details(self, company_slug: str) -> Optional[Dict[str, Any]]:
        return self.company_service(company_slug)
