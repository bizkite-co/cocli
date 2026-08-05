"""Tests for video ffmpeg helpers (encoder selection, duration probing, profiles)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cocli.core.video.ffmpeg import (
    build_codec_args,
    get_duration,
    get_encode_profile_settings,
    get_h264_encoder,
    resolve_encode_profile_name,
)


class TestEncodeProfiles:
    def test_default_is_publish(self) -> None:
        assert resolve_encode_profile_name(None, None) == "publish"

    def test_cli_overrides_campaign(self) -> None:
        assert (
            resolve_encode_profile_name(
                "draft", {"encode": {"profile": "publish"}}
            )
            == "draft"
        )

    def test_campaign_profile(self) -> None:
        assert (
            resolve_encode_profile_name(None, {"encode": {"profile": "Draft"}})
            == "draft"
        )

    def test_publish_libx264_settings(self) -> None:
        s = get_encode_profile_settings("publish")
        assert s["libx264"]["preset"] == "slow"
        assert s["libx264"]["crf"] == 18
        args, preset, crf, cq = build_codec_args("libx264", s)
        assert preset == "slow"
        assert crf == 18
        assert cq is None
        assert "-preset" in args and "slow" in args

    def test_draft_is_faster(self) -> None:
        s = get_encode_profile_settings("draft")
        assert s["libx264"]["preset"] == "veryfast"
        assert s["libx264"]["crf"] == 20
        args, preset, crf, cq = build_codec_args("h264_nvenc", s)
        assert preset == "p2"
        assert cq == 23
        assert crf is None
        assert "h264_nvenc" in args

    def test_campaign_override(self) -> None:
        cfg = {
            "encode": {
                "profiles": {
                    "draft": {
                        "libx264_preset": "fast",
                        "libx264_crf": 21,
                    }
                }
            }
        }
        s = get_encode_profile_settings("draft", cfg)
        assert s["libx264"]["preset"] == "fast"
        assert s["libx264"]["crf"] == 21

    def test_unknown_profile_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown encode profile"):
            get_encode_profile_settings("turbo-max")


class TestGetH264Encoder:
    def test_falls_back_when_nvenc_listed_but_unusable(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" ... h264_nvenc ... libx264 ...")
        with (
            patch("cocli.core.video.ffmpeg.subprocess.run", return_value=encoders),
            patch(
                "cocli.core.video.ffmpeg._nvenc_is_usable",
                return_value=(False, "cuInit failed"),
            ),
        ):
            assert get_h264_encoder() == "libx264"
            from cocli.core.video.ffmpeg import select_h264_encoder

            enc, requested, reason = select_h264_encoder()
            assert enc == "libx264"
            assert requested == "h264_nvenc"
            assert reason == "cuInit failed"

    def test_prefers_nvenc_when_usable(self) -> None:
        encoders = MagicMock(returncode=0, stdout=" ... h264_nvenc ... libx264 ...")
        with (
            patch("cocli.core.video.ffmpeg.subprocess.run", return_value=encoders),
            patch(
                "cocli.core.video.ffmpeg._nvenc_is_usable",
                return_value=(True, None),
            ),
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
