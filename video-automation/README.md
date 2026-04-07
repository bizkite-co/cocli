# Video Automation Suite: Normalize & Publish

This suite automates the process of normalizing video audio to YouTube standards (-14 LUFS), compressing the file for web optimization, and uploading it to a specific YouTube channel using OAuth 2.0 and 1Password.

## ?? File Structure

| Path | Type | Description |
| :--- | :--- | :--- |
| ~\.config\powershell\bin\Publish-Video.ps1 | **PowerShell** | The master orchestrator. Chains normalization and upload. |
| ~\.config\powershell\bin\Normalize-Video.py| **Python** | Video processor. Uses FFmpeg for audio leveling and H.264 compression. |
| ~\.config\powershell\bin\Upload-YouTube.py | **Python** | The uploader. Uses YouTube Data API v3 and 1Password secrets. |
| ~\.config\video-automation\profiles\*.json | **JSON** | Profiles defining specific accounts and 1Password secret paths. |
| ~\.config\video-automation\token.json      | **JSON** | Cached OAuth 2.0 token (Created after first successful login). |

## ?? Configuration

### 1. Google Cloud Project Setup
To recreate this in another account:
1. **Enable API:** Enable the **YouTube Data API v3** in the Google Cloud Console.
2. **OAuth Consent Screen:**
   - Set User Type to **External**.
   - Add your email (e.g., izkitellc@gmail.com) as a **Test User** (Mandatory for unverified apps using sensitive scopes).
3. **Credentials:**
   - Create an **OAuth 2.0 Client ID**.
   - **Type:** Select **Desktop app** (This avoids "redirect_uri_mismatch" and "App Blocked" errors common with Web apps).
   - Download the Client ID and Client Secret.

### 2. Profile Creation
Profiles are stored in ~\.config\video-automation\profiles\.
Example (oadmap.json):
`json
{
    "name": "roadmap",
    "youtube_user": "bizkitellc@gmail.com",
    "youtube_pass_op": "op://Private/Google-BizkiteLLC/client-secret"
}
`

## ?? Linux / WSL / Bash Migration

To move this to a Linux environment:
1. **Dependencies:** Install FFmpeg and the Python libraries:
   pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
2. **Path Mapping:** Update the Publish-Video script (Bash version) to point to your Linux home directory (e.g., ~/.config/powershell/bin/...).
3. **1Password:** Install the op CLI on Linux. In WSL, ensure "Integrate with 1Password CLI" is enabled in the 1Password Windows app settings to allow Windows Hello prompts from the Linux terminal.
4. **Orchestrator:** Replace the .ps1 logic with a simple Bash script:
   `ash
   #!/bin/bash
   # Normalize (returns new path)
   norm_path=
   # Upload
   python3 Upload-YouTube.py "" ""
   `

## ?? Troubleshooting
- **401 Unauthorized (youtubeSignupRequired):** The Google account does not have a YouTube channel created. Visit [youtube.com/create_channel](https://www.youtube.com/create_channel) while logged in.
- **Access Blocked:** Ensure your email is added to the "Test Users" list on the OAuth Consent Screen in Google Cloud Console.
- **Redirect URI Mismatch:** Ensure you are using a **Desktop app** Client ID. Web Client IDs require explicit port whitelisting (e.g., http://localhost:8080/).
