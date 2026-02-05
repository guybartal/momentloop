import asyncio
import base64
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fal_client
import httpx
from PIL import Image
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings

logger = logging.getLogger(__name__)
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
        "v2.6": "fal-ai/kling-video/v2.6/pro/image-to-video",  # Supports end_image_url for transitions
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
        logger.info("Using Kling model: %s", model_id)
        logger.info("Sending prompt to fal.ai: %s", prompt)
        logger.info("Image path: %s, Image size: %d bytes", image_path, len(image_data))

        # Submit to fal.ai and wait for result
        def run_job():
            # Use submit + get for synchronous execution with polling
            handle = fal_client.submit(
                model_id,
                arguments={
                    "prompt": prompt,
                    "image_url": image_url,
                    "duration": "5" if duration <= 5 else "10",
                    "aspect_ratio": "16:9",
                },
            )
            # Poll for result (this blocks until complete)
            return handle.get()

        result = await loop.run_in_executor(_fal_executor, run_job)

        logger.info("Kling response received")

        # Download the video
        video_url = result.get("video", {}).get("url")
        if not video_url:
            raise RuntimeError(f"No video URL in response: {result}")

        client = await self._get_http_client()
        response = await self._download_with_retry(client, video_url)
        return response.content

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
        reraise=True,
    )
    async def _download_with_retry(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        """Download video with retry logic."""
        response = await client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download video: {response.status_code}")
        return response

    async def generate_transition(
        self,
        start_image_path: Path,
        end_image_path: Path,
        prompt: str | None = None,
        duration: float = 5.0,
    ) -> bytes:
        """
        Generate a transition video between two images using Kling 2.6.

        Uses start_image_url + end_image_url for smooth AI-generated morphs.

        Args:
            start_image_path: Path to the starting frame
            end_image_path: Path to the ending frame
            prompt: Optional transition prompt
            duration: Transition duration in seconds (5 or 10 for Kling 2.6)

        Returns:
            Video content as bytes
        """
        if not prompt:
            prompt = "Smooth cinematic transition, camera movement, seamless morph to next scene"

        loop = asyncio.get_running_loop()

        # Read and compress images to reduce size (max 1920x1080, JPEG quality 85)
        def read_and_compress_images():
            def compress_image(path: Path) -> bytes:
                with Image.open(path) as img:
                    # Convert to RGB if necessary (for PNG with alpha)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")

                    # Resize if too large (max 1920x1080 while maintaining aspect ratio)
                    max_size = (1920, 1080)
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)

                    # Save as JPEG with good quality
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=85, optimize=True)
                    return buffer.getvalue()

            start_data = compress_image(start_image_path)
            end_data = compress_image(end_image_path)
            return start_data, end_data

        start_data, end_data = await loop.run_in_executor(_fal_executor, read_and_compress_images)

        # Use JPEG mime type since we compressed to JPEG
        start_base64 = base64.b64encode(start_data).decode()
        end_base64 = base64.b64encode(end_data).decode()

        start_url = f"data:image/jpeg;base64,{start_base64}"
        end_url = f"data:image/jpeg;base64,{end_base64}"

        # Use Kling 2.6 which supports end_image_url
        model_id = self.MODELS["v2.6"]
        logger.info("Generating transition with Kling 2.6: %s", model_id)
        logger.info("Transition prompt: %s", prompt)
        logger.info(
            "Start image: %s (%d bytes), End image: %s (%d bytes)",
            start_image_path,
            len(start_data),
            end_image_path,
            len(end_data),
        )

        # Submit to fal.ai with both start and end images
        def run_job():
            handle = fal_client.submit(
                model_id,
                arguments={
                    "prompt": prompt,
                    "start_image_url": start_url,
                    "end_image_url": end_url,
                    "duration": "5" if duration <= 5 else "10",
                    "negative_prompt": "blur, distort, and low quality",
                    "generate_audio": False,
                },
            )
            try:
                return handle.get()
            except Exception as e:
                # Log the full error details for debugging
                logger.error("Transition API error: %s", e)
                if hasattr(e, "response"):
                    logger.error(
                        "Response body: %s",
                        e.response.text if hasattr(e.response, "text") else e.response,
                    )
                raise

        result = await loop.run_in_executor(_fal_executor, run_job)

        logger.info("Transition video response received")

        # Download the video
        video_url = result.get("video", {}).get("url")
        if not video_url:
            raise RuntimeError(f"No video URL in response: {result}")

        client = await self._get_http_client()
        response = await self._download_with_retry(client, video_url)
        return response.content

    async def check_status(self, request_id: str, model: str = "pro") -> dict:
        """Check the status of a video generation request."""
        # Note: With the new fal_client API, we use submit().get() which blocks
        # until completion, so this method is less useful. Kept for compatibility.
        return {"status": "unknown"}

    async def close(self):
        """Clean up resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()


fal_ai_service = FalAIService()
