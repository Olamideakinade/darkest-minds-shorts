"""Script to unlist a YouTube video by ID."""
import json
import sys
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import config
from app.youtube.channel_manager import YOUTUBE_SCOPES
from app.utils.logger import logger

def unlist_video(video_id: str):
    token_file = config.youtube_token_file
    if not token_file.exists():
        print(f"Error: token file {token_file} does not exist.")
        return False

    with open(token_file, "r", encoding="utf-8") as f:
        token_info = json.load(f)

    creds = Credentials.from_authorized_user_info(token_info, scopes=YOUTUBE_SCOPES)
    service = build("youtube", "v3", credentials=creds)

    print(f"Updating video {video_id} status to 'unlisted'...")
    request = service.videos().update(
        part="status",
        body={
            "id": video_id,
            "status": {
                "privacyStatus": "unlisted"
            }
        }
    )
    response = request.execute()
    new_status = response.get("status", {}).get("privacyStatus")
    print(f"Video {video_id} status is now: {new_status}")
    return new_status == "unlisted"

if __name__ == "__main__":
    vid = sys.argv[1] if len(sys.argv) > 1 else "5S0VXtmi7bQ"
    unlist_video(vid)
