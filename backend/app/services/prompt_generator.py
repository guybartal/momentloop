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

    async def generate_video_prompt(self, image_path: Path) -> str:
        """
        Analyze an image and generate a video animation prompt.

        The prompt includes:
        - Actions for subjects/people in the image
        - Camera movement suggestions
        - Environmental effects (wind, lighting changes, etc.)

        Args:
            image_path: Path to the image file

        Returns:
            A descriptive video animation prompt
        """
        if not self.client:
            raise RuntimeError("Google AI API key not configured")

        image = Image.open(image_path)

        prompt = """Analyze this image and generate a short, cinematic video animation prompt.

Your prompt should describe:
1. SUBJECT ACTIONS: What the people, animals, or main subjects in the image should do (e.g., "the woman turns her head and smiles", "the dog wags its tail and looks up", "the child reaches for the balloon")
2. CAMERA MOVEMENT: Suggest one camera movement (e.g., "slow zoom in on the face", "gentle pan from left to right", "camera slowly pulls back to reveal the scene", "subtle dolly forward")
3. ENVIRONMENTAL EFFECTS: Natural movements like wind in hair/clothes, leaves rustling, water rippling, clouds drifting, light shifting

Keep the prompt under 60 words. Focus on subtle, realistic movements that bring the image to life.
Write ONLY the animation prompt, nothing else. Do not include labels like "Subject Actions:" - just write a flowing description."""

        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[image, prompt],
        )

        return response.text.strip()

    async def generate_prompt(self, image_path: Path, style: str | None = None) -> str:
        """
        Analyze an image and generate an animation prompt.

        DEPRECATED: Use generate_video_prompt instead for better results.

        Args:
            image_path: Path to the image file
            style: Optional style context (ghibli, lego, minecraft, simpsons)

        Returns:
            A descriptive animation prompt
        """
        # Delegate to the new method for better prompts
        return await self.generate_video_prompt(image_path)

    async def regenerate_prompt(
        self, image_path: Path, current_prompt: str, feedback: str | None = None
    ) -> str:
        """
        Regenerate a video animation prompt with optional feedback.

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

        feedback_context = ""
        if feedback:
            feedback_context = f"\n\nUser's modification request: {feedback}"

        prompt = f"""Here is the current video animation prompt for this image:

"{current_prompt}"
{feedback_context}

Generate a new video animation prompt that improves on the current one. The prompt should describe:
1. SUBJECT ACTIONS: What the people, animals, or main subjects should do
2. CAMERA MOVEMENT: One camera movement (zoom, pan, dolly, etc.)
3. ENVIRONMENTAL EFFECTS: Natural movements like wind, light shifts, etc.

Keep it under 60 words. Focus on subtle, realistic movements.
Write ONLY the animation prompt, nothing else."""

        response = self.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=[image, prompt],
        )

        return response.text.strip()


prompt_generator_service = PromptGeneratorService()
