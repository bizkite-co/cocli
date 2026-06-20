from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
import uuid


class ScrapeJobRun(BaseModel):
    """
    Tracks metadata for a single scrape job run on a distributed worker.
    Enables job coordination and result auditing across Pi nodes.

    Stored as JSON in queues/{queue_name}/job_runs/{run_id}.json
    """

    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for this job run")
    campaign_name: str = Field(..., description="Campaign this job ran for")
    queue_name: str = Field(..., description="Queue type (e.g., 'discovery-gen', 'gm-list')")
    stage: int = Field(..., description="Pipeline stage number (1-4 for discovery-gen)")

    # Execution context
    node_hostname: str = Field(..., description="Pi node that executed this job (e.g., 'cocli5x0.pi')")
    started_at: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp when job started")
    completed_at: Optional[datetime] = Field(None, description="UTC timestamp when job completed")

    # Results
    files_processed: int = Field(default=0, description="Number of input files processed")
    items_found: int = Field(default=0, description="Number of items discovered/scraped")
    items_failed: int = Field(default=0, description="Number of items that failed processing")

    # Error tracking
    errors: List[str] = Field(default_factory=list, description="List of error messages encountered")
    status: str = Field(default="pending", description="Job status: pending, running, completed, failed")

    # Optional metadata
    batch_name: Optional[str] = Field(None, description="Batch name if this was a batched job")
    notes: Optional[str] = Field(None, description="Free-form notes about the job")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    def mark_completed(self) -> None:
        """Mark this job as completed."""
        self.completed_at = datetime.utcnow()
        self.status = "completed"

    def mark_failed(self, error: str) -> None:
        """Mark this job as failed and log the error."""
        self.completed_at = datetime.utcnow()
        self.status = "failed"
        self.errors.append(error)

    def add_error(self, error: str) -> None:
        """Add an error to the error log."""
        self.errors.append(error)

    def duration_seconds(self) -> float:
        """Calculate job duration in seconds."""
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return (datetime.utcnow() - self.started_at).total_seconds()
