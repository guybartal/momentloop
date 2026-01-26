import asyncio
import base64
import uuid
from pathlib import Path

import fal_client
import httpx

from app.core.config import get_settings

settings = get_settings()


class FalAIService:
    """fal.ai service for video generation using Kling 2.0."""

    def __init__(self):
        if settings.fal_key:
            fal_client.api_key = settings.fal_key

    async def generate_video(
        self,
        image_path: Path,
        prompt: str,
        duration: float = 5.0,
    ) -> bytes:
        """
        Generate a video from an image using Kling 2.0.

        Args:
            image_path: Path to the source image
            prompt: Animation prompt describing the movement
            duration: Video duration in seconds (default 5)

        Returns:
            Video content as bytes
        """
        # Read image and convert to base64 data URL
        with open(image_path, "rb") as f:
            image_data = f.read()

        # Determine image type
        ext = image_path.suffix.lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "image/jpeg")

        image_base64 = base64.b64encode(image_data).decode()
        image_url = f"data:{mime_type};base64,{image_base64}"

        # Submit to fal.ai
        # Using Kling 2.0 for image-to-video generation
        def submit_job():
            return fal_client.subscribe(
                "fal-ai/kling-video/v1.6/pro/image-to-video",
                arguments={
                    "prompt": prompt,
                    "image_url": image_url,
                    "duration": str(int(duration)),  # "5" or "10"
                    "aspect_ratio": "16:9",
                },
                with_logs=True,
            )

        # Run in thread pool since fal_client is synchronous
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, submit_job)

        # Download the video
        video_url = result.get("video", {}).get("url")
        if not video_url:
            raise RuntimeError("No video URL in response")

        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to download video: {response.status_code}")
            return response.content

    async def generate_transition(
        self,
        start_image_path: Path,
        end_image_path: Path,
        prompt: str | None = None,
        duration: float = 3.0,
    ) -> bytes:
        """
        Generate a transition video between two images.

        Args:
            start_image_path: Path to the starting frame
            end_image_path: Path to the ending frame
            prompt: Optional transition prompt
            duration: Transition duration in seconds

        Returns:
            Video content as bytes
        """
        # For transitions, we use the start image with a prompt describing the transition
        if not prompt:
            prompt = "Smooth cinematic transition, camera movement, seamless morph to next scene"

        # Use the start image to generate a transition
        return await self.generate_video(
            start_image_path,
            prompt,
            duration=duration,
        )

    async def check_status(self, request_id: str) -> dict:
        """Check the status of a video generation request."""

        def get_status():
            return fal_client.status("fal-ai/kling-video/v1.6/pro/image-to-video", request_id)

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, get_status)


fal_ai_service = FalAIService()
