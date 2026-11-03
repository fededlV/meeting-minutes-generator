"""Local CPU INT8 ``faster-whisper`` strategy (spec S3, ADR-0001)."""

import asyncio
import threading
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal

from app.schemas.events import TranscriptChunkPayload
from app.services.asr.base import NO_SPEECH_MESSAGE, ASRError, to_chunk

WhisperModelSize = Literal["base.en", "small.en"]

_MODELS: dict[str, Any] = {}
_MODELS_LOCK = threading.Lock()


def get_whisper_model(model_size: WhisperModelSize) -> Any:
    """Return the process-wide ``WhisperModel``, loading it lazily on first use."""
    with _MODELS_LOCK:
        model = _MODELS.get(model_size)
        if model is None:
            # Imported lazily so `api` mode never loads CTranslate2 into RAM.
            from faster_whisper import WhisperModel

            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _MODELS[model_size] = model
        return model


def clear_model_cache() -> None:
    """Drop cached models (test isolation / memory release)."""
    with _MODELS_LOCK:
        _MODELS.clear()


class _Done:
    """Queue sentinel marking the end of the decoder stream."""


_DONE = _Done()
_QueueItem = TranscriptChunkPayload | BaseException | _Done


class LocalWhisperASR:
    def __init__(self, model_size: WhisperModelSize) -> None:
        self.model_size: WhisperModelSize = model_size

    async def transcribe(self, audio_path: Path) -> AsyncIterator[TranscriptChunkPayload]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[_QueueItem] = asyncio.Queue()
        stop = threading.Event()

        def push(item: _QueueItem) -> None:
            try:
                loop.call_soon_threadsafe(queue.put_nowait, item)
            except RuntimeError:  # event loop already closed; consumer is gone
                stop.set()

        def produce() -> None:
            try:
                model = get_whisper_model(self.model_size)
                segments, _info = model.transcribe(
                    str(audio_path),
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=500),
                )
                for segment in segments:
                    if stop.is_set():
                        return
                    chunk = to_chunk(segment.start, segment.end, segment.text)
                    if chunk is not None:
                        push(chunk)
            except BaseException as exc:  # forwarded to the consumer, never swallowed
                push(exc)
            finally:
                push(_DONE)

        producer = asyncio.ensure_future(asyncio.to_thread(produce))
        emitted = 0
        try:
            while True:
                item = await queue.get()
                if isinstance(item, _Done):
                    break
                if isinstance(item, BaseException):
                    raise ASRError("Local transcription failed") from item
                emitted += 1
                yield item
            if emitted == 0:
                raise ASRError(NO_SPEECH_MESSAGE)
        finally:
            stop.set()
            if producer.done():
                producer.exception()
            else:
                producer.add_done_callback(_consume_result)


def _consume_result(task: "asyncio.Future[None]") -> None:
    if not task.cancelled():
        task.exception()
