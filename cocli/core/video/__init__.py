from typing import Any
from .ffmpeg import normalize_video, get_duration

__all__ = [
    "normalize_video",
    "get_duration",
    "YouTubeUploader",
    "transcriber",
    "thumbnailer",
    "chapters",
    "auth",
]


def __getattr__(name: str) -> Any:
    if name == "YouTubeUploader":
        from .youtube import YouTubeUploader
        return YouTubeUploader
    if name == "transcriber":
        from . import transcriber
        return transcriber
    if name == "thumbnailer":
        from . import thumbnailer
        return thumbnailer
    if name == "chapters":
        from . import chapters
        return chapters
    if name == "auth":
        from . import auth
        return auth
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

