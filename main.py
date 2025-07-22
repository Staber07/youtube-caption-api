from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from youtube_transcript_api import YouTubeTranscriptApi
import uvicorn
import re
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube Caption Extractor API",
    description="FastAPI service for extracting YouTube video captions for Zapier integration",
    version="1.0.0"
)

# CORS configuration for Zapier and other cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for Zapier integration
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class VideoRequest(BaseModel):
    video_id: str

    @field_validator('video_id')
    @classmethod
    def validate_video_id(cls, v):
        # Clean the video_id if it's a full YouTube URL
        if 'youtube.com/watch?v=' in v:
            match = re.search(r'v=([a-zA-Z0-9_-]+)', v)
            if match:
                v = match.group(1)
        elif 'youtu.be/' in v:
            match = re.search(r'youtu\.be/([a-zA-Z0-9_-]+)', v)
            if match:
                v = match.group(1)

        # Validate YouTube video ID format
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', v):
            raise ValueError('Invalid YouTube video ID format')

        return v

class CaptionResponse(BaseModel):
    video_id: str
    captions: str
    language: str = "en"
    total_duration: float = 0.0

class ErrorResponse(BaseModel):
    error: str
    error_code: str
    video_id: str | None = None

@app.get("/", summary="Health Check")
async def health_check():
    return {
        "status": "healthy",
        "service": "YouTube Caption Extractor",
        "version": "1.0.0",
        "endpoints": {
            "get_captions": "/get-captions",
            "health": "/",
            "docs": "/docs"
        }
    }

@app.get("/health", summary="Alternative Health Check")
async def health():
    return {"status": "ok", "service": "youtube-caption-extractor"}

@app.post("/get-captions", 
          response_model=CaptionResponse,
          summary="Extract YouTube Video Captions",
          description="Extract captions/transcripts from a YouTube video by video ID")
async def get_captions(req: VideoRequest):
    try:
        logger.info(f"Processing request for video ID: {req.video_id}")

        try:
            transcript = YouTubeTranscriptApi.get_transcript(req.video_id)
            language = transcript[0].get("language", "en") if transcript else "en"

        except Exception as e:
            logger.error(f"No transcripts available for video {req.video_id}: {str(e)}")
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "No captions/transcripts available for this video",
                    "error_code": "NO_TRANSCRIPT_AVAILABLE",
                    "video_id": req.video_id
                }
            )

        text_segments = []
        total_duration = 0.0

        for segment in transcript:
            text_segments.append(segment["text"])
            segment_end = segment.get("start", 0.0) + segment.get("duration", 0.0)
            if segment_end > total_duration:
                total_duration = segment_end

        captions_text = " ".join(text_segments)
        captions_text = re.sub(r'\s+', ' ', captions_text).strip()

        logger.info(f"Successfully extracted captions for video {req.video_id}, length: {len(captions_text)} characters")

        return CaptionResponse(
            video_id=req.video_id,
            captions=captions_text,
            language=language,
            total_duration=total_duration
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing video {req.video_id}: {str(e)}")

        error_message = str(e).lower()
        if "video unavailable" in error_message or "video does not exist" in error_message:
            error_code = "VIDEO_NOT_FOUND"
            user_message = "Video not found or is unavailable"
            status_code = 404
        elif "private" in error_message:
            error_code = "VIDEO_PRIVATE"
            user_message = "Video is private and captions cannot be accessed"
            status_code = 403
        elif "disabled" in error_message:
            error_code = "CAPTIONS_DISABLED"
            user_message = "Captions are disabled for this video"
            status_code = 400
        else:
            error_code = "PROCESSING_ERROR"
            user_message = f"Error processing video: {str(e)}"
            status_code = 500

        raise HTTPException(
            status_code=status_code,
            detail={
                "error": user_message,
                "error_code": error_code,
                "video_id": req.video_id
            }
        )

@app.get("/video/{video_id}/captions", summary="Get Captions by URL Parameter")
async def get_captions_by_url(video_id: str):
    request = VideoRequest(video_id=video_id)
    return await get_captions(request)

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port,
        log_level="info"
    )
