"""Persist video pipeline job-run receipts under campaign video/job_runs/."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from cocli.models.campaigns.video_job_run import VideoJobRun

logger = logging.getLogger(__name__)


def job_runs_root(video_queue_root: Path) -> Path:
    """``{campaign}/video/job_runs`` — ops telemetry, not a queue product stage."""
    return video_queue_root / "job_runs"


def run_receipt_path(video_queue_root: Path, run: VideoJobRun) -> Path:
    day = run.started_at.strftime("%Y%m%d")
    return job_runs_root(video_queue_root) / day / f"{run.run_id}.json"


def last_normalize_pointer_path(normalized_video_dir: Path) -> Path:
    """``normalized/{slug}/last-normalize-run.json`` — latest receipt next to product."""
    return normalized_video_dir / "last-normalize-run.json"


def last_package_pointer_path(packaged_video_dir: Path) -> Path:
    """``packaged/{slug}/last-package-run.json`` — latest package receipt next to product."""
    return packaged_video_dir / "last-package-run.json"


def last_upload_pointer_path(uploaded_video_dir: Path) -> Path:
    """``uploaded/{slug}/last-upload-run.json`` — latest upload receipt next to product."""
    return uploaded_video_dir / "last-upload-run.json"


def save_video_job_run(video_queue_root: Path, run: VideoJobRun) -> Path:
    """Write (or overwrite) the canonical job-run JSON; returns the path written."""
    path = run_receipt_path(video_queue_root, run)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = run.model_dump(mode="json")
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    logger.debug("Wrote video job run: %s", path)
    return path


def _write_last_run_pointer(
    product_dir: Path,
    pointer_path: Path,
    run: VideoJobRun,
    *,
    receipt_path: Optional[Path] = None,
) -> Path:
    """Mirror the full run receipt next to a product dir for quick inspection."""
    product_dir.mkdir(parents=True, exist_ok=True)
    payload = run.model_dump(mode="json")
    if receipt_path is not None:
        payload["receipt_path"] = str(receipt_path)
    pointer_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    return pointer_path


def write_last_normalize_pointer(
    normalized_video_dir: Path,
    run: VideoJobRun,
    *,
    receipt_path: Optional[Path] = None,
) -> Path:
    """
    Mirror the full run receipt next to the normalized package for quick inspection.

    Also embeds ``receipt_path`` when provided.
    """
    return _write_last_run_pointer(
        normalized_video_dir,
        last_normalize_pointer_path(normalized_video_dir),
        run,
        receipt_path=receipt_path,
    )


def write_last_package_pointer(
    packaged_video_dir: Path,
    run: VideoJobRun,
    *,
    receipt_path: Optional[Path] = None,
) -> Path:
    """Mirror the package run receipt next to the packaged product dir."""
    return _write_last_run_pointer(
        packaged_video_dir,
        last_package_pointer_path(packaged_video_dir),
        run,
        receipt_path=receipt_path,
    )


def write_last_upload_pointer(
    uploaded_video_dir: Path,
    run: VideoJobRun,
    *,
    receipt_path: Optional[Path] = None,
) -> Path:
    """Mirror the upload run receipt next to the uploaded product dir."""
    return _write_last_run_pointer(
        uploaded_video_dir,
        last_upload_pointer_path(uploaded_video_dir),
        run,
        receipt_path=receipt_path,
    )
