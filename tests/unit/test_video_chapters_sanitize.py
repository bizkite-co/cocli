"""Tests for YouTube chapter text sanitization and transcript picking."""

from pathlib import Path
from unittest.mock import patch

import pytest

from cocli.core.video.chapters import (
    load_transcripts_from_dir,
    pick_primary_transcript,
    sanitize_chapters_text,
    write_chapters_for_dir,
)


def test_strips_preamble_and_keeps_chapter_lines() -> None:
    raw = """Here are the YouTube chapters for your video based on the transcript:

00:00 The Problem of Codebase Context
01:46 Introducing "TA next"
03:04 Capturing Ideas with "TA new"

You can copy these into the YouTube description.
"""
    out = sanitize_chapters_text(raw)
    assert "Here are" not in out
    assert "You can copy" not in out
    assert out.startswith("00:00 The Problem")
    assert "01:46 Introducing" in out
    assert out.endswith("\n")


def test_accepts_hms_and_strips_bullets() -> None:
    raw = """
- 0:00 Intro
* 1:02:03 Deep dive
**not a chapter**
"""
    out = sanitize_chapters_text(raw)
    assert out == "0:00 Intro\n1:02:03 Deep dive\n"


def test_pick_primary_prefers_whisper_over_gemini() -> None:
    picked = pick_primary_transcript(
        {
            "gemini": "g",
            "whisper": "w",
            "whisper_granular": "wg",
        }
    )
    assert picked == ("whisper", "w")


def test_pick_primary_skips_granular_only() -> None:
    assert pick_primary_transcript({"whisper_granular": "only"}) is None


def test_pick_primary_explicit_provider() -> None:
    picked = pick_primary_transcript(
        {"whisper": "w", "gemini": "g"}, provider="gemini"
    )
    assert picked == ("gemini", "g")
    assert pick_primary_transcript({"whisper": "w"}, provider="gemini") is None


def test_load_transcripts_from_dir(tmp_path: Path) -> None:
    (tmp_path / "transcript_whisper.md").write_text("hello whisper", encoding="utf-8")
    (tmp_path / "transcript_whisper_granular.md").write_text(
        "granular", encoding="utf-8"
    )
    (tmp_path / "other.md").write_text("nope", encoding="utf-8")
    loaded = load_transcripts_from_dir(tmp_path)
    assert loaded == {
        "whisper": "hello whisper",
        "whisper_granular": "granular",
    }


def test_write_chapters_for_dir_uses_existing_transcript_no_stt(
    tmp_path: Path,
) -> None:
    (tmp_path / "transcript_whisper.md").write_text(
        "0:00 Hello world transcript", encoding="utf-8"
    )

    def fake_create(text: str, campaign: str) -> str:
        assert "Hello world" in text
        assert campaign == "bizkite"
        return sanitize_chapters_text(
            "Here you go:\n0:00 Hello\n1:00 World\nThanks!"
        )

    with patch(
        "cocli.core.video.chapters.create_chapters", side_effect=fake_create
    ):
        out = write_chapters_for_dir(tmp_path, "bizkite")

    assert out == tmp_path / "chapters.md"
    body = out.read_text(encoding="utf-8")
    assert body == "0:00 Hello\n1:00 World\n"
    assert "Here you go" not in body


def test_write_chapters_for_dir_requires_transcript(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="transcript"):
        write_chapters_for_dir(tmp_path, "bizkite")
