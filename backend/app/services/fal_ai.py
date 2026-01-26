import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fal_client
import httpx

from app.core.config import get_settings

settings = get_settings()

# Shared thread pool for fal.ai operations
_fal_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="fal_ai_")


class FalAIService:
    """fal.ai service for video generation using Kling 2.1."""

    # Model options - from fastest/cheapest to highest quality
    MODELS = {
        "turbo": "fal-ai/kling-video/v2.5-turbo/pro/image-to-video",
        "pro": "fal-ai/kling-video/v2.1/pro/image-to-video",
        "master": "fal-ai/kling-video/v2.1/master/image-to-video",
    }

    def __init__(self):
        if settings.fal_key:
            fal_client.api_key = settings.fal_key
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create a shared HTTP client for downloads."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(300.0),  # 5 min timeout for video downloads
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            )
        return self._http_client

    async def generate_video(
        self,
        image_path: Path,
        prompt: str,
        duration: float = 5.0,
        model: str = "pro",
    ) -> bytes:
        """
        Generate a video from an image using Kling 2.1.

        Args:
            image_path: Path to the source image
            prompt: Animation prompt describing the movement
            duration: Video duration in seconds (default 5)
            model: Model quality tier - "turbo", "pro", or "master"

        Returns:
            Video content as bytes
        """
        # Read image in thread pool to avoid blocking
        loop = asyncio.get_running_loop()

        def read_image():
            with open(image_path, "rb") as f:
                return f.read()

        image_data = await loop.run_in_executor(_fal_executor, read_image)

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

        # Get model endpoint
        model_id = self.MODELS.get(model, self.MODELS["pro"])
        print(f"Using Kling model: {model_id}")

        # Submit to fal.ai in thread pool
        def submit_job():
            return fal_client.subscribe(
                model_id,
                arguments={
                    "prompt": prompt,
                    "image_url": image_url,
                    "duration": "5" if duration <= 5 else "10",
                    "aspect_ratio": "16:9",
                },
                with_logs=True,
            )

        result = await loop.run_in_executor(_fal_executor, submit_job)

        print(f"Kling response: {result}")

        # Download the video
        video_url = result.get("video", {}).get("url")
        if not video_url:
            raise RuntimeError(f"No video URL in response: {result}")

        client = await self._get_http_client()
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

    async def check_status(self, request_id: str, model: str = "pro") -> dict:
        """Check the status of a video generation request."""
        model_id = self.MODELS.get(model, self.MODELS["pro"])

        def get_status():
            return fal_client.status(model_id, request_id)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_fal_executor, get_status)

    async def close(self):
        """Clean up resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


fal_ai_service = FalAIService()
