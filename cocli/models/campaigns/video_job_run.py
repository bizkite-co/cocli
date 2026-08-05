"""Job-run receipts for campaign video pipeline stages (normalize, package, upload)."""

from __future__ import annotations

import platform
import socket
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# Stage kinds written under video/job_runs/
KIND_NORMALIZE = "video.normalize"
KIND_TRANSCRIBE = "video.transcribe"
KIND_PACKAGE = "video.package"
KIND_UPLOAD = "video.upload"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def make_video_run_id(slug: str, when: Optional[datetime] = None) -> str:
    """Build a unique, sortable run id: ``{UTC compact}_{slug}_{4hex}``."""
    ts = when or utc_now()
    compact = ts.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in slug).strip("-")
    safe = (safe or "video")[:80]
    return f"{compact}_{safe}_{uuid.uuid4().hex[:4]}"


def default_host_info() -> Dict[str, Any]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "wsl": Path("/proc/sys/fs/binfmt_misc/WSLInterop").exists()
        or "microsoft" in platform.release().lower(),
    }


class PhaseTiming(BaseModel):
    started_at: datetime
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    def close(self, ended_at: Optional[datetime] = None) -> None:
        end = ended_at or utc_now()
        self.ended_at = end
        self.duration_seconds = (end - self.started_at).total_seconds()


class VideoFileIdentity(BaseModel):
    path: str
    bytes: Optional[int] = None
    duration_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


class VideoNormalizeSettings(BaseModel):
    encoder: str
    encoder_requested: Optional[str] = None
    encoder_fallback_reason: Optional[str] = None
    preset: Optional[str] = None
    crf: Optional[int] = None
    cq: Optional[int] = None
    audio: str = "aac@192k"
    loudness: Dict[str, float] = Field(default_factory=dict)
    denoise_nr: Optional[int] = None


class VideoJobRun(BaseModel):
    """
    Single-document lifecycle for a video pipeline attempt.

    Stored as JSON under ``video/job_runs/{YYYYMMDD}/{run_id}.json``.
    On success, optionally mirrored next to the product dir as
    ``last-normalize-run.json``, ``last-package-run.json``, or
    ``last-upload-run.json``.
    """

    schema_version: int = 1
    run_id: str
    kind: str = KIND_NORMALIZE
    status: str = "running"  # running | completed | failed | cancelled
    campaign: str
    slug: str
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    phases: Dict[str, PhaseTiming] = Field(default_factory=dict)
    input: Optional[VideoFileIdentity] = None
    output: Optional[VideoFileIdentity] = None
    settings: Optional[VideoNormalizeSettings] = None
    host: Dict[str, Any] = Field(default_factory=default_host_info)
    errors: List[str] = Field(default_factory=list)
    notes: Optional[str] = None

    @classmethod
    def _start(cls, kind: str, campaign: str, slug: str) -> "VideoJobRun":
        started = utc_now()
        return cls(
            run_id=make_video_run_id(slug, started),
            kind=kind,
            status="running",
            campaign=campaign,
            slug=slug,
            started_at=started,
        )

    @classmethod
    def start_normalize(cls, campaign: str, slug: str) -> "VideoJobRun":
        return cls._start(KIND_NORMALIZE, campaign, slug)

    @classmethod
    def start_package(cls, campaign: str, slug: str) -> "VideoJobRun":
        return cls._start(KIND_PACKAGE, campaign, slug)

    @classmethod
    def start_upload(cls, campaign: str, slug: str) -> "VideoJobRun":
        return cls._start(KIND_UPLOAD, campaign, slug)

    def start_phase(self, name: str) -> None:
        self.phases[name] = PhaseTiming(started_at=utc_now())

    def end_phase(self, name: str) -> None:
        phase = self.phases.get(name)
        if phase is not None and phase.ended_at is None:
            phase.close()

    def mark_completed(self) -> None:
        self.completed_at = utc_now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.status = "completed"

    def mark_failed(self, error: str) -> None:
        self.completed_at = utc_now()
        self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
        self.status = "failed"
        if error:
            self.errors.append(error)

    def add_error(self, error: str) -> None:
        self.errors.append(error)
