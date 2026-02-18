import asyncio
import base64
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import fal_client
import httpx
from PIL import Image

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

STYLE_PROMPTS = {
    "ghibli": "Restyle this image with Studio Ghibli style.",
    "lego": "Restyle this image with LEGO style.",
    "minecraft": "Restyle this image with Minecraft style.",
    "simpsons": "Restyle this image with The Simpsons style.",
}

# Shared thread pool for image operations
_image_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="imagen_")


class ImagenService:
    """fal.ai Nano Banana Pro service for image style transfer."""

    MODEL_ID = "fal-ai/nano-banana-pro/edit"

    def __init__(self):
        if settings.fal_key:
            fal_client.api_key = settings.fal_key
        self._http_client: httpx.AsyncClient | None = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create a shared HTTP client for downloads."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
        return self._http_client

    async def apply_style(
        self, image_path: Path, style: str, custom_prompt: str | None = None
    ) -> bytes:
        """
        Apply a style to an image using fal.ai Nano Banana Pro.
        Returns the styled image as bytes.

        Args:
            image_path: Path to the source image
            style: Style key (ghibli, lego, minecraft, simpsons)
            custom_prompt: Optional custom prompt to use instead of the default
        """
        if style not in STYLE_PROMPTS:
            raise ValueError(f"Unknown style: {style}. Available: {list(STYLE_PROMPTS.keys())}")

        if not settings.fal_key:
            raise RuntimeError("FAL_KEY not configured")

        # Use custom prompt if provided, otherwise use default
        prompt = custom_prompt if custom_prompt else STYLE_PROMPTS[style]

        loop = asyncio.get_running_loop()

        # Read and prepare image
        def prepare_image():
            with Image.open(image_path) as img:
                # Convert to RGB if necessary
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                # Resize if too large (max 1920x1080)
                max_size = (1920, 1080)
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Get original dimensions for aspect ratio
                width, height = img.size

                # Save to buffer
                from io import BytesIO
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=95)
                return buffer.getvalue(), width, height

        image_data, width, height = await loop.run_in_executor(_image_executor, prepare_image)

        # Convert to base64 data URL
        image_base64 = base64.b64encode(image_data).decode()
        image_url = f"data:image/jpeg;base64,{image_base64}"

        logger.info("Sending image to fal.ai Nano Banana Pro for %s style transfer", style)
        logger.info("Prompt: %s", prompt)
        logger.info("Image size: %dx%d, %d bytes", width, height, len(image_data))

        # Submit to fal.ai
        def run_job():
            handle = fal_client.submit(
                self.MODEL_ID,
                arguments={
                    "prompt": prompt,
                    "image_urls": [image_url],
                },
            )
            return handle.get()

        result = await loop.run_in_executor(_image_executor, run_job)

        logger.info("Nano Banana Pro response received")

        # Get the image URL from response
        images = result.get("images", [])
        if not images:
            raise RuntimeError(f"No images in response: {result}")

        image_result_url = images[0].get("url")
        if not image_result_url:
            raise RuntimeError(f"No image URL in response: {result}")

        # Download the styled image
        client = await self._get_http_client()
        response = await client.get(image_result_url)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to download styled image: {response.status_code}")

        logger.info("Downloaded styled image: %d bytes", len(response.content))
        return response.content

    async def close(self):
        """Clean up resources."""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None


imagen_service = ImagenService()
