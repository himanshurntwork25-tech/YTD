import yt_dlp
import logging
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# -------------------- LOGGING --------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# -------------------- FASTAPI INIT --------------------

app = FastAPI(title="YouTube Downloader API", version="2.0")

# Enable CORS (required for React frontend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # change to your domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- REQUEST MODEL --------------------

class DownloadRequest(BaseModel):
    url: str
    mode: str  # audio or video


# -------------------- URL VALIDATION --------------------

# def validate_youtube_url(url: str):
#     if not url or not isinstance(url, str):
#         raise ValueError("Invalid URL")

#     url = url.strip()

#     pattern = r"(youtube\.com|youtu\.be)"
#     if not re.search(pattern, url):
#         raise ValueError("Not a valid YouTube URL")

#     return url

def validate_youtube_url(url: str):
    if not isinstance(url, str) or not url.strip():
        raise ValueError("URL must be a non-empty string")

    url = url.strip()

    if not re.search(r"(youtube\.com|youtu\.be)", url):
        raise ValueError("Not a valid YouTube URL")

    video_patterns = [
        r"(?:youtube\.com/watch\?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
    ]

    for pattern in video_patterns:
        match = re.search(pattern, url)
        if match:
            video_id = match.group(1)
            clean_url = f"https://www.youtube.com/watch?v={video_id}"
            return {
                "type": "video",
                "id": video_id,
                "clean_url": clean_url,
            }

    playlist_pattern = r"(?:youtube\.com/playlist\?list=)([A-Za-z0-9_-]+)"
    match = re.search(playlist_pattern, url)

    if match:
        playlist_id = match.group(1)
        clean_url = f"https://www.youtube.com/playlist?list={playlist_id}"
        return {
            "type": "playlist",
            "id": playlist_id,
            "clean_url": clean_url,
        }

    raise ValueError("Invalid YouTube URL format")


# -------------------- EXTRACT DOWNLOAD LINK --------------------

def extract_download_link(url: str, mode: str):

    try:
        validated_url = validate_youtube_url(url)
        url = validated_url["clean_url"]

        logger.info(f"Extracting link for: {url} | mode: {mode}")

        if mode == "audio":
            ydl_opts = {
                "quiet": True,
                "noplaylist": True,
                "format": "bestaudio/best",
                "extract_flat": False,
                "skip_download": True,
            }

        elif mode == "video":
            ydl_opts = {
                "quiet": True,
                "noplaylist": True,
                "format": "best[ext=mp4]/best",
                "extract_flat": False,
                "skip_download": True,
            }

        else:
            raise ValueError("Mode must be 'audio' or 'video'")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(url, download=False)

            if "entries" in info:
                info = info["entries"][0]

            download_url = info.get("url")
            title = info.get("title", "video")

            if not download_url:
                raise RuntimeError("Could not extract download URL")

            logger.info("Extraction successful")

            return {
                "title": title,
                "download_url": download_url
            }

    except Exception as e:
        logger.exception("Extraction failed")
        raise RuntimeError(str(e))


# -------------------- API ENDPOINT --------------------

@app.post("/download")
def download_endpoint(request: DownloadRequest):

    try:

        result = extract_download_link(
            url=request.url,
            mode=request.mode.lower()
        )

        return {
            "status": "success",
            "title": result["title"],
            "download_url": result["download_url"]
        }

    except ValueError as e:

        raise HTTPException(
            status_code=400,
            detail=str(e)
        )

    except RuntimeError as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


# -------------------- HEALTH CHECK --------------------

@app.get("/")
def root():
    return {
        "status": "API is running"
    }
