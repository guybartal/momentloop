"""Concurrency management for MomentLoop."""

import asyncio
from functools import lru_cache

from app.core.config import get_settings


class SemaphoreManager:
    """Manages semaphores for concurrent operations."""

    def __init__(self):
        settings = get_settings()
        self._style_transfer = asyncio.Semaphore(settings.max_concurrent_style_transfers)
        self._video_generation = asyncio.Semaphore(settings.max_concurrent_video_generations)
        self._exports = asyncio.Semaphore(settings.max_concurrent_exports)
        self._prompt_generation = asyncio.Semaphore(settings.max_concurrent_prompt_generations)

    @property
    def style_transfer(self) -> asyncio.Semaphore:
        """Semaphore for style transfer operations."""
        return self._style_transfer

    @property
    def video_generation(self) -> asyncio.Semaphore:
        """Semaphore for video generation operations."""
        return self._video_generation

    @property
    def exports(self) -> asyncio.Semaphore:
        """Semaphore for export operations."""
        return self._exports

    @property
    def prompt_generation(self) -> asyncio.Semaphore:
        """Semaphore for prompt generation operations."""
        return self._prompt_generation


# Global semaphore manager instance
_semaphore_manager: SemaphoreManager | None = None


def get_semaphore_manager() -> SemaphoreManager:
    """Get the global semaphore manager, creating it if necessary."""
    global _semaphore_manager
    if _semaphore_manager is None:
        _semaphore_manager = SemaphoreManager()
    return _semaphore_manager
