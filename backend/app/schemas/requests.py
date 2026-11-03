"""REST error envelope and BYOK request-header contracts."""

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.schemas.events import ASRMode, ErrorCode, LLMProvider


class APIErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    code: ErrorCode
    message: str = Field(min_length=1)


class APIErrorResponse(BaseModel):
    """Pre-stream error body: ``{"error": {"code": ..., "message": ...}}``."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    error: APIErrorDetail


class BYOKHeaders(BaseModel):
    """Optional client-supplied credentials and routing overrides.

    Tokens are ``SecretStr`` so they never appear in ``repr`` or logs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    x_api_key: SecretStr | None = Field(default=None, alias="X-API-Key")
    x_hf_token: SecretStr | None = Field(default=None, alias="X-HF-Token")
    x_llm_provider: LLMProvider | None = Field(default=None, alias="X-LLM-Provider")
    x_llm_model: str | None = Field(default=None, alias="X-LLM-Model", min_length=1)
    x_asr_mode: ASRMode | None = Field(default=None, alias="X-ASR-Mode")
