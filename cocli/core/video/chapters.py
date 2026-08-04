import logging
import os
import re
from typing import Any, List, cast

from google.genai import Client

from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret

logger = logging.getLogger(__name__)

# YouTube description chapters: "0:00 Title" or "00:00 Title" or "1:02:03 Title"
_CHAPTER_LINE_RE = re.compile(
    r"^\s*(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$"
)


def sanitize_chapters_text(raw: str) -> str:
    """
    Keep only YouTube-ready chapter lines; drop LLM preambles/outros.

    Accepted line shape: ``MM:SS Title`` or ``H:MM:SS Title`` (leading zeros OK).
    Markdown bullets / bold wrappers around the timestamp are stripped.
    """
    lines_out: List[str] = []
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
    contents: List[Any] = [prompt]
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
