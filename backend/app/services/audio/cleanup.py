"""Guaranteed temporary audio cleanup (S2).

Files the request created (``owned=True``) are unlinked on normal completion,
exception, ``asyncio.CancelledError`` or ``aclose()`` -- including ``aclose()``
before the first item is pulled. Unowned files (e.g. the read-only bundled sample
asset) are never touched.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Self


def _release(path: Path, *, owned: bool) -> None:
    if owned:
        # Synchronous on purpose: must complete even while being cancelled.
        path.unlink(missing_ok=True)


@asynccontextmanager
async def temp_audio_file(path: Path, *, owned: bool = True) -> AsyncIterator[Path]:
    try:
        yield path
    finally:
        _release(path, owned=owned)


class CleanupStream[T]:
    """Async iterator that re-yields ``source`` and releases ``path`` when it ends.

    Implemented as a class rather than an async generator because a generator's
    ``finally`` never runs if it is closed before its first ``__anext__``.
    ``__del__`` is the last-resort release for streams abandoned without
    ``aclose()`` (e.g. a consumer task cancelled while sending a frame).
    """

    def __init__(self, source: AsyncGenerator[T], path: Path, *, owned: bool) -> None:
        self._source = source
        self._path = path
        self._owned = owned
        self._closed = False

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> T:
        if self._closed:
            raise StopAsyncIteration
        try:
            return await anext(self._source)
        except BaseException:
            # StopAsyncIteration, upstream errors and cancellation all end the stream.
            self._closed = True
            _release(self._path, owned=self._owned)
            raise

    def __del__(self) -> None:
        if not self._closed:
            self._closed = True
            _release(self._path, owned=self._owned)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            await self._source.aclose()
        finally:
            _release(self._path, owned=self._owned)


def stream_with_cleanup[T](
    source: AsyncGenerator[T], path: Path, *, owned: bool = True
) -> CleanupStream[T]:
    """Wrap ``source`` so ``path`` is released when the stream ends for any reason."""
    return CleanupStream(source, path, owned=owned)
