"""Tests for video job-run receipts and path helpers."""

from __future__ import annotations

import json
from pathlib import Path

from cocli.core.video.job_runs import (
    last_normalize_pointer_path,
    last_package_pointer_path,
    last_upload_pointer_path,
    run_receipt_path,
    save_video_job_run,
    write_last_normalize_pointer,
    write_last_package_pointer,
    write_last_upload_pointer,
)
from cocli.models.campaigns.video_job_run import (
    KIND_NORMALIZE,
    KIND_PACKAGE,
    KIND_UPLOAD,
    VideoJobRun,
    VideoNormalizeSettings,
    make_video_run_id,
)


def test_make_video_run_id_is_unique_and_sortable() -> None:
    a = make_video_run_id("task-agent-intro")
    b = make_video_run_id("task-agent-intro")
    assert a != b
    assert "task-agent-intro" in a
    assert a.count("_") >= 2


def test_save_and_last_pointer_roundtrip(tmp_path: Path) -> None:
    video_root = tmp_path / "video"
    run = VideoJobRun.start_normalize("bizkite", "my-clip")
    run.settings = VideoNormalizeSettings(
        encoder="libx264",
        encoder_requested="h264_nvenc",
        encoder_fallback_reason="cuInit failed",
        preset="slow",
        crf=18,
    )
    run.start_phase("analyze_loudness")
    run.end_phase("analyze_loudness")
    run.start_phase("encode")
    run.end_phase("encode")
    run.mark_completed()

    receipt = save_video_job_run(video_root, run)
    assert receipt.exists()
    assert receipt.parent.name == run.started_at.strftime("%Y%m%d")
    assert receipt.name == f"{run.run_id}.json"
    assert receipt == run_receipt_path(video_root, run)

    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["kind"] == KIND_NORMALIZE
    assert data["status"] == "completed"
    assert data["campaign"] == "bizkite"
    assert data["slug"] == "my-clip"
    assert data["duration_seconds"] is not None
    assert "analyze_loudness" in data["phases"]
    assert data["settings"]["encoder"] == "libx264"
    assert data["settings"]["encoder_requested"] == "h264_nvenc"

    product_dir = video_root / "normalized" / "my-clip"
    pointer = write_last_normalize_pointer(
        product_dir, run, receipt_path=receipt
    )
    assert pointer == last_normalize_pointer_path(product_dir)
    ptr = json.loads(pointer.read_text(encoding="utf-8"))
    assert ptr["run_id"] == run.run_id
    assert ptr["receipt_path"] == str(receipt)


def test_package_job_run_path_helpers(tmp_path: Path) -> None:
    video_root = tmp_path / "video"
    run = VideoJobRun.start_package("bizkite", "my-clip")
    run.start_phase("copy_assets")
    run.end_phase("copy_assets")
    run.start_phase("thumbnail")
    run.end_phase("thumbnail")
    run.mark_completed()

    assert run.kind == KIND_PACKAGE
    receipt = save_video_job_run(video_root, run)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["kind"] == KIND_PACKAGE
    assert "copy_assets" in data["phases"]
    assert "thumbnail" in data["phases"]
    assert data["phases"]["copy_assets"]["duration_seconds"] is not None

    product_dir = video_root / "packaged" / "my-clip"
    pointer = write_last_package_pointer(
        product_dir, run, receipt_path=receipt
    )
    assert pointer == last_package_pointer_path(product_dir)
    assert pointer.name == "last-package-run.json"
    ptr = json.loads(pointer.read_text(encoding="utf-8"))
    assert ptr["kind"] == KIND_PACKAGE
    assert ptr["run_id"] == run.run_id
    assert ptr["receipt_path"] == str(receipt)


def test_upload_job_run_path_helpers(tmp_path: Path) -> None:
    video_root = tmp_path / "video"
    run = VideoJobRun.start_upload("bizkite", "my-clip")
    run.start_phase("prepare_metadata")
    run.end_phase("prepare_metadata")
    run.start_phase("upload_video")
    run.end_phase("upload_video")
    run.start_phase("move_to_uploaded")
    run.end_phase("move_to_uploaded")
    run.notes = "youtube_id=abc123"
    run.mark_completed()

    assert run.kind == KIND_UPLOAD
    receipt = save_video_job_run(video_root, run)
    assert receipt == run_receipt_path(video_root, run)
    data = json.loads(receipt.read_text(encoding="utf-8"))
    assert data["kind"] == KIND_UPLOAD
    assert "prepare_metadata" in data["phases"]
    assert "upload_video" in data["phases"]
    assert data["notes"] == "youtube_id=abc123"

    product_dir = video_root / "uploaded" / "my-clip"
    pointer = write_last_upload_pointer(
        product_dir, run, receipt_path=receipt
    )
    assert pointer == last_upload_pointer_path(product_dir)
    assert pointer.name == "last-upload-run.json"
    ptr = json.loads(pointer.read_text(encoding="utf-8"))
    assert ptr["kind"] == KIND_UPLOAD
    assert ptr["receipt_path"] == str(receipt)


def test_mark_failed_records_error() -> None:
    run = VideoJobRun.start_normalize("bizkite", "x")
    run.mark_failed("boom")
    assert run.status == "failed"
    assert run.errors == ["boom"]
    assert run.completed_at is not None


def test_package_and_upload_factories_use_distinct_kinds() -> None:
    p = VideoJobRun.start_package("c", "s")
    u = VideoJobRun.start_upload("c", "s")
    n = VideoJobRun.start_normalize("c", "s")
    assert p.kind == KIND_PACKAGE
    assert u.kind == KIND_UPLOAD
    assert n.kind == KIND_NORMALIZE
    assert p.status == u.status == n.status == "running"
