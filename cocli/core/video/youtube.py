"""YouTube uploader using 1Password for client credentials and keyring for OAuth tokens."""

import logging
from pathlib import Path
from typing import Optional, Any, Dict, List, Callable as CallableType
from googleapiclient.discovery import build  # type: ignore
from googleapiclient.http import MediaFileUpload  # type: ignore
from google.oauth2.credentials import Credentials as GoogleCredentials

from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret
from cocli.core.video.keyring_manager import KeyringManager

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def get_secrets(campaign: str) -> tuple[str, str, str, str]:
    """Fetch YouTube credentials.

    Resolution:

    1. ``client_id`` / ``client_secret`` always from 1Password (Windows Hello unlock).
    2. OAuth access/refresh tokens from **keyring first** — written by
       ``cocli video auth`` (device flow). This is the live session after re-auth.
    3. 1Password OAuth paths as fallback when keyring is empty.

    Note: 1Password ``item edit`` from WSL often hangs with no Hello prompt, so
    durable 1P token *writes* are best-effort. Auth success = keyring write OK.
    """
    config = load_campaign_config(campaign)
    google_api_config = config.get("google_api_client", {})

    def read_secret(key: str) -> str:
        path = google_api_config.get(key)
        if not path:
            raise ValueError(
                f"Secret path for '{key}' not found in campaign '{campaign}' config"
            )
        secret = get_op_secret(path)
        if not secret:
            raise ValueError(
                f"Could not retrieve secret from 1Password at path: {path}"
            )
        return secret

    # client_id and client_secret from 1Password (triggers Windows Hello when needed)
    client_id = read_secret("client_id_path")
    client_secret = read_secret("client_secret_path")

    oauth_token: Optional[str] = None
    refresh_token: Optional[str] = None
    source = "none"

    # Keyring first: updated by `cocli video auth` even when 1P write hangs
    keyring_mgr = KeyringManager()
    oauth_token = keyring_mgr.get_access_token(campaign)
    refresh_token = keyring_mgr.get_refresh_token(campaign)
    if oauth_token and refresh_token:
        source = "keyring"
        logger.info("Loaded OAuth tokens from keyring for campaign '%s'", campaign)

    # 1Password fallback if keyring empty
    if (not oauth_token or not refresh_token) and google_api_config.get(
        "oauth_token_path"
    ) and google_api_config.get("refresh_token_path"):
        try:
            oauth_token = read_secret("oauth_token_path")
            refresh_token = read_secret("refresh_token_path")
            if oauth_token and refresh_token:
                source = "1password"
                logger.info(
                    "Loaded OAuth tokens from 1Password for campaign '%s'", campaign
                )
        except Exception as e:
            logger.warning(
                "Could not load OAuth tokens from 1Password for '%s': %s", campaign, e
            )

    if not oauth_token or not refresh_token:
        raise ValueError(
            f"OAuth tokens not found in keyring or 1Password for campaign '{campaign}'. "
            f"Run 'cocli video auth -c {campaign}' (complete the Google device code; "
            f"keyring save is enough even if 1Password write hangs)."
        )

    logger.debug("YouTube OAuth token source for %s: %s", campaign, source)
    return client_id, client_secret, oauth_token, refresh_token



def build_credentials(
    client_id: str, client_secret: str, oauth_token: str, refresh_token: str
) -> GoogleCredentials:
    """Build Google credentials from stored tokens."""
    return GoogleCredentials(  # type: ignore
        token=oauth_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )


class YouTubeUploader:
    """YouTube video uploader."""

    def __init__(self, campaign: str = "roadmap"):
        self.campaign = campaign
        self._service: Optional[Any] = None

    @property
    def service(self) -> Any:
        """Lazy-load YouTube service."""
        if self._service is None:
            client_id, client_secret, oauth_token, refresh_token = get_secrets(
                self.campaign
            )
            credentials = build_credentials(
                client_id, client_secret, oauth_token, refresh_token
            )
            self._service = build("youtube", "v3", credentials=credentials)
        return self._service

    def upload(
        self,
        video_path: str | Path,
        title: str,
        description: str = "",
        tags: Optional[List[str]] = None,
        category_id: str = "22",
        privacy: str = "unlisted",
        playlist_id: Optional[str] = None,
        progress_callback: Optional[CallableType[[int], None]] = None,
    ) -> Optional[Dict[str, str]]:
        """Upload video to YouTube."""
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return None

        actual_tags = tags or ["automation", "roadmap"]

        # Sanitize forbidden characters '<' and '>' for YouTube API
        title = title.replace("<", "[").replace(">", "]")
        if description:
            description = description.replace("<", "less than").replace(">", "greater than")
        if actual_tags:
            actual_tags = [t.replace("<", "").replace(">", "") for t in actual_tags]

        # Fail-safe: Truncate description to 5000 characters if still too long
        if description and len(description) > 5000:
            logger.warning(
                f"Description length ({len(description)}) exceeds YouTube's 5000 character limit. Truncating..."
            )
            description = description[:4997] + "..."

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": actual_tags,
                "categoryId": category_id,
            },
            "status": {
                "privacyStatus": privacy,
                "selfDeclaredMadeForKids": False,
            },
        }

        logger.info(f"Uploading: {video_path.name}")

        insert_request = self.service.videos().insert(
            part=",".join(body.keys()),
            body=body,
            media_body=MediaFileUpload(
                str(video_path), chunksize=1024 * 1024, resumable=True
            ),
        )

        response_insert: Optional[Dict[str, Any]] = None
        while response_insert is None:
            try:
                status, response_insert = insert_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    if progress_callback:
                        progress_callback(progress)
                    else:
                        logger.info(f"Progress: {progress}%")
            except Exception as e:
                err_text = str(e)
                logger.error(f"Upload error: {e}")
                if "invalid_grant" in err_text.lower():
                    logger.error(
                        "YouTube OAuth refresh token rejected (invalid_grant). "
                        "Approve Windows Hello if prompted, then re-run: "
                        "cocli video auth -c %s  "
                        "(writes new tokens to 1Password + keyring). "
                        "If Hello already unlocked stale tokens, re-auth is still required.",
                        self.campaign,
                    )
                break

        if response_insert:
            video_id = str(response_insert["id"])
            logger.info(f"Success! Video ID: {video_id}")

            if playlist_id:
                self._add_to_playlist(video_id, playlist_id)

            return {
                "id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }

        return None

    def _add_to_playlist(self, video_id: str, playlist_id: str) -> bool:
        """Add video to a playlist."""
        try:
            self.service.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    }
                },
            ).execute()
            logger.info(f"Added video to playlist: {playlist_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add to playlist: {e}")
            return False

    def upload_thumbnail(self, video_id: str, thumbnail_path: str | Path) -> bool:
        """Upload thumbnail for an existing video."""
        thumbnail_path = Path(thumbnail_path)
        if not thumbnail_path.exists():
            logger.error(f"Thumbnail file not found: {thumbnail_path}")
            return False

        logger.info(f"Uploading thumbnail for video: {video_id}")

        try:
            self.service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path)),
            ).execute()
            logger.info("Thumbnail uploaded successfully")
            return True
        except Exception as e:
            logger.error(f"Thumbnail upload error: {e}")
            return False

    def upload_captions(
        self, video_id: str, captions_path: str | Path, language: str = "en"
    ) -> bool:
        """Upload closed captions (VTT) for a video."""
        captions_path = Path(captions_path)
        if not captions_path.exists():
            logger.error(f"Captions file not found: {captions_path}")
            return False

        logger.info(f"Uploading captions for video: {video_id}")

        try:
            self.service.captions().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "language": language,
                        "name": "English",
                    }
                },
                media_body=MediaFileUpload(str(captions_path)),
            ).execute()
            logger.info("Captions uploaded successfully")
            return True
        except Exception as e:
            logger.error(f"Captions upload error: {e}")
            return False

    def upload_for_campaign(
        self,
        video_path: str | Path,
        title: str,
        campaign: Optional[str] = None,
    ) -> Optional[Dict[str, str]]:
        """Upload with campaign-specific metadata."""
        campaign_name = campaign or self.campaign
        description = f"Uploaded via {campaign_name} automation"
        tags = [campaign_name, "automation"]
        return self.upload(video_path, title, description, tags)
