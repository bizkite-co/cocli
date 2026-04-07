import os
import sys
import subprocess
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

# Scopes required for uploading to YouTube
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']
TOKEN_PATH = os.path.join(os.path.expanduser("~"), ".config", "video-automation", "token.json")

def get_authenticated_service(client_id, client_secret):
    credentials = None
    
    # Ensure config directory exists
    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    
    if os.path.exists(TOKEN_PATH):
        credentials = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    
    if not credentials or not credentials.valid:
        client_config = {
            "web": { # Using 'web' since the ID is a Web Client
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        # We MUST use port 8080 as it's the standard whitelist port for Web Clients on localhost
        print("--- Opening Browser for Authentication ---")
        credentials = flow.run_local_server(host='localhost', port=8080, prompt='select_account')
        with open(TOKEN_PATH, 'w') as token:
            token.write(credentials.to_json())
            
    return build('youtube', 'v3', credentials=credentials)

def upload_video(video_path, title, description="Uploaded via roadmap-automation"):
    try:
        cid = "1014926302266-fu7mk8jehcbg7ablinva67bh0aenlns3.apps.googleusercontent.com"
        # Using the path you confirmed
        secret = subprocess.check_output(["op", "read", "op://Private/Google-BizkiteLLC/client-secret"], text=True).strip()
    except Exception as e:
        print(f"Error fetching secrets: {e}")
        return

    youtube = get_authenticated_service(cid, secret)

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': ['automation', 'roadmap'],
            'categoryId': '22'
        },
        'status': {
            'privacyStatus': 'unlisted',
            'selfDeclaredMadeForKids': False,
        }
    }

    insert_request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=MediaFileUpload(video_path, chunksize=1024*1024, resumable=True)
    )

    print(f"Uploading: {os.path.basename(video_path)}")
    response = None
    while response is None:
        try:
            status, response = insert_request.next_chunk()
            if status:
                print(f"Progress: {int(status.progress() * 100)}%", end='\r')
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
    
    try:
        video_path = sys.argv[1]
        title = sys.argv[2] if len(sys.argv) > 2 else os.path.basename(video_path)
        upload_video(video_path, title)
    except KeyboardInterrupt:
        print("\n\nCancelled by user. Exiting...")
        sys.exit(0)
