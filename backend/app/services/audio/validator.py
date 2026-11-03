"""Audio upload validation (S1): extension, MIME, magic bytes and size cap.

Uploads are streamed in chunks to ``<uuid4>.<ext>`` inside a private directory.
Any failure (validation, I/O, cancellation) unlinks the partial file before the
exception propagates, so rejected requests leave zero files on disk.
"""

import asyncio
import os
import stat
import uuid
from pathlib import Path, PurePath
from typing import Protocol

from app.schemas.events import ErrorCode

MAX_UPLOAD_BYTES = 26_214_400
CHUNK_SIZE = 1024 * 1024
MAGIC_HEADER_BYTES = 12
ALLOWED_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".ogg"})
_GENERIC_CONTENT_TYPE = "application/octet-stream"


class AsyncReadable(Protocol):
    """Subset of Starlette's ``UploadFile`` used by the validator."""

    async def read(self, size: int = -1) -> bytes: ...


class AudioValidationError(Exception):
    code: ErrorCode
    status_code: int

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidAudioFormatError(AudioValidationError):
    code = ErrorCode.INVALID_AUDIO_FORMAT
    status_code = 415


class FileTooLargeError(AudioValidationError):
    code = ErrorCode.FILE_TOO_LARGE
    status_code = 413


class UnsafeUploadDirError(RuntimeError):
    """Server-side misconfiguration: the upload directory cannot be trusted (HTTP 500)."""


def validate_extension(filename: str) -> str:
    """Return the normalised extension; only the suffix of the client name is trusted."""
    ext = PurePath(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise InvalidAudioFormatError(f"Unsupported file extension. Allowed: {allowed}")
    return ext


def validate_content_type(content_type: str | None) -> None:
    media_type = (content_type or "").split(";", 1)[0].strip().lower()
    if not (media_type.startswith("audio/") or media_type == _GENERIC_CONTENT_TYPE):
        raise InvalidAudioFormatError("Unsupported content type. Expected audio/*.")


def matches_magic(ext: str, header: bytes) -> bool:
    """Check that the leading bytes match the signature family of ``ext``."""
    if ext == ".mp3":
        return header.startswith((b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"))
    if ext == ".wav":
        return header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if ext == ".m4a":
        return header[4:8] == b"ftyp"
    if ext == ".ogg":
        return header.startswith(b"OggS")
    return False


async def save_validated_upload(
    upload: AsyncReadable,
    filename: str,
    content_type: str | None,
    *,
    dest_dir: Path,
    max_bytes: int = MAX_UPLOAD_BYTES,
    chunk_size: int = CHUNK_SIZE,
) -> Path:
    """Validate and persist an upload, returning the sanitized on-disk path.

    Raises ``InvalidAudioFormatError`` (415) or ``FileTooLargeError`` (413).
    """
    ext = validate_extension(filename)
    validate_content_type(content_type)

    await asyncio.to_thread(_prepare_upload_dir, dest_dir)
    path = dest_dir / f"{uuid.uuid4().hex}{ext}"

    header = b""
    magic_checked = False
    written = 0
    try:
        with path.open("xb") as sink:
            while chunk := await upload.read(chunk_size):
                written += len(chunk)
                if written > max_bytes:
                    raise FileTooLargeError(f"File exceeds the {max_bytes} byte limit.")
                if not magic_checked:
                    header = (header + chunk)[:MAGIC_HEADER_BYTES]
                    if len(header) >= MAGIC_HEADER_BYTES:
                        _ensure_magic(ext, header)
                        magic_checked = True
                await asyncio.to_thread(sink.write, chunk)
        if not magic_checked:
            _ensure_magic(ext, header)
    except BaseException:
        # Synchronous on purpose: an await here could be interrupted by a second
        # cancellation and leave an orphan file behind.
        path.unlink(missing_ok=True)  # noqa: ASYNC240
        raise
    return path


def _ensure_magic(ext: str, header: bytes) -> None:
    if not matches_magic(ext, header):
        raise InvalidAudioFormatError("File content does not match a supported audio format.")


def _prepare_upload_dir(dest_dir: Path) -> None:
    """Create ``dest_dir`` privately, refusing symlinks or directories owned by others."""
    dest_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = dest_dir.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise UnsafeUploadDirError(f"Upload directory is not a real directory: {dest_dir}")
    if info.st_uid != os.getuid():
        raise UnsafeUploadDirError(f"Upload directory is owned by another user: {dest_dir}")
    if stat.S_IMODE(info.st_mode) != 0o700:
        dest_dir.chmod(0o700)
