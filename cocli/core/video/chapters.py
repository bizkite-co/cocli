from typing import List, Any, cast
from google.genai import Client
import logging
import os
from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret

logger = logging.getLogger(__name__)


def create_chapters(transcript_text: str, campaign: str) -> str:
    """Create chapters from a transcript using Gemini."""

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
    Please analyze the following transcript and create YouTube chapters with timecodes.
    Use the format MM:SS Chapter Title.
    
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
            logger.warning(f"Model {model_name} not found or not supported. Attempting dynamic fallback...")
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
    return str(response.text)
