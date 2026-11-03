"""Runtime selection of the ASR strategy (spec S3/S4)."""

from app.config import Settings
from app.schemas.events import ASRMode
from app.services.asr.base import ASRStrategy


def get_asr_strategy(mode: ASRMode, settings: Settings, api_key: str | None) -> ASRStrategy:
    """Build the strategy for ``mode``.

    ``api_key`` is the BYOK token already resolved from ``X-HF-Token`` / ``X-API-Key``;
    in ``api`` mode it falls back to ``HF_TOKEN`` then ``LLM_API_KEY``.
    Strategy modules are imported lazily so ``api`` mode never loads ``faster_whisper``.
    """
    if mode is ASRMode.LOCAL:
        from app.services.asr.local_whisper import LocalWhisperASR

        return LocalWhisperASR(settings.whisper_model_size)

    from app.services.asr.api_whisper import ApiWhisperASR

    token = api_key
    for fallback in (settings.hf_token, settings.llm_api_key):
        if token:
            break
        token = fallback.get_secret_value() if fallback is not None else None
    return ApiWhisperASR(token)
