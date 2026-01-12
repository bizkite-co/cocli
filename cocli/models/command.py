from typing import List, Optional
from pydantic import BaseModel, Field

class CocliCommand(BaseModel):
    """
    Represents a CLI command to be executed by a worker.
    Example: cocli campaign add-exclude "att-com" --campaign turboship
    """
    command: str = Field(..., description="The raw command string")
    args: Optional[List[str]] = Field(None, description="List of parsed arguments for the cocli command")
    campaign: Optional[str] = Field(None, description="Campaign context")
    ack_token: Optional[str] = Field(None, description="Receipt handle for SQS")
