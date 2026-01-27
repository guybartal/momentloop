from pathlib import Path

from google import genai
from PIL import Image

from app.core.config import get_settings

settings = get_settings()


class PromptGeneratorService:
    """Service for generating animation prompts from images."""

    def __init__(self):
        self.client = None
        if settings.google_ai_api_key:
            self.client = genai.Client(api_key=settings.google_ai_api_key)

    async def generate_prompt(self, image_path: Path, style: str | None = None) -> str:
        """
        Analyze an image and generate an animation prompt.

        Args:
            image_path: Path to the image file
            style: Optional style context (ghibli, lego, minecraft, simpsons)

        Returns:
            A descriptive animation prompt
        """
        if not self.client:
            raise RuntimeError("Google AI API key not configured")

        image = Image.open(image_path)

        style_context = ""
        if style:
            style_contexts = {
                "ghibli": "Studio Ghibli anime style.",
                "lego": "LEGO brick style.",
                "minecraft": "Minecraft style.",
                "simpsons": "The Simpsons cartoon style.",
            }
            style_context = style_contexts.get(style, "")

        prompt = f"""Restyle this image as {style_context}"""

        response = self.client.models.generate_content(
            model="gemini-3-pro-image-preview",
            contents=[image, prompt],
        )

        return response.text.strip()

    async def regenerate_prompt(
        self, image_path: Path, current_prompt: str, feedback: str | None = None
    ) -> str:
        """
        Regenerate an animation prompt with optional feedback.

        Args:
            image_path: Path to the image file
            current_prompt: The current prompt to improve upon
            feedback: Optional user feedback for improvement

        Returns:
            An improved animation prompt
        """
        if not self.client:
            raise RuntimeError("Google AI API key not configured")

        image = Image.open(image_path)

        improvement_context = ""
        if feedback:
            improvement_context = f"\n\nThe user wants to modify this prompt. Their feedback: {feedback}"

        prompt = f"""Here is the current animation prompt for this image:

"{current_prompt}"
{improvement_context}

Generate an improved animation prompt that:
- Better captures the essence of the image
- Creates more dynamic and interesting movement
- Maintains a cinematic quality
- Is under 80 words

Only return the new animation prompt text, nothing else."""

        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[image, prompt],
        )

        return response.text.strip()


prompt_generator_service = PromptGeneratorService()
