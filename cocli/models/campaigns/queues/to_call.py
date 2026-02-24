# POLICY: frictionless-data-policy-enforcement
from .base import QueueMessage
from ....core.ordinant import QueueName

class ToCallTask(QueueMessage):
    """
    Represents a company to be contacted.
    Supports scheduling via callback_at.
    """
    priority: int = 1
    
    @property
    def collection(self) -> QueueName:
        return "to-call"

    @property
    def task_id(self) -> str:
        return self.company_slug
