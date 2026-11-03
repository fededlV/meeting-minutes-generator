"""ASR strategy contract, typed error, and shared segment normalization."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Protocol

from app.schemas.events import ErrorCode, TranscriptChunkPayload

NO_SPEECH_MESSAGE = "No speech detected in audio file"


class ASRError(Exception):
    """Typed ASR failure surfaced to the SSE pipeline as an ``error`` event."""

    def __init__(self, message: str, code: ErrorCode = ErrorCode.ASR_FAILURE) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class ASRStrategy(Protocol):
    def transcribe(self, audio_path: Path) -> AsyncIterator[TranscriptChunkPayload]:
        """Lazily yield timestamped transcript segments from a validated audio file."""
        ...


def to_chunk(start: float, end: float | None, text: str) -> TranscriptChunkPayload | None:
    """Normalize a raw segment; return ``None`` when it carries no speech text."""
    cleaned = text.strip()
    if not cleaned:
        return None
    rounded_start = max(round(start, 2), 0.0)
    rounded_end = rounded_start if end is None else max(round(end, 2), rounded_start)
    return TranscriptChunkPayload(start=rounded_start, end=rounded_end, text=cleaned)
