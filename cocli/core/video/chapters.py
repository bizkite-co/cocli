from typing import List, Any, cast
from google.genai import Client
import logging
from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret

logger = logging.getLogger(__name__)


def create_chapters(transcript_text: str, campaign: str) -> str:
    """Create chapters from a transcript using Gemini."""

    config = load_campaign_config(campaign)
    api_key_path = config.get("google", {}).get("gemini-api-key")

    api_key = get_op_secret(api_key_path)
    if not api_key:
        raise ValueError("No API key retrieved.")
    client = Client(api_key=api_key)

    prompt = f"""
    Please analyze the following transcript and create YouTube chapters with timecodes.
    Use the format MM:SS Chapter Title.
    
    Transcript:
    {transcript_text}
    """

    # Properly cast content to match SDK's expected input type (Union of Content types)
    contents: List[Any] = [prompt]
    response = client.models.generate_content(
        model="gemini-2.0-flash-001", contents=cast(Any, contents)
    )

    if response.text is None:
        return ""
    return str(response.text)
