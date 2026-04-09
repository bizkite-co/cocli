"""YouTube uploader using 1Password for credentials."""

import subprocess
import logging
from pathlib import Path
from typing import Optional
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

from cocli.core.config import load_campaign_config
from cocli.utils.op_utils import get_op_secret

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_secrets(campaign: str) -> tuple[str, str, str, str]:
    """Fetch all secrets from 1Password paths defined in campaign config."""
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

    client_id = read_secret("client_id_path")
    client_secret = read_secret("client_secret_path")
    oauth_token = read_secret("oauth_token_path")
    refresh_token = read_secret("refresh_token_path")
    return client_id, client_secret, oauth_token, refresh_token


def build_credentials(
    client_id: str, client_secret: str, oauth_token: str, refresh_token: str
) -> Credentials:
    """Build Google credentials from stored tokens."""
    return Credentials(
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
        self._service: Optional[object] = None

    @property
    def service(self):
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
        tags: list[str] = None,
        category_id: str = "22",  # People & Blogs
        privacy: str = "unlisted",
    ) -> Optional[dict]:
        """Upload video to YouTube."""
        video_path = Path(video_path)
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return None

        tags = tags or ["automation", "roadmap"]

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "tags": tags,
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
                video_path, chunksize=1024 * 1024, resumable=True
            ),
        )

        response = None
        while response is None:
            try:
                status, response_insert = insert_request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    logger.info(f"Progress: {progress}%")
            except Exception as e:
                logger.error(f"Upload error: {e}")
                break

        if response_insert:
            video_id = response_insert["id"]
            logger.info(f"Success! Video ID: {video_id}")
            return {
                "id": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }

        return None

    def upload_for_campaign(
        self,
        video_path: str | Path,
        title: str,
        campaign: str = None,
    ) -> Optional[dict]:
        """Upload with campaign-specific metadata."""
        campaign = campaign or self.campaign
        description = f"Uploaded via {campaign} automation"
        tags = [campaign, "automation"]
        return self.upload(video_path, title, description, tags)
