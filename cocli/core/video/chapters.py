from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, cast

from google.genai import Client

from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret

logger = logging.getLogger(__name__)

# YouTube description chapters: "0:00 Title" or "00:00 Title" or "1:02:03 Title"
_CHAPTER_LINE_RE = re.compile(
    r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$"
)

# Preferred STT sources when regenerating chapters without re-transcribing.
_TRANSCRIPT_PROVIDER_PREFERENCE = ("whisper", "gemini", "openai")


def load_transcripts_from_dir(video_dir: Path) -> dict[str, str]:
    """Load ``transcript_*.md`` files from a normalized (or packaged) video dir."""
    found: dict[str, str] = {}
    for path in sorted(video_dir.glob("transcript_*.md")):
        key = path.stem.removeprefix("transcript_")
        try:
            found[key] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    return found


def pick_primary_transcript(
    transcripts: dict[str, str],
    *,
    provider: Optional[str] = None,
) -> Optional[tuple[str, str]]:
    """
    Choose one non-granular transcript for chapter generation.

    Returns ``(provider_key, text)`` or None if nothing usable is present.
    Preference: explicit ``provider``, then whisper/gemini/openai, then sorted keys.
    """
    primary = {
        k: v
        for k, v in transcripts.items()
        if not k.endswith("_granular") and (v or "").strip()
    }
    if not primary:
        return None
    if provider is not None:
        if provider not in primary:
            return None
        return provider, primary[provider]
    for preferred in _TRANSCRIPT_PROVIDER_PREFERENCE:
        if preferred in primary:
            return preferred, primary[preferred]
    key = sorted(primary.keys())[0]
    return key, primary[key]


def write_chapters_for_dir(
    video_dir: Path,
    campaign: str,
    *,
    provider: Optional[str] = None,
    transcripts: Optional[dict[str, str]] = None,
) -> Path:
    """
    Regenerate ``chapters.md`` from existing transcripts (no STT / no encode).

    Uses ``create_chapters`` (which applies ``sanitize_chapters_text``).
    Returns the path written.
    """
    loaded = transcripts if transcripts is not None else load_transcripts_from_dir(video_dir)
    picked = pick_primary_transcript(loaded, provider=provider)
    if picked is None:
        if provider:
            raise FileNotFoundError(
                f"No usable transcript_{provider}.md in {video_dir}"
            )
        raise FileNotFoundError(
            f"No usable transcript_*.md in {video_dir} "
            "(need a non-granular transcript before regenerating chapters)"
        )
    provider_key, text = picked
    logger.info("Generating chapters from transcript_%s.md in %s", provider_key, video_dir)
    chapter_text = create_chapters(text, campaign)
    out = video_dir / "chapters.md"
    out.write_text(chapter_text, encoding="utf-8")
    return out



def sanitize_chapters_text(raw: str) -> str:
    """
    Keep only YouTube-ready chapter lines; drop LLM preambles/outros.

    Accepted line shape: ``MM:SS Title`` or ``H:MM:SS Title`` (leading zeros OK).
    Markdown bullets / bold wrappers around the timestamp are stripped.
    """
    lines_out: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        # Strip common markdown list / emphasis wrappers
        cleaned = re.sub(r"^[-*•]\s+", "", cleaned)
        cleaned = re.sub(r"^\*+\s*", "", cleaned)
        cleaned = re.sub(r"\*+$", "", cleaned).strip()
        match = _CHAPTER_LINE_RE.match(cleaned)
        if not match:
            continue
        ts, title = match.group(1), match.group(2).strip()
        # Drop trailing markdown bold
        title = re.sub(r"\*+$", "", title).strip()
        if not title:
            continue
        lines_out.append(f"{ts} {title}")
    return "\n".join(lines_out) + ("\n" if lines_out else "")


def create_chapters(transcript_text: str, campaign: str) -> str:
    """Create chapters from a transcript using Gemini.

    Output is meant for the YouTube description body: only chapter lines,
    no conversational preamble.
    """

    config = load_campaign_config(campaign)
    api_key_path = config.get("google", {}).get("gemini-api-key")

    api_key = get_op_secret(api_key_path) or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError(
            "No Gemini API key found. Please configure `gemini-api-key` under the `[google]` section "
            "in your campaign config, or set the `GEMINI_API_KEY` environment variable."
        )
    client = Client(api_key=api_key)

    prompt = f"""
Analyze the transcript and produce YouTube video chapters for the description.

Output rules (strict):
- Output ONLY chapter lines, one per line.
- Each line: timestamp, then a single space, then a short title.
- Timestamp format: M:SS or MM:SS or H:MM:SS (first chapter MUST be 0:00 or 00:00).
- No preamble, no outro, no markdown, no bullets, no numbering, no quotes around titles.
- No sentences like "Here are the chapters" or "You can upload these".
- About 8–15 chapters for a ~30 minute video; fewer for shorter videos.
- Titles should be concise and viewer-facing.

Example of valid output:
0:00 Opening problem
1:46 Introducing TA next
3:04 Capturing ideas with TA new

Transcript:
{transcript_text}
"""

    # Properly cast content to match SDK's expected input type (Union of Content types)
    contents: list[Any] = [prompt]
    model_name = "gemini-2.0-flash-001"
    try:
        response = client.models.generate_content(
            model=model_name, contents=cast(Any, contents)
        )
    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e):
            logger.warning(
                f"Model {model_name} not found or not supported. Attempting dynamic fallback..."
            )
            from cocli.core.video.transcriber import fallback_resolve_model

            fallback_model = fallback_resolve_model(client, "flash")
            logger.info(f"Retrying with fallback model: {fallback_model}")
            response = client.models.generate_content(
                model=fallback_model, contents=cast(Any, contents)
            )
        else:
            raise

    if response.text is None:
        return ""
    cleaned = sanitize_chapters_text(str(response.text))
    if not cleaned.strip():
        logger.warning(
            "Chapter sanitizer removed all lines; returning raw model text for manual edit"
        )
        return str(response.text).strip() + "\n"
    return cleaned
