"""ASR strategy engine (spec S3/S4, ADR-0001).

Concrete strategies are intentionally not imported here so that ``api`` mode
never pulls ``faster_whisper`` into memory.
"""

from app.services.asr.base import ASRError, ASRStrategy

__all__ = ["ASRError", "ASRStrategy"]
