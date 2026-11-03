"""Tests for S1 (audio upload validation) and S2 (guaranteed temp-file cleanup)."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.schemas.events import (
    ErrorCode,
    ErrorEventPayload,
    LLMProvider,
    LLMTokenPayload,
    PipelineStage,
    StatusEventPayload,
    TranscriptChunkPayload,
    format_sse,
)
from app.schemas.requests import APIErrorResponse, BYOKHeaders
from app.services.audio.cleanup import stream_with_cleanup, temp_audio_file
from app.services.audio.validator import (
    MAX_UPLOAD_BYTES,
    AudioValidationError,
    FileTooLargeError,
    InvalidAudioFormatError,
    UnsafeUploadDirError,
    save_validated_upload,
)
from tests.conftest import (
    M4A_HEADER,
    MP3_ID3_HEADER,
    OGG_HEADER,
    WAV_HEADER,
    FakeUpload,
)

UUID_NAME = re.compile(r"^[0-9a-f]{32}\.(mp3|wav|m4a|ogg)$")
BODY = b"\x00" * 2048


def _files(directory: Path) -> list[Path]:
    return list(directory.iterdir()) if directory.exists() else []


# --------------------------------------------------------------------------- S1


@pytest.mark.parametrize(
    ("filename", "content_type", "header"),
    [
        ("talk.mp3", "audio/mpeg", MP3_ID3_HEADER),
        ("talk.mp3", "audio/mpeg", b"\xff\xfb\x90\x64"),
        ("talk.mp3", "audio/mpeg", b"\xff\xf3\x90\x64"),
        ("talk.mp3", "audio/mpeg", b"\xff\xf2\x90\x64"),
        ("talk.wav", "audio/wav", WAV_HEADER),
        ("talk.m4a", "audio/mp4", M4A_HEADER),
        ("talk.ogg", "audio/ogg", OGG_HEADER),
        ("TALK.MP3", "application/octet-stream", MP3_ID3_HEADER),
        ("talk.ogg", "audio/ogg; codecs=opus", OGG_HEADER),
    ],
)
async def test_valid_audio_is_saved_under_uuid_name(
    upload_dir: Path, filename: str, content_type: str, header: bytes
) -> None:
    data = header + BODY

    path = await save_validated_upload(
        FakeUpload(data), filename, content_type, dest_dir=upload_dir
    )

    assert path.parent == upload_dir
    assert UUID_NAME.match(path.name)
    assert path.suffix == Path(filename).suffix.lower()
    assert path.read_bytes() == data


@pytest.mark.parametrize(
    ("filename", "content_type", "data"),
    [
        ("malware.exe", "application/octet-stream", b"MZ\x90\x00" + BODY),
        ("notes.txt", "text/plain", b"hello world" + BODY),
        ("noext", "audio/mpeg", MP3_ID3_HEADER + BODY),
        ("", "audio/mpeg", MP3_ID3_HEADER + BODY),
        ("talk.mp3", "text/plain", MP3_ID3_HEADER + BODY),
        ("talk.mp3", "", MP3_ID3_HEADER + BODY),
        ("disguised.mp3", "audio/mpeg", b"MZ\x90\x00" + BODY),
        ("disguised.wav", "audio/wav", b"just some plain text pretending"),
        ("wrongfamily.mp3", "audio/mpeg", WAV_HEADER + BODY),
        ("riffnotwave.wav", "audio/wav", b"RIFF\x24\x00\x00\x00AVI " + BODY),
        ("empty.ogg", "audio/ogg", b""),
        ("short.m4a", "audio/mp4", b"\x00\x00"),
    ],
)
async def test_invalid_audio_is_rejected_with_415_and_no_orphans(
    upload_dir: Path, filename: str, content_type: str, data: bytes
) -> None:
    with pytest.raises(InvalidAudioFormatError) as exc_info:
        await save_validated_upload(FakeUpload(data), filename, content_type, dest_dir=upload_dir)

    assert exc_info.value.status_code == 415
    assert exc_info.value.code is ErrorCode.INVALID_AUDIO_FORMAT
    assert _files(upload_dir) == []


async def test_oversized_upload_is_rejected_with_413_and_partial_file_removed(
    upload_dir: Path,
) -> None:
    data = MP3_ID3_HEADER + b"\x00" * (MAX_UPLOAD_BYTES + 1 - len(MP3_ID3_HEADER))

    with pytest.raises(FileTooLargeError) as exc_info:
        await save_validated_upload(FakeUpload(data), "big.mp3", "audio/mpeg", dest_dir=upload_dir)

    assert exc_info.value.status_code == 413
    assert exc_info.value.code is ErrorCode.FILE_TOO_LARGE
    assert isinstance(exc_info.value, AudioValidationError)
    assert _files(upload_dir) == []


async def test_upload_exactly_at_size_cap_is_accepted(upload_dir: Path) -> None:
    data = MP3_ID3_HEADER + b"\x00" * (MAX_UPLOAD_BYTES - len(MP3_ID3_HEADER))

    path = await save_validated_upload(
        FakeUpload(data), "edge.mp3", "audio/mpeg", dest_dir=upload_dir
    )

    assert path.stat().st_size == MAX_UPLOAD_BYTES == 26_214_400


async def test_custom_size_cap_is_honoured(upload_dir: Path) -> None:
    with pytest.raises(FileTooLargeError):
        await save_validated_upload(
            FakeUpload(OGG_HEADER + BODY), "a.ogg", "audio/ogg", dest_dir=upload_dir, max_bytes=100
        )
    assert _files(upload_dir) == []


async def test_path_traversal_filename_never_escapes_upload_dir(upload_dir: Path) -> None:
    path = await save_validated_upload(
        FakeUpload(MP3_ID3_HEADER + BODY), "../../etc/evil.mp3", "audio/mpeg", dest_dir=upload_dir
    )

    assert path.parent == upload_dir
    assert UUID_NAME.match(path.name)
    assert "evil" not in path.name


async def test_missing_upload_dir_is_created_private(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "mmg-uploads"

    path = await save_validated_upload(
        FakeUpload(WAV_HEADER + BODY), "a.wav", "audio/wav", dest_dir=target
    )

    assert path.parent == target
    assert target.stat().st_mode & 0o777 == 0o700


async def test_existing_loose_upload_dir_is_tightened_to_private(tmp_path: Path) -> None:
    target = tmp_path / "mmg-uploads"
    target.mkdir(mode=0o755)
    target.chmod(0o755)

    await save_validated_upload(
        FakeUpload(OGG_HEADER + BODY), "a.ogg", "audio/ogg", dest_dir=target
    )

    assert target.stat().st_mode & 0o777 == 0o700


async def test_symlinked_upload_dir_is_refused(tmp_path: Path) -> None:
    real = tmp_path / "attacker-controlled"
    real.mkdir()
    link = tmp_path / "mmg-uploads"
    link.symlink_to(real, target_is_directory=True)

    with pytest.raises(UnsafeUploadDirError):
        await save_validated_upload(
            FakeUpload(OGG_HEADER + BODY), "a.ogg", "audio/ogg", dest_dir=link
        )

    assert list(real.iterdir()) == []


async def test_reader_failure_mid_stream_removes_partial_file(upload_dir: Path) -> None:
    class ExplodingUpload:
        def __init__(self) -> None:
            self._calls = 0

        async def read(self, size: int = -1) -> bytes:
            self._calls += 1
            if self._calls == 1:
                return OGG_HEADER + BODY
            raise ConnectionResetError("client went away")

    with pytest.raises(ConnectionResetError):
        await save_validated_upload(ExplodingUpload(), "a.ogg", "audio/ogg", dest_dir=upload_dir)

    assert _files(upload_dir) == []


async def test_cancellation_mid_upload_removes_partial_file(upload_dir: Path) -> None:
    first_chunk_sent = asyncio.Event()

    class StallingUpload:
        def __init__(self) -> None:
            self._sent = False

        async def read(self, size: int = -1) -> bytes:
            if not self._sent:
                self._sent = True
                return WAV_HEADER + BODY
            first_chunk_sent.set()
            await asyncio.sleep(3600)
            return b""

    task = asyncio.create_task(
        save_validated_upload(StallingUpload(), "a.wav", "audio/wav", dest_dir=upload_dir)
    )
    await first_chunk_sent.wait()
    assert len(_files(upload_dir)) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _files(upload_dir) == []


async def test_magic_bytes_split_across_tiny_chunks_are_detected(upload_dir: Path) -> None:
    class DripUpload:
        def __init__(self, data: bytes) -> None:
            self._data = data

        async def read(self, size: int = -1) -> bytes:
            chunk, self._data = self._data[:3], self._data[3:]
            return chunk

    path = await save_validated_upload(
        DripUpload(M4A_HEADER + BODY), "a.m4a", "audio/mp4", dest_dir=upload_dir
    )

    assert path.read_bytes() == M4A_HEADER + BODY


# --------------------------------------------------------------------------- S2


@pytest.fixture
def audio_file(upload_dir: Path) -> Path:
    path = upload_dir / "0123456789abcdef0123456789abcdef.mp3"
    path.write_bytes(MP3_ID3_HEADER + BODY)
    return path


async def test_temp_file_removed_after_normal_exit(audio_file: Path) -> None:
    async with temp_audio_file(audio_file) as path:
        assert path.exists()

    assert not audio_file.exists()


async def test_temp_file_removed_after_exception(audio_file: Path) -> None:
    with pytest.raises(RuntimeError, match="ASR exploded"):
        async with temp_audio_file(audio_file):
            raise RuntimeError("ASR exploded")

    assert not audio_file.exists()


async def test_temp_file_removed_after_task_cancellation(audio_file: Path) -> None:
    entered = asyncio.Event()

    async def worker() -> None:
        async with temp_audio_file(audio_file):
            entered.set()
            await asyncio.sleep(3600)

    task = asyncio.create_task(worker())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not audio_file.exists()


async def test_temp_file_already_gone_does_not_raise(audio_file: Path) -> None:
    async with temp_audio_file(audio_file):
        audio_file.unlink()

    assert not audio_file.exists()


async def test_unowned_file_is_never_deleted(audio_file: Path) -> None:
    with pytest.raises(RuntimeError):
        async with temp_audio_file(audio_file, owned=False):
            raise RuntimeError("boom")

    assert audio_file.exists()


async def _segments(count: int) -> AsyncGenerator[int]:
    for index in range(count):
        await asyncio.sleep(0)
        yield index


async def test_stream_wrapper_removes_file_after_full_consumption(audio_file: Path) -> None:
    items = [item async for item in stream_with_cleanup(_segments(3), audio_file)]

    assert items == [0, 1, 2]
    assert not audio_file.exists()


async def test_stream_wrapper_removes_file_on_aclose_mid_stream(audio_file: Path) -> None:
    stream = stream_with_cleanup(_segments(10), audio_file)

    assert await anext(stream) == 0
    assert audio_file.exists()
    await stream.aclose()

    assert not audio_file.exists()


async def test_stream_wrapper_removes_file_when_source_raises(audio_file: Path) -> None:
    async def failing() -> AsyncGenerator[int]:
        yield 1
        raise RuntimeError("LLM upstream 503")

    with pytest.raises(RuntimeError, match="503"):
        async for _ in stream_with_cleanup(failing(), audio_file):
            pass

    assert not audio_file.exists()


async def test_stream_wrapper_removes_file_on_aclose_before_first_item(audio_file: Path) -> None:
    # Client disconnects before the response ever starts iterating.
    stream = stream_with_cleanup(_segments(3), audio_file)
    await stream.aclose()

    assert not audio_file.exists()


async def test_stream_wrapper_closes_started_source_on_aclose(audio_file: Path) -> None:
    source_closed = False

    async def source() -> AsyncGenerator[int]:
        nonlocal source_closed
        try:
            yield 1
            yield 2
        finally:
            source_closed = True

    stream = stream_with_cleanup(source(), audio_file)
    assert await anext(stream) == 1
    await stream.aclose()

    assert source_closed
    assert not audio_file.exists()


async def test_stream_wrapper_aclose_is_idempotent(audio_file: Path) -> None:
    stream = stream_with_cleanup(_segments(2), audio_file)

    await stream.aclose()
    await stream.aclose()

    with pytest.raises(StopAsyncIteration):
        await anext(stream)


async def test_stream_wrapper_keeps_unowned_sample(audio_file: Path) -> None:
    items = [item async for item in stream_with_cleanup(_segments(2), audio_file, owned=False)]

    assert items == [0, 1]
    assert audio_file.exists()


# ------------------------------------------------------------- Schemas & config


@pytest.mark.parametrize(
    ("event", "payload"),
    [
        ("status", StatusEventPayload(stage=PipelineStage.TRANSCRIBING, message="Transcribing")),
        ("transcript_chunk", TranscriptChunkPayload(start=0.0, end=4.5, text="Hello council")),
        ("llm_token", LLMTokenPayload(token="## Executive")),
        ("error", ErrorEventPayload(code=ErrorCode.ASR_FAILURE, message="No speech")),
    ],
)
def test_format_sse_produces_w3c_frame(event: str, payload: BaseModel) -> None:
    frame = format_sse(event, payload)  # type: ignore[arg-type]

    header, data_line, *rest = frame.split("\n")
    assert header == f"event: {event}"
    assert data_line.startswith("data: ")
    assert json.loads(data_line.removeprefix("data: ")) == payload.model_dump(mode="json")
    assert frame.endswith("\n\n")
    assert rest == ["", ""]


def test_payloads_forbid_extra_fields_and_are_frozen() -> None:
    with pytest.raises(ValidationError):
        LLMTokenPayload(token="x", extra="nope")  # type: ignore[call-arg]

    payload = LLMTokenPayload(token="x")
    with pytest.raises(ValidationError):
        payload.token = "y"  # type: ignore[misc]


@pytest.mark.parametrize("message", ["", "x" * 281])
def test_status_message_length_bounds(message: str) -> None:
    with pytest.raises(ValidationError):
        StatusEventPayload(stage=PipelineStage.UPLOADING, message=message)


def test_transcript_chunk_rejects_negative_timestamps_and_empty_text() -> None:
    with pytest.raises(ValidationError):
        TranscriptChunkPayload(start=-1.0, end=1.0, text="hi")
    with pytest.raises(ValidationError):
        TranscriptChunkPayload(start=0.0, end=1.0, text="")


def test_error_event_defaults_to_recoverable() -> None:
    assert ErrorEventPayload(code=ErrorCode.INTERNAL_ERROR, message="x").recoverable is True


def test_api_error_response_shape() -> None:
    body = APIErrorResponse.model_validate(
        {"error": {"code": "FILE_TOO_LARGE", "message": "Max 25 MB"}}
    )

    assert body.model_dump(mode="json") == {
        "error": {"code": "FILE_TOO_LARGE", "message": "Max 25 MB"}
    }


def test_byok_headers_parse_aliases_and_hide_secrets() -> None:
    headers = BYOKHeaders.model_validate(
        {"X-API-Key": "sk-secret", "X-LLM-Provider": "openrouter", "X-ASR-Mode": "api"}
    )

    assert headers.x_api_key is not None
    assert headers.x_api_key.get_secret_value() == "sk-secret"
    assert headers.x_llm_provider is LLMProvider.OPENROUTER
    assert "sk-secret" not in repr(headers)
    assert headers.x_hf_token is None


def test_byok_headers_reject_unknown_provider() -> None:
    with pytest.raises(ValidationError):
        BYOKHeaders.model_validate({"X-LLM-Provider": "skynet"})


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)

    settings = Settings(_env_file=None)

    assert settings.asr_mode == "local"
    assert settings.whisper_model_size == "base.en"
    assert settings.default_llm_provider is LLMProvider.HUGGINGFACE
    assert settings.max_upload_bytes == 26_214_400
    assert settings.rate_limit_requests == 5
    assert settings.rate_limit_window_seconds == 3600
    assert settings.upload_tmp_dir.name == "mmg-uploads"


def test_settings_secrets_are_not_leaked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_supersecret")

    settings = Settings(_env_file=None)

    assert settings.hf_token is not None
    assert settings.hf_token.get_secret_value() == "hf_supersecret"
    assert "hf_supersecret" not in repr(settings)


def test_settings_reject_unsupported_whisper_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "large-v3")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_upload_cap_matches_validator_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MAX_UPLOAD_BYTES", raising=False)

    assert Settings(_env_file=None).max_upload_bytes == MAX_UPLOAD_BYTES
