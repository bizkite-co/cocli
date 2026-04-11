from google import genai  # type: ignore
from pathlib import Path
import logging
import time
from typing import Dict, Union
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


class GeminiTranscriber:
    def transcribe(self, video_path: Path, campaign: str) -> Dict[str, str]:
        config = load_campaign_config(campaign)
        transcription_config = config.get("video", {}).get("transcription", {})

        api_key_path = config.get("google", {}).get("gemini-api-key")
        model_name = transcription_config.get("model", "gemini-2.0-flash")

        api_key = get_op_secret(api_key_path)
        client = genai.Client(api_key=api_key)

        logger.info(f"Uploading {video_path.name} to Gemini using {model_name}...")
        video_file = client.files.upload(file=str(video_path))

        while video_file.state.name == "PROCESSING":
            time.sleep(10)
            video_file = client.files.get(name=video_file.name)

        prompt = "Please provide a timecoded transcript of this video in Markdown format. Use the format [MM:SS] Text content."
        response = client.models.generate_content(
            model=model_name, contents=[prompt, video_file]
        )
        client.files.delete(name=video_file.name)

        full_transcript = (
            f"# Transcript for {video_path.name} ({model_name})\n\n{response.text}"
        )
        return {"gemini": full_transcript}


class WhisperTranscriber:
    def transcribe(self, video_path: Path, campaign: str) -> Dict[str, str]:
        config = load_campaign_config(campaign)
        transcription_config = config.get("video", {}).get("transcription", {})
        model_size = transcription_config.get("whisper_model", "small")

        logger.info(f"Transcribing {video_path.name} using Whisper ({model_size})...")
        model = WhisperModel(model_size, device="cuda", compute_type="float16")

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
