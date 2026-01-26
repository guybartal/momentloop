import asyncio
import base64
import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from google import genai
from google.genai import types
from PIL import Image

from app.core.config import get_settings

settings = get_settings()

STYLE_PROMPTS = {
    "ghibli": "Transform this photo into Studio Ghibli anime style with soft watercolor colors, dreamy atmosphere, and the distinctive artistic style of Hayao Miyazaki's films. Keep the main subjects recognizable but render them in beautiful anime style with hand-painted textures.",
    "lego": "Transform this photo into LEGO brick style. Make everything look like it's built from LEGO bricks with blocky, pixelated characters. Use vibrant primary colors typical of LEGO sets.",
    "minecraft": "Transform this photo into Minecraft pixel art style with cubic, blocky forms. Everything should look like it's made of Minecraft blocks with the characteristic pixelated 8-bit texture.",
    "simpsons": "Transform this photo into The Simpsons cartoon style with yellow skin tones, overbite expressions, and the distinctive 2D animation style of the TV show. Characters should have 4 fingers and the exaggerated features of Simpsons characters.",
}

# Shared thread pool for CPU-bound image operations
_image_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="imagen_")

# Shared HTTP client for API calls
_http_client: httpx.AsyncClient | None = None


async def _get_http_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client."""
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _http_client


class ImagenService:
    """Google Gemini service for image style transfer."""

    def __init__(self):
        self.client = None
        self.api_key = settings.google_ai_api_key
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    async def apply_style(self, image_path: Path, style: str) -> bytes:
        """
        Apply a style to an image using Google's Gemini with image generation.
        Returns the styled image as bytes.
        """
        if style not in STYLE_PROMPTS:
            raise ValueError(f"Unknown style: {style}. Available: {list(STYLE_PROMPTS.keys())}")

        if not self.api_key:
            raise RuntimeError("Google AI API key not configured")

        prompt = STYLE_PROMPTS[style]

        # Read and prepare image in thread pool
        loop = asyncio.get_running_loop()

        def prepare_image():
            image = Image.open(image_path)
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='JPEG', quality=95)
            return image, base64.b64encode(img_buffer.getvalue()).decode('utf-8')

        image, img_base64 = await loop.run_in_executor(_image_executor, prepare_image)

        print(f"Sending image to Gemini for {style} style transfer...")

        # Try SDK first
        if self.client:
            try:
                result = await self._try_sdk_generation(image, prompt, loop)
                if result:
                    return result
            except Exception as e:
                print(f"SDK method failed: {e}")

        # Fallback to direct REST API
        try:
            result = await self._try_rest_api(img_base64, prompt)
            if result:
                return result
        except Exception as e:
            print(f"REST API method failed: {e}")
            import traceback
            traceback.print_exc()

        # Last resort: Apply PIL filters as placeholder
        print("WARNING: Using PIL fallback filters - API calls failed")
        return await loop.run_in_executor(
            _image_executor,
            self._apply_pil_fallback,
            image,
            style
        )

    async def _try_sdk_generation(
        self, image: Image.Image, prompt: str, loop: asyncio.AbstractEventLoop
    ) -> bytes | None:
        """Try generating with SDK in thread pool (SDK is synchronous)."""
        models_to_try = [
            "gemini-3-pro-image-preview",
            "gemini-2.0-flash-preview-image-generation",
            "gemini-2.0-flash-exp-image-generation",
            "gemini-2.0-flash-exp",
        ]

        for model_name in models_to_try:
            try:
                print(f"Trying SDK with model: {model_name}")

                def call_sdk():
                    return self.client.models.generate_content(
                        model=model_name,
                        contents=[prompt, image],
                        config=types.GenerateContentConfig(
                            response_modalities=["IMAGE", "TEXT"],
                        ),
                    )

                response = await loop.run_in_executor(_image_executor, call_sdk)

                if response.candidates and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data is not None:
                            print(f"Received styled image from {model_name}, {len(part.inline_data.data)} bytes")
                            return part.inline_data.data
                        elif part.text:
                            print(f"Model {model_name} response text: {part.text[:200]}...")

            except Exception as e:
                print(f"Model {model_name} failed: {e}")
                continue

        return None

    async def _try_rest_api(self, img_base64: str, prompt: str) -> bytes | None:
        """Try generating with direct REST API call."""
        models = [
            "gemini-2.0-flash-preview-image-generation",
            "gemini-2.0-flash-exp-image-generation",
            "gemini-2.0-flash-exp",
        ]

        client = await _get_http_client()

        for model in models:
            try:
                print(f"Trying REST API with model: {model}")
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

                payload = {
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                                {
                                    "inline_data": {
                                        "mime_type": "image/jpeg",
                                        "data": img_base64
                                    }
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "responseModalities": ["IMAGE", "TEXT"]
                    }
                }

                response = await client.post(
                    url,
                    json=payload,
                    params={"key": self.api_key},
                    headers={"Content-Type": "application/json"}
                )

                if response.status_code == 200:
                    data = response.json()
                    if "candidates" in data and data["candidates"]:
                        parts = data["candidates"][0].get("content", {}).get("parts", [])
                        for part in parts:
                            if "inlineData" in part:
                                image_data = base64.b64decode(part["inlineData"]["data"])
                                print(f"Received styled image from REST API ({model}), {len(image_data)} bytes")
                                return image_data
                            elif "text" in part:
                                print(f"REST API {model} text response: {part['text'][:200]}...")
                else:
                    print(f"REST API {model} error: {response.status_code} - {response.text[:500]}")

            except Exception as e:
                print(f"REST API {model} failed: {e}")
                continue

        return None

    def _apply_pil_fallback(self, image: Image.Image, style: str) -> bytes:
        """Apply basic PIL filters as a fallback when API fails."""
        from PIL import ImageEnhance, ImageFilter

        # Ensure RGB
        if image.mode != 'RGB':
            image = image.convert('RGB')

        if style == "ghibli":
            # Soft, dreamy look
            image = image.filter(ImageFilter.GaussianBlur(1))
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(1.3)
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(1.1)
        elif style == "lego":
            # Pixelated look
            small = image.resize((image.width // 10, image.height // 10), Image.Resampling.NEAREST)
            image = small.resize(image.size, Image.Resampling.NEAREST)
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(1.5)
        elif style == "minecraft":
            # Blocky pixelated
            small = image.resize((image.width // 8, image.height // 8), Image.Resampling.NEAREST)
            image = small.resize(image.size, Image.Resampling.NEAREST)
        elif style == "simpsons":
            # Yellow tint, cartoon effect
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(1.5)
            image = image.filter(ImageFilter.EDGE_ENHANCE)

        img_buffer = io.BytesIO()
        image.save(img_buffer, format='PNG')
        return img_buffer.getvalue()

    async def generate_animation_prompt(self, image_path: Path) -> str:
        """
        Analyze an image and generate an animation prompt.
        """
        if not self.client:
            raise RuntimeError("Google AI API key not configured")

        loop = asyncio.get_running_loop()

        def load_image():
            return Image.open(image_path)

        image = await loop.run_in_executor(_image_executor, load_image)

        def call_api():
            return self.client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[
                    image,
                    """Analyze this image and generate a short, vivid animation prompt
                    describing how this scene could come to life as a 5-second video clip.
                    Focus on subtle movements like:
                    - Wind blowing through hair or leaves
                    - Gentle camera movements (pan, zoom)
                    - Atmospheric effects (clouds moving, light changing)
                    - Character expressions or small movements

                    Keep the prompt under 100 words and make it cinematic.
                    Only return the prompt text, nothing else."""
                ],
            )

        response = await loop.run_in_executor(_image_executor, call_api)
        return response.text.strip()

    async def close(self):
        """Clean up resources."""
        global _http_client
        if _http_client and not _http_client.is_closed:
            await _http_client.aclose()
            _http_client = None


imagen_service = ImagenService()
