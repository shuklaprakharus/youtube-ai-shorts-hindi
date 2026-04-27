"""
youtube.py
==========
Uploads a video to YouTube using the Data API v3.

Authentication flow (one-time setup):
  Run `python setup_auth.py` on your local machine once.
  It opens a browser, you log in, and it prints a JSON credentials blob.
  Paste that blob as a GitHub Secret named YOUTUBE_CREDENTIALS.

Every subsequent automated run uses the stored refresh_token — no browser needed.
"""

import os
import json
from config import YOUTUBE_CATEGORY_ID, YOUTUBE_PRIVACY

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


# ─────────────────────────────────────────────────────────────────────────────
def _get_client():
    """Build an authenticated YouTube API client from the stored credentials."""
    raw = os.environ.get("YOUTUBE_CREDENTIALS")
    if not raw:
        raise EnvironmentError(
            "YOUTUBE_CREDENTIALS secret is not set. "
            "Run setup_auth.py once locally and save the output as a GitHub Secret."
        )

    data = json.loads(raw)

    creds = Credentials(
        token         = data.get("token"),
        refresh_token = data.get("refresh_token"),
        token_uri     = data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id     = data.get("client_id"),
        client_secret = data.get("client_secret"),
        scopes        = data.get("scopes", ["https://www.googleapis.com/auth/youtube.upload"]),
    )

    # Auto-refresh if the access token has expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("youtube", "v3", credentials=creds, cache_discovery=False)


# ─────────────────────────────────────────────────────────────────────────────
def upload_to_youtube(video_file: str,
                      title:      str,
                      description: str,
                      tags:       list[str]) -> str:
    """
    Upload video_file to YouTube.
    Returns the public URL (Shorts format).
    """
    youtube = _get_client()

    # Append hashtags to description so YouTube surfaces it as a Short
    hashtag_str = " ".join(
        f"#{t.replace(' ', '').replace('#', '')}" for t in tags[:8]
    )
    full_desc = (
        f"{description}\n\n"
        f"{hashtag_str}\n\n"
        "#Shorts #AI #AIForBeginners #ArtificialIntelligence #ChatGPT"
    )

    body = {
        "snippet": {
            "title":           title[:100],        # YouTube 100-char limit
            "description":     full_desc[:5000],   # YouTube 5000-char limit
            "tags":            tags[:500],
            "categoryId":      YOUTUBE_CATEGORY_ID,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus":           YOUTUBE_PRIVACY,
            "selfDeclaredMadeForKids": False,
            "madeForKids":             False,
        },
    }

    media = MediaFileUpload(
        video_file,
        mimetype   = "video/mp4",
        resumable  = True,
        chunksize  = 512 * 1024,   # 512 KB chunks
    )

    request  = youtube.videos().insert(
        part       = ",".join(body.keys()),
        body       = body,
        media_body = media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"     · Upload progress: {pct}%")

    video_id = response["id"]
    url      = f"https://youtube.com/shorts/{video_id}"
    print(f"     → Published: {url}")
    return url
