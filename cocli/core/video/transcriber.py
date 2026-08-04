from google.genai import Client
from pathlib import Path
import logging
import os
import time
from typing import Dict, Union, cast, Any

from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret
from faster_whisper import WhisperModel  # type: ignore


logger = logging.getLogger(__name__)


class TranscriptionFactory:
    @staticmethod
    def get_transcriber(
        provider: str,
    ) -> Union["GeminiTranscriber", "WhisperTranscriber", "DualTranscriber"]:
        if provider == "gemini":
            return GeminiTranscriber()
        elif provider == "whisper":
            return WhisperTranscriber()
        elif provider == "both":
            return DualTranscriber()
        else:
            raise ValueError(f"Unknown transcription provider: {provider}")


def fallback_resolve_model(client: Client, preferred_type: str = "flash") -> str:
    """
    Queries the available models from the Client and returns the best matching model.
    Falls back to a hardcoded stable default if listing fails.
    """
    try:
        available_models: list[str] = []
        for m in client.models.list():
            if m.name and m.supported_actions and "generateContent" in m.supported_actions:
                available_models.append(m.name)
        matches = [match for match in available_models if preferred_type in match.lower()]
        if matches:
            order = []
            if preferred_type == "flash":
                order = ["gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]
            elif preferred_type == "pro":
                order = ["gemini-3.5-pro", "gemini-2.5-pro", "gemini-pro-latest"]
            
            for preferred in order:
                for match in matches:
                    if preferred in match:
                        return match
            return matches[0]
        if available_models:
            return available_models[0]
    except Exception as list_err:
        logger.warning(f"Failed to list models: {list_err}")
    
    return f"gemini-2.5-{preferred_type}"




class GeminiTranscriber:
    def transcribe(self, video_path: Path, campaign: str) -> Dict[str, str]:
        config = load_campaign_config(campaign)
        transcription_config = config.get("video", {}).get("transcription", {})

        api_key_path = config.get("google", {}).get("gemini-api-key")
        model_name = transcription_config.get("model", "gemini-2.0-flash")

        api_key = get_op_secret(api_key_path) or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "No Gemini API key found. Please configure `gemini-api-key` under the `[google]` section "
                "in your campaign config, or set the `GEMINI_API_KEY` environment variable."
            )
        client = Client(api_key=api_key)

        logger.info(f"Uploading {video_path.name} to Gemini using {model_name}...")
        video_file = client.files.upload(file=str(video_path))
        assert video_file.name is not None
        assert video_file.state is not None

        while video_file.state.name == "PROCESSING":
            time.sleep(10)
            video_file = client.files.get(name=video_file.name)

        prompt = "Please provide a timecoded transcript of this video in Markdown format. Use the format [MM:SS] Text content."
        try:
            response = client.models.generate_content(
                model=model_name, contents=[cast(Any, prompt), cast(Any, video_file)]
            )
            used_model = model_name
        except Exception as e:
            if "not found" in str(e).lower() or "404" in str(e):
                logger.warning(f"Model {model_name} not found or not supported. Attempting dynamic fallback...")
                used_model = fallback_resolve_model(client, "flash")
                logger.info(f"Retrying with fallback model: {used_model}")
                response = client.models.generate_content(
                    model=used_model, contents=[cast(Any, prompt), cast(Any, video_file)]
                )
            else:
                raise

        client.files.delete(name=cast(str, video_file.name))

        full_transcript = (
            f"# Transcript for {video_path.name} ({used_model})\n\n{response.text}"
        )
        return {"gemini": full_transcript}



def _load_whisper_model(model_size: str) -> WhisperModel:
    """Load faster-whisper; prefer CUDA, fall back to CPU when GPU/CUDA is unusable."""
    try:
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        logger.info("Whisper using device=cuda compute_type=float16")
        return model
    except Exception as e:
        logger.warning(
            "Whisper CUDA unavailable (%s); falling back to device=cpu compute_type=int8",
            e,
        )
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        logger.info("Whisper using device=cpu compute_type=int8")
        return model


class WhisperTranscriber:
    def transcribe(self, video_path: Path, campaign: str) -> Dict[str, str]:
        config = load_campaign_config(campaign)
        transcription_config = config.get("video", {}).get("transcription", {})
        model_size = transcription_config.get("whisper_model", "small")

        logger.info(f"Transcribing {video_path.name} using Whisper ({model_size})...")
        model = _load_whisper_model(model_size)

        # Enable word-level timestamps
        segments, info = model.transcribe(
            str(video_path), beam_size=5, word_timestamps=True
        )

        transcript_standard = [
            f"# Transcript for {video_path.name} (Whisper {model_size})\n\n"
        ]
        transcript_granular = [
            f"# Transcript for {video_path.name} (Whisper {model_size} Granular)\n\n"
        ]

        for segment in segments:
            # Standard segment-based
            minutes, seconds = divmod(int(segment.start), 60)
            transcript_standard.append(f"[{minutes:02d}:{seconds:02d}] {segment.text}")

            # Granular word-based
            if segment.words:
                for word in segment.words:
                    m, s = divmod(int(word.start), 60)
                    ms = int((word.start - int(word.start)) * 1000)
                    transcript_granular.append(
                        f"[{m:02d}:{s:02d}.{ms:03d}] {word.word}"
                    )

        return {
            "whisper": "\n".join(transcript_standard),
            "whisper_granular": "\n".join(transcript_granular),
        }


class DualTranscriber:
    def __init__(self) -> None:
        self.gemini = GeminiTranscriber()
        self.whisper = WhisperTranscriber()

    def transcribe(self, video_path: Path, campaign: str) -> Dict[str, str]:
        results: Dict[str, str] = {}
        results.update(self.gemini.transcribe(video_path, campaign))
        results.update(self.whisper.transcribe(video_path, campaign))
        return results
