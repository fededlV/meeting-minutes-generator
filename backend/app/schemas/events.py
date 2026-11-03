"""Pydantic v2 SSE event contracts (spec §5.1)."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PipelineStage(StrEnum):
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"


class ASRMode(StrEnum):
    LOCAL = "local"
    API = "api"


class LLMProvider(StrEnum):
    HUGGINGFACE = "huggingface"
    OPENROUTER = "openrouter"
    GEMINI = "gemini"


class StatusEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stage: PipelineStage
    message: str = Field(min_length=1, max_length=280)


class TranscriptChunkPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    start: float = Field(ge=0.0, description="Segment start timestamp in seconds")
    end: float = Field(ge=0.0, description="Segment end timestamp in seconds")
    text: str = Field(min_length=1, description="Transcribed segment text")


class LLMTokenPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    token: str = Field(description="Single token or fragment emitted by the LLM")


class ErrorCode(StrEnum):
    INVALID_AUDIO_FORMAT = "INVALID_AUDIO_FORMAT"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    MISSING_API_KEY = "MISSING_API_KEY"
    ASR_FAILURE = "ASR_FAILURE"
    LLM_QUOTA_OR_UPSTREAM_ERROR = "LLM_QUOTA_OR_UPSTREAM_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorEventPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: ErrorCode
    message: str
    recoverable: bool = True


def format_sse(
    event: Literal["status", "transcript_chunk", "llm_token", "error"],
    payload: BaseModel,
) -> str:
    """Serialize a Pydantic payload into a standard W3C Server-Sent Event frame."""
    return f"event: {event}\ndata: {payload.model_dump_json()}\n\n"
