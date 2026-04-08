import os
import sys
import subprocess
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# Scopes required for uploading to YouTube
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def get_secrets():
    """Fetch all secrets from 1Password."""
    client_id = subprocess.check_output(
        ["op", "read", "op::Private/Google-BizkiteLLC/client-id"], text=True
    ).strip()
    client_secret = subprocess.check_output(
        ["op", "read", "op::Private/Google-BizkiteLLC/client-secret"], text=True
    ).strip()
    oauth_token = subprocess.check_output(
        ["op", "read", "op::Private/Google-BizkiteLLC/oauth-token"], text=True
    ).strip()
    refresh_token = subprocess.check_output(
        ["op", "read", "op::Private/Google-BizkiteLLC/refresh-token"], text=True
    ).strip()
    return client_id, client_secret, oauth_token, refresh_token


def build_credentials(client_id, client_secret, oauth_token, refresh_token):
    """Build Google credentials from stored tokens."""
    return Credentials(
        token=oauth_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_uri="https://oauth2.googleapis.com/token",
    )


def get_authenticated_service():
    """Get authenticated YouTube service using 1Password secrets."""
    client_id, client_secret, oauth_token, refresh_token = get_secrets()
    credentials = build_credentials(
        client_id, client_secret, oauth_token, refresh_token
    )

    # If credentials are invalid, token refresh will happen automatically via the library
    # No file writes - tokens stay in 1Password only

    return build("youtube", "v3", credentials=credentials)


def upload_video(video_path, title, description="Uploaded via roadmap-automation"):
    youtube = get_authenticated_service()

    # NOTE: We don't write tokens to disk - they remain in 1Password

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["automation", "roadmap"],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": "unlisted",
            "selfDeclaredMadeForKids": False,
        },
    }

    insert_request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=MediaFileUpload(video_path, chunksize=1024 * 1024, resumable=True),
    )

    print(f"Uploading: {os.path.basename(video_path)}")
    response = None
    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                print(f"Progress: {int(status.progress() * 100)}%", end="\r")
        except Exception as e:
            print(f"\nUpload Error: {e}")
            break

    if response:
        print(f"\nSUCCESS! Video ID: {response['id']}")
        print(f"URL: https://www.youtube.com/watch?v={response['id']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python Upload-YouTube.py <video_path> [title]")
        sys.exit(1)

    video_path = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(video_path)
    upload_video(video_path, title)
