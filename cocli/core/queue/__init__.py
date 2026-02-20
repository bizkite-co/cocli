from abc import ABC, abstractmethod
from typing import List
from ...models.campaigns.queues.base import QueueMessage

class QueueManager(ABC):
    """
    Abstract base class for queue adapters.
    """
    
    @abstractmethod
    def push(self, message: QueueMessage) -> str:
        """Push a message to the queue. Returns the message ID."""
        pass

    @abstractmethod
    def poll(self, batch_size: int = 1) -> List[QueueMessage]:
        """
        Retrieve a batch of messages from the queue.
        These messages should be considered 'locked' or 'invisible' to other consumers.
        """
        pass

    @abstractmethod
    def ack(self, message: QueueMessage) -> None:
        """
        Acknowledge successful processing. The message should be removed.
        """
        pass

    @abstractmethod
    def nack(self, message: QueueMessage, is_http_500: bool = False) -> None:
        """
        Negative acknowledgement. The message should be returned to the queue for retry.
        """
        pass
