"""Remote serverless Whisper strategy via Hugging Face Inference (spec S4)."""

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from huggingface_hub import AsyncInferenceClient

from app.schemas.events import ErrorCode, TranscriptChunkPayload
from app.services.asr.base import NO_SPEECH_MESSAGE, ASRError, to_chunk

DEFAULT_API_ASR_MODEL = "openai/whisper-large-v3"
DEFAULT_API_TIMEOUT_SECONDS = 120.0


class ApiWhisperASR:
    def __init__(
        self,
        token: str | None,
        model: str = DEFAULT_API_ASR_MODEL,
        timeout: float = DEFAULT_API_TIMEOUT_SECONDS,
    ) -> None:
        if token is None or not token.strip():
            raise ASRError(
                "An API token is required for remote ASR mode", code=ErrorCode.MISSING_API_KEY
            )
        self.token = token
        self.model = model
        self.timeout = timeout

    async def transcribe(self, audio_path: Path) -> AsyncIterator[TranscriptChunkPayload]:
        audio = await asyncio.to_thread(audio_path.read_bytes)
        try:
            async with AsyncInferenceClient(token=self.token, timeout=self.timeout) as client:
                output = await client.automatic_speech_recognition(
                    audio, model=self.model, extra_body={"return_timestamps": True}
                )
        except Exception as exc:
            # Message is fixed: upstream errors may echo credentials.
            raise ASRError("Remote ASR request failed") from exc

        if output.chunks:
            chunks = [
                to_chunk(c.timestamp[0], c.timestamp[1] if len(c.timestamp) > 1 else None, c.text)
                for c in output.chunks
            ]
        else:  # endpoint returned no granular timestamps
            chunks = [to_chunk(0.0, 0.0, output.text)]

        emitted = 0
        for chunk in chunks:
            if chunk is not None:
                emitted += 1
                yield chunk
        if emitted == 0:
            raise ASRError(NO_SPEECH_MESSAGE)
