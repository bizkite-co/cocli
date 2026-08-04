"""Tests for YouTube chapter text sanitization (no LLM preamble)."""

from cocli.core.video.chapters import sanitize_chapters_text


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
