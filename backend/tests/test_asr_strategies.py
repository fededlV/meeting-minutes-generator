"""Tests for S3 (local CPU INT8 faster-whisper ASR) and S4 (remote API ASR)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import faster_whisper
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.schemas.events import ASRMode, ErrorCode, TranscriptChunkPayload
from app.services.asr import ASRError, api_whisper
from app.services.asr.api_whisper import DEFAULT_API_ASR_MODEL, ApiWhisperASR
from app.services.asr.factory import get_asr_strategy
from app.services.asr.local_whisper import LocalWhisperASR, clear_model_cache

NO_SPEECH = "No speech detected in audio file"


def seg(start: float, end: float, text: str) -> SimpleNamespace:
    return SimpleNamespace(start=start, end=end, text=text)


async def collect(stream: AsyncIterator[TranscriptChunkPayload]) -> list[TranscriptChunkPayload]:
    return [chunk async for chunk in stream]


@pytest.fixture
def audio_file(tmp_path: Path) -> Path:
    path = tmp_path / "meeting.mp3"
    path.write_bytes(b"ID3\x04\x00fake-audio")
    return path


@pytest.fixture
def whisper_model(monkeypatch: pytest.MonkeyPatch) -> Iterator[MagicMock]:
    """Patch ``faster_whisper.WhisperModel`` so no weights are ever downloaded."""
    clear_model_cache()
    model_cls = MagicMock(name="WhisperModel")
    monkeypatch.setattr(faster_whisper, "WhisperModel", model_cls)
    yield model_cls
    clear_model_cache()


def set_segments(model_cls: MagicMock, segments: Any) -> MagicMock:
    instance: MagicMock = model_cls.return_value
    instance.transcribe.return_value = (segments, SimpleNamespace(duration=10.0))
    return instance


# --------------------------------------------------------------------------- S3


async def test_s3_model_is_lazy_cpu_int8_singleton(
    whisper_model: MagicMock, audio_file: Path
) -> None:
    asr = LocalWhisperASR("base.en")
    whisper_model.assert_not_called()  # lazy: nothing loaded at construction

    set_segments(whisper_model, [seg(0, 1, "hello")])
    await collect(asr.transcribe(audio_file))
    set_segments(whisper_model, [seg(0, 1, "again")])
    await collect(LocalWhisperASR("base.en").transcribe(audio_file))

    whisper_model.assert_called_once_with("base.en", device="cpu", compute_type="int8")


async def test_s3_transcribe_uses_vad_and_yields_normalized_chunks(
    whisper_model: MagicMock, audio_file: Path
) -> None:
    instance = set_segments(
        whisper_model,
        iter(
            [seg(0.0, 2.3456, "  Call to order. "), seg(2.5, 3.0, "   "), seg(3.111, 5.999, "Roll")]
        ),
    )

    chunks = await collect(LocalWhisperASR("small.en").transcribe(audio_file))

    instance.transcribe.assert_called_once_with(
        str(audio_file), vad_filter=True, vad_parameters={"min_silence_duration_ms": 500}
    )
    assert chunks == [
        TranscriptChunkPayload(start=0.0, end=2.35, text="Call to order."),
        TranscriptChunkPayload(start=3.11, end=6.0, text="Roll"),
    ]


async def test_s3_decoding_runs_off_the_event_loop_and_streams_incrementally(
    whisper_model: MagicMock, audio_file: Path
) -> None:
    loop_thread = threading.get_ident()
    decode_threads: list[int] = []
    second_segment_allowed = threading.Event()

    def segments() -> Iterator[SimpleNamespace]:
        decode_threads.append(threading.get_ident())
        yield seg(0, 1, "first")
        # Blocks the decoder until the consumer has already received chunk 1.
        if not second_segment_allowed.wait(timeout=2):
            raise AssertionError("consumer never received the first chunk")
        yield seg(1, 2, "second")

    set_segments(whisper_model, segments())
    stream = LocalWhisperASR("base.en").transcribe(audio_file)

    first = await asyncio.wait_for(anext(stream), timeout=2)
    assert first.text == "first"
    second_segment_allowed.set()
    rest = await asyncio.wait_for(collect(stream), timeout=2)

    assert [c.text for c in rest] == ["second"]
    assert decode_threads and decode_threads[0] != loop_thread


@pytest.mark.parametrize("segments", [[], [seg(0, 1, ""), seg(1, 2, "   \n")]])
async def test_s3_silent_audio_raises_no_speech(
    whisper_model: MagicMock, audio_file: Path, segments: list[SimpleNamespace]
) -> None:
    set_segments(whisper_model, segments)

    with pytest.raises(ASRError) as exc_info:
        await collect(LocalWhisperASR("base.en").transcribe(audio_file))

    assert exc_info.value.code is ErrorCode.ASR_FAILURE
    assert exc_info.value.message == NO_SPEECH


async def test_s3_decoder_failure_is_wrapped_as_asr_error(
    whisper_model: MagicMock, audio_file: Path
) -> None:
    def broken() -> Iterator[SimpleNamespace]:
        yield seg(0, 1, "partial")
        raise RuntimeError("ctranslate2 exploded")

    set_segments(whisper_model, broken())
    stream = LocalWhisperASR("base.en").transcribe(audio_file)

    assert (await anext(stream)).text == "partial"
    with pytest.raises(ASRError) as exc_info:
        await anext(stream)
    assert exc_info.value.code is ErrorCode.ASR_FAILURE
    assert isinstance(exc_info.value.__cause__, RuntimeError)


async def test_s3_model_load_failure_is_wrapped_as_asr_error(
    whisper_model: MagicMock, audio_file: Path
) -> None:
    whisper_model.side_effect = OSError("model not found")

    with pytest.raises(ASRError) as exc_info:
        await collect(LocalWhisperASR("base.en").transcribe(audio_file))
    assert exc_info.value.code is ErrorCode.ASR_FAILURE


async def test_s3_early_close_stops_the_decoder_thread(
    whisper_model: MagicMock, audio_file: Path
) -> None:
    resume = threading.Event()
    pulled: list[int] = []

    def endless() -> Iterator[SimpleNamespace]:
        for i in range(1000):
            pulled.append(i)
            if i == 1:
                resume.wait(timeout=2)
            yield seg(i, i + 1, f"segment {i}")

    set_segments(whisper_model, endless())
    stream = LocalWhisperASR("base.en").transcribe(audio_file)

    await asyncio.wait_for(anext(stream), timeout=2)
    await stream.aclose()  # type: ignore[attr-defined]
    resume.set()

    for _ in range(100):
        if len(pulled) >= 2:
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.1)
    assert len(pulled) <= 3, "decoder kept pulling segments after the consumer closed"


# --------------------------------------------------------------------------- S4


class FakeInferenceClient:
    """Async-context-manager stand-in for ``huggingface_hub.AsyncInferenceClient``."""

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[Any, dict[str, Any]]] = []
        self.init_kwargs: dict[str, Any] = {}
        self.closed = False

    def __call__(self, **kwargs: Any) -> FakeInferenceClient:
        self.init_kwargs = kwargs
        return self

    async def __aenter__(self) -> FakeInferenceClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.closed = True

    async def automatic_speech_recognition(self, audio: Any, **kwargs: Any) -> Any:
        self.calls.append((audio, kwargs))
        if self.error is not None:
            raise self.error
        return self.result


def install_client(monkeypatch: pytest.MonkeyPatch, client: FakeInferenceClient) -> None:
    monkeypatch.setattr(api_whisper, "AsyncInferenceClient", client)


def chunk(text: str, start: float, end: float | None) -> SimpleNamespace:
    return SimpleNamespace(text=text, timestamp=[start, end])


async def test_s4_calls_remote_client_and_normalizes_chunks(
    monkeypatch: pytest.MonkeyPatch, whisper_model: MagicMock, audio_file: Path
) -> None:
    result = SimpleNamespace(
        text="ignored when chunks exist",
        chunks=[
            chunk(" Good evening. ", 0.0, 1.234),
            chunk("  ", 1.3, 2.0),
            chunk("Bye", 9.876, None),
        ],
    )
    client = FakeInferenceClient(result=result)
    install_client(monkeypatch, client)

    chunks = await collect(ApiWhisperASR("hf_secret").transcribe(audio_file))

    assert chunks == [
        TranscriptChunkPayload(start=0.0, end=1.23, text="Good evening."),
        TranscriptChunkPayload(start=9.88, end=9.88, text="Bye"),
    ]
    audio, kwargs = client.calls[0]
    assert audio == audio_file.read_bytes()
    assert kwargs == {"model": DEFAULT_API_ASR_MODEL, "extra_body": {"return_timestamps": True}}
    assert client.init_kwargs["token"] == "hf_secret"
    assert client.closed
    whisper_model.assert_not_called()


async def test_s4_without_chunks_falls_back_to_single_segment(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    install_client(
        monkeypatch, FakeInferenceClient(SimpleNamespace(text=" Whole text. ", chunks=None))
    )

    chunks = await collect(ApiWhisperASR("tok").transcribe(audio_file))

    assert chunks == [TranscriptChunkPayload(start=0.0, end=0.0, text="Whole text.")]


async def test_s4_empty_remote_transcript_raises_no_speech(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    install_client(monkeypatch, FakeInferenceClient(SimpleNamespace(text="  ", chunks=[])))

    with pytest.raises(ASRError) as exc_info:
        await collect(ApiWhisperASR("tok").transcribe(audio_file))
    assert exc_info.value.code is ErrorCode.ASR_FAILURE
    assert exc_info.value.message == NO_SPEECH


async def test_s4_upstream_error_is_wrapped_without_leaking_token(
    monkeypatch: pytest.MonkeyPatch, audio_file: Path
) -> None:
    install_client(monkeypatch, FakeInferenceClient(error=RuntimeError("401 for hf_secret")))

    with pytest.raises(ASRError) as exc_info:
        await collect(ApiWhisperASR("hf_secret").transcribe(audio_file))
    assert exc_info.value.code is ErrorCode.ASR_FAILURE
    assert "hf_secret" not in str(exc_info.value)


@pytest.mark.parametrize("token", [None, "", "   "])
def test_s4_missing_token_fails_fast(token: str | None) -> None:
    with pytest.raises(ASRError) as exc_info:
        ApiWhisperASR(token)
    assert exc_info.value.code is ErrorCode.MISSING_API_KEY


# ---------------------------------------------------------------------- factory


def make_settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {"hf_token": None, "llm_api_key": None}
    return Settings(_env_file=None, **(base | overrides))


def test_factory_local_mode_uses_configured_model_size(whisper_model: MagicMock) -> None:
    strategy = get_asr_strategy(ASRMode.LOCAL, make_settings(whisper_model_size="small.en"), None)

    assert isinstance(strategy, LocalWhisperASR)
    assert strategy.model_size == "small.en"
    whisper_model.assert_not_called()


@pytest.mark.parametrize(
    ("api_key", "settings_kwargs", "expected"),
    [
        ("byok", {"hf_token": SecretStr("server-hf"), "llm_api_key": SecretStr("llm")}, "byok"),
        (None, {"hf_token": SecretStr("server-hf"), "llm_api_key": SecretStr("llm")}, "server-hf"),
        (None, {"llm_api_key": SecretStr("llm")}, "llm"),
    ],
)
def test_factory_api_mode_resolves_token_precedence(
    api_key: str | None, settings_kwargs: dict[str, Any], expected: str
) -> None:
    strategy = get_asr_strategy(ASRMode.API, make_settings(**settings_kwargs), api_key)

    assert isinstance(strategy, ApiWhisperASR)
    assert strategy.token == expected


def test_factory_api_mode_without_any_token_fails_fast() -> None:
    with pytest.raises(ASRError) as exc_info:
        get_asr_strategy(ASRMode.API, make_settings(), None)
    assert exc_info.value.code is ErrorCode.MISSING_API_KEY
