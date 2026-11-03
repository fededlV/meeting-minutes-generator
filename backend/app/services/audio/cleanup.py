"""Guaranteed temporary audio cleanup (S2).

Files the request created (``owned=True``) are unlinked in a ``finally`` block on
normal completion, exception, ``asyncio.CancelledError`` or generator ``aclose()``.
Unowned files (e.g. the read-only bundled sample asset) are never touched.
"""

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import aclosing, asynccontextmanager
from pathlib import Path


@asynccontextmanager
async def temp_audio_file(path: Path, *, owned: bool = True) -> AsyncIterator[Path]:
    try:
        yield path
    finally:
        if owned:
            # Synchronous on purpose: must complete even while being cancelled.
            path.unlink(missing_ok=True)  # noqa: ASYNC240


async def stream_with_cleanup[T](
    source: AsyncGenerator[T], path: Path, *, owned: bool = True
) -> AsyncGenerator[T]:
    """Re-yield ``source`` items and release ``path`` when the stream ends for any reason."""
    async with temp_audio_file(path, owned=owned), aclosing(source) as items:
        async for item in items:
            yield item
