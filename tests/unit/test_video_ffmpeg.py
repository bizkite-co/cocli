"""Tests for video ffmpeg helpers (encoder selection, duration probing)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cocli.core.video.ffmpeg import get_duration, get_h264_encoder


class TestGetH264Encoder:
    def test_falls_back_when_nvenc_listed_but_unusable(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" ... h264_nvenc ... libx264 ...")
        with (
            patch("cocli.core.video.ffmpeg.subprocess.run", return_value=encoders),
            patch("cocli.core.video.ffmpeg._nvenc_is_usable", return_value=False),
        ):
            assert get_h264_encoder() == "libx264"

    def test_prefers_nvenc_when_usable(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" ... h264_nvenc ... libx264 ...")
        with (
            patch("cocli.core.video.ffmpeg.subprocess.run", return_value=encoders),
            patch("cocli.core.video.ffmpeg._nvenc_is_usable", return_value=True),
        ):
            assert get_h264_encoder() == "h264_nvenc"

    def test_libx264_when_nvenc_not_listed(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" ... libx264 ...")
        with patch("cocli.core.video.ffmpeg.subprocess.run", return_value=encoders):
            assert get_h264_encoder() == "libx264"


class TestGetDuration:
    def test_empty_file_raises(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.mp4"
        empty.write_bytes(b"")
        with pytest.raises(RuntimeError, match="empty"):
            get_duration(empty)

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="not found"):
            get_duration(tmp_path / "missing.mp4")

    def test_empty_ffprobe_stdout_raises(self, tmp_path: Path) -> None:
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"not-really-video")
        probe = MagicMock(returncode=1, stdout="", stderr="moov atom not found")
        with patch("cocli.core.video.ffmpeg.subprocess.run", return_value=probe):
            with pytest.raises(RuntimeError, match="ffprobe failed"):
                get_duration(video)

    def test_parses_duration(self, tmp_path: Path) -> None:
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"x")
        probe = MagicMock(returncode=0, stdout="12.5\n", stderr="")
        with patch("cocli.core.video.ffmpeg.subprocess.run", return_value=probe):
            assert get_duration(video) == 12.5
