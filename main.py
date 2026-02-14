import yt_dlp
import os
import platform
import re
from pathlib import Path
import time
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# if os.getenv("DEPLOYMENT") == "server":
#     FFMPEG_PATH = "ffmpeg"
# elif platform.system() == "Windows":
#     FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg", "ffmpeg.exe")
# else:
#     FFMPEG_PATH = os.path.join(BASE_DIR, "ffmpeg", "ffmpeg")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_ffmpeg_path():
    # 1. Check if system ffmpeg exists (Linux, Mac, Windows with PATH)
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    # 2. Check local bundled ffmpeg
    if platform.system() == "Windows":
        local_ffmpeg = os.path.join(BASE_DIR, "ffmpeg", "ffmpeg.exe")
    else:
        local_ffmpeg = os.path.join(BASE_DIR, "ffmpeg", "ffmpeg")

    if os.path.exists(local_ffmpeg):
        return local_ffmpeg

    # 3. If not found, raise error
    raise RuntimeError(
        "FFmpeg not found. Please install ffmpeg or place it in ffmpeg folder."
    )

FFMPEG_PATH = get_ffmpeg_path()

app = FastAPI(title="YouTube Downloader API")

# -------------------- CORS MIDDLEWARE --------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # development only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------------------------------------

class DownloadRequest(BaseModel):
    url: str
    mode: str  # "video", "audio", or "both"


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


# def get_downloads_folder():
#     downloads_path = Path.home() / "Downloads"
#     return str(downloads_path)
# def get_downloads_folder():
#     downloads_path = os.path.join(BASE_DIR, "downloads")
#     os.makedirs(downloads_path, exist_ok=True)
#     return downloads_path
def get_downloads_folder():
    if platform.system() == "Windows":
        return str(Path.home() / "Downloads")
    else:
        downloads_path = os.path.join(BASE_DIR, "downloads")
        os.makedirs(downloads_path, exist_ok=True)
        return downloads_path




def download_video(url, output_path=None, max_retries=3):
    if output_path is None:
        output_path = get_downloads_folder()

    try:
        validated_url = validate_youtube_url(url)
        url = validated_url["clean_url"]
        logger.info(f"Downloading video: {validated_url['id']} ({validated_url['type']})")
        logger.info(f"Output path: {output_path}")
    except ValueError as e:
        logger.error(f"URL Validation Error: {e}")
        raise
    except Exception:
        logger.exception("Unexpected validation error")
        raise

    os.makedirs(output_path, exist_ok=True)

    # ydl_opts = {
    #     "format": "bestvideo+bestaudio/best",
    #     "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
    #     "merge_output_format": "mp4",
    #     "ffmpeg_location": FFMPEG_PATH,
    #     "restrictfilenames": True,
    #     "quiet": True,
    #     "retries": max_retries,
    #     "fragment_retries": max_retries,
    #     "skip_unavailable_fragments": True,
    #     "cookiefile": os.path.join(BASE_DIR, "cookies.txt"),
    #     "extractor_args": {
    #         "youtube": {
    #             "player_client": ["android", "web"]
    #         }
    #     }
    # }
    ydl_opts = {
        "format": "bestvideo+bestaudio/best",
        "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
        "merge_output_format": "mp4",
        "ffmpeg_location": FFMPEG_PATH,

        "restrictfilenames": True,
        "quiet": True,
        "retries": max_retries,
        "fragment_retries": max_retries,
        "skip_unavailable_fragments": True,

        "cookiefile": os.path.join(BASE_DIR, "cookies.txt"),

        "nocheckcertificate": True,
        "geo_bypass": True,
        "geo_bypass_country": "US",

        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        },

        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        }
    }



    for attempt in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info("Video download completed")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Video download attempt {attempt + 1} failed: {e}")
                logger.info(f"Retrying... ({attempt + 2}/{max_retries})")
                time.sleep(2)
            else:
                logger.error(f"Video Error after {max_retries} attempts: {e}")
                raise RuntimeError("Video download failed after retries")


def download_audio(url, output_path=None, max_retries=3):
    if output_path is None:
        output_path = get_downloads_folder()

    try:
        validated_url = validate_youtube_url(url)
        url = validated_url["clean_url"]
        logger.info(f"Downloading audio: {validated_url['id']} ({validated_url['type']})")
        logger.info(f"Output path: {output_path}")
    except ValueError as e:
        logger.error(f"URL Validation Error: {e}")
        raise
    except Exception:
        logger.exception("Unexpected validation error")
        raise

    os.makedirs(output_path, exist_ok=True)

    # ydl_opts = {
    #     "format": "bestaudio/best",
    #     "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
    #     "ffmpeg_location": FFMPEG_PATH,
    #     "restrictfilenames": True,
    #     "postprocessors": [
    #         {
    #             "key": "FFmpegExtractAudio",
    #             "preferredcodec": "mp3",
    #             "preferredquality": "192",
    #         }
    #     ],
    #     "quiet": True,
    #     "retries": max_retries,
    #     "fragment_retries": max_retries,
    #     "skip_unavailable_fragments": True,
    #     "cookiefile": os.path.join(BASE_DIR, "cookies.txt"),
    #     "extractor_args": {
    #         "youtube": {
    #             "player_client": ["android", "web"]
    #         }
    #     }
    # }
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
        "ffmpeg_location": FFMPEG_PATH,

        "restrictfilenames": True,
        "quiet": True,
        "retries": max_retries,
        "fragment_retries": max_retries,
        "skip_unavailable_fragments": True,

        "cookiefile": os.path.join(BASE_DIR, "cookies.txt"),

        "nocheckcertificate": True,
        "geo_bypass": True,
        "geo_bypass_country": "US",

        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
        },

        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],

        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"]
            }
        }
    }


    for attempt in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info("Audio download completed")
            return
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Audio download attempt {attempt + 1} failed: {e}")
                logger.info(f"Retrying... ({attempt + 2}/{max_retries})")
                time.sleep(2)
            else:
                logger.error(f"Audio Error after {max_retries} attempts: {e}")
                raise RuntimeError("Audio download failed after retries")


@app.post("/download")
def download_endpoint(request: DownloadRequest):
    mode = request.mode.lower()

    if mode not in ["video", "audio", "both"]:
        raise HTTPException(
            status_code=400,
            detail="Mode must be 'video', 'audio', or 'both'"
        )

    try:
        if mode == "video":
            download_video(request.url)
        elif mode == "audio":
            download_audio(request.url)
        elif mode == "both":
            download_video(request.url)
            download_audio(request.url)

        return {
            "status": "success",
            "mode": mode,
            "message": "Download completed"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception("Download failed")
        raise HTTPException(status_code=500, detail=str(e))

    

# if __name__ == "__main__":
#     video_url_list = [
#         "https://www.youtube.com/watch?v=2vdZTS3DZ4Q",
#         "https://www.youtube.com/shorts/gGy-JDcOwlI",
#         "https://youtu.be/olUDirBTsTY?si=wFOfpuVUXUDZiese",
#         "https://youtu.be/1BTxxJr8awQ?si=_czzb0dprh3V5L-h"
#     ]

#     for url in video_url_list:
#         download_video(url)
#         download_audio(url)