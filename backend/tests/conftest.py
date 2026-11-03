"""Shared fixtures for backend tests."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

# Minimal valid leading signatures per supported audio family.
MP3_ID3_HEADER = b"ID3\x04\x00\x00\x00\x00\x00\x00"
WAV_HEADER = b"RIFF\x24\x00\x00\x00WAVEfmt "
M4A_HEADER = b"\x00\x00\x00\x20ftypM4A \x00\x00\x00\x00"
OGG_HEADER = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00"


class FakeUpload:
    """In-memory stand-in for Starlette's ``UploadFile`` async ``read`` API."""

    def __init__(self, data: bytes) -> None:
        self._buffer = io.BytesIO(data)

    async def read(self, size: int = -1) -> bytes:
        return self._buffer.read(size)


@pytest.fixture
def upload_dir(tmp_path: Path) -> Path:
    """Isolated upload directory so orphan files are observable per test."""
    target = tmp_path / "uploads"
    target.mkdir()
    return target
