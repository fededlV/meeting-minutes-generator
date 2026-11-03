"""Application settings loaded from environment variables."""

import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.events import ASRMode, LLMProvider


def _default_upload_dir() -> Path:
    return Path(tempfile.gettempdir()) / "mmg-uploads"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    asr_mode: ASRMode = ASRMode.LOCAL
    whisper_model_size: Literal["base.en", "small.en"] = "base.en"
    default_llm_provider: LLMProvider = LLMProvider.HUGGINGFACE

    llm_api_key: SecretStr | None = None
    hf_token: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None

    max_upload_bytes: int = Field(default=26_214_400, gt=0)
    rate_limit_requests: int = Field(default=5, gt=0)
    rate_limit_window_seconds: int = Field(default=3600, gt=0)
    upload_tmp_dir: Path = Field(default_factory=_default_upload_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
