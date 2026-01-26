import asyncio
import subprocess
import tempfile
import uuid
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


class FFmpegService:
    """Service for video manipulation using FFmpeg."""

    async def extract_frame(
        self,
        video_path: Path,
        output_path: Path,
        position: str = "last",  # "first" or "last"
    ) -> Path:
        """
        Extract a frame from a video.

        Args:
            video_path: Path to the video file
            output_path: Path for the output frame
            position: "first" for first frame, "last" for last frame

        Returns:
            Path to the extracted frame
        """
        if position == "first":
            # Extract first frame
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_path),
                "-vf", "select=eq(n\\,0)",
                "-vframes", "1",
                str(output_path),
            ]
        else:
            # Extract last frame - first get duration
            probe_cmd = [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ]
            result = await asyncio.to_thread(
                subprocess.run, probe_cmd, capture_output=True, text=True
            )
            duration = float(result.stdout.strip())

            # Extract frame near the end
            cmd = [
                "ffmpeg",
                "-y",
                "-ss", str(duration - 0.1),
                "-i", str(video_path),
                "-vframes", "1",
                str(output_path),
            ]

        await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, check=True
        )
        return output_path

    async def get_video_duration(self, video_path: Path) -> float:
        """Get the duration of a video in seconds."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True
        )
        return float(result.stdout.strip())

    async def concatenate_videos(
        self,
        video_paths: list[Path],
        output_path: Path,
        transition_duration: float = 0.5,
    ) -> Path:
        """
        Concatenate multiple videos into one.

        Args:
            video_paths: List of paths to videos to concatenate
            output_path: Path for the output video
            transition_duration: Duration of crossfade between clips (0 for hard cuts)

        Returns:
            Path to the concatenated video
        """
        if not video_paths:
            raise ValueError("No videos to concatenate")

        if len(video_paths) == 1:
            # Just copy the single video
            cmd = [
                "ffmpeg",
                "-y",
                "-i", str(video_paths[0]),
                "-c", "copy",
                str(output_path),
            ]
            await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, check=True
            )
            return output_path

        # Create a temporary file list for concat
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for video_path in video_paths:
                f.write(f"file '{video_path}'\n")
            concat_file = f.name

        try:
            if transition_duration > 0:
                # Use xfade filter for crossfade transitions
                # This is more complex but creates smoother transitions
                filter_complex = []
                inputs = []

                for i, video_path in enumerate(video_paths):
                    inputs.extend(["-i", str(video_path)])

                # Build filter chain for crossfades
                if len(video_paths) == 2:
                    filter_complex = [
                        f"[0][1]xfade=transition=fade:duration={transition_duration}:offset=4.5[v]"
                    ]
                    map_args = ["-map", "[v]"]
                else:
                    # For multiple videos, chain xfades
                    current = "[0]"
                    for i in range(1, len(video_paths)):
                        next_input = f"[{i}]"
                        output = f"[v{i}]" if i < len(video_paths) - 1 else "[v]"
                        # Calculate offset based on cumulative duration
                        offset = 4.5 * i - (transition_duration * (i - 1)) if i > 0 else 4.5
                        filter_complex.append(
                            f"{current}{next_input}xfade=transition=fade:duration={transition_duration}:offset={offset}{output}"
                        )
                        current = output
                    map_args = ["-map", "[v]"]

                cmd = (
                    ["ffmpeg", "-y"]
                    + inputs
                    + ["-filter_complex", ";".join(filter_complex)]
                    + map_args
                    + ["-c:v", "libx264", "-preset", "fast", str(output_path)]
                )
            else:
                # Simple concatenation without transitions
                cmd = [
                    "ffmpeg",
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", concat_file,
                    "-c", "copy",
                    str(output_path),
                ]

            await asyncio.to_thread(
                subprocess.run, cmd, capture_output=True, check=True
            )

        finally:
            # Clean up temp file
            Path(concat_file).unlink(missing_ok=True)

        return output_path

    async def add_audio(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path,
    ) -> Path:
        """
        Add audio track to a video.

        Args:
            video_path: Path to the video file
            audio_path: Path to the audio file
            output_path: Path for the output video

        Returns:
            Path to the video with audio
        """
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(output_path),
        ]
        await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, check=True
        )
        return output_path

    async def resize_video(
        self,
        video_path: Path,
        output_path: Path,
        width: int = 1920,
        height: int = 1080,
    ) -> Path:
        """
        Resize a video to specified dimensions.

        Args:
            video_path: Path to the video file
            output_path: Path for the output video
            width: Target width
            height: Target height

        Returns:
            Path to the resized video
        """
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            "-c:v", "libx264",
            "-preset", "fast",
            str(output_path),
        ]
        await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, check=True
        )
        return output_path


ffmpeg_service = FFmpegService()
