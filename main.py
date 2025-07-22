from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, validator
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

# ----------- Data Models -----------

class VideoRequest(BaseModel):
    video_id: str

    @validator('video_id')
    def validate_video_id(cls, v):
        # Clean and extract video ID if it's a URL
        if 'youtube.com/watch?v=' in v:
            match = re.search(r'v=([a-zA-Z0-9_-]{11})', v)
            if match:
                v = match.group(1)
        elif 'youtu.be/' in v:
            match = re.search(r'youtu\.be/([a-zA-Z0-9_-]{11})', v)
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

# ----------- Endpoints -----------

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

@app.post("/get-captions", response_model=CaptionResponse)
async def get_captions(req: VideoRequest):
    try:
        logger.info(f"Processing request for video ID: {req.video_id}")

        # Try to fetch transcript using standard method
        transcript = YouTubeTranscriptApi.get_transcript(req.video_id)

        # Process text and calculate duration
        text_segments = []
        total_duration = 0.0

        for segment in transcript:
            text_segments.append(segment["text"])
            if "start" in segment and "duration" in segment:
                segment_end = segment["start"] + segment["duration"]
                if segment_end > total_duration:
                    total_duration = segment_end

        captions_text = re.sub(r'\s+', ' ', " ".join(text_segments)).strip()
        logger.info(f"Extracted {len(captions_text)} characters of transcript")

        return CaptionResponse(
            video_id=req.video_id,
            captions=captions_text,
            language="en",  # Most transcripts are in English, or you can detect from API
            total_duration=total_duration
        )

    except Exception as e:
        logger.error(f"Error processing video {req.video_id}: {str(e)}")

        error_message = str(e).lower()
        if "video unavailable" in error_message or "does not exist" in error_message:
            raise HTTPException(status_code=404, detail={
                "error": "Video not found or is unavailable",
                "error_code": "VIDEO_NOT_FOUND",
                "video_id": req.video_id
            })
        elif "private" in error_message:
            raise HTTPException(status_code=403, detail={
                "error": "Video is private and captions cannot be accessed",
                "error_code": "VIDEO_PRIVATE",
                "video_id": req.video_id
            })
        elif "not available" in error_message:
            raise HTTPException(status_code=400, detail={
                "error": "Captions are disabled for this video",
                "error_code": "CAPTIONS_DISABLED",
                "video_id": req.video_id
            })
        else:
            raise HTTPException(status_code=500, detail={
                "error": f"Error processing video: {str(e)}",
                "error_code": "PROCESSING_ERROR",
                "video_id": req.video_id
            })

@app.get("/video/{video_id}/captions", response_model=CaptionResponse)
async def get_captions_by_url(video_id: str):
    """Alternative GET endpoint for Zapier compatibility"""
    request = VideoRequest(video_id=video_id)
    return await get_captions(request)

# ----------- Run Locally (optional) -----------

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")
